"""
db-process
====================================
Python interface to DesignBuilder command line processing.

This package provides:

- **Executable discovery** — find DesignBuilder.exe across env vars,
  default install paths, and the system PATH.
- **Typed command model** — dataclasses for every ``/process=`` command
  documented in DesignBuilder Help, with a fluent builder API.
- **Subprocess execution** — blocking and non-blocking modes, timeout
  handling, and idle-detection termination.
"""

from db_process.commands import (
    ChangeAttributeValue,
    ExportAsXML,
    ExternalCommand,
    ImportLibraryData,
    ImportModelData,
    NoClose,
    ProcessChain,
    RunCalculation,
    Screen,
    SimEndDate,
    SimStartDate,
    SwitchScreen,
    TabChange,
    UseSimManager,
    # Convenience factories
    cfd_simulation,
    daylighting,
    eplus_simulation,
    export_xml,
    heating_and_cooling_design,
    sbem_calculation,
)
from db_process.executable import find_designbuilder
from db_process.runner import (
    RunHandle,
    RunResult,
    find_process,
    kill_process,
    kill_when_idle,
    run,
    run_async,
)

__all__ = [
    # Executable
    "find_designbuilder",
    # Commands
    "ChangeAttributeValue",
    "ExportAsXML",
    "ExternalCommand",
    "ImportLibraryData",
    "ImportModelData",
    "NoClose",
    "ProcessChain",
    "RunCalculation",
    "Screen",
    "SimEndDate",
    "SimStartDate",
    "SwitchScreen",
    "TabChange",
    "UseSimManager",
    # Convenience factories
    "cfd_simulation",
    "daylighting",
    "eplus_simulation",
    "export_xml",
    "heating_and_cooling_design",
    "sbem_calculation",
    # Runner
    "RunHandle",
    "RunResult",
    "find_process",
    "kill_process",
    "kill_when_idle",
    "run",
    "run_async",
]
