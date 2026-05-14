import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SessionLogger:
    """Structured JSONL session logger that writes machine-readable event logs."""

    def __init__(self, log_file: Path | None = None) -> None:
        self.log_file = log_file
        self._file_handle: io.TextIOWrapper | None = None
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self._file_handle = open(self.log_file, "a", encoding="utf-8")
            logging.getLogger(__name__).info(
                "Session logging enabled: %s", self.log_file
            )

    def log(self, event_type: str, **data: Any) -> None:
        """Write a JSON log entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": event_type,
            **data,
        }
        line = json.dumps(entry, ensure_ascii=False, default=str)

        if self._file_handle:
            self._file_handle.write(line + "\n")
            self._file_handle.flush()
        else:
            # Fallback to stderr if no file
            print(line, file=__import__("sys").stderr)

    def close(self) -> None:
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None

    def __enter__(self) -> "SessionLogger":
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: object,
    ) -> None:
        self.close()