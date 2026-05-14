# AGENTS.md

Instructions for AI agents working on this codebase.

## Project Overview

`espies` is an autonomous software engineering agent system that iteratively improves code repositories using local LLMs via Ollama. It has a Coder agent that implements changes and a Reviewer agent that validates tests.

## Key Components

- `espies/agent.py` - LLM integration, agent classes, retry logic
- `espies/main.py` - Orchestration loop (coder → tests → reviewer → commit)
- `espies/git_ops.py` - Git operations (clone, diff, add_all, commit, reset_hard, has_changes)
- `espies/tester.py` - Multi-language test detection and execution
- `espies/checkpoint.py` - Crash recovery with checkpoint/resume
- `espies/session_logger.py` - Structured JSONL logging

## Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run integration tests only
uv run pytest tests/integration/ -v

# Run unit tests only
uv run pytest tests/unit/ -v

# Run with coverage
uv run pytest tests/ --cov=espies

# Run specific test file
uv run pytest tests/integration/test_agent.py -v
uv run pytest tests/unit/test_git_ops.py -v
```

## Development Commands

```bash
# Install dependencies
uv sync

# Lint code
uv run ruff check espies/ tests/

# Type check (run after changes)
uv run mypy espies --strict

# Run the agent (requires Ollama running)
uv run espies "Your task here"

# Resume from checkpoint
uv run espies --resume
```

## Verification Checklist

Before completing changes, run:

```bash
uv run ruff check espies/ tests/
uv run mypy espies --strict
uv run pytest tests/ -v
```

## Key Patterns

- All git operations take `repo_dir: Path` parameter
- Checkpoint data is serialized via `@dataclass` to JSON
- Reviewer output must be JSON with `decision`, `explanation`, `commit_message`
- Use `checkpoint_mgr.create_checkpoint()` instead of direct `CheckpointData()` construction
- Scope enforcement via `config.yaml` `scope` field with glob patterns (e.g., `["*.py", "src/**/*.py"]`)

## Files to Avoid Modifying

- `espies/agents/*.md` - Prompt templates (unless improving agent instructions)

