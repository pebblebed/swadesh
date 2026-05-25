# Hyperparameter beam search — log

Goal: find a good way to train the conditional vocalic decoder.
**Selection metric: best clean `val_loss`** (lower = better generalization), with
**relatedness `rho` as a guardrail** (don't ship a config that tanks it). Beam width 4
(4 configs/round, run in parallel on the RTX 4070). Keep the best 1–2 each round,
mutate winners + add a fresh hypothesis. Fixed split (`seed=0`); **test held out**,
read only for the final pick. All runs log to MLflow `swadesh-vocalic-decoder`
(tag `round`), early stopping on `val_loss` (patience 5), `max_epochs 40`, batch 512.

Infra (commit 87327f9): vectorized collate (~400× faster; ~8s/epoch full corpus),
knobs for optimizer / weight decay / cosine+warmup LR / embedding dropout / label
smoothing (train-only so val stays comparable), early stopping + `best_val_loss`.

## Seed observations (runs 0)
- **vanilla** (adam, dropout 0.1): overfit — val_loss crept up while train fell.
- **dropout 0.75**: heavy regularization probe (superseded; reproduce on new infra if needed).

## Round 1 — regularization vs capacity (DONE)
All else equal (lr 2e-3, adam unless noted, no schedule). best_val = min val_loss.

| run | key args | best_val | notes |
|-----|----------|---------:|-------|
| **r1-drop** | dropout 0.3, emb_dropout 0.1 | **5.743** | WINNER — moderate dropout helps most |
| r1-wd | adamw, weight_decay 0.05 | 5.787 | L2 also helps |
| r1-baseline | dropout 0.1 (control) | 5.830 | the overfit reference |
| r1-small | hidden 128, emb 32, dropout 0.2 | 5.860 | too small -> underfits |

Takeaways: regularization helps (drop > wd > baseline); cutting capacity hurts
(underfit), so keep >= baseline capacity and regularize. Direction: stack dropout +
weight decay, probe dropout strength, add an LR schedule, try bigger+regularized.

BUG FOUND + FIXED (commit pending): runs crashed at MLflow `finalize` — it prints a
"🏃 View run" emoji that a Windows cp1252 stdout can't encode (UnicodeEncodeError),
aborting before test/probe/best-val logged (the `; echo` masked the nonzero exit).
Fix: force UTF-8 stdout in train.py/eval.py; log post-hoc metrics (best_val/test/rho)
via the MLflow client with run reactivation (PTL finalizes the run at fit-end and the
server drops late writes). Round 1 still rankable from the complete val_loss history;
rho guardrail resumes round 2. (ad-hoc query scripts: prefix `PYTHONUTF8=1`.)

## Round 2 — exploit the winner + optimization (DONE)
All: max_epochs 60, patience 8, batch 512. (test_loss + rho now logged after the fix.)

| run | key args | best_val | test | rho |
|-----|----------|---------:|-----:|----:|
| **r2-big-reg** | hidden 384, dropout 0.4, emb 0.15, adamw, wd 0.02 | **5.672** | 5.716 | +0.348 |
| r2-drop-wd | dropout 0.3, emb 0.1, adamw, wd 0.05 | 5.674 | 5.743 | +0.370 |
| r2-drop-strong | dropout 0.5, emb 0.2 | 5.683 | – | +– |
| r2-cosine | dropout 0.3, emb 0.1, adamw, cosine, warmup 0.05, lr 3e-3 | 5.709 | 5.756 | +0.391 |

Takeaways: all 4 beat round 1 (5.743 -> ~5.67). Big-reg (more capacity + heavy
dropout) ties drop+wd as the leaders; pushing dropout to 0.5 doesn't help past 0.3;
cosine slightly worse on val but **highest rho** (+0.391) — the guardrail is healthy
(regularization improved relatedness too, rho ~0.35-0.39). Returns on pure
regularization are shrinking; next, push capacity+reg together and probe architecture.

## Round 3 — capacity + architecture (DONE)
Added a `--decoder lstm|gru` knob (commit d2b3c80). All: max_epochs 60, patience 8.

| run | key args | best_val | test | rho |
|-----|----------|---------:|-----:|----:|
| **r3-bigreg-wd** | hidden 384, dropout 0.4, emb 0.15, adamw, wd 0.05 | **5.648** | 5.709 | +0.359 |
| r3-xl | hidden 512, dropout 0.4, emb 0.15, adamw, wd 0.03 | 5.684 | 5.730 | +0.286 |
| r3-2layer | layers 2, hidden 256, dropout 0.3, emb 0.1, adamw, wd 0.02 | 5.705 | 5.801 | +0.306 |
| r3-gru | --decoder gru, hidden 256, dropout 0.3, emb 0.1, adamw, wd 0.02 | 5.769 | 5.810 | +0.392 |

Trajectory 5.743 -> 5.672 -> 5.648 (Δ shrinking). ARCHITECTURE SETTLED: 1-layer LSTM,
hidden 384. h512 overshoots; depth (2-layer) hurts; GRU < LSTM. (r3-2layer's shell
reported exit 127 but the run completed fine — spurious wrapper code, data is logged.)

## Round 4 — fine-tune optimization + reg around the winner (running)
Base = r3-bigreg-wd (h384, dropout 0.4, emb 0.15, adamw, wd 0.05). Probe LR/schedule
+ reg strength. All: round 4, max_epochs 80, patience 10, batch 512, hidden 384.

| run | key args (vs base) | best_val | test | rho |
|-----|--------------------|---------:|-----:|----:|
| **r4-cosine** | cosine, warmup 0.05, lr 3e-3 | **5.585** | 5.671 | +0.378 |
| r4-wd0.1 | weight_decay 0.1 | 5.593 | 5.650 | +0.376 |
| r4-reg+ | dropout 0.45, emb 0.2 | 5.593 | 5.652 | +0.370 |
| r4-lr1e3 | lr 1e-3 | 5.755 | 5.815 | +0.282 |

5.648 -> 5.585 (Δ 0.063 — cosine LR is the unlock). Stronger wd and more dropout also
help (~5.593); lower LR hurts. Not plateaued; combine cosine + stronger reg next.

## Round 5 — cosine + stronger reg + LR probe (running)
Base = r4-cosine (h384, dropout 0.4, emb 0.15, adamw, wd 0.05, cosine, warmup 0.05,
lr 3e-3). All: round 5, max_epochs 80, patience 12, batch 512.

| run | key args (vs base) | best_val | test | rho |
|-----|--------------------|---------:|-----:|----:|
| **r5-cos-both** | wd 0.1 + dropout 0.45 + emb 0.2 | **5.509** | 5.543 | +0.369 |
| r5-cos-lr5e3 | lr 5e-3 | 5.520 | 5.599 | +0.412 |
| r5-cos-wd0.1 | weight_decay 0.1 | 5.529 | 5.603 | +0.405 |
| r5-cos-reg+ | dropout 0.45, emb 0.2 | 5.543 | 5.642 | +0.376 |

5.585 -> 5.509 (Δ 0.076). Stacking all reg + cosine wins; higher LR helps (rho +0.41);
test tracks val (no selection-overfit); rho rising. Still climbing -> push reg + LR.

## Round 6 — push reg strength + LR + anneal (running)
Base = r5-cos-both (h384, cosine, warmup 0.05, adamw). All: round 6, patience 12, batch 512.

| run | key args | best_val | test | rho |
|-----|----------|---------:|-----:|----:|
| **r6-lr7e3** | wd 0.1, drop 0.45, emb 0.2, lr 7e-3 | **5.452** | 5.527 | +0.338 |
| r6-both-lr5e3 | wd 0.1, drop 0.45, emb 0.2, lr 5e-3 | 5.454 | 5.505 | +0.351 |
| r6-fast-anneal | wd 0.1, drop 0.45, emb 0.2, lr 4e-3, 40ep | 5.464 | 5.578 | +0.355 |
| r6-reg++ | wd 0.15, drop 0.5, emb 0.25, lr 3e-3 | 5.475 | 5.506 | +0.307 |

5.509 -> 5.452 (Δ 0.057). LR still the live lever (7e-3 best). REG CEILING reached:
reg++ worst + lowest rho -> sweet spot is dropout 0.45 / emb 0.2 / wd 0.1. WATCH: rho
slowly declining (0.37 -> 0.34) as val drops -> val and the science metric diverging.

## Round 7 — LR ceiling + batch scaling (running)
Hold reg at sweet spot (drop 0.45, emb 0.2, wd 0.1), cosine. Push LR / batch. round 7.

| run | key args | best_val | test | rho |
|-----|----------|---------:|-----:|----:|
| r7-lr1e2-warm | lr 1e-2, warmup 0.1, 100ep | 5.434 | 5.491 | +0.318 |
| r7-bs256 | batch 256, lr 4e-3 | 5.436 | 5.499 | +0.345 |
| r7-lr1e2 | lr 1e-2 | 5.441 | 5.523 | +0.322 |
| r7-bs1024 | batch 1024, lr 1e-2 | 5.465 | 5.576 | +0.332 |

5.452 -> 5.434 (Δ 0.018, shrinking) AND rho degrading (0.34 -> 0.32). PLATEAU: pushing
val now trades off the relatedness metric. Stop.

## CONCLUSION
Trajectory (best val per round): 5.743 -> 5.672 -> 5.648 -> 5.585 -> 5.509 -> 5.452 ->
5.434. Total Δ 0.309 (~5.4% relative) over 7 rounds / 28 configs; test tracks val
throughout (no selection-overfit).

What moved the needle, in order: (1) **regularization** — the overfit wanted heavy
dropout 0.45 + emb_dropout 0.2 + weight_decay 0.1 (more than that underfits + hurts rho);
(2) **cosine LR + warmup with a high peak (7e-3..1e-2)** — the single biggest jump
(r3->r4, Δ0.063); (3) **capacity** sweet spot hidden 384 (128 underfits, 512 overshoots).
Architecture settled: 1-layer LSTM (depth hurts, GRU < LSTM). Batch 256-512 ~ equal.

RECOMMENDED RECIPE (val-optimal): 1-layer LSTM, hidden 384, d_lang=d_concept=64,
dropout 0.45, emb_dropout 0.2, AdamW weight_decay 0.1, cosine LR + warmup, peak lr 1e-2,
batch 512, ~50-70 epochs, early stop on val. -> best_val ~5.43, test ~5.49.

SCIENCE-BALANCED PICK (val vs rho tradeoff): r5-cos-both / r6-both-lr5e3 (val 5.45-5.51,
**rho 0.35-0.37** vs the val-winner's 0.32). Since the project goal is relatedness, prefer
this regime: peak lr 5e-3 (not 1e-2), same reg, h384. Pushing LR past ~7e-3 buys tiny val
at a real rho cost.

Subjective eval (model/sample.py): the model learns each language's PHONOTACTICS
(Tahitian comes out Tahitian-shaped; eye=mata exact) but not arbitrary lexemes; Mandarin
underfits (101 cells, no tone field). Greedy decode of the heavily-regularized winner is
a bland averager -> use temperature sampling / lower dropout for livelier generation.
NEXT (open): IPA-ify the deferred national orthographies (spa/por/eng/...) + add a tone
field to evaluate Mandarin properly; coherence constraint on the per-field heads.

## Round 8 — restart on the EXPANDED inventory (running)
Coverage grew a lot since rounds 1–7 (+Romance, +Mayan, +Latin-2 Turkic/Albanian/Polish/
Hungarian/Basque/Haitian, +Indic Kannada/Hindi, +English via CMUdict — ~292.9k records,
many more languages). val_loss is **not comparable** to the old sweep (different data);
re-anchor and re-test the levers most likely to shift with more data: capacity (h512
*overshot* on the small data — may win now), conditioning-embedding size (more languages
=> the science lever for relatedness), and lighter reg (more data may need less). Common:
adamw, cosine + warmup 0.05, peak lr 5e-3 (science-balanced), max_epochs 80, patience 12,
batch 512, 1-layer LSTM. Select on val with rho + family-purity guardrail (the science
metric is now a convergence readout — see eval.family_report).

| run | key args (vs base) | best_val | test | rho | fam 1-NN | fam 5-NN | fam AUC |
|-----|--------------------|---------:|-----:|----:|---------:|---------:|--------:|
| **r8-base** | h384, drop0.45, emb0.2, wd0.1, d_lc 64 (refresh) | **5.415** | 5.519 | 0.321 | **0.790** | 0.616 | **0.823** |
| r8-cap512 | hidden 512, dropout 0.4, emb 0.15, wd 0.05 | 5.465 | 5.672 | **0.390** | 0.746 | 0.600 | 0.812 |
| r8-bigemb | d_lang/d_concept 96 | 5.436 | 5.521 | 0.345 | 0.782 | **0.623** | 0.819 |
| r8-lightreg | dropout 0.35, emb 0.15, wd 0.05 | 5.480 | 5.627 | 0.366 | 0.753 | 0.596 | 0.812 |

Baseline (model.eval, science recipe, pre-sweep anchor): rho +0.369, 1-NN 0.773, AUC 0.827.
All runs early-stopped e37–e47 (patience 12) — training length isn't the limit.

**Findings.** The recipe TRANSFERS to the expanded inventory: r8-base wins val + family
1-NN (0.790) + family AUC (0.823). All three data-motivated bets lose to it — capacity 512
*still* overshoots (worst val+test even with more data → h384 settled, robustly); lighter reg
hurts (corpus still wants heavy reg); symmetric d96 embeddings ~neutral (best 5-NN, else tied).
KEY: **rho disagrees with the family metric** — r8-cap512 has the best rho (0.390) but the
worst family purity (0.746). The ASJP-LDN rho proxy is misleading; SELECT ON the externally-
validated Glottolog family metric (the science readout), with val as a training-health check.

## Round 9 — isolate the on-theme lever: asymmetric embeddings favoring z_language (running)
The science product is `z_language`, so give it more dimensions than the concept embedding
(r8-bigemb bumped BOTH symmetrically and got best 5-NN; isolate d_lang). Anchor = r8-base
(reused, not rerun). Common as Round 8 (h384, drop0.45, emb0.2, adamw wd0.1, cosine warmup
0.05, lr5e-3 unless noted). Select on family 1-NN/AUC; val = health.

| run | key args (vs base) | best_val | test | rho | fam 1-NN | fam 5-NN | fam AUC |
|-----|--------------------|---------:|-----:|----:|---------:|---------:|--------:|
| r9-dlang128 | d_lang 128, d_concept 64 | – | – | – | – | – | – |
| r9-dlang96 | d_lang 96, d_concept 64 | – | – | – | – | – | – |
| r9-bigemb128 | d_lang 128, d_concept 128 | – | – | – | – | – | – |
| r9-lr7e3 | lr 7e-3 (val+family now correlate) | – | – | – | – | – | – |
