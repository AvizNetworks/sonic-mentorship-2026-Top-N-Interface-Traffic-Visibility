"""
test_top_n_traffic.py
=====================
Pytest suite for the SONiC Top-N Interface Traffic Visibility feature.

Covers:
  - Core delta / rate calculation logic
  - 64-bit ASIC counter overflow (wrap-around)
  - Top-N sorting and truncation
  - Configurable interval scaling
  - PortChannel member aggregation
  - Zero-traffic and single-interface edge cases
  - JSON output structure
  - Redis pipeline bulk-fetch contract (via fakeredis)

Dependencies:
    pip install pytest fakeredis

Run:
    pytest test_top_n_traffic.py -v
"""

import json
import time
import pytest

# ---------------------------------------------------------------------------
# fakeredis is used so tests never need a live Redis / SONiC instance.
# ---------------------------------------------------------------------------
try:
    import fakeredis
    FAKEREDIS_AVAILABLE = True
except ImportError:
    FAKEREDIS_AVAILABLE = False

# ---------------------------------------------------------------------------
# ── Inline reference implementation ────────────────────────────────────────
#
# Both PR #2 and PR #3 expose roughly the same logical surface:
#
#   read_counters(redis_client)  → dict  {iface: {rx_bytes, tx_bytes}}
#   compute_rates(snap0, snap1, interval) → dict {iface: {rx_bps, tx_bps, total_bps}}
#   top_n(rates, n)              → list  of (iface, stats) sorted by total_bps desc
#
# We test the *contract*, not the private implementation, so these stubs let
# the suite run standalone.  When you integrate against the real module, swap
# the import at the top and delete this section.
# ---------------------------------------------------------------------------

UINT64_MAX = 2 ** 64 - 1  # 18_446_744_073_709_551_615


def _delta(t1: int, t0: int) -> int:
    """True byte delta that handles 64-bit hardware counter wrap-around."""
    if t1 >= t0:
        return t1 - t0
    # counter wrapped
    return (UINT64_MAX - t0) + t1 + 1


def compute_rates(
    snap0: dict,
    snap1: dict,
    interval: float,
) -> dict:
    """
    Given two counter snapshots and the elapsed interval (seconds),
    return per-interface bit-rates.

    snap format: {iface_name: {"rx_bytes": int, "tx_bytes": int}}
    output format: {iface_name: {"rx_bps": float, "tx_bps": float, "total_bps": float}}
    """
    rates = {}
    for iface, s1 in snap1.items():
        if iface not in snap0:
            continue
        s0 = snap0[iface]
        rx_delta = _delta(s1["rx_bytes"], s0["rx_bytes"])
        tx_delta = _delta(s1["tx_bytes"], s0["tx_bytes"])
        rx_bps = (rx_delta * 8) / interval
        tx_bps = (tx_delta * 8) / interval
        rates[iface] = {
            "rx_bps": rx_bps,
            "tx_bps": tx_bps,
            "total_bps": rx_bps + tx_bps,
        }
    return rates


def top_n(rates: dict, n: int = 5) -> list:
    """Return the top-N interfaces sorted by total_bps descending."""
    sorted_ifaces = sorted(
        rates.items(), key=lambda x: x[1]["total_bps"], reverse=True
    )
    return sorted_ifaces[:n]


def aggregate_portchannel(
    member_rates: dict,
    portchannel_map: dict,
) -> dict:
    """
    Aggregate member-interface rates into PortChannel logical totals.

    portchannel_map: {"PortChannel1": ["Ethernet0", "Ethernet4"], ...}
    member_rates:    output of compute_rates() for physical interfaces
    """
    aggregated = {}
    for pc, members in portchannel_map.items():
        rx = sum(member_rates.get(m, {}).get("rx_bps", 0) for m in members)
        tx = sum(member_rates.get(m, {}).get("tx_bps", 0) for m in members)
        aggregated[pc] = {"rx_bps": rx, "tx_bps": tx, "total_bps": rx + tx}
    return aggregated


def to_json_output(top_list: list) -> str:
    """Serialise top-N result to JSON string (mirrors --json-out flag)."""
    payload = [
        {
            "interface": iface,
            "rx_bps": stats["rx_bps"],
            "tx_bps": stats["tx_bps"],
            "total_bps": stats["total_bps"],
        }
        for iface, stats in top_list
    ]
    return json.dumps(payload, indent=2)


# ---------------------------------------------------------------------------
# ── Fixtures ────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_snap0():
    return {
        "Ethernet0":  {"rx_bytes": 1_000_000, "tx_bytes": 500_000},
        "Ethernet4":  {"rx_bytes": 2_000_000, "tx_bytes": 1_000_000},
        "Ethernet8":  {"rx_bytes":   100_000, "tx_bytes":  50_000},
        "Ethernet12": {"rx_bytes":         0, "tx_bytes":       0},
    }


@pytest.fixture
def simple_snap1():
    """One second later: each interface sent/received some bytes."""
    return {
        "Ethernet0":  {"rx_bytes": 1_125_000, "tx_bytes":  562_500},  # +125k / +62.5k
        "Ethernet4":  {"rx_bytes": 2_500_000, "tx_bytes": 1_250_000}, # +500k / +250k
        "Ethernet8":  {"rx_bytes":   100_100, "tx_bytes":  50_050},   # near-idle
        "Ethernet12": {"rx_bytes":         0, "tx_bytes":       0},   # dead interface
    }


# ---------------------------------------------------------------------------
# ── 1. Core delta / rate calculation ────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestComputeRates:

    def test_basic_rx_rate(self, simple_snap0, simple_snap1):
        rates = compute_rates(simple_snap0, simple_snap1, interval=1.0)
        # Ethernet4: +500 000 bytes RX → 4 000 000 bps
        assert rates["Ethernet4"]["rx_bps"] == pytest.approx(4_000_000.0)

    def test_basic_tx_rate(self, simple_snap0, simple_snap1):
        rates = compute_rates(simple_snap0, simple_snap1, interval=1.0)
        # Ethernet4: +250 000 bytes TX → 2 000 000 bps
        assert rates["Ethernet4"]["tx_bps"] == pytest.approx(2_000_000.0)

    def test_total_is_rx_plus_tx(self, simple_snap0, simple_snap1):
        rates = compute_rates(simple_snap0, simple_snap1, interval=1.0)
        for iface, stats in rates.items():
            assert stats["total_bps"] == pytest.approx(
                stats["rx_bps"] + stats["tx_bps"]
            ), f"total_bps mismatch for {iface}"

    def test_zero_traffic_interface(self, simple_snap0, simple_snap1):
        rates = compute_rates(simple_snap0, simple_snap1, interval=1.0)
        assert rates["Ethernet12"]["rx_bps"] == 0.0
        assert rates["Ethernet12"]["tx_bps"] == 0.0
        assert rates["Ethernet12"]["total_bps"] == 0.0

    def test_interval_scaling_half_second(self, simple_snap0, simple_snap1):
        """Halving the interval should double the reported rate."""
        rates_1s = compute_rates(simple_snap0, simple_snap1, interval=1.0)
        rates_half = compute_rates(simple_snap0, simple_snap1, interval=0.5)
        assert rates_half["Ethernet4"]["rx_bps"] == pytest.approx(
            rates_1s["Ethernet4"]["rx_bps"] * 2
        )

    def test_interval_scaling_two_seconds(self, simple_snap0, simple_snap1):
        """Doubling the interval should halve the reported rate."""
        rates_1s = compute_rates(simple_snap0, simple_snap1, interval=1.0)
        rates_2s = compute_rates(simple_snap0, simple_snap1, interval=2.0)
        assert rates_2s["Ethernet0"]["total_bps"] == pytest.approx(
            rates_1s["Ethernet0"]["total_bps"] / 2
        )

    def test_interface_missing_from_snap0_is_skipped(self, simple_snap1):
        """New interface appearing between samples must not crash."""
        snap0 = {}  # completely empty
        rates = compute_rates(snap0, simple_snap1, interval=1.0)
        assert rates == {}

    def test_interface_missing_from_snap1_is_skipped(self, simple_snap0):
        """Interface disappearing between samples must not crash."""
        snap1 = {}
        rates = compute_rates(snap0=simple_snap0, snap1=snap1, interval=1.0)
        assert rates == {}


# ---------------------------------------------------------------------------
# ── 2. 64-bit ASIC counter overflow ─────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestCounterOverflow:

    def test_rx_counter_wraps_around(self):
        """
        Classic wrap: counter was near UINT64_MAX, ticked past zero.
        True delta must be positive, not a huge negative number.
        """
        snap0 = {"Ethernet0": {"rx_bytes": UINT64_MAX - 999, "tx_bytes": 0}}
        snap1 = {"Ethernet0": {"rx_bytes": 500,              "tx_bytes": 0}}
        rates = compute_rates(snap0, snap1, interval=1.0)
        # true delta = 999 (to reach UINT64_MAX) + 1 (rollover) + 500 = 1500 bytes → 12000 bps
        assert rates["Ethernet0"]["rx_bps"] == pytest.approx(12_000.0)

    def test_tx_counter_wraps_around(self):
        snap0 = {"Ethernet0": {"rx_bytes": 0, "tx_bytes": UINT64_MAX - 499}}
        snap1 = {"Ethernet0": {"rx_bytes": 0, "tx_bytes": 100}}
        rates = compute_rates(snap0, snap1, interval=1.0)
        # true delta = 600 bytes → 4800 bps
        assert rates["Ethernet0"]["tx_bps"] == pytest.approx(4_800.0)

    def test_exact_boundary_wrap(self):
        """Counter at exactly UINT64_MAX rolls to 0 next tick."""
        snap0 = {"Ethernet0": {"rx_bytes": UINT64_MAX, "tx_bytes": 0}}
        snap1 = {"Ethernet0": {"rx_bytes": 0,          "tx_bytes": 0}}
        rates = compute_rates(snap0, snap1, interval=1.0)
        # delta = 1 byte → 8 bps
        assert rates["Ethernet0"]["rx_bps"] == pytest.approx(8.0)

    def test_no_false_overflow_on_normal_traffic(self):
        """Large but non-wrapping counters must not trigger overflow path."""
        snap0 = {"Ethernet0": {"rx_bytes": UINT64_MAX // 2,       "tx_bytes": 0}}
        snap1 = {"Ethernet0": {"rx_bytes": UINT64_MAX // 2 + 1000, "tx_bytes": 0}}
        rates = compute_rates(snap0, snap1, interval=1.0)
        assert rates["Ethernet0"]["rx_bps"] == pytest.approx(8_000.0)

    def test_400g_sustained_load_no_overflow(self):
        """
        400 Gbps = 50 GB/s.  Over a 1-second window the counter advances
        50_000_000_000 bytes.  Confirm no spurious wrap is detected.
        """
        BYTES_PER_SEC_400G = 50_000_000_000
        snap0 = {"Ethernet0": {"rx_bytes": 1_000_000_000_000, "tx_bytes": 0}}
        snap1 = {"Ethernet0": {
            "rx_bytes": 1_000_000_000_000 + BYTES_PER_SEC_400G,
            "tx_bytes": 0,
        }}
        rates = compute_rates(snap0, snap1, interval=1.0)
        expected_bps = BYTES_PER_SEC_400G * 8  # 400_000_000_000
        assert rates["Ethernet0"]["rx_bps"] == pytest.approx(expected_bps)

    def test_delta_helper_direct(self):
        """Unit-test the _delta helper in isolation."""
        assert _delta(100, 50) == 50                      # normal
        assert _delta(0, UINT64_MAX) == 1                 # exact wrap
        assert _delta(500, UINT64_MAX - 499) == 1000      # partial wrap


# ---------------------------------------------------------------------------
# ── 3. Top-N sorting and truncation ─────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestTopN:

    @pytest.fixture
    def many_iface_rates(self):
        return {
            f"Ethernet{i*4}": {
                "rx_bps": float(i * 1_000_000),
                "tx_bps": float(i * 500_000),
                "total_bps": float(i * 1_500_000),
            }
            for i in range(20)  # Ethernet0 … Ethernet76
        }

    def test_returns_exactly_n_results(self, many_iface_rates):
        result = top_n(many_iface_rates, n=5)
        assert len(result) == 5

    def test_sorted_descending(self, many_iface_rates):
        result = top_n(many_iface_rates, n=10)
        totals = [stats["total_bps"] for _, stats in result]
        assert totals == sorted(totals, reverse=True)

    def test_highest_traffic_iface_is_first(self, many_iface_rates):
        result = top_n(many_iface_rates, n=5)
        # Ethernet76 (i=19) has the highest total_bps
        assert result[0][0] == "Ethernet76"

    def test_n_larger_than_iface_count(self, simple_snap0, simple_snap1):
        """Requesting more results than interfaces must not raise."""
        rates = compute_rates(simple_snap0, simple_snap1, interval=1.0)
        result = top_n(rates, n=100)
        assert len(result) == len(rates)

    def test_n_equals_one(self, many_iface_rates):
        result = top_n(many_iface_rates, n=1)
        assert len(result) == 1
        assert result[0][0] == "Ethernet76"

    def test_zero_traffic_interfaces_sorted_to_bottom(self, simple_snap0, simple_snap1):
        rates = compute_rates(simple_snap0, simple_snap1, interval=1.0)
        result = top_n(rates, n=len(rates))
        last_iface, last_stats = result[-1]
        assert last_stats["total_bps"] == 0.0

    def test_tie_breaking_is_stable(self):
        """Equal-traffic interfaces must not cause an exception."""
        rates = {
            "Ethernet0": {"rx_bps": 1e6, "tx_bps": 1e6, "total_bps": 2e6},
            "Ethernet4": {"rx_bps": 1e6, "tx_bps": 1e6, "total_bps": 2e6},
        }
        result = top_n(rates, n=2)
        assert len(result) == 2

    def test_empty_rates_returns_empty(self):
        result = top_n({}, n=5)
        assert result == []


# ---------------------------------------------------------------------------
# ── 4. PortChannel aggregation ──────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestPortChannelAggregation:

    @pytest.fixture
    def member_rates(self):
        return {
            "Ethernet0": {"rx_bps": 1e9, "tx_bps": 500e6, "total_bps": 1.5e9},
            "Ethernet4": {"rx_bps": 1e9, "tx_bps": 500e6, "total_bps": 1.5e9},
            "Ethernet8": {"rx_bps": 2e9, "tx_bps": 1e9,   "total_bps": 3e9},
            "Ethernet12": {"rx_bps": 0,   "tx_bps": 0,     "total_bps": 0},
        }

    @pytest.fixture
    def pc_map(self):
        return {
            "PortChannel1": ["Ethernet0", "Ethernet4"],
            "PortChannel2": ["Ethernet8", "Ethernet12"],
        }

    def test_portchannel_rx_is_sum_of_members(self, member_rates, pc_map):
        agg = aggregate_portchannel(member_rates, pc_map)
        assert agg["PortChannel1"]["rx_bps"] == pytest.approx(2e9)

    def test_portchannel_tx_is_sum_of_members(self, member_rates, pc_map):
        agg = aggregate_portchannel(member_rates, pc_map)
        assert agg["PortChannel1"]["tx_bps"] == pytest.approx(1e9)

    def test_portchannel_total_bps(self, member_rates, pc_map):
        agg = aggregate_portchannel(member_rates, pc_map)
        assert agg["PortChannel1"]["total_bps"] == pytest.approx(3e9)

    def test_portchannel_with_idle_member(self, member_rates, pc_map):
        """PortChannel2 has one idle member — should not drag total negative."""
        agg = aggregate_portchannel(member_rates, pc_map)
        assert agg["PortChannel2"]["rx_bps"] == pytest.approx(2e9)
        assert agg["PortChannel2"]["total_bps"] == pytest.approx(3e9)

    def test_portchannel_missing_member_skipped(self, pc_map):
        """Member interface absent from rates dict must be treated as 0."""
        partial_rates = {
            "Ethernet0": {"rx_bps": 1e9, "tx_bps": 0, "total_bps": 1e9},
            # Ethernet4 intentionally missing
        }
        agg = aggregate_portchannel(partial_rates, pc_map)
        assert agg["PortChannel1"]["rx_bps"] == pytest.approx(1e9)

    def test_portchannel_appears_in_top_n(self, member_rates, pc_map):
        """After aggregation, PortChannels should rank correctly."""
        agg = aggregate_portchannel(member_rates, pc_map)
        result = top_n(agg, n=2)
        # Both PCs have equal total — 2 results expected
        assert len(result) == 2


# ---------------------------------------------------------------------------
# ── 5. JSON output ───────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestJsonOutput:

    @pytest.fixture
    def sample_top(self, simple_snap0, simple_snap1):
        rates = compute_rates(simple_snap0, simple_snap1, interval=1.0)
        return top_n(rates, n=3)

    def test_output_is_valid_json(self, sample_top):
        raw = to_json_output(sample_top)
        parsed = json.loads(raw)  # must not raise
        assert isinstance(parsed, list)

    def test_output_length_matches_top_n(self, sample_top):
        parsed = json.loads(to_json_output(sample_top))
        assert len(parsed) == 3

    def test_required_keys_present(self, sample_top):
        parsed = json.loads(to_json_output(sample_top))
        for entry in parsed:
            assert "interface" in entry
            assert "rx_bps" in entry
            assert "tx_bps" in entry
            assert "total_bps" in entry

    def test_total_bps_equals_rx_plus_tx_in_json(self, sample_top):
        parsed = json.loads(to_json_output(sample_top))
        for entry in parsed:
            assert entry["total_bps"] == pytest.approx(
                entry["rx_bps"] + entry["tx_bps"]
            )

    def test_ordering_preserved_in_json(self, sample_top):
        """JSON array must preserve descending-rate order."""
        parsed = json.loads(to_json_output(sample_top))
        totals = [e["total_bps"] for e in parsed]
        assert totals == sorted(totals, reverse=True)


# ---------------------------------------------------------------------------
# ── 6. Redis pipeline bulk-fetch contract (fakeredis) ───────────────────────
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not FAKEREDIS_AVAILABLE, reason="fakeredis not installed")
class TestRedisPipelineContract:
    """
    Validates that the bulk-fetch pattern (pipeline HGET) returns the same
    values as individual queries — i.e., pipelining does not corrupt data.
    """

    IFACES = ["Ethernet0", "Ethernet4", "Ethernet8"]
    RX_KEY = "SAI_PORT_STAT_IF_IN_OCTETS"
    TX_KEY = "SAI_PORT_STAT_IF_OUT_OCTETS"

    @pytest.fixture
    def fake_redis(self):
        r = fakeredis.FakeRedis()
        # Populate COUNTERS_DB-style hash entries
        for i, iface in enumerate(self.IFACES):
            oid = f"oid:0x{i+1:016x}"
            r.hset(f"COUNTERS:{oid}", self.RX_KEY, str((i + 1) * 1_000_000))
            r.hset(f"COUNTERS:{oid}", self.TX_KEY, str((i + 1) * 500_000))
            # Interface-name → OID mapping
            r.hset("COUNTERS_PORT_NAME_MAP", iface, oid)
        return r

    def test_pipeline_returns_same_values_as_individual_hget(self, fake_redis):
        r = fake_redis
        port_map = r.hgetall("COUNTERS_PORT_NAME_MAP")

        # Individual HGET
        individual = {}
        for iface, oid in port_map.items():
            iface = iface.decode()
            oid = oid.decode()
            rx = int(r.hget(f"COUNTERS:{oid}", self.RX_KEY))
            tx = int(r.hget(f"COUNTERS:{oid}", self.TX_KEY))
            individual[iface] = {"rx_bytes": rx, "tx_bytes": tx}

        # Pipeline bulk HGET
        pipe = r.pipeline()
        keys_order = []
        for iface, oid in port_map.items():
            iface = iface.decode()
            oid = oid.decode()
            pipe.hget(f"COUNTERS:{oid}", self.RX_KEY)
            pipe.hget(f"COUNTERS:{oid}", self.TX_KEY)
            keys_order.append(iface)

        results = pipe.execute()
        pipeline_fetch = {}
        for idx, iface in enumerate(keys_order):
            rx = int(results[idx * 2])
            tx = int(results[idx * 2 + 1])
            pipeline_fetch[iface] = {"rx_bytes": rx, "tx_bytes": tx}

        assert pipeline_fetch == individual

    def test_all_interfaces_present_in_bulk_fetch(self, fake_redis):
        r = fake_redis
        port_map = r.hgetall("COUNTERS_PORT_NAME_MAP")
        fetched_ifaces = {k.decode() for k in port_map.keys()}
        assert fetched_ifaces == set(self.IFACES)

    def test_counter_values_are_positive_integers(self, fake_redis):
        r = fake_redis
        port_map = r.hgetall("COUNTERS_PORT_NAME_MAP")
        for iface, oid in port_map.items():
            oid = oid.decode()
            rx = r.hget(f"COUNTERS:{oid}", self.RX_KEY)
            tx = r.hget(f"COUNTERS:{oid}", self.TX_KEY)
            assert int(rx) > 0
            assert int(tx) > 0


# ---------------------------------------------------------------------------
# ── 7. Sampling interval edge cases ─────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestSamplingInterval:

    def test_fractional_interval(self, simple_snap0, simple_snap1):
        """Non-integer intervals (e.g. 1.5s) must not raise."""
        rates = compute_rates(simple_snap0, simple_snap1, interval=1.5)
        assert all(v["total_bps"] >= 0 for v in rates.values())

    def test_very_short_interval_does_not_divide_by_zero(self):
        """interval=0 would be a caller error; verify behaviour is defined."""
        snap0 = {"Ethernet0": {"rx_bytes": 0, "tx_bytes": 0}}
        snap1 = {"Ethernet0": {"rx_bytes": 100, "tx_bytes": 50}}
        with pytest.raises((ZeroDivisionError, ValueError)):
            compute_rates(snap0, snap1, interval=0)

    def test_large_interval_gives_low_rate(self, simple_snap0, simple_snap1):
        """Over a 60-second window the same delta → lower per-second rate."""
        rates_1s  = compute_rates(simple_snap0, simple_snap1, interval=1.0)
        rates_60s = compute_rates(simple_snap0, simple_snap1, interval=60.0)
        assert rates_60s["Ethernet4"]["total_bps"] == pytest.approx(
            rates_1s["Ethernet4"]["total_bps"] / 60
        )


# ---------------------------------------------------------------------------
# ── 8. High-density / scale smoke test ──────────────────────────────────────
# ---------------------------------------------------------------------------

class TestScale:

    def test_128_interfaces_timsort_completes(self):
        """
        Simulate a 128-port spine switch. Top-N must return in < 1 second
        (Timsort on 128 items is O(N log N) ≈ trivial).
        """
        n_ports = 128
        snap0 = {
            f"Ethernet{i*4}": {"rx_bytes": i * 1_000, "tx_bytes": i * 500}
            for i in range(n_ports)
        }
        snap1 = {
            f"Ethernet{i*4}": {
                "rx_bytes": i * 1_000 + 125_000,
                "tx_bytes": i * 500  + 62_500,
            }
            for i in range(n_ports)
        }
        start = time.monotonic()
        rates = compute_rates(snap0, snap1, interval=1.0)
        result = top_n(rates, n=5)
        elapsed = time.monotonic() - start

        assert len(result) == 5
        assert elapsed < 1.0, f"top_n took {elapsed:.3f}s on {n_ports} ports"

    def test_all_zero_counters_no_crash(self):
        """Switch just booted — all counters at zero."""
        snap0 = {f"Ethernet{i*4}": {"rx_bytes": 0, "tx_bytes": 0} for i in range(32)}
        snap1 = {f"Ethernet{i*4}": {"rx_bytes": 0, "tx_bytes": 0} for i in range(32)}
        rates = compute_rates(snap0, snap1, interval=1.0)
        result = top_n(rates, n=5)
        assert all(stats["total_bps"] == 0 for _, stats in result)