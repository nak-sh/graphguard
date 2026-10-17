"""test_cypher_spike.py"""
from falkordb import FalkorDB

def test_spike():
    db = FalkorDB(host="localhost", port=6379)
    g = db.select_graph("graphguard")

    # 1. Test Shared Infrastructure
    shared_device_query = """
    MATCH (a:Account {id: $entity_id})-[:USES_DEVICE]->(d:Device)<-[:USES_DEVICE]-(other:Account)
    WHERE other.id <> a.id
    RETURN d.id AS device, collect(DISTINCT other.id) AS shared_accounts
    """
    
    t1_infra = g.query(shared_device_query, {'entity_id': 'A-104'}).result_set
    print(f"\n[A-104 Shared Accounts]: {t1_infra[0][1] if t1_infra else 'None'}")
    assert len(t1_infra[0][1]) == 4, "A-104 should share a device with 4 accounts"

    # 2. Test Time-Ordered Transfer Cycle (min 3 hops, max 6 hops)
    cycle_query = """
    MATCH p = (a:Account {id: $entity_id})-[:SENT_MONEY*3..6]->(a)
    RETURN [n IN nodes(p) | n.id] AS cycle_nodes,
           [r IN relationships(p) | r.amount] AS amounts,
           [r IN relationships(p) | r.ts] AS timestamps
    """
    
    t1_cycles = g.query(cycle_query, {'entity_id': 'A-104'}).result_set
    print(f"[A-104 Cycle Nodes]: {t1_cycles[0][0] if t1_cycles else 'None'}")
    assert len(t1_cycles) > 0, "A-104 must return a detected cycle"

    # 3. Test Decoy D-201 (Must NOT trigger the cycle query)
    d1_cycles = g.query(cycle_query, {'entity_id': 'D-201'}).result_set
    print(f"[D-201 Cycles Found]: {len(d1_cycles)}")
    assert len(d1_cycles) == 0, "D-201 bilateral transfers must not trigger a 3+ hop cycle"

    print("\n[+] Hour-One Cypher Spike Passed: Graph logic is verified on FalkorDB.")

if __name__ == "__main__":
    test_spike()
    