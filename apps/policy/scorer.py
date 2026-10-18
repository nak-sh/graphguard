"""Versioned, deterministic scoring over supplied evidence.

The scorer intentionally has no GraphTools dependency.  A stored evidence
bundle is the complete input, making a score reproducible after graph state
changes and safe to use in offline tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr

from apps.graph_tools.models import (
    CycleResult,
    EvidenceBundle,
    EvidenceItem,
    MoneyPathResult,
    SharedInfraResult,
)
from apps.graph_tools.tools import is_time_respecting_cycle, is_time_respecting_path

try:
    import yaml
except ImportError:  # pragma: no cover - JSON is valid YAML and remains a safe fallback
    yaml = None


POLICY_PATH = Path(__file__).with_name("policy.yaml")
DEFAULT_POLICY_VERSION = "2026-10-v1"


class PolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: StrictStr
    thresholds: dict[StrictStr, StrictInt]
    signals: dict[StrictStr, dict[StrictStr, Any]]
    parameters: dict[StrictStr, Any] = Field(default_factory=dict)


PolicyConfig = PolicyModel


class ScoringResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    score: StrictInt
    tier: StrictStr
    signals: List[dict[str, Any]]
    explanation: StrictStr
    policy_version: StrictStr = DEFAULT_POLICY_VERSION
    raw_score: StrictInt = 0


def load_policy(path: str | Path | None = None, version: str | None = None) -> PolicyModel:
    """Load and validate a versioned policy file on every explicit call."""

    policy_path = Path(path) if path is not None else POLICY_PATH
    raw_text = policy_path.read_text(encoding="utf-8")
    if yaml is not None:
        raw = yaml.safe_load(raw_text)
    else:
        raw = json.loads(raw_text)
    policy = PolicyModel.model_validate(raw)
    if version is not None and policy.version != version:
        raise ValueError(f"policy version {version!r} is not available (loaded {policy.version!r})")
    for key in ("high", "review"):
        if key not in policy.thresholds:
            raise ValueError(f"policy is missing thresholds.{key}")
    if policy.thresholds["review"] > policy.thresholds["high"]:
        raise ValueError("review threshold must not exceed high threshold")
    return policy


def _weight(policy: PolicyModel, rule: str) -> int:
    value = policy.signals.get(rule, {}).get("weight")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"policy signal {rule!r} has no numeric weight")
    return int(value)


def _signal(policy: PolicyModel, rule: str, description: str, *, count: int = 1) -> dict[str, Any]:
    return {"rule": rule, "weight": _weight(policy, rule) * count, "description": description, "count": count}


def _data_item(kind: str, data: Mapping[str, Any], query_name: str = "stored_evidence") -> EvidenceItem:
    return EvidenceItem(id=f"stored-{kind.lower()}", kind=kind, query_name=query_name, summary=kind, data=dict(data))


def _normalise_evidence(evidence: Iterable[Any]) -> list[tuple[str, Any]]:
    """Return typed legacy records and immutable EvidenceItems without querying."""

    normalised: list[tuple[str, Any]] = []
    for item in evidence:
        if isinstance(item, EvidenceBundle):
            normalised.extend(_normalise_evidence(item.items))
        elif isinstance(item, EvidenceItem):
            normalised.append((item.kind.upper(), item))
        elif isinstance(item, CycleResult):
            normalised.append(("CYCLE", item))
        elif isinstance(item, SharedInfraResult):
            normalised.append(("SHARED_INFRA", item))
        elif isinstance(item, MoneyPathResult):
            normalised.append(("MONEY_PATH", item))
        elif isinstance(item, Mapping):
            kind = str(item.get("kind", "UNKNOWN")).upper()
            data = item.get("data", item)
            normalised.append((kind, _data_item(kind, data if isinstance(data, Mapping) else {})))
        else:
            raise TypeError(f"unsupported evidence item {type(item).__name__}")
    return normalised


def _record_data(record: Any) -> Mapping[str, Any]:
    if isinstance(record, EvidenceItem):
        return record.data
    if isinstance(record, BaseModel):
        return record.model_dump()
    return record if isinstance(record, Mapping) else {}


def _record_cycle(record: Any) -> tuple[list[str], list[float], list[int], int] | None:
    if isinstance(record, CycleResult):
        return list(record.cycle_nodes), list(record.amounts), list(record.timestamps), record.time_window_seconds
    data = _record_data(record)
    timestamps = data.get("timestamps")
    if not isinstance(timestamps, (list, tuple)):
        return None
    nodes = [str(node) for node in data.get("cycle_nodes", data.get("path_nodes", []))]
    try:
        amounts = [float(amount) for amount in data.get("amounts", [])]
        times = [int(ts) for ts in timestamps]
        window = int(data.get("time_window_seconds", data.get("window_seconds", 86_400)))
    except (TypeError, ValueError):
        return None
    return nodes, amounts, times, window


def _record_path(record: Any) -> tuple[list[str], list[float], list[int], int] | None:
    if isinstance(record, MoneyPathResult):
        return list(record.path_nodes), list(record.amounts), list(record.timestamps), record.time_window_seconds
    data = _record_data(record)
    timestamps = data.get("timestamps")
    if not isinstance(timestamps, (list, tuple)):
        return None
    try:
        nodes = [str(node) for node in data.get("path_nodes", data.get("cycle_nodes", []))]
        amounts = [float(amount) for amount in data.get("amounts", [])]
        times = [int(ts) for ts in timestamps]
        window = int(data.get("time_window_seconds", data.get("window_seconds", 86_400)))
    except (TypeError, ValueError):
        return None
    return nodes, amounts, times, window


def _rapid_pass_through(path: tuple[list[str], list[float], list[int], int], policy: PolicyModel) -> bool:
    _, amounts, timestamps, _ = path
    if len(amounts) < 2 or len(timestamps) < 2:
        return False
    rapid_window = int(policy.parameters.get("rapid_window_seconds", 3600))
    tolerance = float(policy.parameters.get("rapid_amount_tolerance", 0.10))
    return any(
        0 <= timestamps[index + 1] - timestamps[index] <= rapid_window
        and abs(amounts[index + 1] - amounts[index]) <= max(abs(amounts[index]), 1.0) * tolerance
        for index in range(min(len(amounts), len(timestamps)) - 1)
    )


def _confirmed_bad(record: Any, kind: str, policy: PolicyModel) -> bool:
    data = _record_data(record)
    if kind in {"CONFIRMED_BAD_PROXIMITY", "BAD_PROXIMITY"}:
        return True
    if not bool(data.get("confirmed_bad", data.get("target_confirmed_bad", False))):
        return False
    path = _record_path(record)
    max_hops = int(policy.parameters.get("confirmed_bad_max_hops", 3))
    return path is None or len(path[0]) - 1 <= max_hops


def _payroll_fan_out(kind: str, record: Any) -> bool:
    data = _record_data(record)
    if kind in {"PAYROLL_FAN_OUT", "PAYROLL"}:
        return True
    transfer_kinds = data.get("transfer_kinds", [])
    if isinstance(transfer_kinds, (list, tuple)) and any(str(value).upper() == "PAYROLL" for value in transfer_kinds):
        return True
    pattern = str(data.get("pattern", data.get("subtype", ""))).lower()
    if pattern in {"payroll", "payroll_fan_out", "fan_out"}:
        return not bool(data.get("has_return_flow", data.get("return_flow", False)))
    outbound = data.get("outbound_count", data.get("fan_out_count"))
    if isinstance(outbound, int) and outbound >= 3:
        return not bool(data.get("has_return_flow", data.get("return_flow", False)))
    return False


def score_evidence(
    entity_id: str,
    evidence: EvidenceBundle | Iterable[Any],
    policy_version: str = DEFAULT_POLICY_VERSION,
    policy: PolicyModel | None = None,
) -> ScoringResult:
    """Score only the evidence passed by the caller; this function never queries."""

    if isinstance(evidence, EvidenceBundle):
        if evidence.entity_id != entity_id:
            raise ValueError("evidence entity_id does not match the scored entity")
        if policy_version == DEFAULT_POLICY_VERSION:
            policy_version = evidence.policy_version
        records = _normalise_evidence(evidence.items)
    else:
        records = _normalise_evidence(evidence)
    policy = policy or load_policy(version=policy_version)
    if policy.version != policy_version:
        raise ValueError(f"evidence requested policy {policy_version}, loaded {policy.version}")

    score = 0
    signals: list[dict[str, Any]] = []
    valid_cycles: list[tuple[list[str], list[float], list[int], int]] = []
    infra_records: list[tuple[str, SharedInfraResult | EvidenceItem]] = []

    for kind, record in records:
        if kind in {"CYCLE", "TRANSFER_CYCLE"}:
            data = _record_data(record)
            explicitly_ordered = data.get("is_time_ordered", True)
            cycle = _record_cycle(record)
            if explicitly_ordered is True and cycle and is_time_respecting_cycle(cycle[2], cycle[3]):
                valid_cycles.append(cycle)
        if kind in {"SHARED_INFRA", "SHARED_DEVICE", "SHARED_IP", "DEVICE", "IP", "IPADDRESS"}:
            infra_records.append((kind, record))

    if valid_cycles:
        weight = _weight(policy, "TIME_ORDERED_CYCLE")
        score += weight
        cycle = valid_cycles[0]
        signals.append(_signal(policy, "TIME_ORDERED_CYCLE", f"Found a time-respecting money cycle across {max(len(cycle[0]) - 1, 0)} transfers."))

    # A rapid pass-through is evaluated from the same cycle/path evidence.
    rapid = False
    for kind, record in records:
        data = _record_data(record)
        if bool(data.get("rapid_pass_through", False)):
            rapid = True
        path = _record_path(record)
        explicitly_ordered = data.get("is_time_ordered", True)
        if explicitly_ordered is True and path and (kind in {"CYCLE", "TRANSFER_CYCLE", "MONEY_PATH", "TRANSFER_PATH", "PATH"}) and _rapid_pass_through(path, policy):
            rapid = True
    if rapid:
        score += _weight(policy, "RAPID_PASS_THROUGH")
        signals.append(_signal(policy, "RAPID_PASS_THROUGH", "Inbound and outbound transfers are close in value and time."))

    # A long, rapid, non-circular chain is a review signal in its own right.
    # It is deliberately evaluated from the stored path evidence and does not
    # make a path equivalent to a proven fraud finding.
    if not valid_cycles and any(
        (path := _record_path(record)) is not None
        and len(path[0]) >= 4
        and kind in {"MONEY_PATH", "TRANSFER_PATH", "PATH"}
        for kind, record in records
    ):
        score += _weight(policy, "MULE_CHAIN")
        signals.append(_signal(policy, "MULE_CHAIN", "A multi-hop pass-through path remains open without a closing cycle."))

    household_candidate = False
    household_amount_ok = True
    for kind, record in infra_records:
        if isinstance(record, SharedInfraResult):
            count = record.account_count
            is_hub = record.is_hub
            infra_type = record.infrastructure_type
            infra_id = record.infrastructure_id
        else:
            data = _record_data(record)
            connected = data.get("connected_accounts", data.get("accounts", []))
            count = int(data.get("account_count", len(connected) + 1)) if isinstance(connected, (list, tuple)) else int(data.get("account_count", 0))
            is_hub = bool(data.get("is_hub", False))
            infra_type = str(data.get("infrastructure_type", data.get("kind", kind))).lower()
            infra_id = str(data.get("infrastructure_id", data.get("id", "infrastructure")))
        if is_hub:
            signals.append({"rule": "HUB_IGNORED", "weight": 0, "description": f"Infrastructure {infra_id} is a hub and was excluded from positive cluster signals.", "count": 1})
            continue
        if count >= 3 and str(infra_type).lower() in {"device", "shared_device"}:
            weight = _weight(policy, "SHARED_DEVICE_CLUSTER")
            score += weight
            signals.append(_signal(policy, "SHARED_DEVICE_CLUSTER", f"Non-hub device {infra_id} links {count} accounts."))
        elif count >= 3 and str(infra_type).lower() in {"ip", "ipaddress", "shared_ip"}:
            weight = _weight(policy, "SHARED_IP_CLUSTER")
            score += weight
            signals.append(_signal(policy, "SHARED_IP_CLUSTER", f"Non-hub IP {infra_id} links {count} accounts."))
        elif count == 2:
            household_candidate = True
            data = _record_data(record)
            amounts = data.get("amounts", [])
            if amounts:
                try:
                    household_amount_ok = household_amount_ok and max(float(amount) for amount in amounts) <= float(policy.parameters.get("household_max_amount", 500.0))
                except (TypeError, ValueError):
                    household_amount_ok = False

    if household_candidate and not valid_cycles and household_amount_ok:
        score += _weight(policy, "HOUSEHOLD_MITIGATOR")
        signals.append(_signal(policy, "HOUSEHOLD_MITIGATOR", "Only two accounts share infrastructure and no time-respecting cycle was found."))

    device_cluster = False
    ip_cluster = False
    for _, record in infra_records:
        data = _record_data(record)
        connected = data.get("connected_accounts", data.get("accounts", []))
        count = int(data.get("account_count", len(connected) + 1)) if isinstance(connected, (list, tuple)) else int(data.get("account_count", 0))
        is_hub = bool(data.get("is_hub", False))
        infra_type = str(data.get("infrastructure_type", data.get("kind", ""))).lower()
        if not is_hub and count >= 3 and infra_type in {"device", "shared_device"}:
            device_cluster = True
        if not is_hub and count >= 3 and infra_type in {"ip", "ipaddress", "shared_ip"}:
            ip_cluster = True
    if device_cluster and ip_cluster and not valid_cycles:
        score += _weight(policy, "SYNTHETIC_IDENTITY_CLUSTER")
        signals.append(_signal(policy, "SYNTHETIC_IDENTITY_CLUSTER", "Device and IP clusters independently cover the same non-hub accounts."))

    if any(_confirmed_bad(record, kind, policy) for kind, record in records):
        score += _weight(policy, "CONFIRMED_BAD_PROXIMITY")
        signals.append(_signal(policy, "CONFIRMED_BAD_PROXIMITY", "A supplied directed path reaches a confirmed-bad account within the policy hop limit."))

    if any(_payroll_fan_out(kind, record) for kind, record in records):
        score += _weight(policy, "PAYROLL_FAN_OUT")
        signals.append(_signal(policy, "PAYROLL_FAN_OUT", "One-to-many outbound flow has no supplied return flow."))

    raw_score = score
    score = max(0, score)
    high = policy.thresholds["high"]
    review = policy.thresholds["review"]
    if score >= high:
        tier = "AUTO_HOLD"
        explanation = f"Entity {entity_id} is hold-eligible at {score} points (high threshold {high})."
    elif score >= review:
        tier = "MANUAL_REVIEW"
        explanation = f"Entity {entity_id} requires review at {score} points (review threshold {review})."
    else:
        tier = "NO_ACTION"
        explanation = f"Entity {entity_id} remains below the review threshold ({review}); supplied mitigators and checked signals were recorded."
    return ScoringResult(score=score, raw_score=raw_score, tier=tier, signals=signals, explanation=explanation, policy_version=policy.version)


def score_investigation(
    entity_id: str,
    infra_evidence: Optional[Iterable[Any]] = None,
    cycle_evidence: Optional[Iterable[Any]] = None,
    *,
    evidence: Optional[EvidenceBundle | Iterable[Any]] = None,
    evidence_items: Optional[Iterable[Any]] = None,
    policy_version: str = DEFAULT_POLICY_VERSION,
) -> ScoringResult:
    """Compatibility facade for the v1 call shape and the v2 evidence API."""

    if evidence is not None and evidence_items is not None:
        raise ValueError("pass only one of evidence and evidence_items")
    if evidence is None:
        evidence = evidence_items
    if evidence is None:
        evidence = [*(infra_evidence or []), *(cycle_evidence or [])]
    return score_evidence(entity_id, evidence, policy_version=policy_version)


def explain_non_escalation(
    entity_id: str,
    evidence: EvidenceBundle | Iterable[Any],
    policy_version: str = DEFAULT_POLICY_VERSION,
) -> dict[str, Any]:
    """Return deterministic counterfactual context for a below-threshold score."""

    result = score_evidence(entity_id, evidence, policy_version=policy_version)
    policy = load_policy(version=policy_version)
    return {
        "entity_id": entity_id,
        "score": result.score,
        "tier": result.tier,
        "policy_version": policy.version,
        "thresholds": dict(policy.thresholds),
        "signals_checked": [rule for rule in policy.signals],
        "signals_triggered": [signal["rule"] for signal in result.signals],
        "explanation": result.explanation,
    }
