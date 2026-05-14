"""Unit tests for git_ops module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from espies.git_ops import add_all, clone, commit, diff, has_changes, reset_hard, run, check_scope


class TestRun:
    """Tests for the run helper function."""

    @patch("subprocess.run")
    def test_run_passes_correct_arguments(self, mock_run: MagicMock) -> None:
        """run() passes command and cwd to subprocess.run."""
        mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")

        with patch("espies.git_ops.logger"):
            result = run("git status", Path("/tmp/repo"))

        mock_run.assert_called_once_with(
            "git status", cwd=Path("/tmp/repo"), shell=True, text=True, capture_output=True
        )
        assert result.returncode == 0

    @patch("subprocess.run")
    def test_run_returns_completed_process(self, mock_run: MagicMock) -> None:
        """run() returns the CompletedProcess from subprocess.run."""
        mock_result = MagicMock(stdout="output", stderr="error", returncode=0)
        mock_run.return_value = mock_result

        with patch("espies.git_ops.logger"):
            result = run("git test", Path("/tmp"))

        assert result.stdout == "output"


class TestDiff:
    """Tests for diff function."""

    @patch("espies.git_ops.run")
    def test_diff_calls_git_diff(self, mock_run: MagicMock) -> None:
        """diff() calls 'git diff' in the repo directory."""
        mock_run.return_value.stdout = "--- a/file\n+++ b/file"

        result = diff(Path("/tmp/repo"))

        mock_run.assert_called_once_with("git diff", cwd=Path("/tmp/repo"))
        assert "--- a/file" in result


class TestAddAll:
    """Tests for add_all function."""

    @patch("espies.git_ops.run")
    def test_add_all_stages_changes(self, mock_run: MagicMock) -> None:
        """add_all() runs 'git add -A'."""
        add_all(Path("/tmp/repo"))

        mock_run.assert_called_once_with("git add -A", cwd=Path("/tmp/repo"))


class TestCommit:
    """Tests for commit function."""

    @patch("espies.git_ops.run")
    def test_commit_uses_default_message(self, mock_run: MagicMock) -> None:
        """commit() uses 'agent change' as default message."""
        commit(Path("/tmp/repo"))

        mock_run.assert_called_once_with(
            'git commit -m "agent change"', cwd=Path("/tmp/repo")
        )

    @patch("espies.git_ops.run")
    def test_commit_uses_custom_message(self, mock_run: MagicMock) -> None:
        """commit() uses the provided message."""
        commit(Path("/tmp/repo"), "Custom commit message")

        mock_run.assert_called_once_with(
            'git commit -m "Custom commit message"', cwd=Path("/tmp/repo")
        )


class TestResetHard:
    """Tests for reset_hard function."""

    @patch("espies.git_ops.run")
    def test_reset_hard_discards_changes(self, mock_run: MagicMock) -> None:
        """reset_hard() runs 'git reset --hard'."""
        reset_hard(Path("/tmp/repo"))

        mock_run.assert_called_once_with("git reset --hard", cwd=Path("/tmp/repo"))


class TestHasChanges:
    """Tests for has_changes function."""

    @patch("espies.git_ops.run")
    def test_has_changes_returns_true_when_dirty(self, mock_run: MagicMock) -> None:
        """has_changes() returns True when git status shows output."""
        mock_run.return_value.stdout = "M file.py\n"

        assert has_changes(Path("/tmp/repo")) is True

    @patch("espies.git_ops.run")
    def test_has_changes_returns_false_when_clean(self, mock_run: MagicMock) -> None:
        """has_changes() returns False when git status is empty."""
        mock_run.return_value.stdout = ""

        assert has_changes(Path("/tmp/repo")) is False


class TestClone:
    """Tests for clone function."""

    @patch("espies.git_ops.run")
    def test_clone_clones_repository(self, mock_run: MagicMock) -> None:
        """clone() runs git clone with correct arguments."""
        with patch("espies.git_ops.logger"):
            clone("https://github.com/test/repo.git", Path("/tmp/repo"))

        mock_run.assert_called_once_with(
            "git clone https://github.com/test/repo.git .", cwd=Path("/tmp/repo")
        )


class TestCheckScope:
    """Tests for check_scope function."""

    def test_returns_empty_when_no_patterns(self) -> None:
        """check_scope returns empty list when no patterns provided."""
        diff_text = "--- a/file.py\n+++ b/file.py\n@@ -1,1 +1,1 @@\n-old\n+new"
        assert check_scope(diff_text) == []

    def test_allows_matched_files(self) -> None:
        """check_scope allows files matching patterns."""
        diff_text = "--- a/src/main.py\n+++ b/src/main.py\n@@ -1,1 +1,1 @@\n-old\n+new"
        assert check_scope(diff_text, ["*.py", "src/**/*.py"]) == []

    def test_rejects_unmatched_files(self) -> None:
        """check_scope rejects files not matching patterns."""
        diff_text = "--- a/README.md\n+++ b/README.md\n@@ -1,1 +1,1 @@\n-old\n+new"
        violations = check_scope(diff_text, ["*.py"])
        assert violations == ["README.md"]

    def test_handles_multiple_files(self) -> None:
        """check_scope handles multiple changed files."""
        diff_text = """--- a/src/main.py
+++ b/src/main.py
@@ -1,1 +1,1 @@
-old
+new
--- a/config.yaml
+++ b/config.yaml
@@ -1,1 +1,1 @@
-old
+new"""
        violations = check_scope(diff_text, ["*.py"])
        assert "config.yaml" in violations
        assert "src/main.py" not in violations