"""Additional tests for db_process.commands — validation branches and
factory options not covered by test_commands.py."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from db_process.commands import (
    ChangeAttributeValue,
    ImportLibraryData,
    ImportModelData,
    NoClose,
    ProcessChain,
    Screen,
    SimEndDate,
    SimStartDate,
    SwitchScreen,
    TabChange,
    cfd_simulation,
    daylighting,
    sbem_calculation,
)


class TestSimEndDateValidation:
    def test_invalid_month(self):
        with pytest.raises(ValueError, match="Month must be 1-12"):
            SimEndDate(1, 0)

    def test_invalid_day(self):
        with pytest.raises(ValueError, match="Day must be 1-31"):
            SimEndDate(32, 6)

    def test_boundary_values_accepted(self):
        assert SimEndDate(31, 12).render() == "SimEndDate 31 12"
        assert SimEndDate(1, 1).render() == "SimEndDate 1 1"


class TestProcessChainImportMethods:
    def test_import_model_data(self):
        chain = ProcessChain().import_model_data(r"C:\data\model.csv")
        assert chain.to_list() == [r"ImportModelData_C:\data\model.csv"]
        assert isinstance(chain.commands[0], ImportModelData)

    def test_import_library_data(self):
        chain = ProcessChain().import_library_data(r"C:\data\lib.csv")
        assert chain.to_list() == [r"ImportLibraryData_C:\data\lib.csv"]
        assert isinstance(chain.commands[0], ImportLibraryData)


class TestProcessChainRepr:
    def test_repr_contains_commands(self):
        chain = ProcessChain().run()
        r = repr(chain)
        assert r.startswith("ProcessChain(")
        assert "RunCalculation" in r

    def test_add_returns_self_for_chaining(self):
        chain = ProcessChain()
        assert chain.run() is chain


class TestSbemCalculationOptions:
    def test_with_dates_attributes_and_no_close(self):
        chain = sbem_calculation(
            sim_start_date=(1, 2),
            sim_end_date=(28, 2),
            attributes=[("OccupancyValue", 0.5)],
            no_close=True,
        )
        expected = (
            "/process=SimStartDate 1 2, SimEndDate 28 2, "
            "ChangeAttributeValue OccupancyValue 0.5, "
            "miGCalculate, miTUpdate, NoClose"
        )
        assert chain.to_string() == expected


class TestDaylightingOptions:
    def test_no_close(self):
        chain = daylighting(no_close=True)
        assert chain.to_string() == "/process=miGDY, miTUpdate, NoClose"

    def test_annual_and_no_close(self):
        chain = daylighting(run_annual=True, no_close=True)
        assert (
            chain.to_string()
            == "/process=miGDY, miTUpdate, TabChange_2, miTUpdate, NoClose"
        )


class TestCfdSimulationOptions:
    def test_no_close(self):
        chain = cfd_simulation(no_close=True)
        assert chain.to_string() == "/process=miGCFD, miTUpdate, NoClose"


class TestScreenEnum:
    def test_is_str_subclass(self):
        assert isinstance(Screen.SIMULATION, str)
        assert Screen.SIMULATION == "miGSS"

    def test_lookup_by_value(self):
        assert Screen("miGDY") is Screen.DAYLIGHTING

    def test_all_values(self):
        assert {s.value for s in Screen} == {
            "miGSS", "miGHL", "miGHG", "miGDY", "miGCalculate", "miGCFD"
        }


class TestCommandImmutability:
    def test_switch_screen_is_frozen(self):
        cmd = SwitchScreen(Screen.CFD)
        with pytest.raises(FrozenInstanceError):
            cmd.screen = Screen.SIMULATION  # type: ignore[misc]

    def test_sim_start_date_is_frozen(self):
        cmd = SimStartDate(1, 1)
        with pytest.raises(FrozenInstanceError):
            cmd.day = 2  # type: ignore[misc]

    def test_change_attribute_value_is_frozen(self):
        cmd = ChangeAttributeValue("X", 1)
        with pytest.raises(FrozenInstanceError):
            cmd.value = 2  # type: ignore[misc]

    def test_frozen_commands_are_hashable_and_comparable(self):
        assert SwitchScreen(Screen.CFD) == SwitchScreen(Screen.CFD)
        assert len({NoClose(), NoClose()}) == 1


class TestProcessChainEdgeCases:
    def test_empty_chain_to_list(self):
        assert ProcessChain().to_list() == []

    def test_empty_chain_len(self):
        assert len(ProcessChain()) == 0

    def test_empty_chain_str_raises(self):
        with pytest.raises(ValueError, match="empty"):
            str(ProcessChain())

    def test_add_raw_command_instance(self):
        chain = ProcessChain().add(TabChange(3)).add(NoClose())
        assert chain.to_string() == "/process=TabChange_3, NoClose"

    def test_change_attribute_string_value(self):
        chain = ProcessChain().change_attribute("Template", "Office_OpenPlan")
        assert chain.to_list() == [
            "ChangeAttributeValue Template Office_OpenPlan"
        ]

    def test_invalid_tab_via_builder(self):
        with pytest.raises(ValueError, match="must be >= 1"):
            ProcessChain().tab_change(0)

    def test_invalid_date_via_builder(self):
        with pytest.raises(ValueError, match="Month must be 1-12"):
            ProcessChain().sim_start_date(1, 13)

    def test_separate_chains_do_not_share_commands(self):
        # `commands` uses default_factory, so instances must be independent.
        a = ProcessChain().run()
        b = ProcessChain()
        assert len(a) == 1
        assert len(b) == 0
