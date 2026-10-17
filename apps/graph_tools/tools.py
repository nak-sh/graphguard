import hashlib
from typing import List, Optional
from falkordb import FalkorDB
from apps.graph_tools.models import (
    SubgraphResult, NodeSummary, EdgeSummary,
    SharedInfraResult, CycleResult, EvidenceItem
)

class GraphTools:
    def __init__(self, host: str = "localhost", port: int = 6379, graph_name: str = "graphguard"):
        self.db = FalkorDB(host=host, port=port)
        self.g = self.db.select_graph(graph_name)

    def _generate_evidence_id(self, query_name: str, key: str) -> str:
        return f"EV-{query_name[:3].upper()}-{hashlib.md5(key.encode()).hexdigest()[:6]}"

    def get_neighborhood(self, entity_id: str, max_hops: int = 2, limit: int = 50) -> SubgraphResult:
        query = f"""
        MATCH (a:Account {{id: $entity_id}})
        OPTIONAL MATCH p = (a)-[r*1..{max_hops}]-(m)
        RETURN p
        LIMIT $limit
        """
        result = self.g.query(query, {'entity_id': entity_id, 'limit': limit})
        
        nodes_dict = {}
        edges_list = []

        for row in result.result_set:
            path = row[0]
            if not path:
                continue
            for node in path.nodes:
                if node.properties.get("id") not in nodes_dict:
                    nodes_dict[node.properties.get("id")] = NodeSummary(
                        id=str(node.properties.get("id")),
                        label=node.labels[0] if node.labels else "Unknown",
                        properties=dict(node.properties)
                    )
            for rel in path.relationships:
                edges_list.append(EdgeSummary(
                    source=str(rel.src_node.properties.get("id")),
                    target=str(rel.dest_node.properties.get("id")),
                    relationship=rel.relation,
                    properties=dict(rel.properties)
                ))

        return SubgraphResult(nodes=list(nodes_dict.values()), edges=edges_list)

    def find_shared_infrastructure(self, entity_id: str, hub_cutoff: int = 20) -> List[SharedInfraResult]:
        query = """
        MATCH (a:Account {id: $entity_id})-[:USES_DEVICE]->(d:Device)<-[:USES_DEVICE]-(other:Account)
        WHERE other.id <> a.id
        WITH d, collect(DISTINCT other.id) AS others
        RETURN d.id AS device_id, others, size(others) AS total_count
        """
        result = self.g.query(query, {'entity_id': entity_id})
        infra_results = []

        for row in result.result_set:
            device_id, others, total_count = row[0], row[1], row[2]
            is_hub = (total_count + 1) >= hub_cutoff
            infra_results.append(SharedInfraResult(
                entity_id=entity_id,
                infrastructure_id=device_id,
                infrastructure_type="Device",
                connected_accounts=others,
                is_hub=is_hub
            ))
        return infra_results

    def detect_transfer_cycles(self, entity_id: str, min_hops: int = 3, max_hops: int = 6) -> List[CycleResult]:
        query = f"""
        MATCH p = (a:Account {{id: $entity_id}})-[:SENT_MONEY*{min_hops}..{max_hops}]->(a)
        RETURN [n IN nodes(p) | n.id] AS cycle_nodes,
               [r IN relationships(p) | r.amount] AS amounts,
               [r IN relationships(p) | r.ts] AS timestamps
        """
        result = self.g.query(query, {'entity_id': entity_id})
        cycles = []

        for row in result.result_set:
            nodes, amounts, timestamps = row[0], row[1], row[2]
            ts_list = [int(t) for t in timestamps]
            amt_list = [float(a) for a in amounts]

            # Detect monotonically increasing (forward) or decreasing (reverse unrolling)
            is_fwd = all(ts_list[i] <= ts_list[i+1] for i in range(len(ts_list)-1))
            is_rev = all(ts_list[i] >= ts_list[i+1] for i in range(len(ts_list)-1))
            is_ordered = is_fwd or is_rev

            # Normalize to chronological order if returned in reverse traversal order
            if is_rev and not is_fwd:
                ts_list.reverse()
                amt_list.reverse()
                nodes = list(reversed(nodes))

            cycles.append(CycleResult(
                entity_id=entity_id,
                cycle_nodes=nodes,
                amounts=amt_list,
                timestamps=ts_list,
                is_time_ordered=is_ordered
            ))
        return cycles