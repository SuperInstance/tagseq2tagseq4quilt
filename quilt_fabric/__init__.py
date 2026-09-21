"""Quilt fabric: graph corpora as cellular decision substrates.

Adapts tagseq2tagseq for the quilt ecosystem. Documents become **cells** on
integer addresses; hyperlinks/imports become **LINK** rows; pack traversal
becomes a **TICK** ledger; and the cross-document attention mask stops being
a hand-set flag — it is the output of an integer cellular automaton over the
fabric, receipted row by row.

Design commitments (shared with the rest of the 4quilt family):

- **Integer identity**: a cell's address is (depth, sibling_index) from a BFS
  over the link graph — integers only. Floats never touch identity, and
  energy is fixed-point integer math throughout (encodings you can diff).
  Energy = total degree (in + out) normalized by twice the max in-degree,
  floored — so the corpus's most-cited node can saturate the scale while
  long-tail documents stay near zero.
- **Hash-chained receipts**: every decision books a row; the chain is
  fnv1a-32 over canonical JSON (sorted keys, tight separators), genesis
  chain "0"*8. Same recipe as laya4quilt's decision ledger: one
  verification story across the family, recomputable in any substrate.
- **Refusal visibility**: rejected link grants book named REFUSED rows.
  A fabric that can refuse silently can censor silently.
- **Derived state is derived**: mask exports and fabric digests are VIEW
  projections; the chain head is captured before the VIEW row is booked.
- **Preservation is plural**: fabric snapshots export to jsonl AND canon
  stub, or the export is not preservation.

Stdlib-only. No torch, no numpy, no Triton: the training stack consumes the
module's outputs, never the reverse.
"""
import hashlib
import json
from collections import deque
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

__all__ = [
    "FNV1A_OFFSET",
    "fnv1a32",
    "canonical",
    "sha256_hex",
    "Cell",
    "CellFabric",
    "FabricLedger",
    "fabric_from_graph_index",
]

FNV1A_OFFSET = 0x811C9DC5
FNV1A_PRIME = 0x01000193
MASK32 = 0xFFFFFFFF
GENESIS = "0" * 8

# Cellular policy defaults (integer fixed-point, SCALE = 1024).
ENERGY_SCALE = 1024
SURVIVE_MIN = 256       # 0.25 in fixed point
GRANT_MIN = 256         # a grant requires a living target: attention is earned by survival
DIFFUSION_DAMP = 8      # pull toward neighbor mean, damped
DEFAULT_WARMUP_ROUNDS = 3


def fnv1a32(data):
    """fnv1a-32 over bytes — the 4quilt family's chain algorithm."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    h = FNV1A_OFFSET
    for byte in data:
        h ^= byte
        h = (h * FNV1A_PRIME) & MASK32
    return h


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(obj):
    if not isinstance(obj, str):
        obj = canonical(obj)
    return hashlib.sha256(obj.encode("utf-8")).hexdigest()


class Cell:
    """One document: integer address, content binding, fixed-point energy."""

    __slots__ = ("doc_id", "address", "content_hash", "energy", "out_links", "in_degree")

    def __init__(self, doc_id, address, content_hash, energy, out_links, in_degree):
        self.doc_id = doc_id
        self.address = address            # (depth, sibling_index) — integers
        self.content_hash = content_hash  # sha256 of identity + content binding
        self.energy = energy              # int, fixed point (ENERGY_SCALE = 1.0)
        self.out_links = out_links        # list[doc_id]
        self.in_degree = in_degree


class CellFabric:
    """A graph corpus as a cellular substrate.

    Built from a neutral form — ``nodes``: {doc_id: {"content": str-or-hash,
    "links": [doc_id...]}} — so the fabric never depends on GraphIndex,
    torch, or the filesystem layout. ``fabric_from_graph_index`` adapts the
    real loader; tests and demos can build fabrics from plain dicts.
    """

    def __init__(self, nodes: Dict, seeds: Optional[Sequence] = None,
                 energy_scale: int = ENERGY_SCALE):
        if not nodes:
            raise ValueError("fabric requires at least one node")
        self.energy_scale = energy_scale
        self.policy = {
            "energy_scale": energy_scale,
            "survive_min": SURVIVE_MIN,
            "grant_min": GRANT_MIN,
            "diffusion_damp": DIFFUSION_DAMP,
        }
        self.cells: Dict[str, Cell] = {}
        self._build(nodes, list(seeds) if seeds else None)
        self.rounds_run = 0

    # ------------------------------------------------------------------ build
    def _build(self, nodes: Dict, seeds: Optional[List[str]]):
        # In-degrees first — energy initializes from structural prominence.
        in_degree = {doc_id: 0 for doc_id in nodes}
        for doc_id, spec in nodes.items():
            for target in spec.get("links", []):
                if target in in_degree:
                    in_degree[target] += 1
        max_deg = max(1, max(in_degree.values()))

        # BFS from seeds (or every node, ordered) → integer (depth, index).
        seeds = seeds if seeds else sorted(nodes)
        seen: Set[str] = set()
        q = deque()
        for s in seeds:
            if s in nodes and s not in seen:
                seen.add(s)
                q.append((s, 0))
        sibling_count: Dict[int, int] = {}
        while q:
            doc_id, depth = q.popleft()
            idx = sibling_count.get(depth, 0)
            sibling_count[depth] = idx + 1
            spec = nodes[doc_id]
            deg = in_degree[doc_id] + len(spec.get("links", []))
            energy = int((deg * self.energy_scale) // (2 * max_deg))
            self.cells[doc_id] = Cell(
                doc_id=doc_id,
                address=(depth, idx),
                content_hash=sha256_hex({"id": doc_id, "content": spec.get("content", "")}),
                energy=energy,
                out_links=[t for t in spec.get("links", []) if t in nodes],
                in_degree=in_degree[doc_id],
            )
            for target in self.cells[doc_id].out_links:
                if target not in seen:
                    seen.add(target)
                    q.append((target, depth + 1))
        # Disconnected components: appended after, depth continues as -1 lane.
        for doc_id in sorted(nodes):
            if doc_id not in self.cells:
                spec = nodes[doc_id]
                deg = in_degree[doc_id] + len(spec.get("links", []))
                self.cells[doc_id] = Cell(
                    doc_id=doc_id,
                    address=(-1, len(self.cells)),
                    content_hash=sha256_hex({"id": doc_id, "content": spec.get("content", "")}),
                    energy=int((deg * self.energy_scale) // (2 * max_deg)),
                    out_links=[t for t in spec.get("links", []) if t in nodes],
                    in_degree=in_degree[doc_id],
                )

    # ------------------------------------------------------------------ cellular rules
    def round(self):
        """One cellular round: integer diffusion toward the neighbor mean,
        floored. Survival is not mutated here — a cell is alive iff its
        energy clears SURVIVE_MIN at decision time. Derived state stays
        derived; the fabric books nothing."""
        new_energy = {}
        for doc_id, cell in self.cells.items():
            nbs = [self.cells[t].energy for t in cell.out_links if t in self.cells]
            if not nbs:
                new_energy[doc_id] = cell.energy
                continue
            mean = sum(nbs) // len(nbs)
            pull = (mean - cell.energy) // DIFFUSION_DAMP
            new_energy[doc_id] = cell.energy + pull
        for doc_id, e in new_energy.items():
            self.cells[doc_id].energy = e
        self.rounds_run += 1

    def warmup(self, rounds: int = DEFAULT_WARMUP_ROUNDS):
        for _ in range(rounds):
            self.round()

    def alive(self, doc_id: str) -> bool:
        cell = self.cells.get(doc_id)
        return cell is not None and cell.energy >= SURVIVE_MIN

    def grant(self, src: str, dst: str) -> Tuple[bool, str]:
        """Cellular admission of a cross-document attention grant.

        Returns (admitted, reason). The reason is what the ledger books —
        grants and refusals are both first-class rows.
        """
        if src not in self.cells:
            return False, "SRC_UNKNOWN"
        if dst not in self.cells:
            return False, "DST_UNKNOWN"
        if not self.alive(src):
            return False, "SRC_ENERGY_BELOW_SURVIVE_MIN"
        if self.cells[dst].energy < GRANT_MIN:
            return False, "DST_ENERGY_BELOW_GRANT_MIN"
        return True, "GRANTED"

    # ------------------------------------------------------------------ state views
    def state_hash(self) -> str:
        """Binds the entire fabric state: addresses, energies, content hashes."""
        return sha256_hex({
            doc_id: {
                "address": list(cell.address),
                "energy": cell.energy,
                "content_hash": cell.content_hash,
                "out": sorted(cell.out_links),
            }
            for doc_id, cell in sorted(self.cells.items())
        })

    def digest(self) -> Dict:
        return {
            "cells": len(self.cells),
            "rounds": self.rounds_run,
            "state_hash": self.state_hash(),
            "policy": dict(self.policy),
        }


class FabricLedger:
    """Hash-chained receipts over fabric decisions. Row shape is byte-compatible
    with the laya4quilt decision ledger: same canonical form, same fnv1a-32
    chain, genesis "0"*8 — rows from both repos verify under one recipe."""

    def __init__(self, actor: str, fabric: CellFabric, clock=None):
        if not actor:
            raise ValueError("ledger requires an actor")
        self.actor = actor
        self.fabric = fabric
        self._clock = clock or __import__("time").time
        self.rows: List[dict] = []
        self._tick = 0

    def _book(self, op: str, payload: dict) -> dict:
        self._tick += 1
        row = {
            "tick": self._tick,
            "ts": round(self._clock(), 6),
            "op": op,
            "actor": self.actor,
            "fabric_state": self.fabric.state_hash(),
            "payload": payload,
            "chain_prev": self.rows[-1]["row_hash"] if self.rows else GENESIS,
        }
        row["row_hash"] = "%08x" % fnv1a32(canonical(row))
        self.rows.append(row)
        return row

    # ------------------------------------------------------------------ ops
    def bind_fabric(self):
        """BIND: the fabric snapshot this ledger's history starts from."""
        return self._book("BIND", {
            "kind": "fabric",
            "digest": self.fabric.digest(),
            "cells": {
                doc_id: {
                    "address": list(c.address),
                    "energy": c.energy,
                    "content_hash": c.content_hash,
                }
                for doc_id, c in sorted(self.fabric.cells.items())
            },
        })

    def book_pack(self, pack_ids: List[str], link_positions: Optional[Dict[Tuple[str, str], int]] = None):
        """TICK + EFFECT/REFUSED: one packed training sequence, admitted cell
        by cell, with every cross-document grant decided by the cellular
        policy and booked — grants as EFFECT rows carrying the citation
        edge, rejections as named REFUSED rows. The mask this pack trained
        under is exactly the set of admitted grants: reproducible from rows."""
        link_positions = link_positions or {}
        if not pack_ids:
            return self._book("REFUSED", {"reason": "EMPTY_PACK"})
        seq = []
        for doc_id in pack_ids:
            if doc_id in seq:
                return self._book("REFUSED", {"reason": "DUP_IN_PACK", "doc_id": doc_id})
            seq.append(doc_id)
        grants, refusals = [], []
        for i, src in enumerate(seq):
            for dst in self.fabric.cells[src].out_links:
                if dst not in seq:
                    continue
                admitted, reason = self.fabric.grant(src, dst)
                pos = link_positions.get((src, dst), 0)
                edge = {"src": src, "dst": dst, "src_pos": i, "link_pos": pos}
                if admitted:
                    grants.append(edge)
                else:
                    refusals.append({**edge, "reason": reason})
        pack = self._book("TICK", {
            "kind": "pack",
            "sequence": seq,
            "pack_hash": sha256_hex(seq),
            "grants": len(grants),
        })
        link_row = self._book("LINK", {"kind": "pack-grants", "pack": pack["row_hash"], "edges": grants})
        for ref in refusals:
            self._book("REFUSED", {"kind": "grant", "pack": pack["row_hash"], **ref})
        return {"pack": pack, "link": link_row, "grants": grants, "refusals": refusals}

    def mask_view(self, fmt: str = "canon"):
        """VIEW: receipted mask/digest export. Head captured before booking."""
        head = self.rows[-1]["row_hash"] if self.rows else GENESIS
        if fmt not in ("canon", "jsonl"):
            return self._book("REFUSED", {"reason": "UNKNOWN_VIEW_FORMAT", "format": fmt})
        self._book("VIEW", {"format": fmt, "rows": len(self.rows), "head": head})
        packs = [r for r in self.rows if r["op"] == "TICK"]
        grants = [r for r in self.rows if r["op"] == "LINK" and r["payload"].get("kind") == "pack-grants"]
        if fmt == "canon":
            return {
                "provenance": {
                    "ledger_chain_head": head,
                    "actor": self.actor,
                    "fabric_state": self.fabric.state_hash(),
                    "packs": len(packs),
                },
                "masks": [
                    {
                        "pack": p["payload"]["pack_hash"],
                        "sequence": p["payload"]["sequence"],
                        "mask_hash": sha256_hex(g["payload"]["edges"]),
                        "edges": g["payload"]["edges"],
                    }
                    for p, g in zip(packs, grants)
                ],
            }
        return {"head": head, "rows": list(self.rows)}

    def export_fabric(self):
        """VIEW + plural preservation: fabric snapshot as jsonl rows AND a
        canon stub, in one booked observation."""
        head = self.rows[-1]["row_hash"] if self.rows else GENESIS
        self._book("VIEW", {"format": "fabric-snapshot", "rows": len(self.rows), "head": head})
        jsonl = [
            {"doc_id": c.doc_id, "address": list(c.address), "energy": c.energy,
             "content_hash": c.content_hash, "rounds": self.fabric.rounds_run}
            for c in self.fabric.cells.values()
        ]
        canon = {
            "provenance": {"ledger_chain_head": head, "actor": self.actor,
                           "fabric_state": self.fabric.state_hash()},
            "cells": sorted(({"doc_id": c.doc_id, "address": list(c.address),
                              "hash": c.content_hash} for c in self.fabric.cells.values()),
                            key=lambda e: e["doc_id"]),
        }
        return {"jsonl": jsonl, "canon": canon}

    # ------------------------------------------------------------------ verify
    def verify(self):
        """Replay the chain. Returns (ok, first_bad_row_hash)."""
        prev = GENESIS
        for row in self.rows:
            want = "%08x" % fnv1a32(canonical({k: v for k, v in row.items() if k != "row_hash"}))
            if row.get("chain_prev") != prev or row.get("row_hash") != want:
                return False, row.get("row_hash", "unknown")
            prev = row["row_hash"]
        return True, None


# ---------------------------------------------------------------------- adapter
def fabric_from_graph_index(graph_index, seed_titles: Optional[Sequence[str]] = None) -> CellFabric:
    """Adapt a tagseq2tagseq GraphIndex (or anything duck-typed like one:
    ``ids()`` plus ``get_outgoing_links(title)``) into a CellFabric.

    Content binding hashes the normed identifier and the token locator —
    the durable parts of corpus identity — without touching token shards.
    """
    ids = graph_index.ids() if hasattr(graph_index, "ids") else []
    nodes = {}
    for title in ids:
        links = graph_index.get_outgoing_links(title)
        try:
            locator = graph_index.node_dicts[title]
        except Exception:
            locator = {}
        binding = {k: locator.get(k) for k in ("tok_shard_idx", "tok_offset_bytes", "tok_len") if k in locator}
        nodes[title] = {"content": sha256_hex({"id": title, "locator": binding}), "links": list(links)}
    return CellFabric(nodes, seeds=seed_titles)
