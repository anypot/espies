import argparse
import sys
from datetime import datetime
import yaml
from pathlib import Path
import logging
from dataclasses import dataclass
from typing import Any

from .agent import call_coder, call_reviewer, ReviewResult, Agent, AgentType, DEFAULT_MODELS
from .git_ops import diff, add_all, commit, reset_hard, has_changes, clone, check_scope
from .tester import tests
from .session_logger import SessionLogger
from .checkpoint import CheckpointManager

WORKSPACE = Path("./workspace")

logger = logging.getLogger(__name__)


@dataclass
class IterationContext:
    """Holds state for a single iteration of the main loop."""
    task: str
    repo_url: str
    repo_dir: Path
    max_iters: int
    model_coder: str | None
    model_reviewer: str | None
    feedback_history: list[str]
    config: dict[str, Any]


@dataclass
class IterationResult:
    """Result of running a single iteration."""
    should_continue: bool
    should_break: bool = False


def setup_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)

    fmt = "%(asctime)s [%(levelname)-8s] %(message)s"
    datefmt = "%H:%M:%S"

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    logger.debug("Logging initialized at %s level", level_name)


def _repo_dir_from_url(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


def load_config() -> dict[str, Any]:
    with open("config.yaml") as f:
        config: dict[str, Any] = yaml.safe_load(f)
    return config


def _run_iteration(
    ctx: IterationContext,
    iter_num: int,
    args: argparse.Namespace,
    checkpoint_mgr: CheckpointManager,
    session: SessionLogger,
) -> ReviewResult | IterationResult:
    """Run a single iteration: coder → tests → review → commit or reject."""
    logger.info("Starting iteration %d/%d", iter_num, ctx.max_iters)
    session.log("iteration_start", iteration=iter_num, max_iterations=ctx.max_iters)

    if not args.dry_run:
        ckpt_data = checkpoint_mgr.create_checkpoint(
            ctx.task, ctx.repo_url, ctx.repo_dir, ctx.max_iters, ctx.model_coder,
            ctx.model_reviewer, iter_num, ctx.feedback_history, ctx.config
        )
        checkpoint_mgr.save(ckpt_data)

    diff_text = _run_coder_phase(ctx, iter_num, args, session)
    passed, test_output = _run_test_phase(ctx, iter_num, args, session)

    if not passed:
        logger.warning("Tests failed — resetting repository")
        if not args.dry_run:
            reset_hard(ctx.repo_dir)
        ctx.feedback_history.append(f"Tests failed:\n{test_output[:500]}")
        session.log("iteration_fail", iteration=iter_num, reason="tests_failed")
        return IterationResult(should_continue=True)

    result = _run_review_phase(ctx, iter_num, args, session, diff_text, test_output)
    return result


def _run_coder_phase(
    ctx: IterationContext,
    iter_num: int,
    args: argparse.Namespace,
    session: SessionLogger,
) -> str:
    """Execute the coder phase and return the diff."""
    logger.info("Calling coder agent...")
    if args.dry_run:
        agent = Agent(ctx.model_coder or DEFAULT_MODELS[AgentType.CODER], AgentType.CODER)
        prompt = agent.render_prompt(
            task=ctx.task, repo_dir=str(ctx.repo_dir), feedback_history=ctx.feedback_history
        )
        logger.info("[DRY-RUN] Coder prompt:")
        logger.info(prompt)
        logger.info("[DRY-RUN] Would call coder")
        session.log("coder_call", iteration=iter_num, dry_run=True, model=ctx.model_coder, prompt=repr(prompt))
        return ""
    else:
        diff_text = call_coder(ctx.task, str(ctx.repo_dir), ctx.feedback_history, ctx.model_coder)
        logger.debug("Coder raw output: %s", diff_text[:500])
        logger.info("Coder produced diff (%d characters)", len(diff_text))
        session.log("coder_complete", iteration=iter_num, diff_length=len(diff_text), has_diff=bool(diff_text.strip()))
        return diff_text


def _run_test_phase(
    ctx: IterationContext,
    iter_num: int,
    args: argparse.Namespace,
    session: SessionLogger,
) -> tuple[bool, str]:
    """Execute the test phase and return (passed, output)."""
    logger.info("Running tests...")
    if args.dry_run:
        logger.info("[DRY-RUN] Would run tests in %s", ctx.repo_dir)
        return True, "[DRY-RUN] Tests simulated as passing"
    else:
        passed, test_output = tests(ctx.repo_dir)

    logger.info("Test results: %s", "PASSED" if passed else "FAILED")
    logger.debug("Test output:\n%s", test_output)
    session.log("tests_complete", iteration=iter_num, passed=passed, test_output_length=len(test_output))
    return passed, test_output


def _run_review_phase(
    ctx: IterationContext,
    iter_num: int,
    args: argparse.Namespace,
    session: SessionLogger,
    diff_text: str,
    test_output: str,
) -> ReviewResult | IterationResult:
    """Execute the review phase and return result or iteration signal."""
    if args.dry_run:
        return _run_review_phase_dry_run(ctx, iter_num, session, test_output)

    return _run_review_phase_live(ctx, iter_num, session, diff_text, test_output)


def _run_review_phase_dry_run(
    ctx: IterationContext,
    iter_num: int,
    session: SessionLogger,
    test_output: str,
) -> ReviewResult:
    """Execute the review phase in dry-run mode."""
    logger.info("[DRY-RUN] Reviewer prompt:")
    agent = Agent(ctx.model_reviewer or DEFAULT_MODELS[AgentType.REVIEWER], AgentType.REVIEWER)
    prompt = agent.render_prompt(
        task=ctx.task, diff="[DRY-RUN] Diff would be shown here", test_output=test_output, repo_dir=str(ctx.repo_dir)
    )
    logger.info(prompt)
    logger.info("[DRY-RUN] Would compute diff and call reviewer")
    result = ReviewResult("APPROVE", "", "dry-run commit")
    session.log("review", iteration=iter_num, dry_run=True, decision="APPROVE", prompt=repr(prompt))
    return result


def _run_review_phase_live(
    ctx: IterationContext,
    iter_num: int,
    session: SessionLogger,
    diff_text: str,
    test_output: str,
) -> ReviewResult | IterationResult:
    """Execute the review phase in live mode."""
    diff_text = diff(ctx.repo_dir)
    logger.debug("Diff:\n%s", diff_text)

    allowed_scope = ctx.config.get("scope", [])
    if allowed_scope:
        scope_violations = check_scope(diff_text, allowed_scope)
        if scope_violations:
            logger.warning("Scope violations detected: %s", scope_violations)
            result = ReviewResult(
                "REJECT",
                f"Scope violation: modified files outside allowed patterns: {', '.join(scope_violations)}",
            )
            ctx.feedback_history.append(f"[Scope] {result.explanation}")
            reset_hard(ctx.repo_dir)
            return result

    if not has_changes(ctx.repo_dir):
        logger.info("No changes detected — task complete")
        session.log("no_changes", iteration=iter_num)
        return IterationResult(should_continue=False, should_break=True)

    logger.info("Calling reviewer agent...")
    result = call_reviewer(
        ctx.task, diff_text, test_output, str(ctx.repo_dir), ctx.model_reviewer, use_json_mode=True
    )
    logger.info("Reviewer decision: %s", result.decision)
    if result.explanation:
        logger.info("Reviewer explanation: %s", result.explanation)
    session.log(
        "review_complete",
        iteration=iter_num,
        decision=result.decision,
        explanation=result.explanation[:200] if result.explanation else "",
    )
    return result


def _handle_approved_result(
    ctx: IterationContext,
    result: ReviewResult,
    iter_num: int,
    args: argparse.Namespace,
    checkpoint_mgr: CheckpointManager,
    session: SessionLogger,
) -> None:
    """Handle an approved result: commit and exit."""
    commit_msg = result.commit_message or "agent change"
    if args.dry_run:
        logger.info("[DRY-RUN] Would commit changes: %s", commit_msg)
        logger.info("✅ Iteration complete — would commit")
        session.log("commit", iteration=iter_num, dry_run=True, message=commit_msg)
    else:
        add_all(ctx.repo_dir)
        commit(ctx.repo_dir, commit_msg)
        logger.info("✅ Changes committed: %s", commit_msg)
        session.log("commit", iteration=iter_num, success=True, message=commit_msg)
    checkpoint_mgr.delete_all()
    logger.info("Checkpoints cleared — task completed successfully")


def _handle_rejected_result(
    ctx: IterationContext,
    result: ReviewResult,
    iter_num: int,
    args: argparse.Namespace,
    checkpoint_mgr: CheckpointManager,
    session: SessionLogger,
) -> None:
    """Handle a rejected result: reset and continue."""
    logger.warning("❌ Changes rejected: %s", result.explanation)
    if not args.dry_run:
        reset_hard(ctx.repo_dir)
    ctx.feedback_history.append(f"[Reviewer] {result.explanation}")
    session.log(
        "iteration_fail",
        iteration=iter_num,
        reason="rejected",
        reviewer_explanation=result.explanation[:200],
    )
    if not args.dry_run:
        ckpt_data = checkpoint_mgr.create_checkpoint(
            ctx.task, ctx.repo_url, ctx.repo_dir, ctx.max_iters, ctx.model_coder,
            ctx.model_reviewer, iter_num + 1, ctx.feedback_history, ctx.config
        )
        checkpoint_mgr.save(ckpt_data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Autonomous software engineering agent system"
    )
    parser.add_argument(
        "task", nargs="?", default=None, help="Task description for the coder agent"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging verbosity (default: INFO)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without making any git changes or calling LLMs",
    )
    parser.add_argument(
        "--model-coder", default=None, help="Override the default coder model"
    )
    parser.add_argument(
        "--model-reviewer", default=None, help="Override the default reviewer model"
    )
    parser.add_argument(
        "--session-log", default=None, help="Path to session JSONL log file"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from latest checkpoint if available (ignores task arg if checkpoint has task)",
    )
    args = parser.parse_args()

    setup_logging(args.log_level)

    logger.info("Starting espies agent system")
    logger.debug("CLI args: %s", args)

    session_log_path = _get_session_log_path(args)
    session = SessionLogger(session_log_path)
    session.log(
        "session_start",
        task=args.task or "(resuming)",
        dry_run=args.dry_run,
        resume=args.resume,
    )

    checkpoint_mgr = CheckpointManager(WORKSPACE)
    ctx = _initialize_context(args, checkpoint_mgr, session)

    logger.info("Models: coder=%s, reviewer=%s", ctx.model_coder, ctx.model_reviewer)
    logger.info("Task: %s", ctx.task)
    logger.info("Repository: %s → %s", ctx.repo_url, ctx.repo_dir)
    logger.info("Max iterations: %d", ctx.max_iters)

    try:
        if not ctx.repo_dir.exists():
            if args.dry_run:
                logger.info("[DRY-RUN] Would clone repository to %s", ctx.repo_dir)
            else:
                logger.info("Cloning repository...")
                clone(ctx.repo_url, ctx.repo_dir)
                logger.info("Repository cloned successfully")

        start_iter = 1
        for i in range(start_iter - 1, ctx.max_iters):
            iter_num = i + 1
            result = _run_iteration(ctx, iter_num, args, checkpoint_mgr, session)

            if isinstance(result, IterationResult):
                if result.should_break:
                    break
                continue

            result = result  # ReviewResult

            if result.decision == "APPROVE":
                _handle_approved_result(ctx, result, iter_num, args, checkpoint_mgr, session)
                break
            else:
                _handle_rejected_result(ctx, result, iter_num, args, checkpoint_mgr, session)

        logger.info("Session complete")
        session.log("session_end", status="completed")

    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        session.log("session_end", status="interrupted")
        raise
    except Exception as e:
        logger.error("Session failed with error: %s", e)
        session.log("session_end", status="error", error=str(e))
        raise
    finally:
        session.close()


def _get_session_log_path(args: argparse.Namespace) -> Path:
    if args.session_log:
        return Path(args.session_log)
    return WORKSPACE / ".espies" / f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"


def _initialize_context(
    args: argparse.Namespace,
    checkpoint_mgr: CheckpointManager,
    session: SessionLogger,
) -> IterationContext:
    checkpoint = checkpoint_mgr.load_latest() if args.resume else None

    if checkpoint:
        logger.info("Resuming from checkpoint: iteration %d", checkpoint.current_iteration)
        task = checkpoint.task
        repo_url = checkpoint.repo_url
        repo_dir = Path(checkpoint.repo_dir)
        max_iters = checkpoint.max_iters
        model_coder = checkpoint.model_coder
        model_reviewer = checkpoint.model_reviewer
        feedback_history = checkpoint.feedback_history.copy()
        config = checkpoint.config
    else:
        if not args.task:
            args.parser.error("task is required when not resuming from checkpoint")

        config = load_config()
        repo_url = config["repo_url"]
        max_iters = config.get("max_iters", 3)
        model_coder = args.model_coder or config.get("model_coder")
        model_reviewer = args.model_reviewer or config.get("model_reviewer")

        repo_name = _repo_dir_from_url(repo_url)
        repo_dir = WORKSPACE / repo_name
        feedback_history = []
        task = args.task

    return IterationContext(
        task=task,
        repo_url=repo_url,
        repo_dir=repo_dir,
        max_iters=max_iters,
        model_coder=model_coder,
        model_reviewer=model_reviewer,
        feedback_history=feedback_history,
        config=config,
    )