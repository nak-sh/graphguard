from apps.agent.workflow import InvestigationWorkflow

def test_phase3():
    app = InvestigationWorkflow()

    # ----------------------------------------------------
    # Test A-104 (Ring) Workflow
    # ----------------------------------------------------
    res_a104 = app.run(alert_id="ALERT-104", entity_id="A-104")

    print("\n--- A-104 Workflow Output ---")
    print(f"Visited Tools: {res_a104['visited_tools']}")
    print(f"Evidence Count: {len(res_a104['evidence_items'])}")
    print(f"Final Score: {res_a104['score']} ({res_a104['tier']})")
    print(f"Proposed Actions: {res_a104['proposed_actions']}")
    print(f"Dry-Run Diff: {res_a104['dry_run_diff']}")
    print(f"Approval Status: {res_a104['approval_status']}")

    assert len(res_a104["evidence_items"]) >= 2
    assert res_a104["dry_run_diff"] is not None
    assert res_a104["dry_run_diff"]["proposed_state"]["status"] in ("HOLD", "UNDER_REVIEW")

    # ----------------------------------------------------
    # Test D-201 (Decoy) Workflow
    # ----------------------------------------------------
    res_d201 = app.run(alert_id="ALERT-D201", entity_id="D-201")

    print("\n--- D-201 Workflow Output ---")
    print(f"Final Score: {res_d201['score']} ({res_d201['tier']})")
    print(f"Proposed Actions: {res_d201['proposed_actions']}")
    print(f"Dry-Run Diff: {res_d201['dry_run_diff']}")

    assert res_d201["tier"] == "NO_ACTION"
    assert len(res_d201["proposed_actions"]) == 0
    assert res_d201["dry_run_diff"] is None

    print("\n[+] Phase 3 Passed: LangGraph agent workflow & dry-run planner verified.")

if __name__ == "__main__":
    test_phase3()