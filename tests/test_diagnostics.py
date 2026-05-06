"""Tests for db_process.diagnostics — log parsing and discovery."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from db_process.diagnostics import (
    DiagnosticsLog,
    find_logs,
    latest_log,
    parse_filename_timestamp,
)


# ---------------------------------------------------------------------------
# Filename timestamp parsing
# ---------------------------------------------------------------------------

class TestParseFilenameTimestamp:
    def test_canonical_format(self):
        ts = parse_filename_timestamp("Diagnostics_01_04_2026_14_09_50.log")
        assert ts == datetime(2026, 4, 1, 14, 9, 50)

    def test_zero_padded_components(self):
        ts = parse_filename_timestamp("Diagnostics_05_01_2026_07_05_03.log")
        assert ts == datetime(2026, 1, 5, 7, 5, 3)

    @pytest.mark.parametrize("name", [
        "",
        "random.log",
        "Diagnostics.log",
        "IDF Import_2026_04_10_12_14_41.log",   # different prefix
        "Diagnostics_1_04_2026_14_09_50.log",   # missing zero-pad on day
        "Diagnostics_01-04-2026_14-09-50.log",  # wrong separators
    ])
    def test_non_matching_returns_none(self, name):
        assert parse_filename_timestamp(name) is None


# ---------------------------------------------------------------------------
# Body parsing
# ---------------------------------------------------------------------------

# Minimum-viable log that exercises every field the parser populates.
SAMPLE_LOG = """\
***** Startup log started *****
Reading registry values
All user application folder: C:\\ProgramData\\
revitAddinPath = C:\\ProgramData\\Autodesk\\Revit\\Addins\\2024
Revit 2024 not installed
revitAddinPath = C:\\ProgramData\\Autodesk\\Revit\\Addins\\2025
Revit 2025 installed
Show splash screen
DB AdminRights (as opposed to administrator rights for pc): False
MyDocuments folder: C:\\Users\\model\\Documents\\
Temporary folder: C:\\Users\\model\\AppData\\Local\\Temp\\
DesignBuilder event log file created 01/04/2026 14:09:51
Administrator rights: False
Some intermediate logging here
EnergyPlus simulation failed: out of memory
Before writing registry data...
DesignBuilder event log file closed 01/04/2026 16:05:52
"""


class TestDiagnosticsLogFromText:
    def test_session_start_end_and_duration(self):
        log = DiagnosticsLog.from_text(SAMPLE_LOG)
        assert log.session_start == datetime(2026, 4, 1, 14, 9, 51)
        assert log.session_end == datetime(2026, 4, 1, 16, 5, 52)
        assert log.duration == timedelta(seconds=6961)
        assert log.is_complete is True

    def test_admin_rights_flags(self):
        log = DiagnosticsLog.from_text(SAMPLE_LOG)
        assert log.administrator_rights is False
        assert log.db_admin_rights is False

    def test_revit_versions(self):
        log = DiagnosticsLog.from_text(SAMPLE_LOG)
        # Both are "probed" because we saw their paths
        assert "2024" in log.revit_versions_probed
        assert "2025" in log.revit_versions_probed
        # Only 2025 is installed
        assert log.revit_versions_installed == ["2025"]

    def test_paths_dict_populated(self):
        log = DiagnosticsLog.from_text(SAMPLE_LOG)
        # Values keep DesignBuilder's literal trailing backslashes;
        # Path() consumers normalise on use.
        assert log.paths["MyDocuments folder"].startswith(r"C:\Users\model\Documents")
        assert log.paths["Temporary folder"].startswith(r"C:\Users\model\AppData\Local\Temp")

    def test_errors_are_collected(self):
        log = DiagnosticsLog.from_text(SAMPLE_LOG)
        assert log.error_count == 1
        line_no, text = log.errors[0]
        assert "EnergyPlus simulation failed" in text

    def test_bookkeeping_is_not_an_error(self):
        log = DiagnosticsLog.from_text(
            SAMPLE_LOG + "checking for previous error\n"
                       + "checking for previous error Complete: >>General<<\n"
        )
        # Still just the original 1 real error.
        assert log.error_count == 1

    def test_incomplete_session(self):
        # No "closed" line — DB crashed.
        partial = "\n".join(SAMPLE_LOG.splitlines()[:-2])
        log = DiagnosticsLog.from_text(partial)
        assert log.session_start is not None
        assert log.session_end is None
        assert log.duration is None
        assert log.is_complete is False

    def test_summary_smoke(self):
        log = DiagnosticsLog.from_text(SAMPLE_LOG)
        s = log.summary()
        assert "started=2026-04-01T14:09:51" in s
        assert "errors=1" in s

    def test_lines_preserved(self):
        log = DiagnosticsLog.from_text(SAMPLE_LOG)
        assert len(log.lines) == len(SAMPLE_LOG.splitlines())


# ---------------------------------------------------------------------------
# from_file
# ---------------------------------------------------------------------------

class TestDiagnosticsLogFromFile:
    def test_round_trip(self, tmp_path: Path):
        f = tmp_path / "Diagnostics_01_04_2026_14_09_50.log"
        f.write_text(SAMPLE_LOG, encoding="utf-8")
        log = DiagnosticsLog.from_file(f)
        assert log.path == f
        assert log.file_timestamp == datetime(2026, 4, 1, 14, 9, 50)
        assert log.session_start == datetime(2026, 4, 1, 14, 9, 51)
        assert log.error_count == 1


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

class TestFindLogs:
    def test_empty_directory_returns_empty_list(self, tmp_path: Path):
        assert find_logs(tmp_path) == []

    def test_missing_directory_returns_empty_list(self, tmp_path: Path):
        assert find_logs(tmp_path / "does-not-exist") == []

    def test_lists_only_diagnostics_files(self, tmp_path: Path):
        (tmp_path / "Diagnostics_01_04_2026_10_00_00.log").write_text("a")
        (tmp_path / "Diagnostics_02_04_2026_11_00_00.log").write_text("b")
        (tmp_path / "IDF Import_2026_04_10_12_14_41.log").write_text("c")
        (tmp_path / "random.txt").write_text("d")
        paths = find_logs(tmp_path)
        names = sorted(p.name for p in paths)
        assert names == [
            "Diagnostics_01_04_2026_10_00_00.log",
            "Diagnostics_02_04_2026_11_00_00.log",
        ]

    def test_sorted_newest_first_by_mtime(self, tmp_path: Path):
        import time
        a = tmp_path / "Diagnostics_01_04_2026_10_00_00.log"
        a.write_text("a")
        time.sleep(0.05)
        b = tmp_path / "Diagnostics_02_04_2026_11_00_00.log"
        b.write_text("b")
        paths = find_logs(tmp_path)
        assert paths[0] == b
        assert paths[1] == a


class TestLatestLog:
    def test_returns_none_when_empty(self, tmp_path: Path):
        assert latest_log(tmp_path) is None

    def test_returns_newest(self, tmp_path: Path):
        import time
        a = tmp_path / "Diagnostics_01_04_2026_10_00_00.log"
        a.write_text("a")
        time.sleep(0.05)
        b = tmp_path / "Diagnostics_02_04_2026_11_00_00.log"
        b.write_text("b")
        assert latest_log(tmp_path) == b
