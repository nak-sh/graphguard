"""Pure policy and incident guardrails used by the action executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class LimitDecision:
    allowed: bool
    reason: Optional[str] = None
    count: int = 0
    last_ts: Optional[float] = None


def validate_policy_tier(action_type: str, policy_tier: Optional[str] = None,
                         *, approved: bool = True) -> bool:
    if not approved:
        return False
    if policy_tier is None:
        return True
    tier, action = policy_tier.upper(), action_type.upper()
    if tier == "AUTO_HOLD":
        return action in {"APPLY_HOLD", "HOLD"}
    if tier == "MANUAL_REVIEW":
        return action in {"FLAG_FOR_REVIEW", "RELEASE", "RELEASE_HOLD", "REMOVE_HOLD"}
    return False


def check_incident_limits(timestamps: Iterable[float], *, now: float,
                          cap: Optional[int] = None,
                          cooldown_seconds: Optional[float] = None) -> LimitDecision:
    values = [float(value) for value in timestamps if value is not None]
    count, last_ts = len(values), (max(values) if values else None)
    if cap is not None and cap >= 0 and count >= cap:
        return LimitDecision(False, "incident action cap reached", count, last_ts)
    if cooldown_seconds is not None and last_ts is not None:
        if float(now) - last_ts < cooldown_seconds:
            return LimitDecision(False, "incident action cooldown active", count, last_ts)
    return LimitDecision(True, None, count, last_ts)
