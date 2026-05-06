"""Allow `python -m db_process [subcommand]`."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
