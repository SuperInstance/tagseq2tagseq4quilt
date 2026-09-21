# tagseq2tagseq closeout plan

Horizon: cluster compute available until roughly 2026-10-29 (~6 weeks). Cluster is
near-saturated; assume you get a minority share of nodes, not a queue that drains.

Status of this doc: written 2026-09-17 from a full audit of the repo, all five worktrees,
all three open PRs, and 14 Claude transcripts (including the Bedrock-era ones that can no
longer be opened interactively).

---

## 0. The two things that are actually urgent

**a. You have zero jobs running.** The yield watcher (pid 39863, running 12 days from the
memexp worktree) gave every node back to other users. It is working as designed: it yields
whenever anyone else has unmet demand. On a saturated cluster with a hard deadline, that
policy converges to you getting nothing. Yesterday it cancelled three jobs; today it
cancelled the rest and is now looping on "net 11-12 nodes needed" every six minutes.

Decision needed: keep yielding, yield only to jobs that would otherwise not start at all,
or stop yielding. This is the single largest lever on how much of the remaining six weeks
you actually get.

**b. 27 uncommitted files in `tagseq2tagseq-memexp`**, including three that exist on no
branch anywhere: `eval/viz/plot_epochs_to_degradation.py`,
`eval/viz/epochs_to_degradation_java_runs.json`, and
`paper/figures/epochs_to_degradation_java.png`. Also uncommitted: the `main.py` warmup
rewrite, the `eval/memorization.py --layout-policy` fix, the watcher's lineage-resume
logic, and 10 config changes. One stray `git checkout` or `git reset --hard` destroys the
experiment's only figure and its run manifest. Commit them before anything else touches
that worktree.

---

## 1. Where every thread actually stands

| thread | state | compute needed | blocked on |
|---|---|---|---|
| merged_v2 ladder (PR #12) | **COMPLETE** 2026-09-17 | none | your review + merge |
| eval-run-tracking (PR #9) | mechanism done, reviewed | none | merge #12, then a decision |
| link-injection (PR #11) | sciq grid done, clean | 1 GPU x ~2 h per rung | your call on scope |
| epochs-to-degradation (memexp) | drifted, partly invalidated | large | scope decision |
| sparsity (PR #6) | merged 2026-08-27 | none | worktree/branch cleanup |
| provenance (PR #7) | merged 2026-08-20 | none | nothing |
| paper (PRs #4, #10) | 49-page draft on main | none | items 3 and 4 below |

Merged already: PRs #4, #5, #6, #7, #8, #10. Open: #12 (ready), #11 (draft, disjoint),
#9 (draft, stacked on #12).

### merged_v2 ladder finished today
Job 97490 (16B natural doc_causal) completed 14:37 UTC, its by-source eval (99404)
completed 19:27, and the results are committed and pushed. All four doc_causal controls
are in and the within-pair table is full. PR #12 is mergeable and has never been reviewed
by a human.

One new finding landed with it: **both 32B-balanced arms degraded mid-run at peak LR** and
only the cross_doc arm recovered. That pair is now excluded from the "cross-doc training is
free" claim. Two candidate causes are written up and not separated: LR too hot for the 32B
schedule, or a data-repeat memorization effect. See item 5a.

---

## 2. Merge order (no compute, do this first)

1. Review and merge **#12**. It is complete, clean, 24 commits ahead of main, zero behind.
2. Retarget **#9** to main and rebase. After #12 lands, #9 collapses to a 3-file diff with
   no overlap. Merging #12 first also resolves the only conflicting file in the repo
   (`scripts/sweep_yield_watcher.sh`).
3. Make the RepoBench decision (item 3), apply it, then run the quarantine script that
   ships with #9. Order matters: the quarantine must run only after #9's distiller is on
   the branch you distill from, or main's distiller silently loses those metrics.
4. **#11** is disjoint and can merge whenever.
5. Cleanup: remove the `-sparsity` worktree (merged, remote branch already deleted) and
   delete the dead local branches `run-provenance-artifacts`, `mem-probe-metric`,
   `paper-draft`, `sparsity-scaling-law`, and the seven `worktree-agent-*` refs. Remote
   `paper-prose-draft`, `worktree-synthesis-todos-{dig,notes}`, `train`, `gen-inference`,
   `model_building`, `fix/ddp-multinode-packing-compile` are all merged or ancient.

---

## 3. The paper cites numbers that are known to be wrong

`paper/generated/values.tex` defines `compute.repobench_ppl.*` as 7.25 / 8.94 / 8.76 /
10.4, and `paper/sections/06_results.tex` renders them seven times, including the
compute-control table. Those four values are contaminated: the re-run under PR #9 collapses
all four to about 5.9 with overlapping confidence intervals, because flat `repobench`
hardcodes `mask_type='doc_causal'` (`eval/scoring.py:599`) and is therefore structurally
incapable of showing a cross-doc effect. The old spread came from a different code path
writing eval results into training run dirs.

`check_grounding.py` passes on this, because the ledger's `expected:` still holds the old
values. It cannot detect this class of drift.

Three options, from the thread that found it:
- **(a) Drop** the flat four-way compute-control claim.
- **(b) Re-frame** as a within-`cross_doc_link` delta on `repobench_cross_doc`, which
  reproduced exactly: Java 1.383 vs 1.448, Python 1.700 vs 1.792.
- **(c) Build** a packed multi-doc RepoBench that applies each model's own mask. New code
  plus four small eval jobs.

Recommendation: **(b), and drop the compute-control framing**. It is free, it is honest,
and it is coherent with the sparsity result that the link benefit is overwhelmingly an
inference-time effect. Treat (c) as optional if time allows late. This is the highest-value
unblock in the whole project and it costs no compute.

---

## 4. Remaining paper gaps that cost nothing

- 30 `\fillin{}` blanks: 7 in the datasets section, 10 in results, 1 in the abstract
  ("strengthens/weakens?"). The diversity-scaling blanks are now answerable from the
  finished ladder.
- 11 `literal` ungrounded-debt ledger entries: two traversal val-losses, eight step-time /
  speedup / coverage numbers taken from README prose whose raw CSVs were never located, and
  one cross-run regression fit.
- 16 `singledoc.*.ci` keys are defined but never cited.
- No LaTeX toolchain on this host, so the draft's buildability is unverified. Worth one
  check from your laptop.

---

## 5. What to spend the remaining compute on

Ranked by scientific value per node-hour. My recommendation is to fund 5a and 5b, treat 5c
as optional, and make a hard scope call on 5d.

**5a. Memorization probe on the two 32B-balanced checkpoints.** Eval only, no training.
It separates "LR too hot" from "data-repeat memorization" for the degradation finding, and
it is the one measurement that serves both the ladder and the epochs-to-degradation
experiment. Cheapest load-bearing thing on this list. Do it first.

**5b. Two extra seeds of the 3.9B cross_doc arm.** Every rung in the ladder is a single
seed, and the headline claim is that the cross-doc delta is *flat* across 8x tokens. Flat
against an unmeasured noise floor is not a result a reviewer will accept. The RESULTS doc
already admits a 0.03-0.05 wobble and then dismisses a +0.43 outlier as noise post hoc. Two
more seeds at the cheapest rung convert the weakest part of the paper into a measured one.

**5c. Link-injection: one real retriever rung.** Currently the "retrieved" condition is
junk (302 of 999 titles are literally "?"), so the negative interaction measures junk
tolerance, not retrieval. A BM25 or entity-match rung is roughly one GPU for a couple of
hours and makes PR #11 a result rather than a scaffold. The stronger matched pair it also
wants is a new training run; that needs your explicit approval and I would skip it.

**5d. epochs-to-degradation: decide whether to finish or freeze.** See item 6. If you
finish it: re-run e12 and e16 on both masks at muon_lr 0.002, relaunch the dead java cdl
e16 arm, then probe. That is four multi-day single-node runs and it is the most expensive
item on this page. If you freeze it: probe the already-finished wiki e2-e8 ladder, write up
what the LR sweep showed, and park it. **I recommend freezing it** and spending those nodes
on 5a and 5b.

Also queued but optional, from the ladder's own STATUS: re-port the specialists through
`scripts/eval_ports_slurm.sh` with flat nll, and a wiki community-pack grant check.

---

## 6. Where to be skeptical (you asked)

Ordered by how much damage each does if left alone.

1. **The paper's RepoBench numbers are wrong and still published.** Item 3.
2. **Single seed everywhere in the ladder.** "Flat across scale and diversity" is asserted
   against a noise floor that was never measured. Item 5b.
3. **"Matches or beats specialists on 9 of 13 ports" counts three ties as wins** (6 win, 3
   tie, 4 loss), and the specialist numbers come from a different lineage with different
   harness discipline. The specialist-headroom confound is acknowledged and unresolved.
4. **The retracted headline is still at the top of `RESULTS_merged_v2_diversity_scaling.md`**
   with a "supersede every figure here" banner rather than being removed. The
   `merged_all_v2` family was retracted on 2026-08-14 for a sequential-not-interleaved
   dataloader bug. Anyone reading top-down sees the dead numbers first.
5. **epochs-to-degradation drifted into a different experiment than the one designed.** The
   corpus changed go to java; the cross-doc hard-repetition baseline was dropped entirely,
   so fresh-vs-repeat is no longer tested; the headline metric moved from train/val gap to
   absolute val_nll mid-flight; the eval checkpoint moved from `latest.pt` to
   `best_model.pt`; the probe layout policy differs between arms; and the verbatim-recall
   probe, the dcl/concat masks, and the `standard_pack` baseline were never run. Each change
   was individually defensible. Together they mean the current figure does not answer the
   original question.
6. **That experiment's headline "degradation" is probably an LR artifact.** The LR sweep
   that finished 2026-09-16 shows muon_lr 0.002 recovers the e8 floor (1.0617 vs 1.0604)
   while 0.003 reproduces the degraded e16 number (1.0949 vs 1.0947). The e12/e16 points on
   both masks are uninterpretable until re-run at 0.002. The live session has not yet looked
   at this result.
7. **dc-vs-cdl separation is inside the noise.** Confidence intervals are about +/-0.010 and
   the e8 gap is 0.0146.
8. **Roughly 60 watcher yield-and-resume cycles were never re-audited.** Resume correctness
   was checked once in August, before the churn. A pre-2026-09-02 watcher bug caused 120
   silent full resets ("fresh, no ckpt") against 163 real resumes, so pre-September
   trajectories contain restarted-from-zero segments. Separately, `main.py` now silently
   ignores `train_loop.warmup_steps`, so any stale config trains at 0% warmup with no error.
9. **A latent watcher bug can silently lose runs.** Yielded jobs whose cancel return code
   was swallowed never reach `yielded_jobs.tsv` and therefore never auto-resume. It bit five
   jobs on 2026-08-26 harmlessly. Today's log shows the related failure mode live:
   `SKIP-YIELD 99404: could not map to run_dir/config`.
10. **The link-injection gold interaction is fragile.** +0.27 nats against a +5 main effect,
    heavy-tailed with a +0.10 median, on an undertrained 3614-step pair, after mid-flight
    swaps from hellaswag to sciq and from precise to coarse grant detection.
11. **Yesterday three duplicate LR-sweep jobs ran for about 43 node-hours** re-treading arms
    that had already completed hours earlier, because a session resumed from stale
    checkpoints. On a saturated cluster with six weeks left, add a "does this run already
    exist" check before any launch.

---

## 7. Housekeeping

- `/fss/evin_t/tagseq2tagseq/runs/` is 2.5 TB and nothing has been written to it since
  2026-08-16; the live runs root is `/fss-data`. Largest reclaim target by far.
- `data/github_graph_extractor/sample_{1M,10M,100M}.jsonl` is 131 GB, and the committed
  graph keys predate the 2026-06-17 normalization refactor, so they may be stale as well as
  large.
- Recreatable caches: 7.6 GB in `-evaltrack`, 5.9 GB in `-memexp`.
- Removing the `-sparsity` worktree reclaims 37 MB. Do it for tidiness, not space.
- `/fss/evin_t/aws_keys_scratch.txt` (2026-04-08) sits in your home directory. Worth
  rotating or deleting.

---

## 8. Suggested order

Week 1: commit the memexp files; settle the watcher policy; merge #12; make the RepoBench
call and apply it; launch 5a and 5b.
Week 2: retarget and merge #9; run the quarantine; fill the diversity `\fillin`s from the
finished ladder; merge #11 or fund 5c.
Weeks 3-4: land seed results into the paper; freeze or finish epochs-to-degradation per 5d;
re-port specialists if nodes are free.
Weeks 5-6: paper only. Verify the LaTeX build, clear remaining grounding debt, branch and
worktree cleanup, final artifact backup.
