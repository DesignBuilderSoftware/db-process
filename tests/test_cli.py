"""Tests for db_process.cli — argument parsing + dispatch.

Subcommand handlers are mocked so tests don't touch a real DesignBuilder.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from db_process.cli import build_parser, main


class TestParser:
    def test_no_args_errors(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_close(self):
        ns = build_parser().parse_args(["close"])
        assert ns.cmd == "close"

    def test_status(self):
        ns = build_parser().parse_args(["status"])
        assert ns.cmd == "status"

    def test_open_no_model(self):
        ns = build_parser().parse_args(["open"])
        assert ns.cmd == "open" and ns.model is None

    def test_open_with_model(self):
        ns = build_parser().parse_args(["open", "Model.dsb"])
        assert ns.cmd == "open" and ns.model == Path("Model.dsb")

    def test_restart_default_settle(self):
        ns = build_parser().parse_args(["restart"])
        assert ns.cmd == "restart" and ns.model is None and ns.settle == 1.5

    def test_restart_custom_settle(self):
        ns = build_parser().parse_args(["restart", "--settle", "3"])
        assert ns.settle == 3.0

    def test_restart_with_model(self):
        ns = build_parser().parse_args(["restart", "X.dsb", "--settle", "0.1"])
        assert ns.model == Path("X.dsb") and ns.settle == 0.1


class TestDispatch:
    @patch("db_process.cli.kill_process", return_value=True)
    def test_close_kills(self, mock_kill):
        rc = main(["close"])
        mock_kill.assert_called_once()
        assert rc == 0

    @patch("db_process.cli.kill_process", return_value=False)
    def test_close_no_proc(self, mock_kill):
        rc = main(["close"])
        assert rc == 1

    @patch("db_process.cli.proc_status")
    def test_status_when_nothing_found(self, mock_status, capsys):
        from db_process.runner import ProcessStatus
        mock_status.return_value = ProcessStatus(is_running=False, pid=None, exe_path=None)
        rc = main(["status"])
        out = capsys.readouterr().out
        assert "not running" in out
        assert rc == 1

    @patch("db_process.cli.subprocess.Popen")
    @patch("db_process.cli.find_designbuilder", return_value=Path("X:/DB/DesignBuilder.exe"))
    def test_open_no_model_calls_popen(self, mock_find, mock_popen):
        rc = main(["open"])
        mock_popen.assert_called_once()
        assert rc == 0

    @patch("db_process.cli.run_async")
    @patch("db_process.cli.find_designbuilder", return_value=Path("X:/DB/DesignBuilder.exe"))
    def test_open_with_model_calls_run_async(self, mock_find, mock_run_async):
        rc = main(["open", "M.dsb"])
        mock_run_async.assert_called_once_with("M.dsb")
        assert rc == 0

    @patch("db_process.cli.time.sleep")
    @patch("db_process.cli.subprocess.Popen")
    @patch("db_process.cli.find_designbuilder", return_value=Path("X:/DB/DesignBuilder.exe"))
    @patch("db_process.cli.kill_process", return_value=True)
    def test_restart_kills_then_opens(
        self, mock_kill, mock_find, mock_popen, mock_sleep
    ):
        rc = main(["restart", "--settle", "0"])
        mock_kill.assert_called_once()
        mock_popen.assert_called_once()
        assert rc == 0

    @patch("db_process.cli.time.sleep")
    @patch("db_process.cli.subprocess.Popen")
    @patch("db_process.cli.find_designbuilder", return_value=Path("X:/DB/DesignBuilder.exe"))
    @patch("db_process.cli.kill_process", return_value=False)
    def test_restart_when_nothing_running(
        self, mock_kill, mock_find, mock_popen, mock_sleep
    ):
        # Should still launch DB even if nothing was killed
        rc = main(["restart"])
        mock_popen.assert_called_once()
        assert rc == 0
