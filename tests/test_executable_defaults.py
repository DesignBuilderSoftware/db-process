"""Additional tests for db_process.executable — default install path
resolution and precedence rules not covered by test_executable.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from db_process.executable import ENV_VAR, find_designbuilder


class TestDefaultInstallPaths:
    def test_first_existing_default_path_used(self, tmp_path, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        exe = tmp_path / "DesignBuilder.exe"
        exe.touch()
        with patch(
            "db_process.executable.DEFAULT_INSTALL_PATHS",
            [tmp_path / "missing.exe", exe],
        ):
            assert find_designbuilder() == exe

    def test_default_path_order_respected(self, tmp_path, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        first = tmp_path / "first" / "DesignBuilder.exe"
        second = tmp_path / "second" / "DesignBuilder.exe"
        for p in (first, second):
            p.parent.mkdir()
            p.touch()
        with patch(
            "db_process.executable.DEFAULT_INSTALL_PATHS", [first, second]
        ):
            assert find_designbuilder() == first


class TestPrecedence:
    def test_explicit_arg_beats_env_var(self, tmp_path, monkeypatch):
        explicit = tmp_path / "explicit.exe"
        env_exe = tmp_path / "env.exe"
        explicit.touch()
        env_exe.touch()
        monkeypatch.setenv(ENV_VAR, str(env_exe))
        assert find_designbuilder(explicit) == explicit

    def test_env_var_beats_default_paths(self, tmp_path, monkeypatch):
        env_exe = tmp_path / "env.exe"
        default_exe = tmp_path / "default.exe"
        env_exe.touch()
        default_exe.touch()
        monkeypatch.setenv(ENV_VAR, str(env_exe))
        with patch(
            "db_process.executable.DEFAULT_INSTALL_PATHS", [default_exe]
        ):
            assert find_designbuilder() == env_exe

    def test_default_paths_beat_which(self, tmp_path, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        default_exe = tmp_path / "DesignBuilder.exe"
        default_exe.touch()
        with patch(
            "db_process.executable.DEFAULT_INSTALL_PATHS", [default_exe]
        ), patch("shutil.which") as mock_which:
            assert find_designbuilder() == default_exe
            mock_which.assert_not_called()

    def test_explicit_path_accepts_string(self, tmp_path):
        exe = tmp_path / "DesignBuilder.exe"
        exe.touch()
        result = find_designbuilder(str(exe))
        assert result == Path(exe)


class TestDirectoryAndEmptyValues:
    def test_explicit_directory_rejected(self, tmp_path):
        # A directory is not a file, so it must be rejected.
        with pytest.raises(FileNotFoundError, match="not found at"):
            find_designbuilder(tmp_path)

    def test_env_var_directory_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv(ENV_VAR, str(tmp_path))
        with pytest.raises(FileNotFoundError, match=ENV_VAR):
            find_designbuilder()

    def test_empty_env_var_falls_through_to_defaults(self, tmp_path, monkeypatch):
        # An empty env var is treated as unset, not as an error.
        monkeypatch.setenv(ENV_VAR, "")
        exe = tmp_path / "DesignBuilder.exe"
        exe.touch()
        with patch("db_process.executable.DEFAULT_INSTALL_PATHS", [exe]):
            assert find_designbuilder() == exe
