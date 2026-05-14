"""Unit tests for agent module."""

from unittest.mock import MagicMock, patch

import pytest

from espies.agent import (
    Agent,
    AgentType,
    ReviewResult,
    call_coder,
    call_reviewer,
    is_valid_unified_diff,
    parse_reviewer_response,
)


class TestAgentType:
    """Unit tests for AgentType enum."""

    def test_agent_type_has_coder_and_reviewer(self) -> None:
        """AgentType has CODER and REVIEWER values."""
        assert AgentType.CODER.value == "coder"
        assert AgentType.REVIEWER.value == "reviewer"


class TestReviewResult:
    """Unit tests for ReviewResult named tuple."""

    def test_review_result_with_all_fields(self) -> None:
        """ReviewResult accepts decision, explanation, and commit_message."""
        result = ReviewResult(
            decision="APPROVE",
            explanation="Looks good",
            commit_message="Fix bug"
        )
        assert result.decision == "APPROVE"
        assert result.explanation == "Looks good"
        assert result.commit_message == "Fix bug"

    def test_review_result_defaults(self) -> None:
        """ReviewResult has empty string defaults for explanation and commit_message."""
        result = ReviewResult(decision="REJECT")
        assert result.decision == "REJECT"
        assert result.explanation == ""
        assert result.commit_message == ""


class TestIsValidUnifiedDiff:
    """Unit tests for is_valid_unified_diff function."""

    def test_returns_true_for_diff_with_header(self) -> None:
        """Returns True for diff starting with --- a/ pattern."""
        diff = "--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,4 @@\n line"
        assert is_valid_unified_diff(diff) is True

    def test_returns_true_for_diff_with_hunk(self) -> None:
        """Returns True for diff with @@ hunk marker."""
        diff = "Some text\n@@ -1,3 +1,4 @@\n line"
        assert is_valid_unified_diff(diff) is True

    def test_returns_false_for_plain_text(self) -> None:
        """Returns False for plain text without diff markers."""
        assert is_valid_unified_diff("This is just text") is False

    def test_returns_false_for_empty_string(self) -> None:
        """Returns False for empty input."""
        assert is_valid_unified_diff("") is False

    def test_returns_false_for_whitespace_only(self) -> None:
        """Returns False for whitespace-only input."""
        assert is_valid_unified_diff("   \n\n  ") is False


class TestParseReviewerResponse:
    """Unit tests for parse_reviewer_response function."""

    def test_parses_json_approve(self) -> None:
        """Parses JSON with APPROVE decision."""
        result = parse_reviewer_response('{"decision": "APPROVE", "explanation": "", "commit_message": "Fix auth"}')
        assert result.decision == "APPROVE"
        assert result.commit_message == "Fix auth"

    def test_parses_json_reject(self) -> None:
        """Parses JSON with REJECT decision."""
        result = parse_reviewer_response('{"decision": "REJECT", "explanation": "Bad code", "commit_message": ""}')
        assert result.decision == "REJECT"
        assert result.explanation == "Bad code"

    def test_parses_json_with_extras(self) -> None:
        """Ignores extra fields in JSON."""
        result = parse_reviewer_response('{"decision": "APPROVE", "extra": "ignored", "explanation": "", "commit_message": "msg"}')
        assert result.decision == "APPROVE"

    def test_parses_plain_text_approve(self) -> None:
        """Parses plain text APPROVE."""
        result = parse_reviewer_response("APPROVE")
        assert result.decision == "APPROVE"
        assert result.explanation == ""

    def test_parses_plain_text_reject_with_reason(self) -> None:
        """Parses plain text REJECT with explanation."""
        result = parse_reviewer_response("REJECT Code is broken")
        assert result.decision == "REJECT"
        assert result.explanation == "Code is broken"

    def test_handles_invalid_json(self) -> None:
        """Handles invalid JSON by trying plain text parsing."""
        result = parse_reviewer_response("Not JSON but APPROVE")
        assert result.decision == "REJECT"
        assert "Could not parse" in result.explanation

    def test_handles_invalid_decision_in_json(self) -> None:
        """Returns REJECT for invalid decision value in JSON."""
        result = parse_reviewer_response('{"decision": "MAYBE", "explanation": ""}')
        assert result.decision == "REJECT"

    def test_handles_missing_decision(self) -> None:
        """Returns REJECT when decision is missing."""
        result = parse_reviewer_response('{"explanation": "oops"}')
        assert result.decision == "REJECT"


class TestAgent:
    """Unit tests for Agent class."""

    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_agent_raises_on_missing_template(self, mock_exists: MagicMock, mock_read: MagicMock) -> None:
        """Agent raises FileNotFoundError if template doesn't exist."""
        mock_exists.return_value = False

        with pytest.raises(FileNotFoundError):
            Agent("model", AgentType.CODER)

    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_render_prompt_calls_jinja2(self, mock_exists: MagicMock, mock_read: MagicMock) -> None:
        """render_prompt renders template with jinja2."""
        mock_exists.return_value = True
        mock_read.return_value = "Template: {{ task }}"

        agent = Agent("model", AgentType.CODER)
        result = agent.render_prompt(task="My task")

        assert "My task" in result

    @patch("espies.agent.Agent.call_llm")
    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_call_llm_delegates_to_retry(
        self, mock_exists: MagicMock, mock_read: MagicMock, mock_llm: MagicMock
    ) -> None:
        """call_llm delegates to internal retry logic."""
        mock_exists.return_value = True
        mock_read.return_value = "Template"
        mock_llm.return_value = "response"

        agent = Agent("model", AgentType.CODER)
        agent.call_llm("prompt")

        mock_llm.assert_called_once()


class TestCallCoder:
    """Unit tests for call_coder function."""

    @patch("espies.agent.Agent")
    def test_call_coder_uses_default_model(self, mock_agent_class: MagicMock) -> None:
        """call_coder uses provided model."""
        mock_agent = MagicMock()
        mock_agent.render_prompt.return_value = "prompt"
        mock_agent.call_llm.return_value = "--- a/file"
        mock_agent_class.return_value = mock_agent

        result = call_coder("task", "/tmp/repo", [], "test-model")

        mock_agent_class.assert_called_once_with("test-model", AgentType.CODER)
        assert result == "--- a/file"

    @patch("espies.agent.is_valid_unified_diff")
    @patch("espies.agent.Agent")
    def test_call_coder_validates_diff(self, mock_agent_class: MagicMock, mock_valid: MagicMock) -> None:
        """call_coder checks if output is valid diff."""
        mock_agent = MagicMock()
        mock_agent.render_prompt.return_value = "prompt"
        mock_agent.call_llm.return_value = "--- a/file"
        mock_agent_class.return_value = mock_agent

        call_coder("task", "/tmp/repo", [], "model")

        mock_valid.assert_called()


class TestCallReviewer:
    """Unit tests for call_reviewer function."""

    @patch("espies.agent.Agent")
    @patch("espies.agent.parse_reviewer_response")
    def test_call_reviewer_uses_json_mode(
        self, mock_parse: MagicMock, mock_agent_class: MagicMock
    ) -> None:
        """call_reviewer uses JSON mode by default."""
        mock_agent = MagicMock()
        mock_agent.render_prompt.return_value = "prompt"
        mock_agent.call_llm.return_value = '{"decision": "APPROVE"}'
        mock_agent_class.return_value = mock_agent
        mock_parse.return_value = ReviewResult("APPROVE")

        call_reviewer("task", "diff", "tests passed", "/tmp/repo", "test-model", True)

        mock_agent.call_llm.assert_called_once()
        call_args = mock_agent.call_llm.call_args
        # call_llm(prompt, response_format) - second positional arg
        assert call_args.args[1] == {"type": "json"}

    @patch("espies.agent.Agent")
    @patch("espies.agent.parse_reviewer_response")
    def test_call_reviewer_skips_json_mode(
        self, mock_parse: MagicMock, mock_agent_class: MagicMock
    ) -> None:
        """call_reviewer skips JSON mode when use_json_mode=False."""
        mock_agent = MagicMock()
        mock_agent.render_prompt.return_value = "prompt"
        mock_agent.call_llm.return_value = "APPROVE"
        mock_agent_class.return_value = mock_agent
        mock_parse.return_value = ReviewResult("APPROVE")

        call_reviewer("task", "diff", "tests passed", "/tmp/repo", "test-model", False)

        call_args = mock_agent.call_llm.call_args
        # call_llm(prompt, response_format) - second positional arg
        assert call_args.args[1] is None