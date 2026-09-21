"""Tests for quilt_fabric. Stdlib-only module; pytest harness.

Run: python -m pytest tests/quilt_fabric/ -q
"""
import pytest

from quilt_fabric import (
    ENERGY_SCALE,
    GRANT_MIN,
    SURVIVE_MIN,
    CellFabric,
    FabricLedger,
    canonical,
    fabric_from_graph_index,
    fnv1a32,
    sha256_hex,
)

FIXED = 1000.0


def _clock():
    return FIXED  # deterministic wallclock keeps row hashes addressable


# --------------------------------------------------------------------- fixtures
@pytest.fixture
def wiki_graph():
    # Eight articles, one disconnected island, deliberately lopsided degree.
    return {
        "Fluid dynamics": {"content": "fd text", "links": ["Hydraulics", "Archimedes screw", "Lever"]},
        "Hydraulics": {"content": "hy text", "links": ["Fluid dynamics", "Lever"]},
        "Archimedes screw": {"content": "as text", "links": ["Lever"]},
        "Lever": {"content": "lv text", "links": ["Fluid dynamics"]},
        "Pump": {"content": "pu text", "links": ["Hydraulics"]},
        "Turbine": {"content": "tu text", "links": ["Pump", "Fluid dynamics"]},
        "Isolated A": {"content": "ia text", "links": []},
        "Isolated B": {"content": "ib text", "links": ["Isolated A"]},
    }


@pytest.fixture
def fabric(wiki_graph):
    return CellFabric(wiki_graph, seeds=["Fluid dynamics"])


@pytest.fixture
def ledger(fabric):
    led = FabricLedger(actor="test-crab", fabric=fabric, clock=_clock)
    led.bind_fabric()
    return led


# --------------------------------------------------------------------- hash primitives
def test_fnv1a_offset_basis():
    assert "%08x" % fnv1a32(b"") == "811c9dc5"


def test_fnv1a_matches_laya4quilt_recipe():
    # One recipe across the 4quilt family: canonical JSON + fnv1a-32.
    row = {"b": [2, 3], "a": {"z": 1, "y": 2}}
    want = fnv1a32(canonical(row))
    assert want == fnv1a32('{"a":{"y":2,"z":1},"b":[2,3]}')


def test_canonical_key_order_independent():
    assert canonical({"b": 1, "a": 2}) == canonical({"a": 2, "b": 1})


# --------------------------------------------------------------------- fabric build
def test_addresses_are_integers_and_unique(fabric):
    addrs = [c.address for c in fabric.cells.values()]
    assert all(isinstance(d, int) and isinstance(i, int) for d, i in addrs)
    assert len(set(addrs)) == len(addrs)


def test_bfs_depth_monotonic_along_edges(fabric):
    for cell in fabric.cells.values():
        for target in cell.out_links:
            assert fabric.cells[target].address[0] <= cell.address[0] + 1 or cell.address[0] == -1


def test_seed_gets_depth_zero(fabric):
    assert fabric.cells["Fluid dynamics"].address[0] == 0


def test_disconnected_islands_isolated(fabric):
    assert fabric.cells["Isolated A"].address[0] == -1
    assert fabric.cells["Isolated B"].address[0] == -1


def test_content_binding_deterministic_and_key_order_free(wiki_graph):
    g2 = {k: {"content": v["content"], "links": list(v["links"])} for k, v in wiki_graph.items()}
    f1, f2 = CellFabric(wiki_graph, seeds=["Fluid dynamics"]), CellFabric(g2, seeds=["Fluid dynamics"])
    assert f1.state_hash() == f2.state_hash()


def test_energy_initialized_from_degree(fabric):
    # fd: in 3 + out 3 = 6; max in-degree = 3 → 6*1024//(2*3) = 1024 (saturates).
    assert fabric.cells["Fluid dynamics"].energy == ENERGY_SCALE
    # Isolated A: degree 1, max in-degree 3 → 1*1024//(2*3) = 170.
    assert fabric.cells["Isolated A"].energy == ENERGY_SCALE // 6


def test_energy_is_integer_everywhere(fabric):
    fabric.warmup(5)
    for c in fabric.cells.values():
        assert isinstance(c.energy, int)


# --------------------------------------------------------------------- cellular rules
def test_diffusion_moves_toward_neighbor_mean(fabric):
    hub = fabric.cells["Fluid dynamics"]
    iso = fabric.cells["Isolated A"]
    before_hub, before_iso = hub.energy, iso.energy
    fabric.round()
    # Hub is above the neighbor mean → cools; isolated has no neighbors → frozen.
    assert hub.energy <= before_hub
    assert fabric.cells["Isolated A"].energy == before_iso


def test_diffusion_is_integer_floored(fabric):
    fabric.warmup(10)
    for c in fabric.cells.values():
        assert isinstance(c.energy, int)


def test_survival_threshold(fabric):
    fabric.warmup(10)
    assert not fabric.alive("Isolated A")   # energy 0 < SURVIVE_MIN
    assert fabric.alive("Fluid dynamics")


def test_grant_admission_reasons(fabric):
    fabric.warmup(3)
    ok, reason = fabric.grant("Fluid dynamics", "Hydraulics")
    assert ok and reason == "GRANTED"
    ok, reason = fabric.grant("Ghost", "Hydraulics")
    assert not ok and reason == "SRC_UNKNOWN"
    ok, reason = fabric.grant("Fluid dynamics", "Ghost")
    assert not ok and reason == "DST_UNKNOWN"


def test_low_energy_target_refused():
    # Starve D: hub H and pumper E set max degree 7, so D (deg 1) lands at 73.
    nodes = {
        "H": {"content": "h", "links": ["H", "H", "S"]},
        "S": {"content": "s", "links": ["D"]},
        "D": {"content": "d", "links": []},
        "E": {"content": "e", "links": ["S", "S", "S", "S", "S"]},
    }
    fab = CellFabric(nodes, seeds=["H"])
    assert fab.cells["D"].energy < GRANT_MIN
    assert fab.alive("S")
    ok, reason = fab.grant("S", "D")
    assert not ok and reason == "DST_ENERGY_BELOW_GRANT_MIN"


# --------------------------------------------------------------------- ledger
def test_bind_books_fabric_digest(ledger):
    assert ledger.rows[0]["op"] == "BIND"
    assert ledger.rows[0]["payload"]["digest"]["cells"] == 8


def test_chain_links_and_ticks(ledger):
    pack = ledger.book_pack(["Fluid dynamics", "Hydraulics", "Lever"])
    assert pack["pack"]["op"] == "TICK"
    assert pack["pack"]["chain_prev"] == ledger.rows[0]["row_hash"]
    assert pack["pack"]["tick"] == 2
    assert pack["link"]["op"] == "LINK"


def test_grants_decided_cellularly_and_booked(ledger):
    out = ledger.book_pack(["Fluid dynamics", "Hydraulics", "Lever"])
    # fd→Hydraulics, fd→Lever, Hydraulics→Lever, Hydraulics→fd, Lever→fd all in-pack.
    assert len(out["grants"]) + len(out["refusals"]) == 5
    for g in out["grants"]:
        src, dst = g["src"], g["dst"]
        assert ledger.fabric.cells[dst].energy >= GRANT_MIN


def test_refused_grants_are_named_rows(ledger):
    out = ledger.book_pack(["Pump", "Turbine", "Isolated A", "Isolated B"])
    reasons = [r["payload"]["reason"] for r in ledger.rows if r["op"] == "REFUSED"]
    assert "SRC_ENERGY_BELOW_SURVIVE_MIN" in reasons or "DST_ENERGY_BELOW_GRANT_MIN" in reasons
    assert all(out["pack"]["row_hash"] in r["payload"]["pack"] for r in ledger.rows
               if r["op"] == "REFUSED" and "pack" in r["payload"])


def test_empty_and_duplicate_packs_refuse(ledger):
    r = ledger.book_pack([])
    assert r["op"] == "REFUSED" and r["payload"]["reason"] == "EMPTY_PACK"
    r2 = ledger.book_pack(["Pump", "Pump"])
    assert r2["op"] == "REFUSED" and r2["payload"]["reason"] == "DUP_IN_PACK"


def test_mask_view_reproducible(ledger):
    ledger.book_pack(["Fluid dynamics", "Hydraulics", "Lever"])
    m1 = ledger.mask_view("canon")
    # Recompute mask hash from rows alone: reproducibility receipt.
    link = next(r for r in ledger.rows if r["op"] == "LINK")
    assert m1["masks"][0]["mask_hash"] == sha256_hex(link["payload"]["edges"])


def test_view_head_captured_before_booking(ledger):
    before = ledger.rows[-1]["row_hash"]
    v = ledger.mask_view("canon")
    assert v["provenance"]["ledger_chain_head"] == before
    assert ledger.rows[-1]["op"] == "VIEW"


def test_unknown_view_refuses(ledger):
    r = ledger.mask_view("xml")
    assert r["op"] == "REFUSED" and r["payload"]["reason"] == "UNKNOWN_VIEW_FORMAT"


def test_export_plural_preservation(ledger):
    out = ledger.export_fabric()
    assert len(out["jsonl"]) == 8
    assert len(out["canon"]["cells"]) == 8
    assert ledger.rows[-1]["payload"]["format"] == "fabric-snapshot"


# --------------------------------------------------------------------- verification
def test_verify_ok(ledger):
    ledger.book_pack(["Fluid dynamics", "Hydraulics"])
    ok, bad = ledger.verify()
    assert ok and bad is None


def test_tamper_pins_at_row(ledger):
    ledger.book_pack(["Fluid dynamics", "Hydraulics"])
    victim = ledger.rows[0]
    victim["payload"]["digest"]["cells"] = 999
    ok, bad = ledger.verify()
    assert not ok
    assert bad == victim["row_hash"]


def test_splice_detected(ledger):
    ledger.book_pack(["Fluid dynamics", "Hydraulics"])
    ledger.rows[1]["chain_prev"] = "deadbeef"
    ok, bad = ledger.verify()
    assert not ok


def test_row_hash_stable_under_key_order():
    # The verify recipe must not depend on dict insertion order.
    fab = CellFabric({"A": {"content": "a", "links": ["B"]}, "B": {"content": "b", "links": []}},
                     seeds=["A"])
    led = FabricLedger("x", fab, clock=_clock)
    led.bind_fabric()
    h1 = led.rows[0]["row_hash"]
    led2 = FabricLedger("x", CellFabric({"A": {"content": "a", "links": ["B"]},
                                         "B": {"content": "b", "links": []}}, seeds=["A"]), clock=_clock)
    led2.bind_fabric()
    assert h1 == led2.rows[0]["row_hash"]


# --------------------------------------------------------------------- adapter
def test_graph_index_duck_adapter():
    class FakeGI:
        def ids(self):
            return ["Doc A", "Doc B"]

        def get_outgoing_links(self, title):
            return {"Doc A": ["Doc B"], "Doc B": []}[title]

    fab = fabric_from_graph_index(FakeGI(), seed_titles=["Doc A"])
    assert set(fab.cells) == {"Doc A", "Doc B"}
    assert fab.cells["Doc A"].address[0] == 0
    assert fab.cells["Doc B"].address[0] == 1
    assert fab.cells["Doc A"].content_hash != fab.cells["Doc B"].content_hash
