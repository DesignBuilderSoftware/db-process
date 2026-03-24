"""Tests for db_process.commands module."""

import pytest

from db_process.commands import (
    ChangeAttributeValue,
    ExportAsXML,
    ExternalCommand,
    ImportLibraryData,
    ImportModelData,
    NoClose,
    ProcessChain,
    RunCalculation,
    Screen,
    SimEndDate,
    SimStartDate,
    SwitchScreen,
    TabChange,
    UseSimManager,
    cfd_simulation,
    daylighting,
    eplus_simulation,
    export_xml,
    heating_and_cooling_design,
    sbem_calculation,
)


# ---------------------------------------------------------------------------
# Individual command rendering
# ---------------------------------------------------------------------------


class TestSwitchScreen:
    def test_all_screens(self):
        assert SwitchScreen(Screen.SIMULATION).render() == "miGSS"
        assert SwitchScreen(Screen.HEATING_DESIGN).render() == "miGHL"
        assert SwitchScreen(Screen.COOLING_DESIGN).render() == "miGHG"
        assert SwitchScreen(Screen.DAYLIGHTING).render() == "miGDY"
        assert SwitchScreen(Screen.SBEM_DSM).render() == "miGCalculate"
        assert SwitchScreen(Screen.CFD).render() == "miGCFD"


class TestRunCalculation:
    def test_render(self):
        assert RunCalculation().render() == "miTUpdate"


class TestTabChange:
    def test_render(self):
        assert TabChange(2).render() == "TabChange_2"

    def test_invalid_tab(self):
        with pytest.raises(ValueError, match="must be >= 1"):
            TabChange(0)


class TestSimStartDate:
    def test_render(self):
        assert SimStartDate(4, 5).render() == "SimStartDate 4 5"

    def test_invalid_month(self):
        with pytest.raises(ValueError, match="Month"):
            SimStartDate(1, 13)

    def test_invalid_day(self):
        with pytest.raises(ValueError, match="Day"):
            SimStartDate(0, 6)


class TestSimEndDate:
    def test_render(self):
        assert SimEndDate(11, 5).render() == "SimEndDate 11 5"


class TestChangeAttributeValue:
    def test_integer_value(self):
        cmd = ChangeAttributeValue("Layout", 0)
        assert cmd.render() == "ChangeAttributeValue Layout 0"

    def test_boolean_value(self):
        cmd = ChangeAttributeValue("ComputersOn", 1)
        assert cmd.render() == "ChangeAttributeValue ComputersOn 1"

    def test_float_value(self):
        cmd = ChangeAttributeValue("OccupancyValue", 0.5)
        assert cmd.render() == "ChangeAttributeValue OccupancyValue 0.5"


class TestExternalCommand:
    def test_render(self):
        assert ExternalCommand("ProcessResults").render() == "ExternalCommand_ProcessResults"


class TestImportModelData:
    def test_render(self):
        cmd = ImportModelData(r"C:\data\model.csv")
        assert cmd.render() == r"ImportModelData_C:\data\model.csv"


class TestImportLibraryData:
    def test_render(self):
        cmd = ImportLibraryData(r"C:\data\lib.csv")
        assert cmd.render() == r"ImportLibraryData_C:\data\lib.csv"


class TestExportAsXML:
    def test_render(self):
        assert ExportAsXML().render() == "miFExportAsXML"


class TestUseSimManager:
    def test_render(self):
        assert UseSimManager().render() == "UseSimManager"


class TestNoClose:
    def test_render(self):
        assert NoClose().render() == "NoClose"


# ---------------------------------------------------------------------------
# ProcessChain
# ---------------------------------------------------------------------------


class TestProcessChain:
    def test_empty_chain_raises(self):
        with pytest.raises(ValueError, match="empty"):
            ProcessChain().to_string()

    def test_single_command(self):
        chain = ProcessChain().export_as_xml()
        assert chain.to_string() == "/process=miFExportAsXML"

    def test_eplus_simulation_chain(self):
        chain = (
            ProcessChain()
            .switch_screen(Screen.SIMULATION)
            .run()
        )
        assert chain.to_string() == "/process=miGSS, miTUpdate"

    def test_full_chain(self):
        chain = (
            ProcessChain()
            .use_sim_manager()
            .sim_start_date(1, 1)
            .sim_end_date(31, 12)
            .change_attribute("OccupancyValue", 0.5)
            .switch_screen(Screen.SIMULATION)
            .run()
            .no_close()
        )
        expected = (
            "/process=UseSimManager, SimStartDate 1 1, SimEndDate 31 12, "
            "ChangeAttributeValue OccupancyValue 0.5, miGSS, miTUpdate, NoClose"
        )
        assert chain.to_string() == expected

    def test_len(self):
        chain = ProcessChain().switch_screen(Screen.SIMULATION).run()
        assert len(chain) == 2

    def test_to_list(self):
        chain = ProcessChain().switch_screen(Screen.SIMULATION).run()
        assert chain.to_list() == ["miGSS", "miTUpdate"]

    def test_str(self):
        chain = ProcessChain().run()
        assert str(chain) == "/process=miTUpdate"

    def test_daylighting_with_annual(self):
        """Matches the documented example for both illuminance and annual."""
        chain = (
            ProcessChain()
            .switch_screen(Screen.DAYLIGHTING)
            .run()
            .tab_change(2)
            .run()
        )
        assert chain.to_string() == "/process=miGDY, miTUpdate, TabChange_2, miTUpdate"

    def test_heating_and_cooling(self):
        """Matches the documented example for heating + cooling design."""
        chain = (
            ProcessChain()
            .switch_screen(Screen.HEATING_DESIGN)
            .run()
            .switch_screen(Screen.COOLING_DESIGN)
            .run()
            .no_close()
        )
        expected = "/process=miGHL, miTUpdate, miGHG, miTUpdate, NoClose"
        assert chain.to_string() == expected

    def test_external_command_chain(self):
        """Matches the documented example with ExternalCommand."""
        chain = (
            ProcessChain()
            .switch_screen(Screen.SIMULATION)
            .run()
            .external_command("ProcessResults")
        )
        expected = "/process=miGSS, miTUpdate, ExternalCommand_ProcessResults"
        assert chain.to_string() == expected


# ---------------------------------------------------------------------------
# Convenience factory functions
# ---------------------------------------------------------------------------


class TestEplusSimulation:
    def test_basic(self):
        chain = eplus_simulation()
        assert chain.to_string() == "/process=miGSS, miTUpdate"

    def test_with_all_options(self):
        chain = eplus_simulation(
            sim_start_date=(4, 5),
            sim_end_date=(11, 5),
            use_sim_manager=True,
            attributes=[("ZoneMultiplier", 2), ("OccupancyValue", 0.5)],
            no_close=True,
        )
        expected = (
            "/process=UseSimManager, SimStartDate 4 5, SimEndDate 11 5, "
            "ChangeAttributeValue ZoneMultiplier 2, "
            "ChangeAttributeValue OccupancyValue 0.5, "
            "miGSS, miTUpdate, NoClose"
        )
        assert chain.to_string() == expected


class TestSbemCalculation:
    def test_basic(self):
        chain = sbem_calculation()
        assert chain.to_string() == "/process=miGCalculate, miTUpdate"


class TestExportXml:
    def test_basic(self):
        chain = export_xml()
        assert chain.to_string() == "/process=miFExportAsXML"


class TestHeatingAndCoolingDesign:
    def test_basic(self):
        chain = heating_and_cooling_design()
        assert chain.to_string() == "/process=miGHL, miTUpdate, miGHG, miTUpdate"

    def test_no_close(self):
        chain = heating_and_cooling_design(no_close=True)
        assert chain.to_string() == "/process=miGHL, miTUpdate, miGHG, miTUpdate, NoClose"


class TestDaylighting:
    def test_basic(self):
        chain = daylighting()
        assert chain.to_string() == "/process=miGDY, miTUpdate"

    def test_with_annual(self):
        chain = daylighting(run_annual=True)
        assert chain.to_string() == "/process=miGDY, miTUpdate, TabChange_2, miTUpdate"


class TestCfdSimulation:
    def test_basic(self):
        chain = cfd_simulation()
        assert chain.to_string() == "/process=miGCFD, miTUpdate"


# ---------------------------------------------------------------------------
# Compatibility: ensure the factory output matches db-batch create_cmnd()
# ---------------------------------------------------------------------------


class TestDbBatchCompatibility:
    """Verify that convenience factories produce the same strings
    as the original ``create_cmnd()`` in db-batch/run_batch.py."""

    def test_eplus_basic(self):
        """create_cmnd("eplus", None, None, False, None, False)"""
        chain = eplus_simulation()
        assert chain.to_string() == "/process=miGSS, miTUpdate"

    def test_sbem_basic(self):
        """create_cmnd("sbem", None, None, False, None, False)"""
        chain = sbem_calculation()
        assert chain.to_string() == "/process=miGCalculate, miTUpdate"

    def test_eplus_with_sim_manager_and_dates(self):
        """create_cmnd("eplus", [4, 5], [11, 5], True, None, False)"""
        chain = eplus_simulation(
            sim_start_date=(4, 5),
            sim_end_date=(11, 5),
            use_sim_manager=True,
        )
        expected = (
            "/process=UseSimManager, SimStartDate 4 5, SimEndDate 11 5, "
            "miGSS, miTUpdate"
        )
        assert chain.to_string() == expected

    def test_eplus_with_attributes_and_no_close(self):
        """create_cmnd("eplus", None, None, False, [("ZoneMultiplier", "2")], True)"""
        chain = eplus_simulation(
            attributes=[("ZoneMultiplier", "2")],
            no_close=True,
        )
        expected = (
            "/process=ChangeAttributeValue ZoneMultiplier 2, "
            "miGSS, miTUpdate, NoClose"
        )
        assert chain.to_string() == expected
