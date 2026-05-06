"""db-process CLI.

Small command-line wrapper over the existing process-control primitives:

    db-process status                  # is DB running? where's the exe?
    db-process close                   # kill any running DesignBuilder
    db-process open [MODEL.dsb]        # launch DB; opens MODEL if given
    db-process restart [MODEL.dsb]     # close + open

Equivalent to:

    python -m db_process <subcommand> [args]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from .diagnostics import DiagnosticsLog, find_logs, latest_log
from .executable import find_designbuilder
from .runner import find_process, is_running, kill_process, run_async, status as proc_status


def cmd_status(args: argparse.Namespace) -> int:
    s = proc_status()
    print(f"DesignBuilder exe     : {s.exe_path or '<not found>'}")
    if not s.is_running:
        print("DesignBuilder process : not running")
        return 1
    print(f"DesignBuilder process : pid={s.pid}")
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    if kill_process():
        print("Closed running DesignBuilder.")
        return 0
    print("No DesignBuilder process to close.")
    return 1


def cmd_open(args: argparse.Namespace) -> int:
    exe = find_designbuilder()
    if args.model is not None:
        print(f"Opening {args.model} with {exe} ...")
        run_async(str(args.model))
    else:
        print(f"Launching {exe} (no model)...")
        subprocess.Popen([str(exe)])
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    if kill_process():
        print(f"Closed existing process; settling for {args.settle}s ...")
        time.sleep(args.settle)
    return cmd_open(args)


def cmd_diag_list(args: argparse.Namespace) -> int:
    paths = find_logs(args.dir)
    if not paths:
        print("No diagnostic logs found.")
        return 1
    for p in paths[: args.limit]:
        size_kb = p.stat().st_size // 1024
        print(f"{p.stat().st_mtime:>13.0f}  {size_kb:>5} KB  {p.name}")
    return 0


def cmd_diag_latest(args: argparse.Namespace) -> int:
    path = latest_log(args.dir)
    if path is None:
        print("No diagnostic logs found.")
        return 1
    log = DiagnosticsLog.from_file(path)
    print(log.summary())
    if args.errors and log.errors:
        print("\nError lines:")
        for line_no, text in log.errors:
            print(f"  {line_no:5}: {text}")
    return 0


def cmd_diag_summary(args: argparse.Namespace) -> int:
    log = DiagnosticsLog.from_file(args.path)
    print(log.summary())
    if args.errors and log.errors:
        print("\nError lines:")
        for line_no, text in log.errors:
            print(f"  {line_no:5}: {text}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="db-process",
                                description="DesignBuilder process control")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show DesignBuilder exe path and PID").set_defaults(func=cmd_status)
    sub.add_parser("close", help="Kill any running DesignBuilder").set_defaults(func=cmd_close)

    p_open = sub.add_parser("open", help="Launch DesignBuilder")
    p_open.add_argument("model", nargs="?", type=Path, default=None,
                        help="Optional .dsb model to open")
    p_open.set_defaults(func=cmd_open)

    p_restart = sub.add_parser("restart", help="Close then open DesignBuilder")
    p_restart.add_argument("model", nargs="?", type=Path, default=None,
                           help="Optional .dsb model to open after restart")
    p_restart.add_argument("--settle", type=float, default=1.5,
                           help="Seconds to wait between close and open (default 1.5)")
    p_restart.set_defaults(func=cmd_restart)

    # ── diag — diagnostic-log inspection ──────────────────────────────────
    p_diag = sub.add_parser("diag", help="Inspect DesignBuilder diagnostic logs")
    diag_sub = p_diag.add_subparsers(dest="diag_cmd", required=True)

    p_diag_list = diag_sub.add_parser("list", help="List recent diagnostic logs")
    p_diag_list.add_argument("--dir", type=Path, default=None,
                             help="Diagnostics folder (default: LOCALAPPDATA/DesignBuilder/Diagnostics)")
    p_diag_list.add_argument("-n", "--limit", type=int, default=10,
                             help="Number of logs to show (default 10)")
    p_diag_list.set_defaults(func=cmd_diag_list)

    p_diag_latest = diag_sub.add_parser("latest", help="Summarise the newest log")
    p_diag_latest.add_argument("--dir", type=Path, default=None,
                               help="Diagnostics folder")
    p_diag_latest.add_argument("--errors", action="store_true",
                               help="Also print every error line found")
    p_diag_latest.set_defaults(func=cmd_diag_latest)

    p_diag_sum = diag_sub.add_parser("summary", help="Summarise a specific log")
    p_diag_sum.add_argument("path", type=Path, help="Path to a diagnostic log")
    p_diag_sum.add_argument("--errors", action="store_true",
                            help="Also print every error line found")
    p_diag_sum.set_defaults(func=cmd_diag_summary)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
