"""
executable.py
====================================
Locate and validate the DesignBuilder executable.

Resolution order:
    1. Explicit path argument
    2. DESIGNBUILDER_EXE environment variable
    3. Common Windows installation directories
    4. System PATH (via shutil.which)
"""

import os
import shutil
from pathlib import Path
from typing import Optional

# Environment variable to override the DesignBuilder executable path.
ENV_VAR = "DESIGNBUILDER_EXE"

# Common DesignBuilder installation paths (Windows).
DEFAULT_INSTALL_PATHS = [
    Path(r"C:\Program Files (x86)\DesignBuilder\DesignBuilder.exe"),
    Path(r"C:\Program Files\DesignBuilder\DesignBuilder.exe"),
]


def find_designbuilder(exe_path: Optional[str | Path] = None) -> Path:
    """Locate the DesignBuilder executable.

    Parameters
    ----------
    exe_path : str or Path, optional
        Explicit path to DesignBuilder.exe.  Takes highest priority.

    Returns
    -------
    Path
        Resolved path to the executable.

    Raises
    ------
    FileNotFoundError
        If DesignBuilder cannot be found via any method.
    """
    # 1. Explicit argument
    if exe_path is not None:
        p = Path(exe_path)
        if p.is_file():
            return p
        raise FileNotFoundError(f"DesignBuilder not found at: {p}")

    # 2. Environment variable
    env = os.environ.get(ENV_VAR)
    if env:
        p = Path(env)
        if p.is_file():
            return p
        raise FileNotFoundError(
            f"{ENV_VAR} is set to '{env}' but the file does not exist."
        )

    # 3. Common install locations
    for p in DEFAULT_INSTALL_PATHS:
        if p.is_file():
            return p

    # 4. System PATH
    which = shutil.which("DesignBuilder")
    if which:
        return Path(which)

    raise FileNotFoundError(
        "Could not find DesignBuilder.exe. "
        f"Set the {ENV_VAR} environment variable or pass the path explicitly."
    )
