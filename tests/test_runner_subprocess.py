"""Integration tests for db_process.runner using real subprocesses.

The mock-based tests in test_runner.py verify call wiring; these tests
exercise the actual subprocess machinery by substituting the Python
interpreter for DesignBuilder.exe via the ``exe_path`` argument.

``kill_process`` is patched in timeout tests so nothing on the host
machine (e.g. a genuinely running DesignBuilder) is ever touched.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

from db_process.runner import RunHandle, run, run_async


class TestRunRealSubprocess:
    def test_success(self):
        # `python -V` exits 0 and prints the version to stdout.
        result = run("-V", exe_path=sys.executable)
        assert result.success is True
        assert result.returncode == 0
        assert "Python" in result.stdout
        assert result.timed_out is False
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0

    def test_failure_nonzero_exit(self, tmp_path):
        script = tmp_path / "fail.py"
        script.write_text("import sys; sys.stderr.write('boom'); sys.exit(3)")
        result = run(script, exe_path=sys.executable)
        assert result.success is False
        assert result.returncode == 3
        assert "boom" in result.stderr

    @patch("db_process.runner.kill_process")
    def test_timeout_real_process(self, mock_kill, tmp_path):
        script = tmp_path / "sleep.py"
        script.write_text("import time; time.sleep(30)")
        result = run(script, exe_path=sys.executable, timeout=1)
        assert result.success is False
        assert result.timed_out is True
        assert result.returncode is None
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 1
        mock_kill.assert_called_once()


class TestRunAsyncRealSubprocess:
    def test_launch_and_wait(self, tmp_path):
        script = tmp_path / "ok.py"
        script.write_text("print('hello from fake DB')")
        handle = run_async(script, exe_path=sys.executable)
        assert isinstance(handle, RunHandle)
        result = handle.wait(timeout=30)
        assert result.success is True
        assert result.returncode == 0
        assert handle.is_running() is False

    def test_failure_returncode_propagates(self, tmp_path):
        script = tmp_path / "fail.py"
        script.write_text("raise SystemExit(7)")
        handle = run_async(script, exe_path=sys.executable)
        result = handle.wait(timeout=30)
        assert result.success is False
        assert result.returncode == 7

    @patch("db_process.runner.kill_process")
    def test_wait_timeout_on_real_process(self, mock_kill, tmp_path):
        script = tmp_path / "sleep.py"
        script.write_text("import time; time.sleep(30)")
        handle = run_async(script, exe_path=sys.executable)
        try:
            assert handle.is_running() is True
            result = handle.wait(timeout=1)
            assert result.success is False
            assert result.timed_out is True
            mock_kill.assert_called_once()
        finally:
            # kill_process was mocked, so terminate the real child ourselves.
            handle.process.kill()
            handle.process.wait(timeout=10)
