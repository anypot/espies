"""Integration tests for checkpoint module."""

import tempfile
from pathlib import Path

from espies.checkpoint import CheckpointData, CheckpointManager


class TestCheckpointData:
    """Tests for CheckpointData dataclass."""

    def test_create_checkpoint_data(self):
        """CheckpointData can be created with valid fields."""
        data = CheckpointData(
            task="Test task",
            repo_url="https://github.com/test/repo.git",
            repo_dir="/tmp/repo",
            max_iters=5,
            model_coder="qwen2.5-coder:14b",
            model_reviewer="deepseek-r1:14b",
            current_iteration=2,
            feedback_history=["feedback 1"],
            config={"key": "value"},
            created_at="2024-01-01T00:00:00Z",
            last_updated="2024-01-01T00:00:00Z",
        )
        assert data.task == "Test task"
        assert data.current_iteration == 2


class TestCheckpointManager:
    """Tests for CheckpointManager class."""

    def test_create_checkpoint_helper(self):
        """create_checkpoint method builds correct CheckpointData."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CheckpointManager(Path(tmpdir))
            data = mgr.create_checkpoint(
                task="Test task",
                repo_url="https://github.com/test/repo.git",
                repo_dir=Path("/tmp/repo"),
                max_iters=3,
                model_coder="qwen",
                model_reviewer="deepseek",
                current_iteration=1,
                feedback_history=["fb"],
                config={"k": "v"},
            )
            assert isinstance(data, CheckpointData)
            assert data.task == "Test task"
            assert data.current_iteration == 1
            assert data.feedback_history == ["fb"]

    def test_save_and_load_roundtrip(self):
        """Checkpoint can be saved and loaded correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CheckpointManager(Path(tmpdir))

            data = CheckpointData(
                task="Test task",
                repo_url="https://github.com/test/repo.git",
                repo_dir="/tmp/repo",
                max_iters=5,
                model_coder="qwen",
                model_reviewer="deepseek",
                current_iteration=2,
                feedback_history=["feedback"],
                config={"key": "value"},
                created_at="2024-01-01T00:00:00Z",
                last_updated="2024-01-01T00:01:00Z",
            )

            saved_path = mgr.save(data)
            assert saved_path.exists()

            loaded = mgr.load_latest()
            assert loaded is not None
            assert loaded.task == data.task
            assert loaded.current_iteration == data.current_iteration

    def test_load_latest_returns_none_when_no_checkpoint(self):
        """load_latest returns None when no checkpoint exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CheckpointManager(Path(tmpdir))
            assert mgr.load_latest() is None

    def test_delete_all_removes_checkpoints(self):
        """delete_all removes all checkpoint files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CheckpointManager(Path(tmpdir))

            data = CheckpointData(
                task="Test",
                repo_url="https://github.com/test/repo.git",
                repo_dir="/tmp/repo",
                max_iters=3,
                model_coder="qwen",
                model_reviewer="deepseek",
                current_iteration=1,
                feedback_history=[],
                config={},
                created_at="2024-01-01T00:00:00Z",
                last_updated="2024-01-01T00:00:00Z",
            )
            mgr.save(data)

            mgr.delete_all()

            checkpoint_dir = Path(tmpdir) / ".espies" / "checkpoints"
            assert not any(checkpoint_dir.glob("*.json"))

    def test_latest_symlink_updated(self):
        """latest.json is updated on each save."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = CheckpointManager(Path(tmpdir))

            data1 = CheckpointData(
                task="Task 1",
                repo_url="https://github.com/test/repo.git",
                repo_dir="/tmp/repo",
                max_iters=3,
                model_coder="qwen",
                model_reviewer="deepseek",
                current_iteration=1,
                feedback_history=[],
                config={},
                created_at="2024-01-01T00:00:00Z",
                last_updated="2024-01-01T00:00:00Z",
            )
            mgr.save(data1)

            data2 = CheckpointData(
                task="Task 2",
                repo_url="https://github.com/test/repo.git",
                repo_dir="/tmp/repo",
                max_iters=3,
                model_coder="qwen",
                model_reviewer="deepseek",
                current_iteration=2,
                feedback_history=[],
                config={},
                created_at="2024-01-01T00:00:00Z",
                last_updated="2024-01-01T00:00:00Z",
            )
            mgr.save(data2)

            loaded = mgr.load_latest()
            assert loaded.task == "Task 2"