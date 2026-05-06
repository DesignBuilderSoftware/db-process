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

from .executable import find_designbuilder
from .runner import find_process, kill_process, run_async


def cmd_status(args: argparse.Namespace) -> int:
    proc = find_process()
    try:
        exe = find_designbuilder()
    except FileNotFoundError as e:
        exe = f"<not found: {e}>"
    print(f"DesignBuilder exe : {exe}")
    if proc is None:
        print("DesignBuilder process : not running")
        return 1
    print(f"DesignBuilder process : pid={proc.pid}")
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

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
