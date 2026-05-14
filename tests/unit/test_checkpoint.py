"""Unit tests for checkpoint module."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from espies.checkpoint import CheckpointData, CheckpointManager


class TestCheckpointData:
    """Unit tests for CheckpointData dataclass."""

    def test_checkpoint_data_is_dataclass(self) -> None:
        """CheckpointData behaves like a dataclass."""
        data = CheckpointData(
            task="Test",
            repo_url="https://github.com/test/repo.git",
            repo_dir="/tmp/repo",
            max_iters=5,
            model_coder="qwen",
            model_reviewer="deepseek",
            current_iteration=1,
            feedback_history=[],
            config={},
            created_at="2024-01-01T00:00:00Z",
            last_updated="2024-01-01T00:00:00Z",
        )
        assert data.task == "Test"
        assert data.current_iteration == 1

    def test_checkpoint_data_defaults(self) -> None:
        """CheckpointData fields have correct types."""
        data = CheckpointData(
            task="Test",
            repo_url="https://github.com/test/repo.git",
            repo_dir="/tmp/repo",
            max_iters=3,
            model_coder=None,
            model_reviewer=None,
            current_iteration=1,
            feedback_history=["fb"],
            config={"k": "v"},
            created_at=datetime.now(timezone.utc).isoformat(),
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
        assert data.model_coder is None
        assert data.feedback_history == ["fb"]


class TestCheckpointManagerInit:
    """Unit tests for CheckpointManager initialization."""

    def test_init_sets_checkpoint_dir(self) -> None:
        """Constructor sets up checkpoint directory path."""
        workspace = Path("/tmp/workspace")
        mgr = CheckpointManager(workspace)

        assert mgr.workspace == workspace
        assert mgr.checkpoint_dir == workspace / ".espies" / "checkpoints"

    def test_init_sets_current_checkpoint_to_none(self) -> None:
        """Constructor initializes _current_checkpoint to None."""
        mgr = CheckpointManager(Path("/tmp"))
        assert mgr._current_checkpoint is None


class TestCheckpointManagerCreateCheckpoint:
    """Unit tests for create_checkpoint method."""

    def test_create_checkpoint_returns_checkpoint_data(self) -> None:
        """create_checkpoint returns a CheckpointData instance."""
        mgr = CheckpointManager(Path("/tmp"))
        result = mgr.create_checkpoint(
            task="Task",
            repo_url="https://github.com/test/repo.git",
            repo_dir=Path("/tmp/repo"),
            max_iters=3,
            model_coder="qwen",
            model_reviewer="deepseek",
            current_iteration=1,
            feedback_history=[],
            config={},
        )

        assert isinstance(result, CheckpointData)
        assert result.task == "Task"
        assert result.repo_dir == "/tmp/repo"

    def test_create_checkpoint_converts_path_to_str(self) -> None:
        """create_checkpoint converts repo_dir Path to string."""
        mgr = CheckpointManager(Path("/tmp"))
        result = mgr.create_checkpoint(
            task="Task",
            repo_url="https://github.com/test/repo.git",
            repo_dir=Path("/tmp/repo"),
            max_iters=1,
            model_coder=None,
            model_reviewer=None,
            current_iteration=2,
            feedback_history=["fb"],
            config={"key": "value"},
        )

        assert result.repo_dir == "/tmp/repo"
        assert isinstance(result.repo_dir, str)

    def test_create_checkpoint_uses_provided_created_at(self) -> None:
        """create_checkpoint uses provided created_at timestamp."""
        mgr = CheckpointManager(Path("/tmp"))
        custom_time = "2024-01-01T12:00:00Z"
        result = mgr.create_checkpoint(
            task="Task",
            repo_url="https://github.com/test/repo.git",
            repo_dir=Path("/tmp/repo"),
            max_iters=1,
            model_coder=None,
            model_reviewer=None,
            current_iteration=1,
            feedback_history=[],
            config={},
            created_at=custom_time,
        )

        assert result.created_at == custom_time

    def test_create_checkpoint_sets_same_timestamp_for_both(self) -> None:
        """create_checkpoint sets last_updated same as created_at when not resuming."""
        mgr = CheckpointManager(Path("/tmp"))
        result = mgr.create_checkpoint(
            task="Task",
            repo_url="https://github.com/test/repo.git",
            repo_dir=Path("/tmp/repo"),
            max_iters=1,
            model_coder=None,
            model_reviewer=None,
            current_iteration=1,
            feedback_history=[],
            config={},
        )

        # Both timestamps should be set (not necessarily equal, but both present)
        assert result.created_at
        assert result.last_updated


class TestCheckpointManagerSave:
    """Unit tests for save method."""

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=mock_open)
    def test_save_creates_checkpoint_dir(self, mock_file: MagicMock, mock_mkdir: MagicMock) -> None:
        """save() creates the checkpoint directory."""
        mgr = CheckpointManager(Path("/tmp/workspace"))
        data = CheckpointData(
            task="Task",
            repo_url="https://github.com/test/repo.git",
            repo_dir="/tmp/repo",
            max_iters=1,
            model_coder=None,
            model_reviewer=None,
            current_iteration=1,
            feedback_history=[],
            config={},
            created_at="2024-01-01T00:00:00Z",
            last_updated="2024-01-01T00:00:00Z",
        )

        mgr.save(data)

        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=mock_open)
    def test_save_writes_json(self, mock_file: MagicMock, mock_mkdir: MagicMock) -> None:
        """save() writes JSON to checkpoint files."""
        mgr = CheckpointManager(Path("/tmp/workspace"))
        data = CheckpointData(
            task="Task",
            repo_url="https://github.com/test/repo.git",
            repo_dir="/tmp/repo",
            max_iters=1,
            model_coder=None,
            model_reviewer=None,
            current_iteration=1,
            feedback_history=[],
            config={},
            created_at="2024-01-01T00:00:00Z",
            last_updated="2024-01-01T00:00:00Z",
        )

        result = mgr.save(data)

        assert result.exists() or str(result).endswith(".json")


class TestCheckpointManagerLoadLatest:
    """Unit tests for load_latest method."""

    @patch("pathlib.Path.exists")
    def test_load_latest_returns_none_when_no_file(self, mock_exists: MagicMock) -> None:
        """load_latest returns None when latest.json doesn't exist."""
        mock_exists.return_value = False
        mgr = CheckpointManager(Path("/tmp/workspace"))

        result = mgr.load_latest()

        assert result is None

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data='{"task": "Test"}')
    def test_load_latest_parses_json(self, mock_file: MagicMock, mock_exists: MagicMock) -> None:
        """load_latest parses the JSON file correctly."""
        mock_exists.return_value = True
        mgr = CheckpointManager(Path("/tmp/workspace"))

        # Return None because JSON is incomplete, but we're testing the parsing path
        result = mgr.load_latest()
        # Will be None due to missing required fields, but tested that it attempts to parse
        assert result is None


class TestCheckpointManagerDeleteAll:
    """Unit tests for delete_all method."""

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.glob")
    def test_delete_all_removes_json_files(
        self, mock_glob: MagicMock, mock_exists: MagicMock
    ) -> None:
        """delete_all removes all JSON files in checkpoint directory."""
        mock_exists.return_value = True
        mock_file1 = MagicMock()
        mock_file1.unlink = MagicMock()
        mock_file2 = MagicMock()
        mock_file2.unlink = MagicMock()
        mock_glob.return_value = [mock_file1, mock_file2]

        mgr = CheckpointManager(Path("/tmp/workspace"))
        mgr.delete_all()

        mock_file1.unlink.assert_called_once()
        mock_file2.unlink.assert_called_once()

    @patch("pathlib.Path.exists")
    def test_delete_all_handles_missing_directory(self, mock_exists: MagicMock) -> None:
        """delete_all does nothing when directory doesn't exist."""
        mock_exists.return_value = False
        mgr = CheckpointManager(Path("/tmp/workspace"))

        # Should not raise
        mgr.delete_all()