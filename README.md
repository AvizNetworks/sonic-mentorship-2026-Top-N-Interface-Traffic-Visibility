# 🚀 SONiC Top-N Interface Traffic Visibility Engine

A production-grade implementation of the `show interfaces top-n` feature for the SONiC Network Operating System, tailored for the LFX Mentorship 2026. 

This repository proves the capability to achieve zero-blocking, `O(N log N)` scaled traffic visibility across hundreds of high-density interfaces (400G/800G) without starving the Control-Plane CPU.

## 🎯 The "Zero-Blocking" Differentiator
Unlike basic Python loops sequentially fetching `100s` of OIDs (creating an N+1 query bottleneck that harms BGP/orchagent up-time), this implementation leverages **Redis Pipelining**. It bulk-fetches all `SAI_PORT_STAT_IF_IN_OCTETS` instantly.

## ✨ Core Features
- **High-Performance Ingestion:** Direct `redis-py` pipeline connections minimize round-trip database latency.
- **64-Bit Rollover Native Handling:** 400G+ ASIC counters overflow their 32/64-bit boundaries rapidly. The math engine natively computes theoretical maximum distances to prevent negative bandwidth metrics.
- **O(N log N) Sorting:** Relies entirely on optimized Python Timsort over total throughput (RX + TX) across data mappings, not raw loops.
- **LAG Delineation Ready:** Built to support parsing `APPL_DB` to prevent double-counting LACP PortChannels.
- **Automation First:** JSON output for streaming into external telemetry collectors (e.g., Aviz ONES).

## 🛠️ Quick Start & Testing

**1. Install Dependencies**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. CLI Usage**
```bash
# Display top 5 interfaces (Human-readable table)
python3 cli.py --top 5 --interval 1.5

# JSON Output for API consumption
python3 cli.py --top 3 --json-out
```

**3. Run the Automated Tests (Pytest)**
Validation explicitly proves that the 64-bit hardware counter rollover (`$Octets_{t1} < Octets_{t0}`) does not crash the sorting logic.
```bash
pytest test_traffic.py -v
```

## 🏗️ Architecture Breakdown

```text
├── cli.py               # Click CLI grouping & entry point
├── traffic_analysis.py  # Core BPS delta logic & Timsort sorting
├── redis_client.py      # Simulated SonicV2Connector mapping & Pipelining
├── test_traffic.py      # Pytest validation for edge-case overflows
└── requirements.txt     # click, tabulate, pytest
```
