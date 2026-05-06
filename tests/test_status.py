"""Tests for db_process.runner status helpers (is_running, status, ProcessStatus)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from db_process.runner import ProcessStatus, is_running, status


class TestIsRunning:
    @patch("db_process.runner.find_process", return_value=None)
    def test_false_when_no_process(self, mock_find):
        assert is_running() is False

    @patch("db_process.runner.find_process")
    def test_true_when_process_found(self, mock_find):
        # Stand-in for a psutil.Process — only attribute touched is `pid`.
        class FakeProc:
            pid = 1234
        mock_find.return_value = FakeProc()
        assert is_running() is True


class TestStatus:
    @patch("db_process.runner.find_designbuilder", return_value=Path("X:/DB.exe"))
    @patch("db_process.runner.find_process", return_value=None)
    def test_not_running_with_exe(self, mock_find_proc, mock_find_exe):
        s = status()
        assert isinstance(s, ProcessStatus)
        assert s.is_running is False
        assert s.pid is None
        assert s.exe_path is not None and "DB.exe" in s.exe_path

    @patch("db_process.runner.find_designbuilder")
    @patch("db_process.runner.find_process")
    def test_running(self, mock_find_proc, mock_find_exe):
        class FakeProc:
            pid = 4242
        mock_find_proc.return_value = FakeProc()
        mock_find_exe.return_value = Path("X:/DB.exe")
        s = status()
        assert s.is_running is True
        assert s.pid == 4242
        assert s.exe_path is not None and "DB.exe" in s.exe_path

    @patch("db_process.runner.find_designbuilder", side_effect=FileNotFoundError("no DB"))
    @patch("db_process.runner.find_process", return_value=None)
    def test_no_exe_found(self, mock_find_proc, mock_find_exe):
        s = status()
        assert s.is_running is False
        assert s.exe_path is None

    def test_ProcessStatus_is_frozen(self):
        s = ProcessStatus(is_running=False, pid=None, exe_path=None)
        with pytest.raises(Exception):
            s.is_running = True  # type: ignore[misc]
