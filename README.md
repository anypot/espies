# espies — Autonomous Software Engineering Agents

A lightweight, multi-agent system that iteratively improves code repositories
using local LLMs via Ollama. Two specialized agents work together:
a **Coder** that implements changes, and a **Reviewer** that validates templates
against tests and quality criteria.

```text
Task → Coder → Tests → Reviewer → Commit (if approved) → Repeat
```

---

## Project Structure

```text
espies/
├── pyproject.toml        # Project configuration & dependencies
├── config.yaml.sample    # Configuration template (copy to config.yaml)
├── agents/               # Jinja2 prompt templates (copied into package)
│   ├── coder.md
│   └── reviewer.md
├── workspace/           # Cloned repositories (gitignored)
│   └── <repo-name>/
│   └── .espies/         # Runtime data (logs, checkpoints)
│       ├── session-*.jsonl
│       └── checkpoints/
│           ├── latest.json
│           └── checkpoint-*.json
├── tests/                # Test suite
│   ├── __init__.py
│   ├── unit/             # Unit tests
│   └── integration/      # Integration tests
├── espies/              # Python package
│   ├── __init__.py
│   ├── main.py          # Entry point & orchestration loop
│   ├── agent.py         # Agent definitions, LLM integration, factories
│   ├── git_ops.py       # Git operations (clone, diff, commit, reset, etc.)
│   ├── tester.py        # Multi-language test detection and execution
│   ├── session_logger.py  # Structured JSONL event logging
│   └── checkpoint.py    # Session recovery from crashes
```

---

## Core Components

### `agent.py`

#### Classes

- `AgentType(Enum)` — `CODER` | `REVIEWER`
- `ReviewResult(NamedTuple)` — `decision: str` (`APPROVE`/`REJECT`) +
  `explanation: str`
- `Agent` — loads agent-specific Markdown template, renders with Jinja2,
  calls LLM via Ollama with retry logic

#### Factory Functions

- `call_coder(task, repo_dir, feedback_history, model=None) -> str` —
  generates unified diff, validates format
- `call_reviewer(..., use_json_mode=True) -> ReviewResult` —
  returns structured result, uses JSON mode

#### Default Models (configurable via `config.yaml` or CLI flags)

- Coder → `qwen2.5-coder:14b`
- Reviewer → `deepseek-r1:14b`

#### LLM Backend

- Calls `OLLAMA_BASE_URL/v1/chat/completions` (OpenAI-compatible)
- Supports `response_format={"type": "json"}` for structured output
- Retry: up to 3 attempts with exponential backoff (2s → 4s → 8s) on network errors
- Configurable via `OLLAMA_BASE_URL` environment variable

### `git_ops.py`

All git operations accept a `repo_dir: Path` parameter pointing
to the working repository root:

| Function | Purpose |
| ---------- | --------- |
| `clone(url, repo_dir)` | Clones `url` into `repo_dir` |
| `diff(repo_dir)` | Returns `git diff` output |
| `add_all(repo_dir)` | Stages all changes |
| `commit(repo_dir, message)` | Commits staged changes |
| `reset_hard(repo_dir)` | Discards all changes |
| `has_changes(repo_dir)` | Checks if working tree is dirty |
| `check_scope(diff_text, patterns)` | Validates files match scope patterns |

### `tester.py`

Language-aware test runner that detects project type from common manifest files
and executes appropriate test commands.

**Detected languages:** Python, JavaScript (Node.js), Rust, Go,
Java (Maven/Gradle), Ruby, Elixir, PHP, CMake/CTest, Makefile

**Signature:** `tests(repo_dir: Path) -> tuple[bool, str]`

- Returns `(all_passed, combined_output)` where `combined_output` completions
results from all detected language test runners

### `session_logger.py`

Structured JSONL logging for observability and debugging.

**`SessionLogger` class:**

- Writes one JSON object per line to a log file
- Each entry includes `timestamp` (ISO 8601 UTC), `event`,
and arbitrary key/value data
- Automatic `flush()` after each write
- Context manager support

**Common events logged:**
`session_start`, `clone`, `iteration_start`, `coder_call`, `coder_complete`,
`tests_complete`, `review_complete`, `commit`, `iteration_fail`, `session_end`

### `checkpoint.py`

Crash-recovery system for long-running sessions.

**`CheckpointManager` class:**

- `save(data)` — writes checkpoint JSON to `workspace/.espies/checkpoints/`
- `load_latest()` — loads most recent checkpoint (or `None`)
- `delete_all()` — clears all checkpoints after successful completion

**`CheckpointData` dataclass:** serializable state including `task`, `repo_url`,
`repo_dir`, `current_iteration`, `feedback_history`, `model_coder`,
`model_reviewer`, `config`, timestamps

**Workflow:**

- Checkpoint saved before each iteration (includes accumulated feedback)
- On test failure or rejection → checkpoint with `current_iteration + 1`
- On success → checkpoints deleted
- Resume via `--resume` flag

### `main.py`

The orchestration loop:

1. Read `task` from command-line argument and `config.yaml`
2. Clone repository into `workspace/<repo_name>` using `git_ops.clone()`
3. For up to `max_iters` iterations (default 3, configurable):
   a. **Coder** → `call_coder(task, repo_dir)` generates
      code changes (as unified diff)
   b. **Tester** → `tests(repo_dir)` runs language-appropriate tests, returns output
   c. **Reviewer** → `call_reviewer(task, diff, test_output, repo_dir)`
      decides `APPROVE` or `REJECT`
   d. On `APPROVE` → commit changes and exit
   e. On `REJECT` → `git reset --hard` and retry

All agent calls are made with the `repo_dir` variable made explicitly
in the prompt context.

---

## Key Features

- **JSON mode** — Reviewer uses Ollama's `response_format={"type": "json"}`
  for 100% parse reliability (with regex fallback)
- **Retry with exponential backoff** — LLM calls automatically retry
  on network errors (up to 3 attempts, 2s→4s→8s)
- **Checkpoint/resume** — crash-resilient; resume from last iteration
  without losing progress via `--resume`
- **Session logging** — structured JSONL logs for observability
  (`--session-log` or auto to `workspace/.espies/`)
- **Feedback loop** — reviewer rejection reasons are fed back to coder
  in subsequent iterations
- **Multi-language** — auto-detects 10+ languages and runs appropriate test commands
- **Type-safe** — full type hints, passes `mypy --strict`

## Configuration

### `config.yaml`

Copy `config.yaml.sample` to `config.yaml` and customize:

```yaml
repo_url: "https://github.com/user/repo.git"  # Required
max_iters: 5                                  # Optional, default: 3
model_coder: "qwen2.5-coder:14b"             # Optional, default: qwen2.5-coder:14b
model_reviewer: "deepseek-r1:14b"            # Optional, default: deepseek-r1:14b
scope:                                        # Optional, file whitelist (glob patterns)
  - "*.py"                                      # Only allow Python files to be modified
  - "espies/*.py"                               # ...and any Python file in espies/
  # If omitted or empty, all files are allowed
```

CLI flags `--model-coder` and `--model-reviewer` override config values.

### Environment Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama API base URL |

---

## Usage

1. **Install dependencies**

```bash
uv sync  # or: pip install -e .
```

1. **Ensure Ollama is running**

```bash
ollama serve  # In a separate terminal
ollama pull qwen2.5-coder:14b
ollama pull deepseek-r1:14b
```

1. **Run the agent**

```bash
uv run espies "Refactor the authentication module to use_token-based auth"
```

With options:

```bash
# Override models (if you pulled different variants)
uv run espies --model-coder qwen2.5-coder:7b --model-reviewer deepseek-r1:7b \
"Fix the bug"

# Enable debug logging
uv run espies --log-level DEBUG "Add feature X"

# Dry-run (no git changes, no LLM calls)
uv run espies --dry-run "Refactor Y"

# Save session log to custom location
uv run espies --session-log /tmp/session.jsonl "Task"

# Resume from checkpoint after crash
uv run espies --resume
```

**All CLI flags:**

| Flag | Description |
| ---- | ----------- |
| `--log-level` | Set log verbosity (DEBUG, INFO, WARNING, ERROR) |
| `--dry-run` | Simulate without making changes or calling LLMs |
| `--model-coder <model>` | Override the default coder model |
| `--model-reviewer <model>` | Override the default reviewer model |
| `--session-log <path>` | Save session JSONL log to custom file |
| `--resume` | Resume from checkpoint, ignore task arg |
| `--help` | Show full usage |

The agent will:

- Clone the repository to `workspace/<repo_name>`
- Run up to `max_iters` iterations of code → test → review
- Commit on first `APPROVE` decision

---

## Agent Prompt Templates

Templates are Jinja2-rendered Markdown files in `agents/`:

- `coder.md` — Instructs the LLM to output **only a unified diff** with minimal,
  focused changes. Emphasizes scope discipline, code quality,
  and working within `{{ repo_dir }}`.
- `reviewer.md` — Requests `APPROVE` or `REJECT` decisions based on correctness,
  quality, safety, test results, and scope. No vague feedback.

Variables passed to templates:

- `task` — The original task string from CLI
- `repo_dir` — Absolute path to cloned repository root
- For reviewer only:
  - `diff` — Git diff output of changes
  - `test_output` — Combined test runner output

---

## Safety & Guardrails

- Agents are explicitly forbidden from modifying files
  outside the cloned repository
- Templates enforce "diff-only" output for coder;
  reviewer uses structured JSON output
- Each iteration starts from a clean git state;
  rejected changes have all modifications reset
- Only **one file** (the code itself) may pass through agents —
  no automatic dependency installs, no config changes

---

## Reliability & Observability

### Checkpoint / Resume

The system saves checkpoint state before each iteration toml
`workspace/.espies/checkpoints/`. If the process crashes or is interrupted,
you can resume without losing progress:

```bash
# Resume from latest checkpoint
uv run espies --resume

# The checkpoint includes: current iteration, feedback history, config, and models
# Automatically cleared on successful commit
```

Checkpoint files: `latest.json` + timestamped `checkpoint-<YYYYMMDD-HHMMSS>.json`

### Session Logging (JSONL)

Every event is logged as structured JSON for debugging/analysis:

**Default location:** `workspace/.espies/session-<timestamp>.jsonl`

**Custom location:**

```bash
uv run espies --session-log /tmp/mysession.jsonl "task"
```

Log events: `session_start`, `clone`, `iteration_start`, `coder_call`,
`coder_complete`, `tests_complete`, `review_complete`, `commit`,
`iteration_fail`, `session_end`

Example query with `jq`:

```bash
jq -r 'select(.event=="review_complete")' workspace/.espies/session-*.jsonl
```

### Retry with Exponential Backoff

All LLM calls automatically retry on transient network failures:

- Up to 3 attempts total
- Wait: 2s → 4s → 8s
- Retries on: connection errors, timeouts, network errors
- Fails fast on HTTP 4xx/5xx errors (permanent failures)

### Structured Output (JSON Mode)

The reviewer agent uses Ollama's `response_format={"type": "json"}` to enforce
valid JSON output, eliminating parsing failures.
Falls back to regex parsing if JSON mode is unavailable.

---

## Current Status & Roadmap

### Implemented

- Two-agent feedback loop (coder → tests → reviewer → commit)
- 10 language test runners (Python, JS, Rust, Go, Java, Ruby, Elixir,
  PHP, CMake, Make)
- JSON mode for reliable reviewer parsing
- Retry logic with exponential backoff
- Checkpoint/resume for crash recovery
- Structured JSONL session logging
- Rich CLI (`--log-level`, `--dry-run`, `--model-*`, `--session-log`, `--resume`)
- Per-agent model configuration in `config.yaml`
- Type-safe codebase (mypy, ruff)
- **Scope enforcement** — File whitelist via `config.yaml` `scope` field

### Near-term additions

- Dependency bootstrapping (auto-install from lockfiles)
- Pre-commit lint gate (ruff, eslint, etc.)
- Better language detection (actual source file scanning)
- Partial commits / interactive staging
- Per-project template overrides

### Long-term vision

- Tool-calling agents (grep, read_file, search)
- Multi-agent planning & task decomposition
- Web UI for monitoring and manual approval
- GitHub/GitLab integration (PR creation, comments)
- Cost tracking & analytics dashboard
- Parallel test execution and agent work

---

## Troubleshooting

| Symptom | Likely Cause | Solution |
| ------- | ------------ | -------- |
| `Import "httpx"` | Not installed | Run `pip install -e .` or `uv sync` |
| `ConnectionError` | Ollama off | Start with `ollama serve` |
| `FileNotFoundError` | Missing `agents` | Ensure `agents/` exists |
| `No recognized` | Test runner failed | Check manifest files |
| Agent extra text | LLM ignores format | Use instruction-tuned model |
