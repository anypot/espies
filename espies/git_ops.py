import subprocess
import re
from pathlib import Path
import logging
from fnmatch import fnmatch

logger = logging.getLogger(__name__)


def run(cmd: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    logger.debug("Running command: %s (cwd=%s)", cmd, cwd)
    result = subprocess.run(cmd, cwd=cwd, shell=True, text=True, capture_output=True)
    logger.debug("Command completed with rc=%d", result.returncode)
    if result.stdout:
        logger.debug("Stdout: %s", result.stdout[:200])
    if result.stderr:
        logger.debug("Stderr: %s", result.stderr[:200])
    return result


def diff(repo_dir: Path) -> str:
    logger.debug("Computing git diff for %s", repo_dir)
    result = run("git diff", cwd=repo_dir)
    return result.stdout


def add_all(repo_dir: Path) -> None:
    logger.debug("Staging all changes in %s", repo_dir)
    run("git add -A", cwd=repo_dir)


def commit(repo_dir: Path, message: str = "agent change") -> None:
    logger.debug("Committing with message: %s", message)
    run(f'git commit -m "{message}"', cwd=repo_dir)


def reset_hard(repo_dir: Path) -> None:
    logger.debug("Resetting repository hard")
    run("git reset --hard", cwd=repo_dir)


def has_changes(repo_dir: Path) -> bool:
    result = run("git status --porcelain", cwd=repo_dir)
    changes = bool(result.stdout.strip())
    logger.debug("Repository has changes: %s", changes)
    return changes


def clone(url: str, repo_dir: Path) -> None:
    logger.info("Cloning %s into %s", url, repo_dir)
    repo_dir.mkdir(parents=True, exist_ok=True)
    run(f"git clone {url} .", cwd=repo_dir)
    logger.info("Clone completed")


def check_scope(diff_text: str, allowed_patterns: list[str] | None = None) -> list[str]:
    """
    Validate that changed files match allowed scope patterns.

    Returns list of violations (files that don't match scope).
    Empty list means scope is respected.
    """
    if not allowed_patterns:
        return []

    changed_files = set()
    for line in diff_text.split("\n"):
        # Match diff header lines: --- a/path or +++ b/path
        match = re.match(r"^(---|\+\+\+) [ab]/(.+)$", line)
        if match:
            changed_files.add(match.group(2))

    violations = []
    for file_path in changed_files:
        if not any(fnmatch(file_path, pattern) for pattern in allowed_patterns):
            violations.append(file_path)

    return violations