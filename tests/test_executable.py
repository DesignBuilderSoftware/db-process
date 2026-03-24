"""Tests for db_process.executable module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from db_process.executable import ENV_VAR, find_designbuilder


class TestFindDesignBuilder:
    def test_explicit_path_valid(self, tmp_path):
        exe = tmp_path / "DesignBuilder.exe"
        exe.touch()
        result = find_designbuilder(exe)
        assert result == exe

    def test_explicit_path_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="not found at"):
            find_designbuilder(tmp_path / "nonexistent.exe")

    def test_env_var_valid(self, tmp_path, monkeypatch):
        exe = tmp_path / "DesignBuilder.exe"
        exe.touch()
        monkeypatch.setenv(ENV_VAR, str(exe))
        result = find_designbuilder()
        assert result == exe

    def test_env_var_invalid(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "/nonexistent/DesignBuilder.exe")
        with pytest.raises(FileNotFoundError, match=ENV_VAR):
            find_designbuilder()

    @patch("db_process.executable.DEFAULT_INSTALL_PATHS", [])
    @patch("shutil.which", return_value=None)
    def test_not_found_anywhere(self, mock_which, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        with pytest.raises(FileNotFoundError, match="Could not find"):
            find_designbuilder()

    @patch("db_process.executable.DEFAULT_INSTALL_PATHS", [])
    @patch("shutil.which", return_value="/usr/bin/DesignBuilder")
    def test_which_fallback(self, mock_which, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        result = find_designbuilder()
        assert result == Path("/usr/bin/DesignBuilder")
