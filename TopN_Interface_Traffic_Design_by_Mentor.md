# TopN Interface Traffic — Design Proposal


## 1. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ User:  $ show interfaces counters topn -n 5 --sort total         │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ show/interfaces/__init__.py                                      │
│   @counters.command("topn")  ← new Click subcommand              │
│   builds argv → invokes  scripts/portstat -X N --sort … [-w T]   │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ scripts/portstat                                                 │
│   new flags: -X/--topn, --sort {rx,tx,total,util},               │
│              --units {bps,pps}, -w/--watch                       │
│   calls Portstat.get_cnstat_dict() → topn filter → existing      │
│   tabulate / JSON formatter                                      │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ utilities_common/portstat.py                                     │
│   new method:  get_topn(n, sort_key, units) -> OrderedDict       │
│   reads from   self.ratestat_dict   (populated by get_cnstat())  │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ COUNTERS_DB                                                      │
│   RATES:oid:0x1000000000012 → RX_BPS, RX_PPS, TX_BPS, TX_PPS …   │
│   (populated by orchagent port_rates.lua every 1 s)              │
└──────────────────────────────────────────────────────────────────┘
```

Three files changed. No new daemons, no new DB tables, no orchagent changes, no Lua.

## 2. CLI surface

```
show interfaces counters topn [OPTIONS]

Options:
  -n, --count INTEGER          Number of top interfaces to show.  Default: 5.
  --sort [rx|tx|total|util]    Sort key.                          Default: total.
  --units [bps|pps]            Rank by bits/sec or packets/sec.   Default: bps.
  -w, --watch INTEGER          Refresh every N seconds.           Default: off.
  -p, --period INTEGER         Two-sample delta fallback for      Default: off.
                               environments without RATES:.
  -j, --json                   JSON output.
  -s, --display TEXT           all|frontend                       Default: frontend.
  --namespace TEXT             Restrict to namespace.
  --verbose                    Print the underlying command.
```

### Sample output (human)

```
$ show interfaces counters topn -n 5 --sort total

Sampled at 2026-05-22 10:14:03  (rates pre-smoothed by orchagent, α=0.5, 1s interval)

  RANK    IFACE   STATE        RX_BPS         RX_PPS        TX_BPS         TX_PPS    UTIL
------  --------- -----   ----------    -----------    ----------    -----------   -------
     1  Ethernet0     U    2.00 GB/s   247,000.00/s    1.50 GB/s   183,000.00/s    64.00%
     2  Ethernet8     U    1.35 MB/s     9,000.00/s   13.37 MB/s     9,000.00/s       N/A
     3  Ethernet4     U  204.80 KB/s       200.00/s  204.85 KB/s       201.00/s       N/A
     4  Ethernet12    D     0.00 B/s         0.00/s     0.00 B/s         0.00/s       N/A
     5  Ethernet16    D     0.00 B/s         0.00/s     0.00 B/s         0.00/s       N/A
```

### Sample output (JSON)

```json
{
  "sampled_at": "2026-05-22T10:14:03.118",
  "sort_key": "total_bps",
  "count": 5,
  "interfaces": [
    {"rank": 1, "iface": "Ethernet0", "state": "U",
     "rx_bps": 2000000000.0, "rx_pps": 247000.0,
     "tx_bps": 1500000000.0, "tx_pps": 183000.0,
     "rx_util_pct": 64.0, "tx_util_pct": 48.0}
  ]
}
```

## 3. Why pre-computed rates beat sample-and-diff

| Concern | `RATES:` table (recommended) | Two-sample delta |
|---|---|---|
| Latency to first result | ~50 ms (single Redis read) | `--period` seconds blocking |
| Numerical consistency with `show … rates` | Identical (same source) | Different (no EWMA smoothing) |
| Orchagent load | Zero added | Zero added |
| Management-plane CPU | Negligible | Two full counter scans |
| Behavior during port flap | Handled by orchagent | Possible huge spike |
| Works on virtual switch w/o plugin loaded | **No — needs fallback** | Yes |

The `-p N` fallback covers the one case the primary mechanism misses (virtual switches or unit-test environments where the Lua plugin isn't loaded). Detection is easy: if `ratestat_dict` is empty or all `N/A` after one read, print a clear message — "rate plugin not loaded — try `--period 5` for sampled mode" — and offer the fallback.


## 4. Stretch goals (no architectural change required)

- **`--exclude-down`** — filter to `oper_status=up` interfaces (cheap; `Portstat.get_port_state` already reads this).
- **`--threshold X`** — show interfaces above X Gbps instead of fixed N.
- **gNMI / streaming telemetry export** — Out of scope for an initial PR but worth flagging in the upstream RFC discussion.


## 5. Things to be considered

1. **`RATES:` population varies by platform.** Some vendor SDKs disable specific stats. The `-p N` fallback handles this; the CLI should detect missing fields and surface a clear message rather than a row of `N/A`.
2. **VOQ chassis path.** On supervisor cards, `Portstat.collect_stat_from_lc` reads from `CHASSIS_STATE_DB` with a different schema. From `portstat.py:254-280` the rate fields (`rx_bps`, `tx_bps`, …) are present there too — needs one VOQ-fixture test to confirm.
3. **EWMA α value.** The smoothing factor is configured per-deployment in `RATES:PORT`. A short microburst won't show up here; users investigating microbursts should be pointed at `--period 1` or the watermark counters.
4. **Tie-breakers among 0-bps interfaces.** Use `natsorted` as the secondary key so output is deterministic — important for the JSON consumers.


## 6. Recommendation

Build TopN as a **thin filter on top of `Portstat`**, reading the `COUNTERS_DB:RATES:` entries that orchagent already maintains. Numerically consistent with `show interfaces counters rates`, multi-ASIC and VOQ-chassis aware, and trivially extensible to queues once your done with this upstream.
