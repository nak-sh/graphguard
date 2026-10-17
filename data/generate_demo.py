"""generate_demo.py"""
import time
from falkordb import FalkorDB

def seed_database():
    db = FalkorDB(host="localhost", port=6379)
    g = db.select_graph("graphguard")

    # Clear existing graph
    try:
        g.delete()
    except Exception:
        pass
    g = db.select_graph("graphguard")

    print("[*] Creating indexes...")
    g.query("CREATE INDEX FOR (a:Account) ON (a.id)")
    g.query("CREATE INDEX FOR (d:Device) ON (d.id)")

    base_time = int(time.time())

    # ---------------------------------------------------------
    # Scenario T1: 5-Account Time-Ordered Laundering Ring
    # A104 -> A105 -> A106 -> A107 -> A108 -> A104
    # All link to shared device DEV-999
    # ---------------------------------------------------------
    print("[*] Injecting Scenario T1 (Planted Ring)...")
    g.query("""
        CREATE 
          (a104:Account {id: 'A-104', status: 'ACTIVE', tier: 'STANDARD'}),
          (a105:Account {id: 'A-105', status: 'ACTIVE', tier: 'STANDARD'}),
          (a106:Account {id: 'A-106', status: 'ACTIVE', tier: 'STANDARD'}),
          (a107:Account {id: 'A-107', status: 'ACTIVE', tier: 'STANDARD'}),
          (a108:Account {id: 'A-108', status: 'ACTIVE', tier: 'STANDARD'}),
          (dev:Device {id: 'DEV-999', fingerprint_hash: 'fp_hash_t1'}),
          (ip1:IPAddress {id: 'IP-10', region: 'US-East'}),
          (ip2:IPAddress {id: 'IP-20', region: 'US-West'}),
          (alert:Alert {id: 'ALERT-104', priority: 'HIGH', status: 'OPEN'}),

          (alert)-[:ABOUT]->(a104),
          (a104)-[:USES_DEVICE]->(dev),
          (a105)-[:USES_DEVICE]->(dev),
          (a106)-[:USES_DEVICE]->(dev),
          (a107)-[:USES_DEVICE]->(dev),
          (a108)-[:USES_DEVICE]->(dev),
          (a104)-[:USED_IP]->(ip1),
          (a105)-[:USED_IP]->(ip2),

          (a104)-[:SENT_MONEY {id: 'tx_1', amount: 9500, ts: $t0}]->(a105),
          (a105)-[:SENT_MONEY {id: 'tx_2', amount: 9400, ts: $t1}]->(a106),
          (a106)-[:SENT_MONEY {id: 'tx_3', amount: 9350, ts: $t2}]->(a107),
          (a107)-[:SENT_MONEY {id: 'tx_4', amount: 9200, ts: $t3}]->(a108),
          (a108)-[:SENT_MONEY {id: 'tx_5', amount: 9000, ts: $t4}]->(a104)
    """, {
        't0': base_time - 3600,
        't1': base_time - 3000,
        't2': base_time - 2400,
        't3': base_time - 1800,
        't4': base_time - 1200
    })

    # ---------------------------------------------------------
    # Scenario D1: Family Decoy (Household)
    # D201 <-> D202 share a device, small bilateral transactions
    # ---------------------------------------------------------
    print("[*] Injecting Scenario D1 (Decoy Household)...")
    g.query("""
        CREATE 
          (d201:Account {id: 'D-201', status: 'ACTIVE', tier: 'STANDARD'}),
          (d202:Account {id: 'D-202', status: 'ACTIVE', tier: 'STANDARD'}),
          (fdev:Device {id: 'DEV-FAMILY-1', fingerprint_hash: 'fp_hash_fam'}),
          (alert_d:Alert {id: 'ALERT-D201', priority: 'LOW', status: 'OPEN'}),

          (alert_d)-[:ABOUT]->(d201),
          (d201)-[:USES_DEVICE]->(fdev),
          (d202)-[:USES_DEVICE]->(fdev),

          (d201)-[:SENT_MONEY {id: 'dtx_1', amount: 45, ts: $t0}]->(d202),
          (d202)-[:SENT_MONEY {id: 'dtx_2', amount: 20, ts: $t1}]->(d201)
    """, {
        't0': base_time - 8000,
        't1': base_time - 4000
    })

    print("[+] Database seeded successfully with T1 and D1.")

if __name__ == "__main__":
    seed_database()
