from typing import List, Dict, Any
from pydantic import BaseModel
from apps.graph_tools.models import SharedInfraResult, CycleResult

class ScoringResult(BaseModel):
    score: int
    tier: str  # "AUTO_HOLD", "MANUAL_REVIEW", "NO_ACTION"
    signals: List[Dict[str, Any]]
    explanation: str

def score_investigation(
    entity_id: str,
    infra_evidence: List[SharedInfraResult],
    cycle_evidence: List[CycleResult]
) -> ScoringResult:
    score = 0
    signals = []

    # 1. Evaluate Cycles (Weight: +40 for time-ordered)
    valid_cycles = [c for c in cycle_evidence if c.is_time_ordered]
    if valid_cycles:
        score += 40
        signals.append({
            "rule": "TIME_ORDERED_CYCLE",
            "weight": 40,
            "description": f"Found time-ordered money-flow cycle across {len(valid_cycles[0].cycle_nodes)-1} accounts."
        })

    # 2. Evaluate Shared Infrastructure
    for infra in infra_evidence:
        if infra.is_hub:
            signals.append({
                "rule": "HUB_DEVICE_IGNORED",
                "weight": 0,
                "description": f"Device {infra.infrastructure_id} exceeded hub threshold; ignored."
            })
            continue

        num_accounts = len(infra.connected_accounts) + 1
        if num_accounts >= 3:
            score += 25
            signals.append({
                "rule": "SHARED_DEVICE_CLUSTER",
                "weight": 25,
                "description": f"Shared device {infra.infrastructure_id} linked to {num_accounts} accounts."
            })
        elif num_accounts == 2 and not valid_cycles:
            # Household / Decoy Mitigator (-15)
            score -= 15
            signals.append({
                "rule": "HOUSEHOLD_MITIGATOR",
                "weight": -15,
                "description": f"Shared device {infra.infrastructure_id} used only by 2 accounts with no cycles."
            })

    # 3. Determine Action Tier
    # >= 70: Hold Eligible, 40-69: Review, < 40: No Action
    if score >= 70:
        tier = "AUTO_HOLD"
        explanation = f"Entity {entity_id} flagged for immediate hold based on critical structural patterns."
    elif score >= 40:
        tier = "MANUAL_REVIEW"
        explanation = f"Entity {entity_id} requires manual review; moderate risk signals present."
    else:
        tier = "NO_ACTION"
        explanation = f"Entity {entity_id} cleared or below operational threshold. Decoys respected."

    return ScoringResult(
        score=max(0, score),
        tier=tier,
        signals=signals,
        explanation=explanation
    )