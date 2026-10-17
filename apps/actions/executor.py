import time
import uuid
from typing import Dict, Any
from falkordb import FalkorDB

class ActionExecutor:
    def __init__(self, host: str = "localhost", port: int = 6379, graph_name: str = "graphguard"):
        self.db = FalkorDB(host=host, port=port)
        self.g = self.db.select_graph(graph_name)

    def execute_action(self, action: Dict[str, Any], idempotency_key: str = None) -> Dict[str, Any]:
        if not idempotency_key:
            idempotency_key = f"IDEM-{uuid.uuid4().hex}"

        entity_id = action["target_entity"]
        action_type = action["type"]
        
        # 1. Get previous state
        prev_query = "MATCH (a:Account {id: $id}) RETURN a.status"
        res = self.g.query(prev_query, {"id": entity_id}).result_set
        if not res:
            return {"success": False, "error": "Entity not found"}
        prev_status = res[0][0]

        # 2. Determine new state
        new_status = "HOLD" if action_type == "APPLY_HOLD" else "UNDER_REVIEW"

        # 3. Mutate graph & write audit event node
        audit_id = f"AUDIT-{uuid.uuid4().hex[:8]}"
        ts = int(time.time())
        
        mutate_query = """
        MATCH (a:Account {id: $entity_id})
        SET a.status = $new_status
        CREATE (ev:AuditEvent {
            id: $audit_id, 
            ts: $ts, 
            action: $action_type, 
            prev_state: $prev_status, 
            new_state: $new_status, 
            idempotency_key: $idempotency_key
        })
        CREATE (ev)-[:TARGETED]->(a)
        """
        self.g.query(mutate_query, {
            "entity_id": entity_id,
            "new_status": new_status,
            "audit_id": audit_id,
            "ts": ts,
            "action_type": action_type,
            "prev_status": prev_status,
            "idempotency_key": idempotency_key
        })

        # 4. Verify mutation landed by re-querying FalkorDB
        verify_res = self.g.query(prev_query, {"id": entity_id}).result_set
        actual_status = verify_res[0][0]
        
        return {
            "success": actual_status == new_status,
            "entity_id": entity_id,
            "audit_id": audit_id,
            "verified_status": actual_status
        }

    def rollback_action(self, audit_id: str) -> Dict[str, Any]:
        # 1. Fetch Audit Event and original previous state
        fetch_query = """
        MATCH (ev:AuditEvent {id: $audit_id})-[:TARGETED]->(a:Account)
        RETURN ev.prev_state, a.id, ev.action
        """
        res = self.g.query(fetch_query, {"audit_id": audit_id}).result_set
        if not res:
            return {"success": False, "error": "Audit event not found"}
        
        prev_state, entity_id, original_action = res[0]

        # 2. Restore state & record rollback audit
        new_audit_id = f"ROLLBACK-{uuid.uuid4().hex[:8]}"
        ts = int(time.time())
        
        restore_query = """
        MATCH (a:Account {id: $entity_id})
        SET a.status = $prev_state
        CREATE (ev:AuditEvent {
            id: $new_audit_id,
            ts: $ts,
            action: 'ROLLBACK',
            prev_state: a.status,
            new_state: $prev_state,
            rolled_back_audit_id: $audit_id
        })
        CREATE (ev)-[:TARGETED]->(a)
        """
        self.g.query(restore_query, {
            "entity_id": entity_id,
            "prev_state": prev_state,
            "new_audit_id": new_audit_id,
            "ts": ts,
            "audit_id": audit_id
        })
        
        # 3. Verify restoration
        verify_query = "MATCH (a:Account {id: $id}) RETURN a.status"
        verify_res = self.g.query(verify_query, {"id": entity_id}).result_set
        actual_status = verify_res[0][0]

        return {
            "success": actual_status == prev_state,
            "entity_id": entity_id,
            "audit_id": new_audit_id,
            "verified_status": actual_status
        }