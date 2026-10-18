"""Contracts shared by the graph tools and deterministic policy engine."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr


class StrictModel(BaseModel):
    """Fail closed at the graph/evidence boundary."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class NodeSummary(StrictModel):
    id: StrictStr
    label: StrictStr
    properties: Dict[StrictStr, Any] = Field(default_factory=dict)


class EdgeSummary(StrictModel):
    source: StrictStr
    target: StrictStr
    relationship: StrictStr
    properties: Dict[StrictStr, Any] = Field(default_factory=dict)


class SubgraphResult(StrictModel):
    nodes: List[NodeSummary] = Field(default_factory=list)
    edges: List[EdgeSummary] = Field(default_factory=list)


class EntitySummary(StrictModel):
    entity_id: StrictStr
    label: StrictStr = "Account"
    properties: Dict[StrictStr, Any] = Field(default_factory=dict)
    direct_neighbors: List[NodeSummary] = Field(default_factory=list)

    @property
    def neighbors(self) -> List[NodeSummary]:
        return self.direct_neighbors


class EntitySummaryResult(EntitySummary):
    pass


class EntitySummaryRequest(StrictModel):
    entity_id: StrictStr
    limit: StrictInt = Field(default=50, ge=1, le=1000)


class NeighborhoodRequest(StrictModel):
    entity_id: StrictStr
    max_hops: StrictInt = Field(default=2, ge=1, le=4)
    hub_cutoff: StrictInt = Field(default=20, ge=2, le=1000)
    limit: StrictInt = Field(default=50, ge=1, le=1000)
    rel_allowlist: List[Literal["USES_DEVICE", "USED_IP", "SENT_MONEY"]] = Field(
        default_factory=lambda: ["USES_DEVICE", "USED_IP", "SENT_MONEY"]
    )


class NeighborhoodSubgraphResult(SubgraphResult):
    """Long-form alias for the bounded explorer result."""


class NeighborhoodResult(SubgraphResult):
    entity_id: StrictStr
    max_hops: StrictInt
    hub_cutoff: StrictInt
    truncated: StrictBool = False
    hub_nodes: List[StrictStr] = Field(default_factory=list)


class SharedInfrastructureRequest(StrictModel):
    entity_id: StrictStr
    kind: Literal["device", "ip"] = "device"
    window_seconds: StrictInt = Field(default=86400, ge=0, le=31_536_000)
    min_accounts: StrictInt = Field(default=2, ge=2, le=1000)
    hub_cutoff: StrictInt = Field(default=20, ge=2, le=1000)
    limit: StrictInt = Field(default=50, ge=1, le=1000)


class SharedInfraResult(StrictModel):
    entity_id: StrictStr
    infrastructure_id: StrictStr
    infrastructure_type: Literal["Device", "IPAddress"]
    connected_accounts: List[StrictStr] = Field(default_factory=list)
    is_hub: StrictBool = False
    hub_degree: StrictInt = 0
    window_seconds: StrictInt = 0

    @property
    def account_count(self) -> int:
        return len(self.connected_accounts) + 1


class SharedInfrastructureResult(SharedInfraResult):
    pass


class MoneyPath(StrictModel):
    """Input contract alias retained for tool registries."""

    source_id: StrictStr
    target_id: Optional[StrictStr] = None
    max_hops: StrictInt = Field(default=4, ge=1, le=6)
    window_seconds: StrictInt = Field(default=86_400, ge=0, le=31_536_000)
    min_amount: StrictFloat = Field(default=0.0, ge=0.0)
    limit: StrictInt = Field(default=50, ge=1, le=1000)


class MoneyPathRequest(StrictModel):
    source_id: StrictStr
    target_id: Optional[StrictStr] = None
    max_hops: StrictInt = Field(default=4, ge=1, le=6)
    window_seconds: StrictInt = Field(default=86_400, ge=0, le=31_536_000)
    min_amount: StrictFloat = Field(default=0.0, ge=0.0)
    limit: StrictInt = Field(default=50, ge=1, le=1000)


class MoneyPathResult(StrictModel):
    source_id: StrictStr
    target_id: StrictStr
    path_nodes: List[StrictStr] = Field(min_length=2)
    amounts: List[StrictFloat] = Field(min_length=1)
    timestamps: List[StrictInt] = Field(min_length=1)
    is_time_ordered: StrictBool
    time_window_seconds: StrictInt = Field(ge=0)
    target_confirmed_bad: StrictBool = False
    transfer_kinds: List[StrictStr] = Field(default_factory=list)


class TransferPathResult(MoneyPathResult):
    pass


class CycleRequest(StrictModel):
    entity_id: StrictStr
    min_len: StrictInt = Field(default=3, ge=3, le=6)
    max_len: StrictInt = Field(default=6, ge=3, le=6)
    window_seconds: StrictInt = Field(default=86_400, ge=0, le=31_536_000)
    time_ordered: StrictBool = True
    limit: StrictInt = Field(default=50, ge=1, le=1000)


class CycleResult(StrictModel):
    entity_id: StrictStr
    cycle_nodes: List[StrictStr] = Field(min_length=4)
    amounts: List[StrictFloat] = Field(min_length=3)
    timestamps: List[StrictInt] = Field(min_length=3)
    is_time_ordered: StrictBool
    time_window_seconds: StrictInt = Field(default=86_400, ge=0)


class EvidenceItem(StrictModel):
    id: StrictStr
    kind: StrictStr
    query_name: StrictStr
    summary: StrictStr
    data: Dict[StrictStr, Any] = Field(default_factory=dict)
    flagged: StrictBool = False
    result_hash: Optional[StrictStr] = None


class EvidenceBundle(StrictModel):
    entity_id: StrictStr
    items: List[EvidenceItem] = Field(default_factory=list)
    policy_version: StrictStr = "2026-10-v1"
