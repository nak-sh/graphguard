"""Offline contracts and temporal graph-tool tests."""

import pytest

from apps.graph_tools.models import CycleResult, MoneyPathResult, SharedInfraResult
from apps.graph_tools.tools import is_time_respecting_cycle, is_time_respecting_path


def test_cycle_is_rotation_invariant():
    # The same ring is valid regardless of which edge is returned first.
    assert is_time_respecting_cycle([100, 200, 300, 50], 250)
    assert is_time_respecting_cycle([50, 100, 200, 300], 250)
    assert is_time_respecting_cycle([200, 300, 50, 100], 250)


def test_reverse_unrolling_is_not_a_cycle():
    assert not is_time_respecting_cycle([400, 300, 200, 100], 400)
    assert not is_time_respecting_cycle([100, 50, 200, 150], 400)


def test_cycle_window_uses_max_minus_min():
    assert is_time_respecting_cycle([10, 20, 5], 15)
    assert not is_time_respecting_cycle([10, 20, 5], 14)


def test_money_paths_are_linear_and_bounded_by_window():
    assert is_time_respecting_path([10, 20, 25], 15)
    assert not is_time_respecting_path([10, 9, 25], 15)
    assert not is_time_respecting_path([10, 20, 30], 19)


def test_v2_contracts_reject_unknown_fields_and_coercion():
    with pytest.raises(Exception):
        CycleResult(
            entity_id="A-1",
            cycle_nodes=["A-1", "A-2", "A-3", "A-1"],
            amounts=[1.0, 2.0, 3.0],
            timestamps=[1, 2, 3],
            is_time_ordered=True,
            unexpected="not allowed",
        )
    with pytest.raises(Exception):
        SharedInfraResult(
            entity_id="A-1",
            infrastructure_id="D-1",
            infrastructure_type="Device",
            connected_accounts=["A-2"],
            is_hub="false",
        )
