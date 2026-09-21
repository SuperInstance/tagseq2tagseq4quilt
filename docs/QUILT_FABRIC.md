# Quilt Fabric: graph corpora as cellular decision substrates

Adapts tagseq2tagseq for the quilt ecosystem. The corpus's documents become
**cells** on integer addresses; its hyperlinks/imports become **LINK** rows;
pack traversal becomes a **TICK** ledger; and the cross-document attention
mask stops being a hand-set flag — it becomes the output of an integer
cellular automaton over the fabric, receipted row by row.

This is *data-level* provenance, complementary to the existing
[`provenance/`](../provenance/) system: `provenance/` answers "which run
produced this paper number?" — the fabric answers "which cells, admitted in
what order, under which receipted cellular policy, produced this training
example?" Both are grounded ledgers; they bind different layers.

## The mapping

| tagseq2tagseq concept | quilt fabric concept |
|---|---|
| document (node) | **cell** — integer address `(depth, sibling_index)` from directed BFS |
| hyperlink / import | **LINK** row — citation edges as first-class receipts |
| pack (sequence of docs) | **TICK** row — the pack's cell sequence under one hash |
| cross-doc attention grant | **EFFECT** — decided by the cellular policy, booked or REFUSED |
| attention mask | **VIEW** — `mask_view()`: a receipted, recomputable projection |
| training example | attested observation: pack hash + grant set + fabric state hash |

## Cellular logic (integer fixed-point throughout, SCALE = 1024)

- **Energy** initializes from structural prominence: total degree (in + out)
  normalized by twice the max in-degree, floored. The most-cited node can
  saturate; the long tail stays near zero. No floats touch identity or energy.
- **Diffusion** (`round()`): each cell pulls toward its out-neighbor energy
  mean, damped `// 8`. Cells with no out-links are frozen — isolation is
  data, not costume.
- **Survival**: a cell is alive iff energy ≥ 256.
- **Grant admission**: source alive AND target energy ≥ 256 — *a grant
  requires a living target; attention is earned by survival.* Rejections
  book named REFUSED rows (`SRC_ENERGY_BELOW_SURVIVE_MIN`,
  `DST_ENERGY_BELOW_GRANT_MIN`, …). A fabric that can refuse silently can
  censor silently.

## Encodings and verification

- **Chain**: fnv1a-32 over canonical JSON (`sort_keys`, tight separators,
  `ensure_ascii=False`), genesis `"0"*8` — byte-compatible with the
  laya4quilt decision ledger. One verification recipe across the 4quilt
  family; any substrate that can JSON-encode and run fnv1a verifies any
  other substrate's rows.
- **Content binding**: sha-256 over `{id, content}` per cell; fabric state
  hash binds addresses, energies, content hashes, and edges — same corpus +
  same policy = same state hash = reproducibility receipt.
- **Mask receipts**: `mask_view("canon")` emits per-pack `mask_hash` =
  sha-256 over the booked grant edges. Two nodes building the same mask
  from rows alone agree on the hash, or something is lying.
- **Plural preservation**: `export_fabric()` books one VIEW row and returns
  the snapshot as both JSONL and a canon stub — k ≥ 2 formats or it is not
  preservation.
- **Tamper**: `verify()` replays the chain and pins the first bad row.
  Mutating any booked field — a sequence, a grant, a cell count — names its
  row. (The demo's `--check` runs a live tamper drill.)

## Using it from the real pipeline

```python
from quilt_fabric import CellFabric, FabricLedger, fabric_from_graph_index

fabric = fabric_from_graph_index(graph_index, seed_titles=seed_ids)
fabric.warmup(3)                      # let diffusion settle
ledger = FabricLedger(actor="train-run-7", fabric=fabric)
ledger.bind_fabric()                  # receipt the corpus snapshot

for pack_ids, link_positions in my_pack_sampler():
    out = ledger.book_pack(pack_ids, link_positions)
    grants = out["grants"]            # feed your mask builder exactly this
mask_canon = ledger.mask_view("canon")
ok, bad = ledger.verify()
```

`book_pack` never touches Triton or torch: it decides *which* grants the
mask may contain. The kernel consumes the grant list; the ledger keeps the
receipts. The training stack consumes the module's outputs, never the
reverse.

## Tests

```bash
python -m pytest tests/quilt_fabric/ -q   # 29 tests, stdlib-only module
python demo_quilt_fabric.py --check
```

Note: the repo's root `tests/conftest.py` imports `tunalab.testing`,
which was missing from the tree and blocked *all* pytest collection. A
minimal `tunalab/testing.py` (device/dtype parametrization) is included in
this change to unblock collection.
