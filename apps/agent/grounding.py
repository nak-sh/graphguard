"""Evidence-grounding checks for narratives and copilot responses."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


ID_PATTERN = re.compile(r"\b(?:A|D|T[23]|N|DEV|IP|ALERT|INCIDENT|EV|ACT|AUDIT|GW|ROLLBACK)-[A-Za-z0-9_.:-]+\b")
AMOUNT_PATTERN = re.compile(r"(?<![A-Za-z0-9-])\$?\d+(?:\.\d+)?(?![A-Za-z0-9-])")


@dataclass(frozen=True)
class GroundingResult:
    grounded: bool
    violations: tuple[str, ...]
    allowed_ids: tuple[str, ...]
    allowed_amounts: tuple[float, ...]


def _evidence_facts(evidence: Sequence[Mapping[str, Any]]) -> tuple[set[str], set[float]]:
    ids: set[str] = set()
    amounts: set[float] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key in {"id", "entity_id", "source_id", "target_id", "cycle_nodes", "path_nodes", "connected_accounts", "infrastructure_id"}:
                    if isinstance(child, str):
                        ids.add(child)
                    elif isinstance(child, (list, tuple)):
                        ids.update(str(item) for item in child if item is not None)
                if key in {"amount", "amounts", "monthly_volume"}:
                    if isinstance(child, (int, float)) and not isinstance(child, bool):
                        amounts.add(float(child))
                    elif isinstance(child, (list, tuple)):
                        amounts.update(float(item) for item in child if isinstance(item, (int, float)) and not isinstance(item, bool))
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(evidence)
    return ids, amounts


def check_grounding(text: str, evidence: Sequence[Mapping[str, Any]]) -> GroundingResult:
    allowed_ids, allowed_amounts = _evidence_facts(evidence)
    violations: list[str] = []
    for value in ID_PATTERN.findall(text):
        if value not in allowed_ids and not value.startswith(("EV-", "ACT-", "AUDIT-", "INCIDENT-", "GW-", "ROLLBACK-")):
            violations.append(f"unsupported id: {value}")
    for raw in AMOUNT_PATTERN.findall(text):
        number = float(raw.replace("$", ""))
        # Scores, thresholds and counts are narrative metadata. Large or
        # decimal transfer amounts are checked against the evidence facts.
        if number not in allowed_amounts and (number >= 1000 or "." in raw):
            violations.append(f"unsupported amount: {raw}")
    return GroundingResult(not violations, tuple(violations), tuple(sorted(allowed_ids)), tuple(sorted(allowed_amounts)))
