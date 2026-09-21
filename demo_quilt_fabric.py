"""Demo: a wiki corpus as a quilt fabric.

A small synthetic article graph stands in for a pretokenized corpus. The
fabric assigns integer cell addresses, runs the cellular policy, books two
packed sequences with receipted mask grants, resolves a tamper attempt, and
prints a canon mask digest. Stdlib-only: no torch, no shards, no network.

Run:  python demo_quilt_fabric.py --check
"""
import sys

from quilt_fabric import CellFabric, FabricLedger

WIKI = {
    "Fluid dynamics": {"content": "fd v1", "links": ["Hydraulics", "Archimedes screw", "Lever"]},
    "Hydraulics": {"content": "hy v1", "links": ["Fluid dynamics", "Lever"]},
    "Archimedes screw": {"content": "as v1", "links": ["Lever"]},
    "Lever": {"content": "lv v1", "links": ["Fluid dynamics"]},
    "Pump": {"content": "pu v1", "links": ["Hydraulics"]},
    "Turbine": {"content": "tu v1", "links": ["Pump", "Fluid dynamics"]},
    "Ancient technology": {"content": "at v1", "links": ["Archimedes screw", "Lever"]},
    "Unlinked orphan": {"content": "uo v1", "links": ["Pump"]},
}


def main():
    fabric = CellFabric(WIKI, seeds=["Fluid dynamics"])
    fabric.warmup(3)

    ledger = FabricLedger(actor="demo-operator", fabric=fabric)
    ledger.bind_fabric()

    print("cells (integer addresses, fixed-point energy):")
    for doc_id, cell in sorted(fabric.cells.items(), key=lambda kv: kv[1].address):
        print("  %-20s addr=%-8s energy=%4d in=%d" % (doc_id, cell.address, cell.energy, cell.in_degree))

    pack1 = ledger.book_pack(["Fluid dynamics", "Hydraulics", "Lever", "Archimedes screw"],
                             link_positions={("Fluid dynamics", "Hydraulics"): 12})
    pack2 = ledger.book_pack(["Pump", "Turbine", "Ancient technology", "Unlinked orphan"])

    print("\npacks:")
    for pack in (pack1, pack2):
        print("  %-28s grants=%d refusals=%d" % (
            pack["pack"]["payload"]["pack_hash"][:16] + "…",
            len(pack["grants"]), len(pack["refusals"])))
        for ref in pack["refusals"]:
            print("    REFUSED %-22s → %-22s %s" % (ref["src"], ref["dst"], ref["reason"]))

    ok, bad = ledger.verify()
    print("\nledger: %d rows, verify=%s" % (len(ledger.rows), ok))

    if "--check" in sys.argv:
        if not ok:
            print("CHECK FAILED: tamper pinned at row %s" % bad)
            return 1
        # Tamper drill: rewrite history, expect the chain to name the row.
        victim = ledger.rows[1]
        victim["payload"]["sequence"] = ["forged", "pack"]
        ok2, bad2 = ledger.verify()
        if ok2 or bad2 != victim["row_hash"]:
            print("CHECK FAILED: tamper drill did not pin at the forged row")
            return 1
        print("CHECK OK: %d-row chain verifies; tamper drill pins at forged row" % len(ledger.rows))

    canon = ledger.mask_view("canon")
    print("\ncanon mask digest (first pack):")
    m0 = canon["masks"][0]
    print("  pack:      %s…" % m0["pack"][:16])
    print("  mask hash: %s" % m0["mask_hash"])
    print("  edges:     %d granted cross-document grants" % len(m0["edges"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
