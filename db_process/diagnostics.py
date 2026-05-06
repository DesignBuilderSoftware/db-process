"""
diagnostics.py
====================================
Parser for DesignBuilder diagnostic logs.

DesignBuilder writes a per-session log to::

    %LOCALAPPDATA%\\DesignBuilder\\Diagnostics\\Diagnostics_DD_MM_YYYY_HH_MM_SS.log

Logs are free-text but consistently structured:

  * Filename has the launch timestamp.
  * First line is ``***** Startup log started *****``.
  * Body contains key-value lines (``key = value`` or ``key: value``),
    Revit addin probes, "Administrator rights: True/False", and free-text
    status messages.
  * Near the top: ``DesignBuilder event log file created DD/MM/YYYY HH:MM:SS``.
  * Last line of a clean shutdown: ``DesignBuilder event log file closed
    DD/MM/YYYY HH:MM:SS``. A crashed session has no closed line.

This module exposes:

  * :class:`DiagnosticsLog` — parsed view of one log file.
  * :func:`find_logs` — list logs under the default Diagnostics folder.
  * :func:`latest_log` — newest log path or None.
  * :data:`DEFAULT_DIAGNOSTICS_DIR` — `%LOCALAPPDATA%\\DesignBuilder\\Diagnostics`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Default location
# ---------------------------------------------------------------------------

def _default_diagnostics_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "DesignBuilder" / "Diagnostics"
    # Best-effort fallback for non-Windows; tests can override via argument.
    return Path.home() / "AppData" / "Local" / "DesignBuilder" / "Diagnostics"


DEFAULT_DIAGNOSTICS_DIR: Path = _default_diagnostics_dir()


# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------

# Diagnostics_01_04_2026_14_09_50.log → datetime(2026, 4, 1, 14, 9, 50)
_FILENAME_RE = re.compile(
    r"^Diagnostics_(?P<d>\d{2})_(?P<m>\d{2})_(?P<y>\d{4})_"
    r"(?P<H>\d{2})_(?P<M>\d{2})_(?P<S>\d{2})\.log$"
)


def parse_filename_timestamp(name: str) -> Optional[datetime]:
    """Extract the launch timestamp encoded in the log filename.

    Returns None for filenames that don't match the standard
    ``Diagnostics_DD_MM_YYYY_HH_MM_SS.log`` shape (e.g. ``IDF Import_*.log``).
    """
    m = _FILENAME_RE.match(name)
    if not m:
        return None
    return datetime(
        int(m["y"]), int(m["m"]), int(m["d"]),
        int(m["H"]), int(m["M"]), int(m["S"]),
    )


# ---------------------------------------------------------------------------
# Body parsing
# ---------------------------------------------------------------------------

# DesignBuilder event log file created 01/04/2026 14:09:51
_EVENT_DATE_RE = re.compile(
    r"DesignBuilder event log file (?P<verb>created|closed) "
    r"(?P<d>\d{2})/(?P<m>\d{2})/(?P<y>\d{4}) "
    r"(?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2})"
)

# revitAddinPath = C:\ProgramData\Autodesk\Revit\Addins\2024
_REVIT_PATH_RE = re.compile(r"revitAddinPath\s*=.*Addins\\(?P<year>\d{4})")
_REVIT_NOT_INSTALLED_RE = re.compile(r"^Revit (?P<year>\d{4}) not installed", re.IGNORECASE)
_REVIT_INSTALLED_RE = re.compile(r"^Revit (?P<year>\d{4}) installed", re.IGNORECASE)

_ADMIN_RIGHTS_RE = re.compile(
    r"^Administrator rights:\s*(?P<val>True|False)\s*$"
)
_DB_ADMIN_RIGHTS_RE = re.compile(
    r"^DB AdminRights[^:]*:\s*(?P<val>True|False)\s*$"
)

# Generic "Key = Value" and "Key: Value" lines we surface as a dict.
_KEY_EQ_VALUE_RE = re.compile(r"^(?P<key>[A-Za-z][\w ]*?)\s*=\s*(?P<val>.+?)\s*$")
_KEY_COLON_VALUE_RE = re.compile(r"^(?P<key>[A-Za-z][\w ]*?)\s*:\s*(?P<val>.+?)\s*$")

# Lines we treat as "errors / failures". Word-boundary regex so identifiers
# like "GL_KHR_no_error" (an OpenGL extension) and "Set Fail Image" (a DB UI
# command name) don't trigger.
_ERROR_KEYWORD_RE = re.compile(
    r"\b(?:errors?|failed|failure|fails|exception|fatal|crash(?:ed)?)\b",
    re.IGNORECASE,
)
# Negative phrases — substrings of lines that mention error/fail keywords
# but are known DB bookkeeping/UI/extension noise.
_ERROR_NEGATIVE_KEYWORDS = (
    "checking for previous error",          # bookkeeping
    "checking for previous error complete",
    "table advancedcfderrorlist",           # table name
    "after table advancedcfderrorlist",
    "set fail image",                       # DB UI command name
    "gl_khr_no_error",                      # OpenGL extension name
    "fail safe",
    "errorlevel",
)


def _is_error_line(text: str) -> bool:
    if not _ERROR_KEYWORD_RE.search(text):
        return False
    low = text.lower()
    return not any(n in low for n in _ERROR_NEGATIVE_KEYWORDS)


# ---------------------------------------------------------------------------
# Parsed log
# ---------------------------------------------------------------------------

@dataclass
class DiagnosticsLog:
    """Parsed view of a single DesignBuilder diagnostics log file."""

    path: Optional[Path]
    file_timestamp: Optional[datetime]
    session_start: Optional[datetime] = None
    session_end: Optional[datetime] = None
    administrator_rights: Optional[bool] = None
    db_admin_rights: Optional[bool] = None
    paths: dict = field(default_factory=dict)
    revit_versions_installed: List[str] = field(default_factory=list)
    revit_versions_probed: List[str] = field(default_factory=list)
    errors: List[Tuple[int, str]] = field(default_factory=list)
    lines: List[str] = field(default_factory=list)

    # ── Derived ────────────────────────────────────────────────────────────

    @property
    def duration(self) -> Optional[timedelta]:
        """Time between the embedded created/closed timestamps, or None."""
        if self.session_start and self.session_end:
            return self.session_end - self.session_start
        return None

    @property
    def is_complete(self) -> bool:
        """True iff a 'closed' line was found — false implies a crash/abort."""
        return self.session_end is not None

    @property
    def error_count(self) -> int:
        return len(self.errors)

    # ── Parsing ────────────────────────────────────────────────────────────

    @classmethod
    def from_file(cls, path: str | Path) -> "DiagnosticsLog":
        """Read and parse a diagnostics log from disk."""
        p = Path(path)
        text = p.read_text(encoding="utf-8", errors="replace")
        ts = parse_filename_timestamp(p.name)
        return cls.from_text(text, path=p, file_timestamp=ts)

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        path: Optional[Path] = None,
        file_timestamp: Optional[datetime] = None,
    ) -> "DiagnosticsLog":
        """Parse a log from a string (used by tests)."""
        log = cls(path=path, file_timestamp=file_timestamp)
        log.lines = text.splitlines()

        for i, raw in enumerate(log.lines, start=1):
            line = raw.rstrip()

            # Session start/end timestamps (most informative single field).
            m = _EVENT_DATE_RE.search(line)
            if m:
                stamp = datetime(
                    int(m["y"]), int(m["m"]), int(m["d"]),
                    int(m["H"]), int(m["M"]), int(m["S"]),
                )
                if m["verb"] == "created":
                    log.session_start = stamp
                else:  # "closed"
                    log.session_end = stamp
                continue

            # Admin-rights flags.
            m = _ADMIN_RIGHTS_RE.match(line)
            if m:
                log.administrator_rights = (m["val"] == "True")
                continue
            m = _DB_ADMIN_RIGHTS_RE.match(line)
            if m:
                log.db_admin_rights = (m["val"] == "True")
                continue

            # Revit probes.
            m = _REVIT_PATH_RE.search(line)
            if m:
                year = m["year"]
                if year not in log.revit_versions_probed:
                    log.revit_versions_probed.append(year)
            m = _REVIT_NOT_INSTALLED_RE.match(line)
            if m:
                # Already in 'probed'; do NOT add to 'installed'.
                continue
            m = _REVIT_INSTALLED_RE.match(line)
            if m:
                y = m["year"]
                if y not in log.revit_versions_installed:
                    log.revit_versions_installed.append(y)
                continue

            # Errors.
            if _is_error_line(line):
                log.errors.append((i, line))

            # Generic key = value (record once; later sees overwrite).
            m = _KEY_EQ_VALUE_RE.match(line)
            if m:
                log.paths[m["key"].strip()] = m["val"].strip()
                continue
            m = _KEY_COLON_VALUE_RE.match(line)
            if m:
                key = m["key"].strip()
                # Don't capture event-log-file lines (already handled above).
                if key.startswith("DesignBuilder event log file"):
                    continue
                log.paths[key] = m["val"].strip()

        return log

    # ── Friendly summary ──────────────────────────────────────────────────

    def summary(self) -> str:
        """Single-paragraph human-readable summary of this log."""
        bits = []
        bits.append(
            f"path={self.path.name if self.path else '<inline>'}"
        )
        if self.file_timestamp:
            bits.append(f"launched_at={self.file_timestamp.isoformat()}")
        if self.session_start:
            bits.append(f"started={self.session_start.isoformat()}")
        if self.session_end:
            bits.append(f"closed={self.session_end.isoformat()}")
        else:
            bits.append("closed=NO (incomplete/crashed)")
        if self.duration is not None:
            secs = int(self.duration.total_seconds())
            bits.append(f"duration={secs}s")
        if self.administrator_rights is not None:
            bits.append(f"admin={self.administrator_rights}")
        if self.revit_versions_installed:
            bits.append(f"revit={','.join(self.revit_versions_installed)}")
        bits.append(f"errors={self.error_count}")
        return "  ".join(bits)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def find_logs(
    directory: str | Path | None = None,
    *,
    pattern: str = "Diagnostics_*.log",
) -> List[Path]:
    """Return all diagnostic log paths under ``directory``, newest first.

    Defaults to ``DEFAULT_DIAGNOSTICS_DIR``. Sorted by file mtime
    descending so the first element is the newest.
    """
    d = Path(directory) if directory else DEFAULT_DIAGNOSTICS_DIR
    if not d.exists():
        return []
    files = list(d.glob(pattern))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def latest_log(directory: str | Path | None = None) -> Optional[Path]:
    """Return the newest diagnostic log path, or None if the folder is empty/missing."""
    files = find_logs(directory)
    return files[0] if files else None
