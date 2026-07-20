"""Tests for db_process.runner — process discovery, kill helpers,
blocking/non-blocking execution and idle detection.

Everything is mocked; no real DesignBuilder process or subprocess is
started by these tests.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil
import pytest

from db_process.commands import ProcessChain, Screen
from db_process.runner import (
    DESIGNBUILDER_PROCESS_NAME,
    RunHandle,
    RunResult,
    find_process,
    is_running,
    kill_process,
    kill_when_idle,
    run,
    run_async,
    status,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakePsProc:
    """Minimal stand-in for psutil.Process as used by runner.py."""

    def __init__(self, name: str, pid: int = 111):
        self.info = {"name": name}
        self.pid = pid
        self.killed = False
        self.waited = False

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.waited = True


class RaisingProc:
    """Process whose .info access raises, mimicking a vanished process."""

    @property
    def info(self):
        raise psutil.NoSuchProcess(pid=999)


# ---------------------------------------------------------------------------
# RunResult defaults
# ---------------------------------------------------------------------------


class TestRunResult:
    def test_defaults(self):
        r = RunResult(success=True)
        assert r.returncode is None
        assert r.stdout == "" and r.stderr == ""
        assert r.timed_out is False
        assert r.killed_idle is False
        assert r.duration_seconds is None


# ---------------------------------------------------------------------------
# find_process
# ---------------------------------------------------------------------------


class TestFindProcess:
    @patch("db_process.runner.psutil.process_iter")
    def test_returns_first_match(self, mock_iter):
        other = FakePsProc("notepad.exe", pid=1)
        db1 = FakePsProc(DESIGNBUILDER_PROCESS_NAME, pid=2)
        db2 = FakePsProc(DESIGNBUILDER_PROCESS_NAME, pid=3)
        mock_iter.return_value = [other, db1, db2]
        found = find_process()
        assert found is db1
        mock_iter.assert_called_once_with(["name"])

    @patch("db_process.runner.psutil.process_iter")
    def test_returns_none_when_no_match(self, mock_iter):
        mock_iter.return_value = [FakePsProc("explorer.exe")]
        assert find_process() is None

    @patch("db_process.runner.psutil.process_iter")
    def test_skips_vanished_processes(self, mock_iter):
        db = FakePsProc(DESIGNBUILDER_PROCESS_NAME, pid=7)
        mock_iter.return_value = [RaisingProc(), db]
        assert find_process() is db

    @patch("db_process.runner.psutil.process_iter")
    def test_custom_name(self, mock_iter):
        target = FakePsProc("MyApp.exe")
        mock_iter.return_value = [FakePsProc(DESIGNBUILDER_PROCESS_NAME), target]
        assert find_process("MyApp.exe") is target


# ---------------------------------------------------------------------------
# kill_process
# ---------------------------------------------------------------------------


class TestKillProcess:
    @patch("db_process.runner.find_process", return_value=None)
    def test_returns_false_when_not_found(self, mock_find):
        assert kill_process() is False

    @patch("db_process.runner.find_process")
    def test_kills_and_waits(self, mock_find):
        proc = FakePsProc(DESIGNBUILDER_PROCESS_NAME)
        mock_find.return_value = proc
        assert kill_process() is True
        assert proc.killed is True
        assert proc.waited is True

    @patch("db_process.runner.find_process", return_value=None)
    def test_passes_name_through(self, mock_find):
        kill_process("Other.exe")
        mock_find.assert_called_once_with("Other.exe")


# ---------------------------------------------------------------------------
# kill_when_idle
# ---------------------------------------------------------------------------


class IdleScriptProc:
    """Fake process with a scripted cpu_percent sequence."""

    def __init__(self, cpu_values, running_after_script=False):
        self._cpu = list(cpu_values)
        self._running_after = running_after_script
        self.killed = False

    def is_running(self):
        if self.killed:
            return False
        return bool(self._cpu) or self._running_after

    def cpu_percent(self, interval=None):
        return self._cpu.pop(0)

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        pass


class TestNamePassthrough:
    """Custom process names must be forwarded to find_process."""

    @patch("db_process.runner.find_process", return_value=None)
    def test_is_running_passes_name(self, mock_find):
        is_running("Custom.exe")
        mock_find.assert_called_once_with("Custom.exe")

    @patch("db_process.runner.find_designbuilder", side_effect=FileNotFoundError)
    @patch("db_process.runner.find_process", return_value=None)
    def test_status_passes_name(self, mock_find_proc, mock_find_exe):
        status("Custom.exe")
        mock_find_proc.assert_called_once_with("Custom.exe")

    @patch("db_process.runner.find_process", return_value=None)
    def test_kill_when_idle_passes_name(self, mock_find):
        kill_when_idle("Custom.exe")
        mock_find.assert_called_once_with("Custom.exe")


class TestKillWhenIdle:
    @patch("db_process.runner.find_process", return_value=None)
    def test_no_process_returns_false(self, mock_find):
        assert kill_when_idle() is False

    @patch("db_process.runner.time.sleep")
    @patch("db_process.runner.find_process")
    def test_kills_after_idle_threshold(self, mock_find, mock_sleep):
        # Active once, then idle long enough to trip the threshold.
        proc = IdleScriptProc([50.0, 0.0, 0.0], running_after_script=True)
        mock_find.return_value = proc
        result = kill_when_idle(
            idle_threshold=1.0, check_interval=0.5, startup_period=0
        )
        assert result is True
        assert proc.killed is True

    @patch("db_process.runner.time.sleep")
    @patch("db_process.runner.find_process")
    def test_never_active_process_exits_on_its_own(self, mock_find, mock_sleep):
        # Idle from the start: has_been_active never set, so no kill.
        proc = IdleScriptProc([0.0, 0.0, 0.0], running_after_script=False)
        mock_find.return_value = proc
        result = kill_when_idle(
            idle_threshold=1.0, check_interval=0.5, startup_period=0
        )
        assert result is False
        assert proc.killed is False

    @patch("db_process.runner.time.sleep")
    @patch("db_process.runner.find_process")
    def test_activity_resets_idle_timer(self, mock_find, mock_sleep):
        # idle_threshold=1.0 / check_interval=0.5 needs two consecutive
        # idle readings; activity in between resets the counter.
        proc = IdleScriptProc(
            [50.0, 0.0, 50.0, 0.0, 0.0], running_after_script=True
        )
        mock_find.return_value = proc
        result = kill_when_idle(
            idle_threshold=1.0, check_interval=0.5, startup_period=0
        )
        assert result is True
        # All five scripted readings were consumed (kill on the last one).
        assert proc._cpu == []

    @patch("db_process.runner.time.sleep")
    @patch("db_process.runner.find_process")
    def test_startup_period_sleep(self, mock_find, mock_sleep):
        proc = IdleScriptProc([], running_after_script=False)
        mock_find.return_value = proc
        kill_when_idle(startup_period=20)
        mock_sleep.assert_any_call(20)

    @patch("db_process.runner.time.sleep")
    @patch("db_process.runner.find_process")
    def test_vanished_process_returns_false(self, mock_find, mock_sleep):
        proc = MagicMock()
        proc.is_running.return_value = True
        proc.cpu_percent.side_effect = psutil.NoSuchProcess(pid=1)
        mock_find.return_value = proc
        result = kill_when_idle(startup_period=0)
        assert result is False

    @patch("db_process.runner.time.sleep")
    @patch("db_process.runner.find_process")
    def test_access_denied_returns_false(self, mock_find, mock_sleep):
        proc = MagicMock()
        proc.is_running.return_value = True
        proc.cpu_percent.side_effect = psutil.AccessDenied(pid=1)
        mock_find.return_value = proc
        result = kill_when_idle(startup_period=0)
        assert result is False


# ---------------------------------------------------------------------------
# run (blocking)
# ---------------------------------------------------------------------------


EXE = Path("X:/DB/DesignBuilder.exe")


class TestRun:
    @patch("db_process.runner.subprocess.run")
    @patch("db_process.runner.find_designbuilder", return_value=EXE)
    def test_success(self, mock_find, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok", stderr=""
        )
        result = run("Model.dsb")
        assert result.success is True
        assert result.returncode == 0
        assert result.stdout == "ok"
        assert result.timed_out is False
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0

    @patch("db_process.runner.subprocess.run")
    @patch("db_process.runner.find_designbuilder", return_value=EXE)
    def test_failure_nonzero_returncode(self, mock_find, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=2, stdout="", stderr="boom"
        )
        result = run("Model.dsb")
        assert result.success is False
        assert result.returncode == 2
        assert result.stderr == "boom"

    @patch("db_process.runner.subprocess.run")
    @patch("db_process.runner.find_designbuilder", return_value=EXE)
    def test_command_without_chain(self, mock_find, mock_run):
        mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
        run("Model.dsb")
        cmd = mock_run.call_args[0][0]
        assert cmd == [str(EXE), "Model.dsb"]

    @patch("db_process.runner.subprocess.run")
    @patch("db_process.runner.find_designbuilder", return_value=EXE)
    def test_command_with_chain(self, mock_find, mock_run):
        mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
        chain = ProcessChain().switch_screen(Screen.SIMULATION).run()
        run("Model.dsb", chain)
        cmd = mock_run.call_args[0][0]
        assert cmd == [str(EXE), "Model.dsb", "/process=miGSS, miTUpdate"]

    @patch("db_process.runner.subprocess.run")
    @patch("db_process.runner.find_designbuilder", return_value=EXE)
    def test_timeout_passed_through(self, mock_find, mock_run):
        mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
        run("Model.dsb", timeout=42)
        assert mock_run.call_args.kwargs["timeout"] == 42

    @patch("db_process.runner.kill_process")
    @patch("db_process.runner.subprocess.run")
    @patch("db_process.runner.find_designbuilder", return_value=EXE)
    def test_timeout_kills_process(self, mock_find, mock_run, mock_kill):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="db", timeout=1)
        result = run("Model.dsb", timeout=1)
        assert result.success is False
        assert result.timed_out is True
        assert result.returncode is None
        assert result.duration_seconds is not None
        mock_kill.assert_called_once()

    @patch("db_process.runner.find_designbuilder", return_value=EXE)
    def test_explicit_exe_path_forwarded(self, mock_find):
        with patch("db_process.runner.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
            run("Model.dsb", exe_path="Y:/custom/DB.exe")
        mock_find.assert_called_once_with("Y:/custom/DB.exe")

    @patch("db_process.runner.subprocess.run")
    @patch("db_process.runner.find_designbuilder", return_value=EXE)
    def test_model_path_object_accepted(self, mock_find, mock_run):
        mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
        model = Path("C:/models/Office.dsb")
        run(model)
        cmd = mock_run.call_args[0][0]
        assert cmd == [str(EXE), str(model)]

    @patch("db_process.runner.subprocess.run")
    @patch("db_process.runner.find_designbuilder", return_value=EXE)
    def test_no_timeout_by_default(self, mock_find, mock_run):
        mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
        run("Model.dsb")
        assert mock_run.call_args.kwargs["timeout"] is None


# ---------------------------------------------------------------------------
# RunHandle
# ---------------------------------------------------------------------------


class TestRunHandle:
    def _handle(self, poll=None, returncode=0, wait_raises=None):
        popen = MagicMock(spec=subprocess.Popen)
        popen.poll.return_value = poll
        popen.returncode = returncode
        if wait_raises is not None:
            popen.wait.side_effect = wait_raises
        return RunHandle(process=popen)

    def test_is_running_true(self):
        handle = self._handle(poll=None)
        assert handle.is_running() is True

    def test_is_running_false(self):
        handle = self._handle(poll=0)
        assert handle.is_running() is False

    def test_wait_success(self):
        handle = self._handle(returncode=0)
        result = handle.wait()
        assert result.success is True
        assert result.returncode == 0
        assert result.duration_seconds is not None

    def test_wait_failure(self):
        handle = self._handle(returncode=5)
        result = handle.wait()
        assert result.success is False
        assert result.returncode == 5

    @patch("db_process.runner.kill_process")
    def test_wait_timeout(self, mock_kill):
        handle = self._handle(
            wait_raises=subprocess.TimeoutExpired(cmd="db", timeout=1)
        )
        result = handle.wait(timeout=1)
        assert result.success is False
        assert result.timed_out is True
        mock_kill.assert_called_once()

    @patch("db_process.runner.kill_process")
    def test_kill_delegates(self, mock_kill):
        handle = self._handle()
        handle.kill()
        mock_kill.assert_called_once()

    @patch("db_process.runner.kill_when_idle", return_value=True)
    def test_kill_when_idle_delegates(self, mock_kwi):
        handle = self._handle()
        assert handle.kill_when_idle(idle_threshold=3) is True
        mock_kwi.assert_called_once_with(idle_threshold=3)


# ---------------------------------------------------------------------------
# run_async
# ---------------------------------------------------------------------------


class TestRunAsync:
    @patch("db_process.runner.subprocess.Popen")
    @patch("db_process.runner.find_designbuilder", return_value=EXE)
    def test_launches_without_chain(self, mock_find, mock_popen):
        handle = run_async("Model.dsb")
        assert isinstance(handle, RunHandle)
        cmd = mock_popen.call_args[0][0]
        assert cmd == [str(EXE), "Model.dsb"]
        assert handle.process is mock_popen.return_value

    @patch("db_process.runner.subprocess.Popen")
    @patch("db_process.runner.find_designbuilder", return_value=EXE)
    def test_launches_with_chain(self, mock_find, mock_popen):
        chain = ProcessChain().export_as_xml()
        run_async("Model.dsb", chain)
        cmd = mock_popen.call_args[0][0]
        assert cmd == [str(EXE), "Model.dsb", "/process=miFExportAsXML"]

    @patch("db_process.runner.subprocess.Popen")
    @patch("db_process.runner.find_designbuilder", return_value=EXE)
    def test_explicit_exe_path_forwarded(self, mock_find, mock_popen):
        run_async("Model.dsb", exe_path="Y:/custom/DB.exe")
        mock_find.assert_called_once_with("Y:/custom/DB.exe")

    @patch("db_process.runner.subprocess.Popen")
    @patch("db_process.runner.find_designbuilder", return_value=EXE)
    def test_handle_records_start_time(self, mock_find, mock_popen):
        handle = run_async("Model.dsb")
        assert handle.start_time > 0
