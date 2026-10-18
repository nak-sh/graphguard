"""Generate the deterministic GraphGuard demonstration graph.

The records produced by :func:`build_fixture` are *load rows*, rather than a
second graph implementation.  FalkorDB remains the source of truth: the rows
are sent to FalkorDB by :func:`seed_database`, and all application queries
continue to read FalkorDB.

The generator deliberately has no wall-clock input.  A seed and a base
timestamp can be supplied through the environment so a run can be reproduced
exactly:

``GRAPHGUARD_SEED=20241018 GRAPHGUARD_BASE_TS=1704067200 python data/generate_demo.py``

Running the script resets the demo graph by default and writes
``data/ground_truth.json``.  Use ``GRAPHGUARD_RESET_GRAPH=0`` to preserve
unrelated graph data; writes still use ``MERGE`` keys so rerunning is
idempotent.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import networkx as nx
from faker import Faker


DEFAULT_SEED = 20241018
DEFAULT_BASE_TS = 1704067200  # 2024-01-01T00:00:00Z
DEFAULT_NOISE_ACCOUNTS = 1000
MAX_NOISE_ACCOUNTS = 2000
DEFAULT_GRAPH_NAME = "graphguard"
DEFAULT_GROUND_TRUTH_PATH = Path(__file__).with_name("ground_truth.json")


def _env_int(*names: str, default: int) -> int:
    """Read an integer environment setting, accepting the first set name."""

    value: Optional[str] = None
    for name in names:
        if os.getenv(name) is not None:
            value = os.getenv(name)
            break
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        joined = ", ".join(names)
        raise ValueError(f"{joined} must be an integer, got {value!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean (0/1 or true/false), got {value!r}")


def configuration_from_env() -> Dict[str, Any]:
    """Return validated generator/database settings from environment variables."""

    noise_accounts = _env_int(
        "GRAPHGUARD_NOISE_ACCOUNTS", "DEMO_NOISE_ACCOUNTS", default=DEFAULT_NOISE_ACCOUNTS
    )
    if not 0 <= noise_accounts <= MAX_NOISE_ACCOUNTS:
        raise ValueError(
            f"GRAPHGUARD_NOISE_ACCOUNTS must be between 0 and {MAX_NOISE_ACCOUNTS}"
        )

    port = _env_int("GRAPHGUARD_DB_PORT", default=6379)
    if not 1 <= port <= 65535:
        raise ValueError("GRAPHGUARD_DB_PORT must be between 1 and 65535")

    return {
        "seed": _env_int("GRAPHGUARD_SEED", "DEMO_SEED", default=DEFAULT_SEED),
        "base_ts": _env_int("GRAPHGUARD_BASE_TS", "DEMO_BASE_TS", default=DEFAULT_BASE_TS),
        "noise_accounts": noise_accounts,
        "db_host": os.getenv("GRAPHGUARD_DB_HOST", "localhost"),
        "db_port": port,
        "graph_name": os.getenv("GRAPHGUARD_GRAPH_NAME", DEFAULT_GRAPH_NAME),
        "reset_graph": _env_bool("GRAPHGUARD_RESET_GRAPH", True),
    }


def _account(
    account_id: str,
    scenario: str,
    monthly_volume: float,
    legit_activity: bool,
    legit_activity_ratio: float,
    *,
    tier: str = "STANDARD",
    is_noise: bool = False,
) -> Dict[str, Any]:
    return {
        "id": account_id,
        "status": "ACTIVE",
        "tier": tier,
        "scenario": scenario,
        "monthly_volume": monthly_volume,
        "legit_activity": legit_activity,
        "legit_activity_ratio": legit_activity_ratio,
        "is_noise": is_noise,
    }


def _device(
    device_id: str,
    scenario: str,
    *,
    fingerprint_hash: str,
    account_count: int,
    is_hub: bool,
    hub_type: str = "NONE",
) -> Dict[str, Any]:
    return {
        "id": device_id,
        "fingerprint_hash": fingerprint_hash,
        "scenario": scenario,
        "account_count": account_count,
        "hub_degree": account_count,
        "is_hub": is_hub,
        "is_shared_hub": is_hub,
        "hub_type": hub_type,
    }


def _ip(
    ip_id: str,
    scenario: str,
    *,
    region: str,
    account_count: int,
    is_hub: bool,
    hub_type: str = "NONE",
) -> Dict[str, Any]:
    return {
        "id": ip_id,
        "region": region,
        "scenario": scenario,
        "account_count": account_count,
        "hub_degree": account_count,
        "is_hub": is_hub,
        "is_shared_hub": is_hub,
        "hub_type": hub_type,
    }


def _alert(
    alert_id: str,
    scenario: str,
    entity_id: str,
    priority: str,
    expected_disposition: str,
    reason: str,
) -> Dict[str, Any]:
    return {
        "id": alert_id,
        "priority": priority,
        "status": "OPEN",
        "scenario": scenario,
        "entity_id": entity_id,
        "expected_disposition": expected_disposition,
        "reason": reason,
    }


def _transfer(
    transfer_id: str,
    source: str,
    target: str,
    amount: float,
    ts: int,
    scenario: str,
    *,
    transfer_kind: str = "TRANSFER",
) -> Dict[str, Any]:
    return {
        "id": transfer_id,
        "source": source,
        "target": target,
        "amount": amount,
        "ts": ts,
        "scenario": scenario,
        "transfer_kind": transfer_kind,
    }


def _link(source: str, target: str, scenario: str) -> Dict[str, str]:
    return {"source": source, "target": target, "scenario": scenario}


def build_fixture(
    *,
    seed: int = DEFAULT_SEED,
    base_ts: int = DEFAULT_BASE_TS,
    noise_accounts: int = DEFAULT_NOISE_ACCOUNTS,
) -> Dict[str, Any]:
    """Build deterministic FalkorDB load rows and scenario expectations.

    This function is intentionally pure.  It does not instantiate FalkorDB or
    answer graph queries; it only returns rows that :func:`seed_database` will
    write to FalkorDB.  ``noise_accounts`` is bounded to prevent an accidental
    environment setting from making a demo graph unexpectedly large.
    """

    if not 0 <= noise_accounts <= MAX_NOISE_ACCOUNTS:
        raise ValueError(f"noise_accounts must be between 0 and {MAX_NOISE_ACCOUNTS}")

    rng = random.Random(seed)
    faker = Faker()
    faker.seed_instance(seed)
    accounts: List[Dict[str, Any]] = []
    devices: List[Dict[str, Any]] = []
    ips: List[Dict[str, Any]] = []
    alerts: List[Dict[str, Any]] = []
    transfers: List[Dict[str, Any]] = []
    device_links: List[Dict[str, str]] = []
    ip_links: List[Dict[str, str]] = []
    scenarios: Dict[str, Dict[str, Any]] = {}

    def add_accounts(rows: Iterable[Dict[str, Any]]) -> None:
        accounts.extend(rows)

    def scenario(
        key: str,
        *,
        pattern: str,
        anchor: str,
        account_ids: List[str],
        expected: Dict[str, Any],
        alert_rows: Iterable[Dict[str, Any]],
    ) -> None:
        alert_list = list(alert_rows)
        alerts.extend(alert_list)
        scenarios[key] = {
            "pattern": pattern,
            "anchor": anchor,
            "account_ids": account_ids,
            "alert_ids": [row["id"] for row in alert_list],
            "expected": expected,
        }

    # ------------------------------------------------------------------ T1 --
    # Five-account, monotonically timestamped ring.  Keep the original IDs so
    # existing demo/benchmark commands continue to have a stable anchor.
    t1_ids = [f"A-{number}" for number in range(104, 109)]
    add_accounts(
        _account(account_id, "T1", 45000 + i * 1250, False, 0.08)
        for i, account_id in enumerate(t1_ids)
    )
    devices.append(
        _device("DEV-999", "T1", fingerprint_hash="fp_hash_t1", account_count=5, is_hub=False)
    )
    ips.extend(
        [
            _ip("IP-10", "T1", region="US-East", account_count=1, is_hub=False),
            _ip("IP-20", "T1", region="US-West", account_count=1, is_hub=False),
        ]
    )
    device_links.extend(_link(account_id, "DEV-999", "T1") for account_id in t1_ids)
    ip_links.extend([_link(t1_ids[0], "IP-10", "T1"), _link(t1_ids[1], "IP-20", "T1")])
    t1_amounts = [9500, 9400, 9350, 9200, 9000]
    t1_transfers = []
    for i, (source, target, amount) in enumerate(
        zip(t1_ids, t1_ids[1:] + t1_ids[:1], t1_amounts), start=1
    ):
        t1_transfers.append(
            _transfer(
                f"tx_{i}",
                source,
                target,
                amount,
                base_ts + i * 600,
                "T1",
                transfer_kind="RING_TRANSFER",
            )
        )
    transfers.extend(t1_transfers)
    scenario(
        "T1",
        pattern="time_ordered_ring",
        anchor="A-104",
        account_ids=t1_ids,
        expected={
            "cycle": True,
            "time_ordered": True,
            "cycle_hops": 5,
            "shared_device": "DEV-999",
            "shared_device_accounts": 5,
            "expected_disposition": "AUTO_HOLD",
        },
        alert_rows=[
            _alert(
                "ALERT-104",
                "T1",
                "A-104",
                "HIGH",
                "AUTO_HOLD",
                "Five-account time-ordered laundering ring",
            )
        ],
    )

    # ------------------------------------------------------------------ T2 --
    # A directed mule chain has suspiciously high throughput but deliberately
    # does not close a cycle.
    t2_ids = [f"T2-{number}" for number in range(201, 207)]
    t2_accounts = [
        _account(account_id, "T2", 62000 - i * 1750, False, 0.14)
        for i, account_id in enumerate(t2_ids)
    ]
    # The third-hop endpoint is a synthetic confirmed-bad anchor so the
    # proximity signal can be evaluated without treating the whole chain as
    # adjudicated.
    t2_accounts[3]["confirmed_bad"] = True
    add_accounts(t2_accounts)
    for i, account_id in enumerate(t2_ids):
        device_id = f"DEV-T2-{i + 1:02d}"
        ip_id = f"IP-T2-{i + 1:02d}"
        devices.append(
            _device(
                device_id,
                "T2",
                fingerprint_hash=f"fp_hash_t2_{i + 1:02d}",
                account_count=1,
                is_hub=False,
            )
        )
        ips.append(_ip(ip_id, "T2", region="US-Central", account_count=1, is_hub=False))
        device_links.append(_link(account_id, device_id, "T2"))
        ip_links.append(_link(account_id, ip_id, "T2"))
    transfers.extend(
        _transfer(
            f"t2_tx_{i}",
            source,
            target,
            15500 - (i * 400),
            base_ts + 10000 + i * 900,
            "T2",
            transfer_kind="MULE_CHAIN",
        )
        for i, (source, target) in enumerate(zip(t2_ids, t2_ids[1:]), start=1)
    )
    scenario(
        "T2",
        pattern="mule_chain",
        anchor=t2_ids[0],
        account_ids=t2_ids,
        expected={
            "cycle": False,
            "time_ordered": False,
            "chain_hops": 5,
            "expected_disposition": "MANUAL_REVIEW",
        },
        alert_rows=[
            _alert(
                "ALERT-T2-201",
                "T2",
                t2_ids[0],
                "HIGH",
                "MANUAL_REVIEW",
                "Directed high-throughput mule chain",
            )
        ],
    )

    # ------------------------------------------------------------------ T3 --
    # Synthetic identities share infrastructure and have near-identical
    # activity profiles, but no transfers are needed to represent the cluster.
    t3_ids = [f"T3-{number}" for number in range(301, 307)]
    add_accounts(
        _account(account_id, "T3", 28000, False, 0.05)
        for account_id in t3_ids
    )
    devices.append(
        _device(
            "DEV-T3-SYNTH",
            "T3",
            fingerprint_hash="fp_hash_t3_synthetic",
            account_count=len(t3_ids),
            is_hub=False,
            hub_type="SYNTHETIC_IDENTITY_CLUSTER",
        )
    )
    ips.append(
        _ip(
            "IP-T3-SYNTH",
            "T3",
            region="US-East",
            account_count=len(t3_ids),
            is_hub=False,
            hub_type="SYNTHETIC_IDENTITY_CLUSTER",
        )
    )
    device_links.extend(_link(account_id, "DEV-T3-SYNTH", "T3") for account_id in t3_ids)
    ip_links.extend(_link(account_id, "IP-T3-SYNTH", "T3") for account_id in t3_ids)
    scenario(
        "T3",
        pattern="synthetic_identity_cluster",
        anchor=t3_ids[0],
        account_ids=t3_ids,
        expected={
            "cycle": False,
            "identity_cluster": True,
            "shared_device": "DEV-T3-SYNTH",
            "shared_ip": "IP-T3-SYNTH",
            "cluster_size": len(t3_ids),
            "expected_disposition": "MANUAL_REVIEW",
        },
        alert_rows=[
            _alert(
                "ALERT-T3-301",
                "T3",
                t3_ids[0],
                "MEDIUM",
                "MANUAL_REVIEW",
                "Synthetic identity cluster with near-identical activity",
            )
        ],
    )

    # ------------------------------------------------------------------ D1 --
    # Existing household IDs and transfer names remain stable for the original
    # phase tests and README walkthrough.
    d1_ids = ["D-201", "D-202"]
    add_accounts(
        [
            _account(d1_ids[0], "D1", 1800, True, 0.94),
            _account(d1_ids[1], "D1", 1500, True, 0.96),
        ]
    )
    devices.append(
        _device(
            "DEV-FAMILY-1",
            "D1",
            fingerprint_hash="fp_hash_fam",
            account_count=2,
            is_hub=False,
            hub_type="HOUSEHOLD",
        )
    )
    ips.append(_ip("IP-D1-HOME", "D1", region="US-East", account_count=2, is_hub=False, hub_type="HOUSEHOLD"))
    device_links.extend(_link(account_id, "DEV-FAMILY-1", "D1") for account_id in d1_ids)
    ip_links.extend(_link(account_id, "IP-D1-HOME", "D1") for account_id in d1_ids)
    transfers.extend(
        [
            _transfer("dtx_1", d1_ids[0], d1_ids[1], 45, base_ts - 8000, "D1", transfer_kind="HOUSEHOLD"),
            _transfer("dtx_2", d1_ids[1], d1_ids[0], 20, base_ts - 4000, "D1", transfer_kind="HOUSEHOLD"),
        ]
    )
    scenario(
        "D1",
        pattern="family_device_decoy",
        anchor=d1_ids[0],
        account_ids=d1_ids,
        expected={
            "cycle": False,
            "shared_device": "DEV-FAMILY-1",
            "shared_device_accounts": 2,
            "expected_disposition": "NO_ACTION",
        },
        alert_rows=[
            _alert(
                "ALERT-D201",
                "D1",
                d1_ids[0],
                "LOW",
                "NO_ACTION",
                "Two household accounts sharing a family device",
            )
        ],
    )

    # ------------------------------------------------------------------ D2 --
    # A payroll account legitimately fans out to employees.  Every edge is
    # explicitly typed so downstream consumers can distinguish it from a mule
    # chain without adding special graph structures.
    d2_ids = ["D2-201"] + [f"D2-{number}" for number in range(202, 208)]
    add_accounts(
        [_account(d2_ids[0], "D2", 96000, True, 0.99, tier="BUSINESS")]
        + [_account(account_id, "D2", 7200, True, 0.98) for account_id in d2_ids[1:]]
    )
    for i, account_id in enumerate(d2_ids):
        device_id = f"DEV-D2-{i + 1:02d}"
        ip_id = f"IP-D2-{i + 1:02d}"
        devices.append(
            _device(
                device_id,
                "D2",
                fingerprint_hash=f"fp_hash_d2_{i + 1:02d}",
                account_count=1,
                is_hub=False,
            )
        )
        ips.append(_ip(ip_id, "D2", region="US-West", account_count=1, is_hub=False))
        device_links.append(_link(account_id, device_id, "D2"))
        ip_links.append(_link(account_id, ip_id, "D2"))
    transfers.extend(
        _transfer(
            f"d2_payroll_{i}",
            d2_ids[0],
            employee_id,
            3200 + i * 175,
            base_ts + 20000,
            "D2",
            transfer_kind="PAYROLL",
        )
        for i, employee_id in enumerate(d2_ids[1:], start=1)
    )
    scenario(
        "D2",
        pattern="payroll_fan_out",
        anchor=d2_ids[0],
        account_ids=d2_ids,
        expected={
            "cycle": False,
            "fan_out": True,
            "payroll_edges": len(d2_ids) - 1,
            "expected_disposition": "NO_ACTION",
        },
        alert_rows=[
            _alert(
                "ALERT-D2-201",
                "D2",
                d2_ids[0],
                "LOW",
                "NO_ACTION",
                "Legitimate payroll fan-out to employees",
            )
        ],
    )

    # ------------------------------------------------------------------ D3 --
    # Forty accounts behind an office NAT.  Both infrastructure records carry
    # explicit hub metadata so consumers can prune this expected high-degree
    # coincidence instead of treating it as a compact fraud ring.
    d3_ids = [f"D3-{number:03d}" for number in range(1, 41)]
    add_accounts(
        _account(account_id, "D3", 9000 + (i % 5) * 300, True, 0.89)
        for i, account_id in enumerate(d3_ids)
    )
    devices.append(
        _device(
            "DEV-OFFICE-HUB",
            "D3",
            fingerprint_hash="fp_hash_office_hub",
            account_count=len(d3_ids),
            is_hub=True,
            hub_type="SHARED_OFFICE",
        )
    )
    ips.append(
        _ip(
            "IP-OFFICE-HUB",
            "D3",
            region="US-West",
            account_count=len(d3_ids),
            is_hub=True,
            hub_type="SHARED_OFFICE",
        )
    )
    device_links.extend(_link(account_id, "DEV-OFFICE-HUB", "D3") for account_id in d3_ids)
    ip_links.extend(_link(account_id, "IP-OFFICE-HUB", "D3") for account_id in d3_ids)
    scenario(
        "D3",
        pattern="shared_office_ip_hub",
        anchor=d3_ids[0],
        account_ids=d3_ids,
        expected={
            "cycle": False,
            "shared_ip": "IP-OFFICE-HUB",
            "shared_device": "DEV-OFFICE-HUB",
            "hub_degree": len(d3_ids),
            "is_hub": True,
            "expected_disposition": "NO_ACTION",
        },
        alert_rows=[
            _alert(
                "ALERT-D3-001",
                "D3",
                d3_ids[0],
                "LOW",
                "NO_ACTION",
                "Shared office IP/device hub with approximately forty accounts",
            )
        ],
    )

    # ------------------------------------------------------------------ D4 --
    # This loop is intentionally out of chronological order.  It is useful for
    # proving that a topological cycle alone is not enough to call a ring.
    d4_ids = [f"D4-{number}" for number in range(401, 405)]
    add_accounts(
        _account(account_id, "D4", 4100 + i * 250, True, 0.71)
        for i, account_id in enumerate(d4_ids)
    )
    for i, account_id in enumerate(d4_ids):
        device_id = f"DEV-D4-{i + 1:02d}"
        ip_id = f"IP-D4-{i + 1:02d}"
        devices.append(
            _device(
                device_id,
                "D4",
                fingerprint_hash=f"fp_hash_d4_{i + 1:02d}",
                account_count=1,
                is_hub=False,
            )
        )
        ips.append(_ip(ip_id, "D4", region="US-Central", account_count=1, is_hub=False))
        device_links.append(_link(account_id, device_id, "D4"))
        ip_links.append(_link(account_id, ip_id, "D4"))
    d4_timestamps = [base_ts + 42000, base_ts + 39600, base_ts + 44400, base_ts + 38400]
    transfers.extend(
        _transfer(
            f"d4_tx_{i}",
            source,
            target,
            600 + i * 35,
            d4_timestamps[i - 1],
            "D4",
            transfer_kind="COINCIDENTAL_LOOP",
        )
        for i, (source, target) in enumerate(
            zip(d4_ids, d4_ids[1:] + d4_ids[:1]), start=1
        )
    )
    scenario(
        "D4",
        pattern="out_of_order_coincidental_loop",
        anchor=d4_ids[0],
        account_ids=d4_ids,
        expected={
            "cycle": True,
            "time_ordered": False,
            "cycle_hops": 4,
            "expected_disposition": "NO_ACTION",
        },
        alert_rows=[
            _alert(
                "ALERT-D4-401",
                "D4",
                d4_ids[0],
                "LOW",
                "NO_ACTION",
                "Coincidental loop with out-of-order timestamps",
            )
        ],
    )

    # ------------------------------------------------------------ Background --
    # A simple directed chain is bounded and cannot accidentally form a cycle.
    # Randomized values make the fixture's seed useful without changing its
    # known structural outcomes.
    noise_ids = [f"N-{number:03d}" for number in range(1, noise_accounts + 1)]
    noise_graph = nx.DiGraph()
    noise_graph.add_nodes_from(noise_ids)
    noise_graph.add_edges_from(zip(noise_ids, noise_ids[1:]))
    if not nx.is_directed_acyclic_graph(noise_graph):
        raise ValueError("deterministic background noise must remain acyclic")
    add_accounts(
        {
            **_account(
            account_id,
            "NOISE",
            monthly_volume=rng.randint(800, 12000),
            legit_activity=True,
            legit_activity_ratio=round(rng.uniform(0.72, 0.99), 3),
            is_noise=True,
            ),
            "synthetic_profile": faker.safe_email(),
        }
        for account_id in noise_ids
    )
    for i, account_id in enumerate(noise_ids):
        device_id = f"DEV-N-{i + 1:03d}"
        ip_id = f"IP-N-{i + 1:03d}"
        devices.append(
            _device(
                device_id,
                "NOISE",
                fingerprint_hash=f"fp_hash_noise_{i + 1:03d}",
                account_count=1,
                is_hub=False,
            )
        )
        ips.append(_ip(ip_id, "NOISE", region="US-East", account_count=1, is_hub=False))
        device_links.append(_link(account_id, device_id, "NOISE"))
        ip_links.append(_link(account_id, ip_id, "NOISE"))
    transfers.extend(
        _transfer(
            f"noise_tx_{i}",
            source,
            target,
            rng.randint(50, 800),
            base_ts + 60000 + i * 300,
            "NOISE",
            transfer_kind="LEGITIMATE",
        )
        for i, (source, target) in enumerate(noise_graph.edges(), start=1)
    )
    scenarios["NOISE"] = {
        "pattern": "bounded_background_chain",
        "anchor": noise_ids[0] if noise_ids else None,
        "account_ids": noise_ids,
        "alert_ids": [],
        "expected": {
            "cycle": False,
            "max_accounts": MAX_NOISE_ACCOUNTS,
            "expected_disposition": "NO_ACTION",
        },
    }

    # Stable ordering is important both for reproducibility and for readable
    # diffs in the checked-in ground-truth file.
    return {
        "config": {
            "seed": seed,
            "base_ts": base_ts,
            "noise_accounts": noise_accounts,
            "max_noise_accounts": MAX_NOISE_ACCOUNTS,
        },
        "accounts": accounts,
        "devices": devices,
        "ips": ips,
        "alerts": alerts,
        "transfers": transfers,
        "device_links": device_links,
        "ip_links": ip_links,
        "scenarios": scenarios,
    }


# Friendly alias for callers that call the function a generator rather than a
# fixture builder.
generate_fixture = build_fixture


def ground_truth_document(fixture: Mapping[str, Any]) -> Dict[str, Any]:
    """Create the small, machine-readable expected-outcomes document."""

    rows_for_digest = {
        key: fixture[key]
        for key in (
            "accounts",
            "devices",
            "ips",
            "alerts",
            "transfers",
            "device_links",
            "ip_links",
        )
    }
    canonical = json.dumps(rows_for_digest, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema_version": 1,
        "generator": "data/generate_demo.py",
        "fixture_sha256": hashlib.sha256(canonical).hexdigest(),
        "config": dict(fixture["config"]),
        "scenario_field_notes": {
            "monthly_volume": "deterministic monthly account volume in USD-like demo units",
            "legit_activity": "boolean indicating whether activity is expected to be legitimate",
            "legit_activity_ratio": "deterministic 0..1 legitimate-activity share",
            "hub_degree": "expected account degree for the infrastructure node",
            "is_hub": "whether high-degree infrastructure should be pruned as a hub",
            "is_shared_hub": "compatibility alias for shared IP/device hub metadata",
        },
        "scenarios": fixture["scenarios"],
        "counts": {
            "accounts": len(fixture["accounts"]),
            "devices": len(fixture["devices"]),
            "ips": len(fixture["ips"]),
            "alerts": len(fixture["alerts"]),
            "transfers": len(fixture["transfers"]),
        },
    }


def write_ground_truth(
    fixture: Mapping[str, Any], path: Path | str = DEFAULT_GROUND_TRUTH_PATH
) -> Path:
    """Write ground truth atomically and return its path."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(ground_truth_document(fixture), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def _chunks(rows: List[Dict[str, Any]], size: int = 200) -> Iterable[List[Dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _write_nodes(graph: Any, label: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    query = f"""
    UNWIND $rows AS row
    MERGE (n:{label} {{id: row.id}})
    SET n += row
    """
    for chunk in _chunks(rows):
        graph.query(query, {"rows": chunk})


def _write_links(graph: Any, relationship: str, rows: List[Dict[str, str]], target_label: str) -> None:
    if not rows:
        return
    query = f"""
    UNWIND $rows AS row
    MATCH (a:Account {{id: row.source}}), (target:{target_label} {{id: row.target}})
    MERGE (a)-[r:{relationship}]->(target)
    SET r.scenario = row.scenario
    """
    for chunk in _chunks(rows):
        graph.query(query, {"rows": chunk})


def _write_transfers(graph: Any, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    query = """
    UNWIND $rows AS row
    MATCH (source:Account {id: row.source}), (target:Account {id: row.target})
    MERGE (source)-[r:SENT_MONEY {id: row.id}]->(target)
    SET r.amount = row.amount,
        r.ts = row.ts,
        r.scenario = row.scenario,
        r.transfer_kind = row.transfer_kind
    """
    for chunk in _chunks(rows):
        graph.query(query, {"rows": chunk})


def _write_alerts(graph: Any, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    query = """
    UNWIND $rows AS row
    MERGE (alert:Alert {id: row.id})
    SET alert += row
    WITH alert, row
    MATCH (account:Account {id: row.entity_id})
    MERGE (alert)-[:ABOUT]->(account)
    """
    for chunk in _chunks(rows):
        graph.query(query, {"rows": chunk})


def seed_database(
    *,
    host: Optional[str] = None,
    port: Optional[int] = None,
    graph_name: Optional[str] = None,
    reset_graph: Optional[bool] = None,
    fixture: Optional[Mapping[str, Any]] = None,
    ground_truth_path: Path | str = DEFAULT_GROUND_TRUTH_PATH,
) -> Dict[str, Any]:
    """Write fixture rows to FalkorDB and return a seed summary.

    FalkorDB is imported lazily so pure generation and ground-truth tests work
    when the database client or server is unavailable.  Connection/query
    failures are intentionally propagated to the CLI, which reports the
    database-dependent gap without pretending that graph seeding succeeded.
    """

    settings = configuration_from_env()
    fixture = fixture or build_fixture(
        seed=settings["seed"],
        base_ts=settings["base_ts"],
        noise_accounts=settings["noise_accounts"],
    )
    written_ground_truth = write_ground_truth(fixture, ground_truth_path)

    # Keep this import out of module import time: offline fixture tests should
    # not require a live FalkorDB installation.
    from falkordb import FalkorDB  # type: ignore

    db = FalkorDB(host=host or settings["db_host"], port=port or settings["db_port"])
    selected_graph_name = graph_name or settings["graph_name"]
    graph = db.select_graph(selected_graph_name)
    should_reset = settings["reset_graph"] if reset_graph is None else reset_graph

    if should_reset:
        try:
            graph.delete()
        except Exception as exc:
            # An absent graph is harmless; a subsequent write/query will make
            # an unavailable server fail loudly rather than silently passing.
            print(f"[i] Graph reset skipped ({exc}); continuing with MERGE writes", file=sys.stderr)
        graph = db.select_graph(selected_graph_name)

    for index_query in (
        "CREATE INDEX FOR (a:Account) ON (a.id)",
        "CREATE INDEX FOR (d:Device) ON (d.id)",
        "CREATE INDEX FOR (i:IPAddress) ON (i.id)",
        "CREATE INDEX FOR (al:Alert) ON (al.id)",
    ):
        try:
            graph.query(index_query)
        except Exception as exc:
            # Index creation is an optimization and can legitimately report an
            # already-existing index when reset_graph is disabled.
            print(f"[i] Index setup skipped ({exc})", file=sys.stderr)

    _write_nodes(graph, "Account", list(fixture["accounts"]))
    _write_nodes(graph, "Device", list(fixture["devices"]))
    _write_nodes(graph, "IPAddress", list(fixture["ips"]))
    _write_links(graph, "USES_DEVICE", list(fixture["device_links"]), "Device")
    _write_links(graph, "USED_IP", list(fixture["ip_links"]), "IPAddress")
    _write_transfers(graph, list(fixture["transfers"]))
    _write_alerts(graph, list(fixture["alerts"]))

    return {
        "graph_name": selected_graph_name,
        "reset_graph": should_reset,
        "ground_truth_path": str(written_ground_truth),
        "counts": ground_truth_document(fixture)["counts"],
        "seed": fixture["config"]["seed"],
    }


def main() -> int:
    """Seed FalkorDB, or report a clear database-dependent gap."""

    try:
        summary = seed_database()
    except Exception as exc:
        # Generation and ground truth remain useful without FalkorDB.  Ensure
        # the file is present even if importing/connecting to the client failed.
        try:
            settings = configuration_from_env()
            path = write_ground_truth(
                build_fixture(
                    seed=settings["seed"],
                    base_ts=settings["base_ts"],
                    noise_accounts=settings["noise_accounts"],
                )
            )
        except Exception as generation_exc:
            print(f"[!] Fixture generation failed: {generation_exc}", file=sys.stderr)
            return 2
        print(f"[!] FalkorDB unavailable; graph seed not completed: {exc}", file=sys.stderr)
        print(f"[+] Pure fixture and ground truth are available at {path}")
        return 2

    print(
        f"[+] Seeded FalkorDB graph {summary['graph_name']!r} with "
        f"{summary['counts']['accounts']} accounts, "
        f"{summary['counts']['transfers']} transfers (seed={summary['seed']})."
    )
    print(f"[+] Ground truth: {summary['ground_truth_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
