"""Offline checks for the deterministic GraphGuard data layer."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.generate_demo import (
    MAX_NOISE_ACCOUNTS,
    build_fixture,
    configuration_from_env,
    ground_truth_document,
    write_ground_truth,
    DEFAULT_GROUND_TRUTH_PATH,
)


def _account_ids(fixture, scenario):
    return [row["id"] for row in fixture["accounts"] if row["scenario"] == scenario]


def test_fixture_is_repeatable_and_contains_all_scenarios():
    first = build_fixture(seed=7, base_ts=1_700_000_000, noise_accounts=4)
    second = build_fixture(seed=7, base_ts=1_700_000_000, noise_accounts=4)

    assert first == second
    assert set(first["scenarios"]) == {"T1", "T2", "T3", "D1", "D2", "D3", "D4", "NOISE"}
    assert len(_account_ids(first, "D3")) == 40
    assert len(_account_ids(first, "NOISE")) == 4
    assert len(first["accounts"]) <= 40 + 50 + 30


def test_ground_truth_captures_temporal_and_hub_expectations(tmp_path):
    fixture = build_fixture(noise_accounts=0)
    ground_truth = ground_truth_document(fixture)

    assert ground_truth["scenarios"]["T1"]["expected"] == {
        "cycle": True,
        "time_ordered": True,
        "cycle_hops": 5,
        "shared_device": "DEV-999",
        "shared_device_accounts": 5,
        "expected_disposition": "AUTO_HOLD",
    }
    assert ground_truth["scenarios"]["D4"]["expected"]["time_ordered"] is False
    assert ground_truth["scenarios"]["D3"]["expected"]["hub_degree"] == 40

    path = write_ground_truth(fixture, tmp_path / "ground_truth.json")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["fixture_sha256"] == ground_truth["fixture_sha256"]
    assert loaded["counts"]["accounts"] == len(fixture["accounts"])


def test_seed_changes_noise_without_changing_planted_graph_shapes():
    first = build_fixture(seed=1, noise_accounts=3)
    second = build_fixture(seed=2, noise_accounts=3)

    assert first["scenarios"] == second["scenarios"]
    first_noise = [row for row in first["accounts"] if row["scenario"] == "NOISE"]
    second_noise = [row for row in second["accounts"] if row["scenario"] == "NOISE"]
    assert first_noise != second_noise
    assert all("monthly_volume" in row and "legit_activity" in row for row in first["accounts"])


def test_environment_settings_are_validated_and_bounded(monkeypatch):
    monkeypatch.setenv("GRAPHGUARD_SEED", "99")
    monkeypatch.setenv("GRAPHGUARD_NOISE_ACCOUNTS", str(MAX_NOISE_ACCOUNTS))
    settings = configuration_from_env()
    assert settings["seed"] == 99
    assert settings["noise_accounts"] == MAX_NOISE_ACCOUNTS

    monkeypatch.setenv("GRAPHGUARD_NOISE_ACCOUNTS", str(MAX_NOISE_ACCOUNTS + 1))
    try:
        configuration_from_env()
    except ValueError as exc:
        assert "between 0" in str(exc)
    else:
        raise AssertionError("out-of-range noise setting must be rejected")


def test_checked_in_ground_truth_matches_default_fixture():
    checked_in = json.loads(DEFAULT_GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    assert checked_in == ground_truth_document(build_fixture())
