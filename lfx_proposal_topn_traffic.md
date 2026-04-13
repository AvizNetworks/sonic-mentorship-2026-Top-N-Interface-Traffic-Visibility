# LFX Mentorship Proposal: Top-N Interface Traffic Visibility Feature in SONiC

---

## 1. Personal Introduction

<!--
  Replace the placeholder below with your actual details.
  Keep it concise — 4-6 lines maximum.
-->

| | |
|---|---|
| **Name** | *SAMANVAI CHANDRA* |
| **University** | *AIT,VTU,6TH SEM,information science* |
| **GitHub** | *https://github.com/notorious1337* |
| **LinkedIn** | *[https://linkedin.com/in/samanvai-chandra]* |
| **Location** | India |
| **Availability** | 40 hours/week — Summer 2026 |

**Relevant Skills:** Python (3+ years), Linux networking (TCP/IP, iproute2, netstat), Redis (basic CLI and Python client), Git & open-source contribution workflows. Familiar with Click CLI framework and pytest. Comfortable reading and navigating large Python codebases.

---

## 2. Problem Statement & Motivation

SONiC exposes per-interface traffic counters via `show interfaces counters`, but in large-scale data-center deployments with **hundreds to thousands of ports**, operators lack a quick, built-in mechanism to answer:

> *"Which interfaces are carrying the most traffic right now?"*

Today, answering this requires:

1. Running `show interfaces counters` twice with a manual delay
2. Exporting data to a spreadsheet or script
3. Computing deltas and sorting manually

This is **slow, error-prone, and not automatable**. Network operators performing capacity planning, troubleshooting congestion, or investigating microbursts need an instant, single-command answer.

### Why This Matters

| Use Case | Pain Today | With Top-N |
|---|---|---|
| **Congestion triage** | Scan 500+ interfaces manually | One command, instant answer |
| **Capacity planning** | Export + spreadsheet analysis | JSON output → automation pipeline |
| **Microburst detection** | No quick way to identify hot ports | Configurable short sampling intervals |
| **NOC dashboards** | Custom scripts per deployment | Standard CLI, consistent output |

---

## 3. Understanding of SONiC Architecture

Before diving into the implementation plan, here is my understanding of how the relevant subsystems work — demonstrating that I've studied the codebase:

### 3.1 COUNTERS_DB (Redis DB 2)

SONiC uses a **database-centric architecture** where all subsystem communication flows through Redis. The `COUNTERS_DB` (database index 2) stores per-port statistics as **Redis hashes**:

```
Key:    COUNTERS:<OID>
Fields: SAI_PORT_STAT_IF_IN_OCTETS     → cumulative RX bytes
        SAI_PORT_STAT_IF_OUT_OCTETS    → cumulative TX bytes
        SAI_PORT_STAT_IF_IN_UCAST_PKTS → RX unicast packets
        SAI_PORT_STAT_IF_OUT_UCAST_PKTS→ TX unicast packets
        ... (40+ SAI counter fields)
```

Port OIDs are mapped to human-readable names via the `COUNTERS_PORT_NAME_MAP` table:

```
Key:    COUNTERS_PORT_NAME_MAP
Fields: Ethernet0  → oid:0x1000000000002
        Ethernet4  → oid:0x1000000000003
        ...
```

**Data flow:** ASIC → SAI → `syncd` (via Flex Counters) → `COUNTERS_DB`

### 3.2 sonic-utilities CLI

The CLI is built with **Python Click** and lives in the `sonic-net/sonic-utilities` repository:

```
sonic-utilities/
├── show/
│   ├── main.py              ← top-level 'show' command group
│   └── interfaces/
│       ├── __init__.py
│       └── ...              ← 'show interfaces counters' wiring
├── scripts/
│   └── portstat             ← core counter-reading logic
├── utilities_common/
│   └── cli.py               ← shared CLI utilities
└── tests/
    └── ...                  ← pytest test infrastructure
```

The existing `portstat` script already:
- Reads `COUNTERS_PORT_NAME_MAP` to resolve port names
- Reads `COUNTERS:<OID>` hashes for counter values
- Computes deltas against a saved-state file (for `show interfaces counters -d`)
- Formats output as a tabular CLI display

**This is a critical insight** — I can reuse and extend `portstat`'s counter-reading infrastructure rather than building from scratch.

### 3.3 Architecture Diagram

```
┌──────────────────────────────────────────────────────────┐
│                    SONiC Switch                           │
│                                                           │
│  ┌─────────┐     ┌──────────┐     ┌──────────────────┐  │
│  │  ASIC   │────▶│  syncd   │────▶│  COUNTERS_DB     │  │
│  │(Hardware)│ SAI │(Flex Ctr)│     │  (Redis DB 2)    │  │
│  └─────────┘     └──────────┘     │                  │  │
│                                    │  COUNTERS:<OID>  │  │
│                                    │  ├─ IF_IN_OCTETS │  │
│                                    │  ├─ IF_OUT_OCTETS│  │
│                                    │  └─ ...          │  │
│                                    └────────┬─────────┘  │
│                                             │             │
│                                     ┌───────▼──────────┐ │
│                                     │  NEW: topstat    │ │
│                                     │  (Top-N Engine)  │ │
│                                     │                  │ │
│                                     │  1. Sample T₀    │ │
│                                     │  2. Sleep Δt     │ │
│                                     │  3. Sample T₁    │ │
│                                     │  4. Δ = T₁ - T₀  │ │
│                                     │  5. Sort by Δ    │ │
│                                     │  6. Display Top N│ │
│                                     └───────┬──────────┘ │
│                                             │             │
│                                     ┌───────▼──────────┐ │
│                                     │  show interfaces │ │
│                                     │  top [OPTIONS]   │ │
│                                     │  (Click CLI)     │ │
│                                     └──────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Proposed Implementation

### 4.1 New CLI Command

```
show interfaces top [OPTIONS]

Options:
  -n, --top-n INTEGER       Number of top interfaces to display (default: 5)
  -i, --interval FLOAT      Sampling interval in seconds (default: 3.0)
  -s, --sort-by [total|rx|tx|rx_pps|tx_pps]
                             Sort criterion (default: total = RX+TX bytes/s)
  -j, --json                Output in JSON format
  -p, --period INTEGER      Continuous monitoring: refresh every PERIOD seconds
  --no-header               Suppress table header
  --namespace TEXT           Multi-ASIC namespace filter (for multi-ASIC platforms)
```

### 4.2 Example Output — Tabular (Default)

```
admin@sonic:~$ show interfaces top -n 5 -i 3

Top 5 Interfaces by Traffic Rate (sampled over 3.0s)
=====================================================
  Interface     RX Rate      TX Rate      Total Rate     RX PPS     TX PPS
-----------  ----------  -----------  ------------  ---------  ---------
 Ethernet48   1.24 Gb/s    987 Mb/s     2.21 Gb/s     824.5K     652.1K
 Ethernet12   756 Mb/s     812 Mb/s     1.57 Gb/s     501.3K     538.2K
 Ethernet0    623 Mb/s     541 Mb/s     1.16 Gb/s     412.8K     358.7K
 Ethernet36   412 Mb/s     389 Mb/s     801 Mb/s      273.1K     257.8K
 Ethernet24   198 Mb/s     210 Mb/s     408 Mb/s      131.2K     139.3K

Sampling interval: 3.0s | Sorted by: total
```

### 4.3 Example Output — JSON

```json
{
  "sampling_interval_sec": 3.0,
  "sort_by": "total",
  "timestamp": "2026-06-15T14:32:01Z",
  "interfaces": [
    {
      "interface": "Ethernet48",
      "rx_bps": 1240000000,
      "tx_bps": 987000000,
      "total_bps": 2227000000,
      "rx_pps": 824500,
      "tx_pps": 652100
    },
    ...
  ]
}
```

### 4.4 Core Algorithm — Delta-Based Rate Computation

```python
# Pseudocode for the core engine (topstat.py)

def get_top_interfaces(db, top_n=5, interval=3.0, sort_by='total'):
    """
    1. Read all interface counters at time T0
    2. Sleep for `interval` seconds
    3. Read all interface counters at time T1
    4. Compute per-interface rate = (T1 - T0) / interval
    5. Sort by chosen metric
    6. Return top N
    """
    port_map = db.get_all('COUNTERS_DB', 'COUNTERS_PORT_NAME_MAP')

    # Snapshot T0
    t0 = time.monotonic()
    counters_t0 = {}
    for port_name, oid in port_map.items():
        counters_t0[port_name] = db.get_all('COUNTERS_DB', f'COUNTERS:{oid}')

    time.sleep(interval)

    # Snapshot T1
    t1 = time.monotonic()
    counters_t1 = {}
    for port_name, oid in port_map.items():
        counters_t1[port_name] = db.get_all('COUNTERS_DB', f'COUNTERS:{oid}')

    actual_interval = t1 - t0  # account for timing jitter

    # Compute rates
    rates = []
    for port_name in port_map:
        rx_bytes = _safe_delta(
            counters_t1[port_name].get('SAI_PORT_STAT_IF_IN_OCTETS', 0),
            counters_t0[port_name].get('SAI_PORT_STAT_IF_IN_OCTETS', 0)
        )
        tx_bytes = _safe_delta(
            counters_t1[port_name].get('SAI_PORT_STAT_IF_OUT_OCTETS', 0),
            counters_t0[port_name].get('SAI_PORT_STAT_IF_OUT_OCTETS', 0)
        )
        rx_pps = _safe_delta(
            counters_t1[port_name].get('SAI_PORT_STAT_IF_IN_UCAST_PKTS', 0),
            counters_t0[port_name].get('SAI_PORT_STAT_IF_IN_UCAST_PKTS', 0)
        )
        tx_pps = _safe_delta(
            counters_t1[port_name].get('SAI_PORT_STAT_IF_OUT_UCAST_PKTS', 0),
            counters_t0[port_name].get('SAI_PORT_STAT_IF_OUT_UCAST_PKTS', 0)
        )

        rates.append({
            'interface': port_name,
            'rx_bps': (rx_bytes * 8) / actual_interval,
            'tx_bps': (tx_bytes * 8) / actual_interval,
            'total_bps': ((rx_bytes + tx_bytes) * 8) / actual_interval,
            'rx_pps': rx_pps / actual_interval,
            'tx_pps': tx_pps / actual_interval,
        })

    # Sort & slice
    sort_key = SORT_KEYS[sort_by]  # maps to lambda
    rates.sort(key=sort_key, reverse=True)
    return rates[:top_n]


def _safe_delta(new, old):
    """Handle 64-bit counter wraps."""
    new, old = int(new), int(old)
    if new >= old:
        return new - old
    return (2**64 - old) + new  # counter wrap
```

### 4.5 Files to Be Created / Modified

| Action | File | Description |
|---|---|---|
| **NEW** | `scripts/topstat` | Core engine: counter reading, delta computation, sorting |
| **NEW** | `show/interfaces/top.py` | Click command definition for `show interfaces top` |
| **MODIFY** | `show/interfaces/__init__.py` | Register the new `top` subcommand |
| **MODIFY** | `setup.py` | Add `topstat` to `scripts` entry point |
| **NEW** | `tests/test_topstat.py` | Unit tests with mocked COUNTERS_DB |
| **NEW** | `doc/Command-Reference.md` (update) | CLI documentation for the new command |

### 4.6 Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Reuse portstat patterns** | Yes | Consistent with codebase; reduces review friction |
| **Counter wrap handling** | 64-bit wrap detection | SAI counters are 64-bit; must handle edge case |
| **Rate vs. absolute** | Rate (bits/sec) | More operationally useful than raw byte counts |
| **Default interval** | 3 seconds | Balances accuracy with responsiveness |
| **PPS alongside BPS** | Include both | Operators need both for different troubleshooting |
| **Multi-ASIC support** | Namespace option | SONiC 202311+ supports multi-ASIC; future-proof |
| **Human-readable units** | Auto-scale (Kb/Mb/Gb) | Easier to read in CLI output |

---

## 5. Testing Strategy

### 5.1 Unit Tests (pytest)

| Test Case | What It Validates |
|---|---|
| `test_basic_top5` | Returns exactly 5 interfaces sorted by total rate |
| `test_custom_n` | `--top-n 10` returns 10 interfaces |
| `test_sort_by_rx` | `--sort-by rx` sorts by RX rate correctly |
| `test_sort_by_tx` | `--sort-by tx` sorts by TX rate correctly |
| `test_json_output` | `--json` produces valid JSON with correct schema |
| `test_counter_wrap` | Handles 64-bit counter wrapping correctly |
| `test_empty_counters` | Gracefully handles ports with no counter data |
| `test_zero_interval` | Rejects `--interval 0` with helpful error |
| `test_negative_delta` | Handles edge case of counter reset mid-sample |
| `test_namespace_filter` | Multi-ASIC: only shows ports in selected namespace |
| `test_human_readable_units` | Formats rates as Kb/s, Mb/s, Gb/s correctly |

**Mocking approach:** Use `unittest.mock.patch` to mock `SonicV2Connector` and inject controlled counter values. This is consistent with the existing sonic-utilities test infrastructure.

### 5.2 VS (Virtual Switch) Integration Test

```bash
# On a SONiC VS image
show interfaces top -n 5 -i 2
show interfaces top -n 3 -i 1 --json
show interfaces top --sort-by rx
show interfaces top -p 5  # continuous mode, 5-second refresh
```

### 5.3 Performance Validation

- Measure execution time on a system with 256+ interfaces
- Target: < 50ms overhead beyond the sampling interval itself
- Verify no measurable impact on `COUNTERS_DB` read latency for other consumers

---

## 6. Timeline — 12-Week Plan

| Week | Phase | Deliverables |
|---|---|---|
| **1** | **Onboarding & Deep Dive** | Set up dev environment (sonic-buildimage, VS image). Read `portstat`, `show/interfaces/`, and `COUNTERS_DB` schema in depth. Identify all reusable components. |
| **2** | **Design & HLD** | Write High-Level Design (HLD) document following SONiC HLD template. Submit for mentor review. Finalize CLI interface and output format. |
| **3** | **Core Engine v1** | Implement `topstat` script: counter reading, delta computation, rate calculation. Handle counter wraps. Standalone testable module. |
| **4** | **CLI Integration** | Wire `topstat` into Click CLI as `show interfaces top`. Implement all options (`-n`, `-i`, `-s`, `--json`, `--no-header`). Register in `show/interfaces/__init__.py`. |
| **5** | **Unit Tests** | Write comprehensive pytest suite (10+ test cases). Mock `SonicV2Connector`. Achieve >90% code coverage on `topstat`. |
| **6** | **Midterm Review + Polish** | Mentor review. Incorporate feedback. Fix edge cases (no data, single interface, admin-down ports). Add human-readable unit formatting (Kb/Mb/Gb). |
| **7** | **Continuous Mode** | Implement `--period` option for real-time refresh (like `watch`). Handle terminal resize and Ctrl+C gracefully. |
| **8** | **Multi-ASIC Support** | Add `--namespace` option. Test on multi-ASIC VS topology. Ensure correct port-to-namespace resolution. |
| **9** | **VS Integration Testing** | End-to-end testing on SONiC Virtual Switch. Generate traffic with `iperf3`, verify top-N output matches expected rankings. Performance benchmarking. |
| **10** | **Documentation** | Update Command-Reference.md. Write user guide with examples. Add inline code documentation. |
| **11** | **Code Review & Upstream Prep** | Submit PR to `sonic-net/sonic-utilities`. Address code review feedback. Ensure CI passes. Sign CLA if needed. |
| **12** | **Final Review & Stretch Goals** | Final mentor review. Start stretch goals if time permits. Write mentorship summary blog post. |

---

## 7. Stretch Goals (If Time Permits)

| Priority | Goal | Description |
|---|---|---|
| 🥇 | **Threshold Alerts** | `show interfaces top --alert-above 1G` — highlight interfaces exceeding a threshold in red |
| 🥈 | **Historical Comparison** | `show interfaces top --compare` — compare current top-N against last saved snapshot |
| 🥉 | **PortChannel Aggregation** | Show top-N for PortChannel aggregate traffic (sum member ports) |
| 4 | **Interface Filtering** | `--include Ethernet*` / `--exclude Management*` — glob-based filtering |
| 5 | **gNMI Telemetry Integration** | Expose top-N data via SONiC's gNMI telemetry for remote monitoring |

---

## 8. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Unfamiliarity with SONiC build system** | Medium | Medium | Week 1 dedicated to onboarding; mentor guidance |
| **Counter wrap edge cases** | Low | High | Explicit 64-bit wrap handling + dedicated tests |
| **Multi-ASIC complexity** | Medium | Medium | Start with single-ASIC; multi-ASIC in Week 8 with mentor help |
| **PR review delays** | Medium | Low | Submit early (Week 11); small, focused PRs |
| **Performance on large port count** | Low | Medium | Benchmark early (Week 9); optimize if needed |

---

## 9. Why Me?

<!--
  Customize the bullets below to match your actual experience.
  Be specific — mention project names, contributions, and metrics.
-->

- **Python proficiency:** 5 years of experience;building prototypes for indian govt and indian railway
- **Linux networking:** Been very familiar to unix and linux systems throughout my journey
- **Open-source contributions:** *(https://github.com/sonic-net/sonic-utilities/pull/4382)
- **Redis familiarity:** Used Redis as cache layer in a college project
- **Motivated by impact:** This feature will be used by every SONiC operator globally. Shipping a merged feature to a Linux Foundation project is a meaningful career milestone I'm committed to delivering.

---

## 10. References

- [SONiC Architecture](https://github.com/sonic-net/SONiC/wiki/Architecture)
- [sonic-utilities repository](https://github.com/sonic-net/sonic-utilities)
- [COUNTERS_DB schema](https://github.com/sonic-net/sonic-swss/blob/master/doc/swss-schema.md)
- [SONiC CLI Reference](https://github.com/sonic-net/sonic-utilities/blob/master/doc/Command-Reference.md)
- [portstat script](https://github.com/sonic-net/sonic-utilities/blob/master/scripts/portstat)
- [SONiC HLD Template](https://github.com/sonic-net/SONiC/blob/master/doc/template.md)
- [LFX Mentorship Platform](https://mentorship.lfx.linuxfoundation.org/)

---

> **Commitment:** I am fully available for 40 hours/week during Summer 2026 with no conflicting internships, courses, or travel. I will maintain weekly progress reports and attend all mentor sync meetings.
