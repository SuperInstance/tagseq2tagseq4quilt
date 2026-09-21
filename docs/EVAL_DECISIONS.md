# Evaluation decisions and their reasoning

Why the evaluation is built the way it is, what has been retracted, and which
conclusions are load-bearing. Framing positions for the paper's prose live in
`paper/notes/synthesis_framing_notes.md`; open work lives in `TODOS.md`.

---

## The thesis metric

**Held-out perplexity is the wrong axis.** It measures base language-model quality,
which data volume dominates, so a merged model trailing specialists on it says nothing
about the mechanism. The thesis metric is the within-model cross-document delta on the
benchmark ports.

**The right comparison is a crossover at matched per-domain tokens**, not merged against
finished specialists. A merged model reaching a specialist's cross-doc ability at a
fraction of that specialist's per-domain data is the claim.

**Specialists are a fixed reference line, not a curve.** Only final and best checkpoints
were kept, so the intermediate specialist trajectory is unrecoverable. Rather than
retrain, the merged rungs are walked up to the fixed specialist reference.

**The contribution-isolating contrast is against matched-FLOP concat**, the residual of
`cross_doc_link` minus `doc_concat_link`, not minus `doc_causal`. A concat baseline
already buys most of the generic long-context gain; what it cannot have is a notion of
which document grants which. This is why the concat arms are rigor, not a survival test.

---

## Design choices and why the alternatives were rejected

**FineWeb was dropped entirely.** On an edgeless corpus the two masks are identical, so
a FineWeb-only baseline has no A/B at all. FineWeb mixed *into* the merge is pure
dilution: both arms see it identically, so it can only shrink the fraction of corpus
where the masks can differ, mechanically shrinking the measured effect. Using the FineWeb
fraction as a density axis is doubly confounded, since it is also a data-quality axis and
is not even monotone in density.

**Density is manipulated by per-edge, mask-time dropping.** Dropping at traversal time
changes which documents co-occur, so a change in the effect could be density or content
shift. Mask-time dropping holds the packing fixed, and keep=0 is then exactly equivalent
to `doc_causal`, which pins the line at zero by construction rather than by fit. Node
dropout was run as a robustness check and landed within 5 percent, so hub sensitivity is
not a concern.

**Repetition is capped at roughly four epochs per source**, following the memorization
literature. A balanced 32B build was caught repeating some small sources far past that
before it reached the flagship run.

**Evals use the fully cooled final checkpoint, not the best-validation checkpoint,**
because best-checkpoint selection ran on a validation metric that was itself buggy.

**Grants during training and validation are built from the graph's own ground-truth
edges.** A learned detector is needed only where links are not known ahead of time, which
means benchmarks and generation. That detector was designed and never built, which is why
native corpus-fetching generation is still unmeasured.

**No auxiliary structure loss.** Training and inference use the same mask under plain
next-token prediction. The argument is made in prose rather than by running an
auxiliary-loss arm.

---

## What is retracted

**Everything from the merged_all_v2 family, and every figure built on it.** Training
consumed each density bucket in pack order while the pack writer emitted sources in
blocks, so training began overwhelmingly on one source and ended on another, causing
catastrophic forgetting mid-run. This masqueraded convincingly as a too-hot learning
rate and cost a multi-day sweep before it was caught. The pre-fix ladder, the celebrated
8B port numbers, and the "merge beats specialists by 1.7 to 11 times" table were all
built on it. A canary confirmed the fix.

**"Diversity rescues wiki."** Re-investigated blind, with the investigating agent given
no priors. The harness was sound and grants fire densely on wiki, but the result splits
by model fit rather than by solo against merged: strongly positive on an under-fit model,
slightly negative on a well-fit one. The mechanism is that linked context helps a weak
language model and becomes noise to a strong one.

**The four-way RepoBench compute control.** The flat benchmark scores every model under
`doc_causal`, so it compares four checkpoints on an identical flat task. See `TODOS.md`.

---

## What survived scrutiny, and how much

**The placebo control.** The concern was that the cross-document arm simply sees more
tokens. The derangement keeps an example's own identifiers but swaps in a donor's
auxiliary *content*, so grant fire-rate is preserved by construction and the arms differ
only in what the grant reads. Placebo separation excludes zero on all three arms.

**The leakage control.** The concern was that the gain is memorized re-exposure, since
grants make verbatim copying easy and deduplication was sampling-only. Stratifying by
target-to-auxiliary n-gram overlap, the effect survives in the lowest-overlap stratum
everywhere. The honest nuance is that the leakage-robust component is smaller than the
headline average, so part of the headline magnitude was overlap-assisted.

**The within-code sparsity law.** The effect scales close to linearly with kept edge
fraction at evaluation time, with a strong fit across many cells.

---

## Results that complicate the story

**The benefit is largely inference-time, at least for code.** In the two-dimensional grid
over training density and evaluation density, training saturates early, and a model
trained *without* cross-document links exploits cross-document attention at inference
about as well as, and sometimes better than, one trained with them. This agrees
independently with the flat-RepoBench finding and with the sparsity result. It does not
sink the thesis, but it means "training installs the capability" is not what the code
evidence shows, and the paper should not imply it.

**The cross-dataset density regression is null and wrong-signed.** Pooling across the
inherent densities of many corpora to extrapolate past the densest buildable graph was
the original motivation for the sparsity sweep, and it does not work: the correlation is
weak and negative, with model convergence a heavy confound. Only the within-code
evaluation-time law is claimed.

**Every ladder rung is a single seed.** The headline is that the effect is flat across
scale, asserted against a noise floor that was never measured.

**The compute-matched crossover rests specifically on the cheapest rung.** At larger
rungs, merged-beats-specialist conflates diversity with more compute.

---

## Reproducibility

Eval numbers are not bit-reproducible across code evolution. Re-running a grounded
evaluation on a later commit gave results identical across two reruns but different from
the stored value, so the cause is code drift rather than hardware nondeterminism, and the
drift is visible at the precision the paper reports. Recording a commit per eval result is
insufficient because evals are often run with uncommitted changes, which is why each eval
now gets its own captured run directory.
