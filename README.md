# db-process

Python interface to DesignBuilder's command-line driver — typed `/process=` commands,
subprocess execution, process discovery, and diagnostics-log parsing.

DesignBuilder is a Windows GUI app, but it exposes a `/process=` argument
that runs a sequence of commands non-interactively and exits. `db-process`
wraps that surface in real Python: dataclass commands instead of stringly-typed
flags, a `ProcessChain` builder, blocking and non-blocking runners, helpers
to find/kill the process, and a parser for the rolling diagnostics logs
DesignBuilder writes under `%LOCALAPPDATA%`.

## Install

```bash
pip install db-process
# or, from the cloned repo:
pip install -e .[dev]
```

Requires Python 3.10+ and `psutil`. DesignBuilder itself only runs on Windows;
on other platforms, the package imports fine but `run()` and the process
helpers will raise `FileNotFoundError`.

## Quick start

### Python — run a model with a chain of commands

```python
from db_process import ProcessChain, Screen, run

chain = (
    ProcessChain()
    .use_sim_manager()
    .switch_screen(Screen.SIMULATION)
    .sim_start_date(1, 1)
    .sim_end_date(31, 12)
    .change_attribute("OccupancyValue", 0.5)
    .run()
)

result = run("models/office.dsb", chain, timeout=600)
print(result.success, result.duration_seconds)
```

### Python — convenience factories for common runs

```python
from db_process import eplus_simulation, run

# A pre-built ProcessChain for "open model, run EnergyPlus, close".
result = run("models/office.dsb", eplus_simulation())
```

Other factories: `sbem_calculation`, `export_xml`, `heating_and_cooling_design`,
`daylighting`, `cfd_simulation`.

### Python — non-blocking with idle-detection kill

```python
from db_process import run_async

handle = run_async("models/office.dsb")
# Block until DesignBuilder finishes its work and CPU drops, then kill it.
handle.kill_when_idle(idle_threshold=10, cpu_threshold=0.1)
```

`kill_when_idle` is the workaround for runs where DesignBuilder finishes the
calculation but doesn't exit — common with the GUI Sim Manager path.

### CLI

```bash
db-process status              # is DesignBuilder running? show pid + exe path
db-process open                # launch DesignBuilder
db-process open path/to.dsb    # launch with a model
db-process close               # kill any running DesignBuilder
db-process restart [model]     # close + open (with a 1.5 s settle)

db-process diag list           # list recent diagnostic logs (newest first)
db-process diag latest         # print a one-paragraph summary of the newest log
db-process diag latest --errors   # also list every error line found
db-process diag summary <path>    # summarise a specific log
```

`db-process` is the entry point installed by the package; you can also run it
as `python -m db_process`.

## Public API

```python
from db_process import (
    # Executable discovery
    find_designbuilder,                          # () -> Path

    # Process status
    is_running, find_process, status,            # status() -> ProcessStatus
    kill_process, kill_when_idle,
    ProcessStatus,                               # is_running, pid, exe_path

    # Run
    run, run_async, RunHandle, RunResult,

    # Command model
    ProcessChain, Screen,
    SwitchScreen, RunCalculation, TabChange,
    SimStartDate, SimEndDate, ChangeAttributeValue,
    ExternalCommand, ImportModelData, ImportLibraryData,
    ExportAsXML, UseSimManager, NoClose,

    # Convenience factories
    eplus_simulation, sbem_calculation, export_xml,
    heating_and_cooling_design, daylighting, cfd_simulation,

    # Diagnostics logs
    DiagnosticsLog, find_logs, latest_log,
    parse_filename_timestamp, DEFAULT_DIAGNOSTICS_DIR,
)
```

### Executable discovery

`find_designbuilder(exe_path=None)` resolves DesignBuilder.exe in this order:

1. The explicit `exe_path` argument, if given.
2. `DESIGNBUILDER_EXE` environment variable.
3. `C:\Program Files (x86)\DesignBuilder\DesignBuilder.exe`,
   then `C:\Program Files\DesignBuilder\DesignBuilder.exe`.
4. The system `PATH` (`shutil.which("DesignBuilder")`).

Raises `FileNotFoundError` with a hint to set `DESIGNBUILDER_EXE` if none match.

### Process status

`status()` is a one-shot snapshot:

```python
from db_process import status

s = status()
# ProcessStatus(is_running=True, pid=12345, exe_path='C:\\...\\DesignBuilder.exe')
if not s.is_running and s.exe_path:
    # Discovered but not running — safe to launch.
    ...
```

`exe_path` is populated regardless of whether the process is running, so
callers can decide whether to launch without a second `find_designbuilder`
call.

### `ProcessChain` — building a `/process=` argument

`ProcessChain` is a fluent builder for the `/process=` command sequence
documented in DesignBuilder Help. Example output of `chain.to_string()`:

```
/process=UseSimManager, miGSS, SimStartDate 1 1, SimEndDate 31 12,
         ChangeAttributeValue OccupancyValue 0.5, miTUpdate
```

Every command is also exposed as a plain dataclass, so you can construct
chains without the builder when that's clearer.

### Diagnostics logs

DesignBuilder writes a per-session diagnostics log to
`%LOCALAPPDATA%\DesignBuilder\Diagnostics\` named like
`DesignBuilder_diagnostic_2026-04-23_15-12-08.txt`. `DiagnosticsLog`
parses one of those files into a structured object:

```python
from db_process import latest_log, DiagnosticsLog

log = DiagnosticsLog.from_file(latest_log())
print(log.summary())
print(log.is_complete, log.duration, log.error_count)
for line_no, text in log.errors:
    print(f"L{line_no}: {text}")
```

Error detection uses word-boundary matching (`error`, `failed`, `exception`,
`fatal`, `crash`) plus a small negative list to suppress known benign markers
(e.g. the `GL_KHR_no_error` OpenGL extension).

## Compatibility

- **DesignBuilder**: any version that supports the `/process=` argument.
  Tested against the v25.1 / v26.1 lines.
- **Python**: 3.10+.
- **OS**: Windows for live runs. The command model and diagnostics parser
  are pure Python and import on any platform — useful for unit tests on
  Linux CI.

## Development

```bash
pip install -e .[dev]
pytest                 # 86 tests, no DesignBuilder required
ruff check .
```

Tests are split by area:

| File | Covers |
| --- | --- |
| `test_commands.py`     | `ProcessChain` building + every command's `to_string()` |
| `test_executable.py`   | `find_designbuilder` resolution order |
| `test_status.py`       | `status` / `ProcessStatus` |
| `test_diagnostics.py`  | log parsing, error detection, filename timestamps |
| `test_cli.py`          | CLI argparse wiring (mocked subprocess) |

## License

MIT — see [LICENSE](LICENSE).
