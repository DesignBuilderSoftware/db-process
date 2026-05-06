"""
runner.py
====================================
Run DesignBuilder as a subprocess with support for blocking and
non-blocking execution, timeouts, and idle-detection termination.

This module unifies the execution patterns from ``designbuilder_schema``
(blocking with error capture) and ``db-batch`` (Popen + idle monitoring).
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import psutil

from db_process.commands import ProcessChain
from db_process.executable import find_designbuilder


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    """Outcome of a DesignBuilder process execution."""

    success: bool
    """Whether the process completed without error."""

    returncode: Optional[int] = None
    """Process return code (None if killed or not yet finished)."""

    stdout: str = ""
    """Captured stdout (blocking mode only)."""

    stderr: str = ""
    """Captured stderr (blocking mode only)."""

    timed_out: bool = False
    """True if the process was killed due to timeout."""

    killed_idle: bool = False
    """True if the process was killed by idle detection."""

    duration_seconds: Optional[float] = None
    """Wall-clock duration of the run in seconds."""


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------

DESIGNBUILDER_PROCESS_NAME = "DesignBuilder.exe"


def find_process(name: str = DESIGNBUILDER_PROCESS_NAME) -> Optional[psutil.Process]:
    """Find a running process by name.

    Returns the first matching process, or None.
    """
    for p in psutil.process_iter(["name"]):
        try:
            if p.info["name"] == name:
                return p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def is_running(name: str = DESIGNBUILDER_PROCESS_NAME) -> bool:
    """Return True iff a DesignBuilder process is currently running."""
    return find_process(name) is not None


@dataclass(frozen=True)
class ProcessStatus:
    """Snapshot of DesignBuilder's running state."""
    is_running: bool
    pid: Optional[int]
    exe_path: Optional[str]


def status(name: str = DESIGNBUILDER_PROCESS_NAME) -> ProcessStatus:
    """Return a structured snapshot: running/pid/exe path.

    The exe_path field is the discovered DesignBuilder.exe location (via
    ``find_designbuilder``); it is populated regardless of whether the
    process is currently running, so callers can decide whether to launch.
    """
    proc = find_process(name)
    try:
        exe = str(find_designbuilder())
    except FileNotFoundError:
        exe = None
    return ProcessStatus(
        is_running=proc is not None,
        pid=proc.pid if proc else None,
        exe_path=exe,
    )


def kill_process(name: str = DESIGNBUILDER_PROCESS_NAME) -> bool:
    """Terminate a DesignBuilder process forcefully.

    Returns True if a process was found and killed, False otherwise.
    """
    proc = find_process(name)
    if proc is None:
        return False

    proc.kill()
    proc.wait(timeout=5)
    return True


def kill_when_idle(
    name: str = DESIGNBUILDER_PROCESS_NAME,
    *,
    idle_threshold: float = 10,
    check_interval: float = 0.5,
    startup_period: float = 20,
    cpu_threshold: float = 0.1,
) -> bool:
    """Monitor a process and kill it once CPU usage stays below threshold.

    The function blocks until the process is killed or exits on its own.

    Parameters
    ----------
    name : str
        Process name to monitor.
    idle_threshold : float
        Seconds the process must be idle before termination.
    check_interval : float
        Polling interval in seconds.
    startup_period : float
        Grace period before idle detection begins.
    cpu_threshold : float
        CPU percentage below which the process is considered idle.

    Returns
    -------
    bool
        True if the process was killed due to idle, False if it
        exited on its own or was not found.
    """
    proc = find_process(name)
    if proc is None:
        return False

    idle_time = 0.0
    has_been_active = False

    try:
        if startup_period > 0:
            time.sleep(startup_period)

        while proc.is_running():
            cpu = proc.cpu_percent(interval=0.1)

            if cpu >= cpu_threshold:
                has_been_active = True
                idle_time = 0.0
            elif has_been_active:
                idle_time += check_interval
                if idle_time >= idle_threshold:
                    proc.kill()
                    proc.wait(timeout=5)
                    return True

            time.sleep(check_interval)

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    return False


# ---------------------------------------------------------------------------
# Blocking execution
# ---------------------------------------------------------------------------

def run(
    model_path: Union[str, Path],
    process_chain: Optional[ProcessChain] = None,
    *,
    exe_path: Optional[Union[str, Path]] = None,
    timeout: Optional[int] = None,
) -> RunResult:
    """Run DesignBuilder in blocking mode and wait for completion.

    Parameters
    ----------
    model_path : str or Path
        Path to the .dsb model file.
    process_chain : ProcessChain, optional
        Commands to execute.  When None, DesignBuilder opens the file
        without processing (useful for XML import).
    exe_path : str or Path, optional
        Explicit path to DesignBuilder.exe.
    timeout : int, optional
        Maximum seconds to wait.  None means wait indefinitely.

    Returns
    -------
    RunResult
        Outcome of the execution.
    """
    exe = find_designbuilder(exe_path)
    model = Path(model_path)

    cmd = [str(exe), str(model)]
    if process_chain is not None:
        cmd.append(process_chain.to_string())

    t0 = time.monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        duration = time.monotonic() - t0
        return RunResult(
            success=result.returncode == 0,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=duration,
        )
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - t0
        kill_process()
        return RunResult(
            success=False,
            timed_out=True,
            duration_seconds=duration,
        )


# ---------------------------------------------------------------------------
# Non-blocking execution
# ---------------------------------------------------------------------------

@dataclass
class RunHandle:
    """Handle for a non-blocking DesignBuilder process.

    Use :meth:`wait`, :meth:`kill`, or :meth:`kill_when_idle` to
    manage the process after launch.
    """

    process: subprocess.Popen
    """The underlying Popen object."""

    start_time: float = field(default_factory=time.monotonic)
    """Monotonic timestamp when the process was launched."""

    def is_running(self) -> bool:
        """Check if the process is still running."""
        return self.process.poll() is None

    def wait(self, timeout: Optional[int] = None) -> RunResult:
        """Block until the process finishes or timeout expires."""
        try:
            self.process.wait(timeout=timeout)
            duration = time.monotonic() - self.start_time
            return RunResult(
                success=self.process.returncode == 0,
                returncode=self.process.returncode,
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - self.start_time
            kill_process()
            return RunResult(
                success=False,
                timed_out=True,
                duration_seconds=duration,
            )

    def kill(self) -> None:
        """Terminate the process immediately."""
        kill_process()

    def kill_when_idle(self, **kwargs) -> bool:
        """Monitor and kill the process when it becomes idle.

        Accepts the same keyword arguments as :func:`kill_when_idle`.
        This call blocks until the process is killed or exits.
        """
        return kill_when_idle(**kwargs)


def run_async(
    model_path: Union[str, Path],
    process_chain: Optional[ProcessChain] = None,
    *,
    exe_path: Optional[Union[str, Path]] = None,
) -> RunHandle:
    """Launch DesignBuilder in non-blocking mode.

    Returns a :class:`RunHandle` that can be used to wait for
    completion, kill the process, or monitor for idle termination.

    Parameters
    ----------
    model_path : str or Path
        Path to the .dsb model file.
    process_chain : ProcessChain, optional
        Commands to execute.
    exe_path : str or Path, optional
        Explicit path to DesignBuilder.exe.

    Returns
    -------
    RunHandle
        Handle for the launched process.
    """
    exe = find_designbuilder(exe_path)
    model = Path(model_path)

    cmd = [str(exe), str(model)]
    if process_chain is not None:
        cmd.append(process_chain.to_string())

    proc = subprocess.Popen(cmd)
    return RunHandle(process=proc)
