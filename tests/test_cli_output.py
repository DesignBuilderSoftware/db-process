"""Additional CLI tests — output formatting and branches not covered by
test_cli.py (status when running, open/restart with model, module entry
point, package exports)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from db_process.cli import main
from db_process.runner import ProcessStatus


class TestStatusOutput:
    @patch("db_process.cli.proc_status")
    def test_status_running_returns_zero(self, mock_status, capsys):
        mock_status.return_value = ProcessStatus(
            is_running=True, pid=4321, exe_path="X:/DB/DesignBuilder.exe"
        )
        rc = main(["status"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "pid=4321" in out
        assert "X:/DB/DesignBuilder.exe" in out

    @patch("db_process.cli.proc_status")
    def test_status_exe_missing_shows_placeholder(self, mock_status, capsys):
        mock_status.return_value = ProcessStatus(
            is_running=False, pid=None, exe_path=None
        )
        main(["status"])
        out = capsys.readouterr().out
        assert "<not found>" in out


class TestCloseOutput:
    @patch("db_process.cli.kill_process", return_value=True)
    def test_close_message(self, mock_kill, capsys):
        main(["close"])
        assert "Closed running DesignBuilder." in capsys.readouterr().out

    @patch("db_process.cli.kill_process", return_value=False)
    def test_no_close_message(self, mock_kill, capsys):
        main(["close"])
        assert "No DesignBuilder process to close." in capsys.readouterr().out


class TestOpenOutput:
    @patch("db_process.cli.run_async")
    @patch(
        "db_process.cli.find_designbuilder",
        return_value=Path("X:/DB/DesignBuilder.exe"),
    )
    def test_open_with_model_message(self, mock_find, mock_run_async, capsys):
        main(["open", "M.dsb"])
        out = capsys.readouterr().out
        assert "Opening M.dsb" in out

    @patch("db_process.cli.subprocess.Popen")
    @patch(
        "db_process.cli.find_designbuilder",
        return_value=Path("X:/DB/DesignBuilder.exe"),
    )
    def test_open_without_model_message(self, mock_find, mock_popen, capsys):
        main(["open"])
        out = capsys.readouterr().out
        assert "no model" in out
        mock_popen.assert_called_once_with(["X:\\DB\\DesignBuilder.exe"])


class TestRestart:
    @patch("db_process.cli.time.sleep")
    @patch("db_process.cli.run_async")
    @patch(
        "db_process.cli.find_designbuilder",
        return_value=Path("X:/DB/DesignBuilder.exe"),
    )
    @patch("db_process.cli.kill_process", return_value=True)
    def test_restart_with_model_uses_run_async(
        self, mock_kill, mock_find, mock_run_async, mock_sleep
    ):
        rc = main(["restart", "M.dsb", "--settle", "2"])
        assert rc == 0
        mock_run_async.assert_called_once_with("M.dsb")
        mock_sleep.assert_called_once_with(2.0)

    @patch("db_process.cli.time.sleep")
    @patch("db_process.cli.subprocess.Popen")
    @patch(
        "db_process.cli.find_designbuilder",
        return_value=Path("X:/DB/DesignBuilder.exe"),
    )
    @patch("db_process.cli.kill_process", return_value=False)
    def test_restart_skips_settle_when_nothing_killed(
        self, mock_kill, mock_find, mock_popen, mock_sleep
    ):
        main(["restart"])
        mock_sleep.assert_not_called()


class TestOpenErrors:
    @patch(
        "db_process.cli.find_designbuilder",
        side_effect=FileNotFoundError("Could not find DesignBuilder.exe"),
    )
    def test_open_propagates_missing_exe(self, mock_find):
        # cmd_open does not catch discovery failures; they surface to the caller.
        with pytest.raises(FileNotFoundError, match="Could not find"):
            main(["open"])

    @patch(
        "db_process.cli.find_designbuilder",
        side_effect=FileNotFoundError("Could not find DesignBuilder.exe"),
    )
    @patch("db_process.cli.kill_process", return_value=False)
    def test_restart_propagates_missing_exe(self, mock_kill, mock_find):
        with pytest.raises(FileNotFoundError):
            main(["restart"])


class TestModuleEntryPoint:
    def test_python_m_db_process_no_args_exits_2(self):
        """`python -m db_process` with no subcommand exits with argparse error."""
        result = subprocess.run(
            [sys.executable, "-m", "db_process"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert "usage" in result.stderr.lower()

    def test_python_m_db_process_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "db_process", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "DesignBuilder process control" in result.stdout

    def test_python_m_cli_module_directly(self):
        """cli.py's own `if __name__ == "__main__"` guard also works."""
        result = subprocess.run(
            [sys.executable, "-m", "db_process.cli", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "DesignBuilder process control" in result.stdout

    def test_help_lists_all_subcommands(self):
        result = subprocess.run(
            [sys.executable, "-m", "db_process", "--help"],
            capture_output=True,
            text=True,
        )
        for sub in ("status", "close", "open", "restart"):
            assert sub in result.stdout


class TestPackageExports:
    def test_all_names_importable(self):
        import db_process

        for name in db_process.__all__:
            assert hasattr(db_process, name), f"__all__ lists missing name: {name}"

    def test_invalid_subcommand_exits(self):
        with pytest.raises(SystemExit):
            main(["bogus"])
