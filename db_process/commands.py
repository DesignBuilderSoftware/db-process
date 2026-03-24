"""
commands.py
====================================
Typed representation of DesignBuilder command line process commands.

DesignBuilder CLI syntax::

    "DesignBuilder.exe" "MyFile.dsb" /process=Command1, Command2, ...

This module provides dataclasses for each command type and a
:class:`ProcessChain` builder to compose them into valid ``/process=`` strings.

Reference: DesignBuilder Help > Reference > Command Line Processing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union


# ---------------------------------------------------------------------------
# Screen / view commands
# ---------------------------------------------------------------------------

class Screen(str, Enum):
    """Available DesignBuilder screen commands."""

    SIMULATION = "miGSS"
    HEATING_DESIGN = "miGHL"
    COOLING_DESIGN = "miGHG"
    DAYLIGHTING = "miGDY"
    SBEM_DSM = "miGCalculate"
    CFD = "miGCFD"


# ---------------------------------------------------------------------------
# Individual command dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SwitchScreen:
    """Change the view to a specific DesignBuilder screen.

    Examples: miGSS, miGHL, miGHG, miGDY, miGCalculate, miGCFD
    """

    screen: Screen

    def render(self) -> str:
        return self.screen.value


@dataclass(frozen=True)
class RunCalculation:
    """Run the calculation for the current screen (miTUpdate).

    Generally this command should be placed after screen switching
    and before any ChangeAttributeValue commands that follow it.
    """

    def render(self) -> str:
        return "miTUpdate"


@dataclass(frozen=True)
class TabChange:
    """Change the view to tab *n* on the current screen.

    Example: ``TabChange_2`` on the Daylighting screen switches to
    the Annual daylighting tab.
    """

    tab: int

    def __post_init__(self) -> None:
        if self.tab < 1:
            raise ValueError(f"Tab number must be >= 1, got {self.tab}")

    def render(self) -> str:
        return f"TabChange_{self.tab}"


@dataclass(frozen=True)
class SimStartDate:
    """Set simulation start date.

    Parameters are day and month as integers.
    Example: ``SimStartDate 4 5`` sets start to May 4.
    """

    day: int
    month: int

    def __post_init__(self) -> None:
        if not (1 <= self.month <= 12):
            raise ValueError(f"Month must be 1-12, got {self.month}")
        if not (1 <= self.day <= 31):
            raise ValueError(f"Day must be 1-31, got {self.day}")

    def render(self) -> str:
        return f"SimStartDate {self.day} {self.month}"


@dataclass(frozen=True)
class SimEndDate:
    """Set simulation end date.

    Parameters are day and month as integers.
    Example: ``SimEndDate 11 5`` sets end to May 11.
    """

    day: int
    month: int

    def __post_init__(self) -> None:
        if not (1 <= self.month <= 12):
            raise ValueError(f"Month must be 1-12, got {self.month}")
        if not (1 <= self.day <= 31):
            raise ValueError(f"Day must be 1-31, got {self.day}")

    def render(self) -> str:
        return f"SimEndDate {self.day} {self.month}"


@dataclass(frozen=True)
class ChangeAttributeValue:
    """Change a model attribute at building level.

    Attribute value types (from documentation):
        - Numeric enums: integer codes (e.g. ``Layout 0``)
        - Booleans: ``1`` for True, ``0`` for False
        - Real numbers: SI units, ``.`` decimal separator
        - Database table selections: numeric Id (obtain via API)

    Tip: Enable *Show attribute names in tooltips* in
    Tools > Program Options > Interface to find attribute names.
    """

    attribute: str
    value: Union[str, int, float]

    def render(self) -> str:
        return f"ChangeAttributeValue {self.attribute} {self.value}"


@dataclass(frozen=True)
class ExternalCommand:
    """Run an external command with optional arguments.

    The external executable must be on the system PATH or in the
    working directory.
    """

    command: str

    def render(self) -> str:
        return f"ExternalCommand_{self.command}"


@dataclass(frozen=True)
class ImportModelData:
    """Import model data from a CSV file previously exported from the model."""

    filepath: str

    def render(self) -> str:
        return f"ImportModelData_{self.filepath}"


@dataclass(frozen=True)
class ImportLibraryData:
    """Import library data from a file."""

    filepath: str

    def render(self) -> str:
        return f"ImportLibraryData_{self.filepath}"


@dataclass(frozen=True)
class ExportAsXML:
    """Export the model as a dsbXML file (miFExportAsXML)."""

    def render(self) -> str:
        return "miFExportAsXML"


@dataclass(frozen=True)
class UseSimManager:
    """Ensure the simulation runs using the Simulation Manager.

    Uses the Server and EnergyPlus server method settings
    currently configured in the model.
    """

    def render(self) -> str:
        return "UseSimManager"


@dataclass(frozen=True)
class NoClose:
    """Prevent DesignBuilder from shutting down after all commands."""

    def render(self) -> str:
        return "NoClose"


# Union of all command types for type hints.
Command = Union[
    SwitchScreen,
    RunCalculation,
    TabChange,
    SimStartDate,
    SimEndDate,
    ChangeAttributeValue,
    ExternalCommand,
    ImportModelData,
    ImportLibraryData,
    ExportAsXML,
    UseSimManager,
    NoClose,
]


# ---------------------------------------------------------------------------
# ProcessChain builder
# ---------------------------------------------------------------------------

@dataclass
class ProcessChain:
    """Build a ``/process=`` command string from a sequence of commands.

    Usage::

        chain = (
            ProcessChain()
            .use_sim_manager()
            .switch_screen(Screen.SIMULATION)
            .sim_start_date(1, 1)
            .sim_end_date(31, 12)
            .change_attribute("OccupancyValue", 0.5)
            .run()
        )
        print(chain.to_string())
        # /process=UseSimManager, miGSS, SimStartDate 1 1, SimEndDate 31 12,
        #          ChangeAttributeValue OccupancyValue 0.5, miTUpdate
    """

    commands: list[Command] = field(default_factory=list)

    # -- Fluent builder methods -----------------------------------------------

    def add(self, command: Command) -> ProcessChain:
        """Add an arbitrary command to the chain."""
        self.commands.append(command)
        return self

    def switch_screen(self, screen: Screen) -> ProcessChain:
        """Add a screen-switching command."""
        return self.add(SwitchScreen(screen))

    def run(self) -> ProcessChain:
        """Add miTUpdate (run calculation for current screen)."""
        return self.add(RunCalculation())

    def tab_change(self, tab: int) -> ProcessChain:
        """Switch to a specific tab on the current screen."""
        return self.add(TabChange(tab))

    def sim_start_date(self, day: int, month: int) -> ProcessChain:
        """Set simulation start date."""
        return self.add(SimStartDate(day, month))

    def sim_end_date(self, day: int, month: int) -> ProcessChain:
        """Set simulation end date."""
        return self.add(SimEndDate(day, month))

    def change_attribute(
        self, attribute: str, value: Union[str, int, float]
    ) -> ProcessChain:
        """Change a model attribute value."""
        return self.add(ChangeAttributeValue(attribute, value))

    def external_command(self, command: str) -> ProcessChain:
        """Run an external command."""
        return self.add(ExternalCommand(command))

    def import_model_data(self, filepath: str) -> ProcessChain:
        """Import model data from a CSV file."""
        return self.add(ImportModelData(filepath))

    def import_library_data(self, filepath: str) -> ProcessChain:
        """Import library data from a file."""
        return self.add(ImportLibraryData(filepath))

    def export_as_xml(self) -> ProcessChain:
        """Export the model as dsbXML."""
        return self.add(ExportAsXML())

    def use_sim_manager(self) -> ProcessChain:
        """Use the Simulation Manager for the run."""
        return self.add(UseSimManager())

    def no_close(self) -> ProcessChain:
        """Prevent DesignBuilder from closing after processing."""
        return self.add(NoClose())

    # -- Rendering ------------------------------------------------------------

    def to_string(self) -> str:
        """Render the chain as a ``/process=...`` argument string.

        Raises
        ------
        ValueError
            If the chain contains no commands.
        """
        if not self.commands:
            raise ValueError("ProcessChain is empty — add at least one command.")
        parts = [cmd.render() for cmd in self.commands]
        return "/process=" + ", ".join(parts)

    def to_list(self) -> list[str]:
        """Return the chain as a list of individual command strings."""
        return [cmd.render() for cmd in self.commands]

    def __str__(self) -> str:
        return self.to_string()

    def __repr__(self) -> str:
        return f"ProcessChain({self.commands!r})"

    def __len__(self) -> int:
        return len(self.commands)


# ---------------------------------------------------------------------------
# Convenience factory functions
# ---------------------------------------------------------------------------

def eplus_simulation(
    *,
    sim_start_date: Optional[tuple[int, int]] = None,
    sim_end_date: Optional[tuple[int, int]] = None,
    use_sim_manager: bool = False,
    attributes: Optional[list[tuple[str, Union[str, int, float]]]] = None,
    no_close: bool = False,
) -> ProcessChain:
    """Build a standard EnergyPlus simulation command chain.

    This produces the equivalent of what ``db-batch`` creates for
    ``analysis_type="eplus"``.
    """
    chain = ProcessChain()

    if use_sim_manager:
        chain.use_sim_manager()

    if sim_start_date:
        chain.sim_start_date(sim_start_date[0], sim_start_date[1])

    if sim_end_date:
        chain.sim_end_date(sim_end_date[0], sim_end_date[1])

    if attributes:
        for attr, val in attributes:
            chain.change_attribute(attr, val)

    chain.switch_screen(Screen.SIMULATION)
    chain.run()

    if no_close:
        chain.no_close()

    return chain


def sbem_calculation(
    *,
    sim_start_date: Optional[tuple[int, int]] = None,
    sim_end_date: Optional[tuple[int, int]] = None,
    attributes: Optional[list[tuple[str, Union[str, int, float]]]] = None,
    no_close: bool = False,
) -> ProcessChain:
    """Build a standard SBEM/DSM calculation command chain."""
    chain = ProcessChain()

    if sim_start_date:
        chain.sim_start_date(sim_start_date[0], sim_start_date[1])

    if sim_end_date:
        chain.sim_end_date(sim_end_date[0], sim_end_date[1])

    if attributes:
        for attr, val in attributes:
            chain.change_attribute(attr, val)

    chain.switch_screen(Screen.SBEM_DSM)
    chain.run()

    if no_close:
        chain.no_close()

    return chain


def export_xml() -> ProcessChain:
    """Build a command chain to export the model as dsbXML."""
    return ProcessChain().export_as_xml()


def heating_and_cooling_design(*, no_close: bool = False) -> ProcessChain:
    """Run both Heating and Cooling Design calculations."""
    chain = (
        ProcessChain()
        .switch_screen(Screen.HEATING_DESIGN)
        .run()
        .switch_screen(Screen.COOLING_DESIGN)
        .run()
    )
    if no_close:
        chain.no_close()
    return chain


def daylighting(
    *, run_annual: bool = False, no_close: bool = False
) -> ProcessChain:
    """Run daylighting calculation, optionally including annual daylighting.

    When *run_annual* is True, runs both Illuminance (tab 1) and
    Annual daylighting (tab 2) calculations.
    """
    chain = ProcessChain().switch_screen(Screen.DAYLIGHTING).run()
    if run_annual:
        chain.tab_change(2).run()
    if no_close:
        chain.no_close()
    return chain


def cfd_simulation(*, no_close: bool = False) -> ProcessChain:
    """Run a CFD simulation."""
    chain = ProcessChain().switch_screen(Screen.CFD).run()
    if no_close:
        chain.no_close()
    return chain
