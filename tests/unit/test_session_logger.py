"""Unit tests for session_logger module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from espies.session_logger import SessionLogger


class TestSessionLoggerInit:
    """Unit tests for SessionLogger initialization."""

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open")
    def test_init_creates_parent_directory(self, mock_open: MagicMock, mock_mkdir: MagicMock) -> None:
        """__init__ creates parent directories for log file."""
        mock_open.return_value = MagicMock()

        SessionLogger(Path("/tmp/logs/session.jsonl"))

        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open")
    def test_init_opens_file(self, mock_open: MagicMock, mock_mkdir: MagicMock) -> None:
        """__init__ opens the log file in append mode."""
        mock_handle = MagicMock()
        mock_open.return_value = mock_handle

        logger = SessionLogger(Path("/tmp/logs/session.jsonl"))

        mock_open.assert_called_once_with(Path("/tmp/logs/session.jsonl"), "a", encoding="utf-8")
        assert logger._file_handle is mock_handle

    @patch("builtins.open")
    def test_init_none_log_file(self, mock_open: MagicMock) -> None:
        """__init__ handles None log_file gracefully."""
        logger = SessionLogger(None)

        assert logger.log_file is None
        assert logger._file_handle is None
        mock_open.assert_not_called()


class TestSessionLoggerLog:
    """Unit tests for SessionLogger.log method."""

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open")
    def test_log_writes_json_line(self, mock_open: MagicMock, mock_mkdir: MagicMock) -> None:
        """log() writes a JSON line to the file."""
        mock_handle = MagicMock()
        mock_open.return_value = mock_handle

        logger = SessionLogger(Path("/tmp/test.jsonl"))
        logger.log("test_event", key="value")

        mock_handle.write.assert_called_once()
        mock_handle.flush.assert_called_once()

        # Verify JSON content
        written = mock_handle.write.call_args[0][0]
        entry = json.loads(written)
        assert entry["event"] == "test_event"
        assert entry["key"] == "value"
        assert "timestamp" in entry

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open")
    def test_log_includes_timestamp(self, mock_open: MagicMock, mock_mkdir: MagicMock) -> None:
        """log() includes ISO format timestamp."""
        mock_handle = MagicMock()
        mock_open.return_value = mock_handle

        logger = SessionLogger(Path("/tmp/test.jsonl"))
        logger.log("event")

        written = mock_handle.write.call_args[0][0]
        entry = json.loads(written)
        assert "timestamp" in entry
        assert entry["timestamp"].endswith("Z")

    def test_log_without_file_writes_to_stderr(self) -> None:
        """log() writes to stderr when no file is set."""
        logger = SessionLogger(None)

        with patch("builtins.print") as mock_print:
            logger.log("event", data="test")
            mock_print.assert_called()


class TestSessionLoggerClose:
    """Unit tests for SessionLogger.close method."""

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open")
    def test_close_closes_file_handle(self, mock_open: MagicMock, mock_mkdir: MagicMock) -> None:
        """close() closes the file handle."""
        mock_handle = MagicMock()
        mock_open.return_value = mock_handle

        logger = SessionLogger(Path("/tmp/test.jsonl"))
        logger.close()

        mock_handle.close.assert_called_once()
        assert logger._file_handle is None

    def test_close_with_no_handle(self) -> None:
        """close() handles missing file handle gracefully."""
        logger = SessionLogger(None)
        logger.close()  # Should not raise

        assert logger._file_handle is None


class TestSessionLoggerContextManager:
    """Unit tests for SessionLogger context manager protocol."""

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open")
    def test_enter_returns_self(self, mock_open: MagicMock, mock_mkdir: MagicMock) -> None:
        """__enter__ returns self."""
        mock_handle = MagicMock()
        mock_open.return_value = mock_handle

        logger = SessionLogger(Path("/tmp/test.jsonl"))
        result = logger.__enter__()

        assert result is logger

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open")
    def test_exit_closes_file(self, mock_open: MagicMock, mock_mkdir: MagicMock) -> None:
        """__exit__ calls close."""
        mock_handle = MagicMock()
        mock_open.return_value = mock_handle

        logger = SessionLogger(Path("/tmp/test.jsonl"))
        logger.__enter__()
        logger.__exit__(None, None, None)

        mock_handle.close.assert_called_once()

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open")
    def test_with_statement(self, mock_open: MagicMock, mock_mkdir: MagicMock) -> None:
        """SessionLogger works as context manager."""
        mock_handle = MagicMock()
        mock_open.return_value = mock_handle

        with SessionLogger(Path("/tmp/test.jsonl")) as logger:
            logger.log("test")

        mock_handle.close.assert_called_once()