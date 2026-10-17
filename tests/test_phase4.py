from apps.actions.executor import ActionExecutor

def test_phase4():
    executor = ActionExecutor()
    entity_id = "A-104"

    print("\n--- 1. Executing Hold Action on A-104 ---")
    action_payload = {
        "target_entity": entity_id,
        "type": "APPLY_HOLD"
    }
    
    exec_result = executor.execute_action(action_payload)
    print(f"Action Success: {exec_result['success']}")
    print(f"Audit ID Created: {exec_result['audit_id']}")
    print(f"Verified Node Status: {exec_result['verified_status']}")
    
    assert exec_result["success"] is True
    assert exec_result["verified_status"] == "HOLD"

    print("\n--- 2. Rolling Back Action ---")
    audit_id = exec_result["audit_id"]
    rollback_result = executor.rollback_action(audit_id)
    
    print(f"Rollback Success: {rollback_result['success']}")
    print(f"Rollback Audit ID: {rollback_result['audit_id']}")
    print(f"Verified Node Status (Restored): {rollback_result['verified_status']}")

    assert rollback_result["success"] is True
    assert rollback_result["verified_status"] == "ACTIVE"

    print("\n[+] Phase 4 Passed: Action execution, state verification, and rollback are fully functional.")

if __name__ == "__main__":
    test_phase4()