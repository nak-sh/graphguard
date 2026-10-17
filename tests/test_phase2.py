import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from apps.graph_tools.tools import GraphTools
from apps.policy.scorer import score_investigation

def test_phase2():
    tools = GraphTools()

    # ----------------------------------------------------
    # Test A-104 (Planted Ring)
    # ----------------------------------------------------
    a104_infra = tools.find_shared_infrastructure("A-104")
    a104_cycles = tools.detect_transfer_cycles("A-104")
    a104_score = score_investigation("A-104", a104_infra, a104_cycles)

    print("\n--- A-104 Evaluation ---")
    print(f"Cycles Found: {len(a104_cycles)}")
    if a104_cycles:
        print(f"Cycle Nodes: {a104_cycles[0].cycle_nodes}")
        print(f"Timestamps: {a104_cycles[0].timestamps}")
        print(f"Is Time Ordered: {a104_cycles[0].is_time_ordered}")
    print(f"Shared Device Accounts: {len(a104_infra[0].connected_accounts) if a104_infra else 0}")
    print(f"Triggered Signals: {[s['rule'] for s in a104_score.signals]}")
    print(f"Final Score: {a104_score.score} | Tier: {a104_score.tier}")

    assert len(a104_cycles) > 0, "A-104 must have a detected cycle"
    assert a104_score.score >= 65, "A-104 must score high risk"

    # ----------------------------------------------------
    # Test D-201 (Family Decoy)
    # ----------------------------------------------------
    d201_infra = tools.find_shared_infrastructure("D-201")
    d201_cycles = tools.detect_transfer_cycles("D-201")
    d201_score = score_investigation("D-201", d201_infra, d201_cycles)

    print("\n--- D-201 Evaluation ---")
    print(f"Cycles Found: {len(d201_cycles)}")
    print(f"Shared Device Accounts: {len(d201_infra[0].connected_accounts) if d201_infra else 0}")
    print(f"Triggered Signals: {[s['rule'] for s in d201_score.signals]}")
    print(f"Final Score: {d201_score.score} | Tier: {d201_score.tier}")

    assert len(d201_cycles) == 0, "D-201 must have 0 cycles"
    assert d201_score.tier == "NO_ACTION", "D-201 decoy must result in NO_ACTION"

    print("\n[+] Phase 2 Passed: Deterministic tools and scoring verified.")

if __name__ == "__main__":
    test_phase2()