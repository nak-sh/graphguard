from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class NodeSummary(BaseModel):
    id: str
    label: str
    properties: Dict[str, Any] = Field(default_factory=dict)

class EdgeSummary(BaseModel):
    source: str
    target: str
    relationship: str
    properties: Dict[str, Any] = Field(default_factory=dict)

class SubgraphResult(BaseModel):
    nodes: List[NodeSummary]
    edges: List[EdgeSummary]

class SharedInfraResult(BaseModel):
    entity_id: str
    infrastructure_id: str
    infrastructure_type: str  # "Device" or "IPAddress"
    connected_accounts: List[str]
    is_hub: bool = False

class CycleResult(BaseModel):
    entity_id: str
    cycle_nodes: List[str]
    amounts: List[float]
    timestamps: List[int]
    is_time_ordered: bool

class EvidenceItem(BaseModel):
    id: str
    kind: str  # "CYCLE", "SHARED_INFRA", "NEIGHBORHOOD"
    query_name: str
    summary: str
    data: Dict[str, Any]
    flagged: bool = False