import time
from falkordb import FalkorDB

def run_benchmark():
    db = FalkorDB(host="localhost", port=6379)
    g = db.select_graph("graphguard")
    
    query = """
    MATCH p = (a:Account {id: 'A-104'})-[:SENT_MONEY*3..6]->(a)
    RETURN count(p)
    """
    
    print("Warming up engine...")
    for _ in range(5):
        g.query(query)
        
    print("Running Benchmark (30 iterations)...")
    latencies = []
    for _ in range(30):
        start = time.perf_counter()
        g.query(query)
        latencies.append((time.perf_counter() - start) * 1000)
        
    p50 = sorted(latencies)[15]
    p95 = sorted(latencies)[28]
    
    print(f"\nFalkorDB 3-to-6 Hop Cycle Query Latency:")
    print(f"p50: {p50:.2f} ms")
    print(f"p95: {p95:.2f} ms")

if __name__ == "__main__":
    run_benchmark()