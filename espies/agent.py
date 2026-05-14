import os
import re
from enum import Enum
from pathlib import Path
from typing import Any, NamedTuple
import logging

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_log,
)

logger = logging.getLogger(__name__)


class AgentType(Enum):
    CODER = "coder"
    REVIEWER = "reviewer"


class ReviewResult(NamedTuple):
    """Structured result from a reviewer agent."""

    decision: str
    explanation: str = ""
    commit_message: str = ""


DEFAULT_MODELS: dict[AgentType, str] = {
    AgentType.CODER: "qwen2.5-coder:14b",
    AgentType.REVIEWER: "deepseek-r1:14b",
}


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")


# Retry configuration for LLM calls
# - Up to 3 attempts total (1 initial + 2 retries)
# - Wait 2s, then 4s, then 8s between retries (exponential backoff)
# - Retry on network errors and timeouts, not on 4xx errors
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=8),
    retry=retry_if_exception_type(
        (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.NetworkError)
    ),
    before=before_log(logger, logging.WARNING),
)
def _call_llm_with_retry(
    agent_model: str, prompt: str, response_format: dict[str, Any] | None = None
) -> str:
    """
    Internal: call LLM with retry logic.
    Wrapped by Agent.call_llm() for per-agent retry behavior.
    """
    logger.debug(
        "Calling LLM: model=%s, prompt_length=%d, response_format=%s",
        agent_model,
        len(prompt),
        response_format,
    )
    logger.debug("Prompt:\n%s", prompt)

    request_body: dict[str, Any] = {
        "model": agent_model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if response_format:
        request_body["response_format"] = response_format

    response = httpx.post(
        f"{OLLAMA_BASE_URL}/chat/completions",
        json=request_body,
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()

    content = str(data["choices"][0]["message"]["content"])
    logger.debug("LLM response length: %d chars", len(content))
    logger.debug("Response:\n%s", content)

    return content


def parse_reviewer_response(response: str) -> ReviewResult:
    """
    Parse reviewer response into a structured decision.
    Supports both plain text (APPROVE/REJECT prefix) and JSON mode output.
    """
    cleaned = response.strip()

    # Try JSON parsing first (when response_format={"type": "json"} is used)
    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            import json

            data = json.loads(cleaned)
            decision = data.get("decision", "").upper()
            explanation = data.get("explanation", "")
            commit_message = data.get("commit_message", "")
            if decision in ("APPROVE", "REJECT"):
                return ReviewResult(decision=decision, explanation=explanation, commit_message=commit_message)
            else:
                logger.warning("Invalid decision '%s' in JSON response", decision)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Failed to parse JSON response: %s", e)
            # Fall through to text parsing

    # Plain text parsing (legacy format)
    match = re.match(r"^(APPROVE|REJECT)\b\s*(.*)", cleaned, re.IGNORECASE | re.DOTALL)

    if not match:
        logger.warning("Could not parse reviewer response: %s", cleaned[:200])
        return ReviewResult(
            decision="REJECT",
            explanation=f"Could not parse decision from response: {cleaned[:200]}",
        )

    decision = match.group(1).upper()
    explanation = match.group(2).strip() if decision == "REJECT" else ""

    if decision not in ("APPROVE", "REJECT"):
        logger.warning("Invalid decision '%s' in reviewer response", decision)
        return ReviewResult(
            decision="REJECT", explanation=f"Invalid decision '{decision}' in response"
        )

    logger.debug("Reviewer parsed decision: %s", decision)
    return ReviewResult(decision=decision, explanation=explanation)


def is_valid_unified_diff(diff_text: str) -> bool:
    """
    Basic validation that a string looks like a unified diff.
    Checks for typical diff headers like '--- a/file' or '+++ b/file'.
    """
    lines = diff_text.strip().split("\n")
    has_header = any(
        line.startswith("--- ")
        and (
            "a/" in line
            or line.endswith(".py")
            or line.endswith(".js")
            or line.endswith(".rs")
        )
        for line in lines[:10]
    )
    has_hunk = any(line.startswith("@@ ") for line in lines)
    return has_header or has_hunk


class Agent:
    def __init__(self, model: str, agent_type: AgentType):
        self.model = model
        self.agent_type = agent_type
        self._template_path = (
            Path(__file__).parent / "agents" / f"{agent_type.value}.md"
        )
        if not self._template_path.exists():
            raise FileNotFoundError(f"Template not found: {self._template_path}")
        self._template = self._template_path.read_text()

    def render_prompt(self, **kwargs: Any) -> str:
        from jinja2 import Template

        return Template(self._template).render(**kwargs)

    def call_llm(self, prompt: str, response_format: dict[str, Any] | None = None) -> str:
        """Call the LLM with retry logic for transient failures."""
        try:
            return _call_llm_with_retry(self.model, prompt, response_format)
        except Exception as e:
            logger.error("LLM call failed after retries: %s", e)
            raise


def call_coder(
    task: str,
    repo_dir: str,
    feedback_history: list[str] | None = None,
    model: str | None = None,
) -> str:
    """
    Generate code changes as a unified diff.

    Args:
        task: The original task description
        repo_dir: Path to the repository root
        feedback_history: List of previous rejection reasons from reviewer (for iterative improvement)
        model: Optional model override

    Returns:
        Raw unified diff string from the LLM
    """
    agent_model = model or DEFAULT_MODELS[AgentType.CODER]
    logger.debug("Creating coder agent with model=%s", agent_model)

    agent = Agent(agent_model, AgentType.CODER)
    prompt = agent.render_prompt(
        task=task, repo_dir=repo_dir, feedback_history=feedback_history or []
    )

    logger.info("Requesting code changes from coder...")
    raw_diff = agent.call_llm(prompt)

    # Validate that the output looks like a diff
    if not is_valid_unified_diff(raw_diff):
        logger.warning("Coder output doesn't appear to be a valid unified diff")

    return raw_diff


def call_reviewer(
    task: str,
    diff: str,
    test_output: str,
    repo_dir: str,
    model: str | None = None,
    use_json_mode: bool = True,
) -> ReviewResult:
    """
    Review proposed changes and return structured decision.
    Uses JSON mode for reliable parsing when available.

    Args:
        task: The original task description
        diff: Git diff of changes
        test_output: Combined test results
        repo_dir: Path to repository root
        model: Optional model override
        use_json_mode: If True, request JSON-formatted response from LLM

    Returns:
        ReviewResult with decision and explanation
    """
    agent_model = model or DEFAULT_MODELS[AgentType.REVIEWER]
    logger.debug(
        "Creating reviewer agent with model=%s, json_mode=%s",
        agent_model,
        use_json_mode,
    )

    agent = Agent(agent_model, AgentType.REVIEWER)
    prompt = agent.render_prompt(
        task=task, diff=diff, test_output=test_output, repo_dir=repo_dir
    )

    response_format = {"type": "json"} if use_json_mode else None
    raw_response = agent.call_llm(prompt, response_format)

    logger.debug("Reviewer raw response: %s", raw_response[:300])

    result = parse_reviewer_response(raw_response)
    logger.debug("Reviewer parsed decision: %s", result.decision)

    return result
