import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CheckpointData:
    """Serializable checkpoint state."""

    task: str
    repo_url: str
    repo_dir: str
    max_iters: int
    model_coder: str | None
    model_reviewer: str | None
    current_iteration: int  # 1-based iteration number (next iteration to run)
    feedback_history: list[str]
    config: dict[str, Any]
    created_at: str
    last_updated: str


class CheckpointManager:
    """Manages saving and loading session checkpoints."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.checkpoint_dir = workspace / ".espies" / "checkpoints"
        self._current_checkpoint: CheckpointData | None = None

    def create_checkpoint(
        self,
        task: str,
        repo_url: str,
        repo_dir: Path,
        max_iters: int,
        model_coder: str | None,
        model_reviewer: str | None,
        current_iteration: int,
        feedback_history: list[str],
        config: dict[str, Any],
        created_at: str | None = None,
    ) -> CheckpointData:
        """Create a CheckpointData instance with current timestamp."""
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return CheckpointData(
            task=task,
            repo_url=repo_url,
            repo_dir=str(repo_dir),
            max_iters=max_iters,
            model_coder=model_coder,
            model_reviewer=model_reviewer,
            current_iteration=current_iteration,
            feedback_history=feedback_history,
            config=config,
            created_at=created_at or now,
            last_updated=now,
        )

    def save(self, data: CheckpointData) -> Path:
        """Save checkpoint to disk."""
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = f"checkpoint-{timestamp}.json"
        path = self.checkpoint_dir / filename

        # Also write "latest.json" for easy resume
        latest_path = self.checkpoint_dir / "latest.json"

        with open(path, "w") as f:
            json.dump(asdict(data), f, indent=2)

        with open(latest_path, "w") as f:
            json.dump(asdict(data), f, indent=2)

        logger.info("Checkpoint saved: %s", path)
        logger.debug("Latest checkpoint symlink updated: %s", latest_path)
        return path

    def load_latest(self) -> CheckpointData | None:
        """Load the most recent checkpoint if it exists."""
        latest_path = self.checkpoint_dir / "latest.json"
        if not latest_path.exists():
            logger.debug("No checkpoint found at %s", latest_path)
            return None

        try:
            with open(latest_path) as f:
                data = json.load(f)

            checkpoint = CheckpointData(
                task=data["task"],
                repo_url=data["repo_url"],
                repo_dir=data["repo_dir"],
                max_iters=data["max_iters"],
                model_coder=data.get("model_coder"),
                model_reviewer=data.get("model_reviewer"),
                current_iteration=data["current_iteration"],
                feedback_history=data["feedback_history"],
                config=data["config"],
                created_at=data["created_at"],
                last_updated=data["last_updated"],
            )
            logger.info(
                "Loaded checkpoint from %s (created: %s)",
                latest_path,
                checkpoint.created_at,
            )
            return checkpoint
        except (KeyError, json.JSONDecodeError) as e:
            logger.error("Failed to load checkpoint: %s", e)
            return None

    def delete_all(self) -> None:
        """Delete all checkpoints (e.g., after successful completion)."""
        if self.checkpoint_dir.exists():
            for f in self.checkpoint_dir.glob("*.json"):
                f.unlink()
            logger.info("Deleted all checkpoints in %s", self.checkpoint_dir)
