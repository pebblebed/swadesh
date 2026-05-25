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

## Round 3 — capacity + architecture (PENDING; launch after restart)
Leaders are big-reg & drop-wd. Combine them, scale capacity, try a 2-layer LSTM and
a GRU decoder (needs a `--decoder` knob, to add). Provisional:

| run | hypothesis | key args |
|-----|-----------|----------|
| r3-bigreg-wd | combine the two leaders | hidden 384, dropout 0.4, emb 0.15, adamw, wd 0.05 |
| r3-xl | scale capacity + reg | hidden 512, dropout 0.4, emb 0.15, adamw, wd 0.03 |
| r3-2layer | depth + inter-layer dropout | layers 2, hidden 256, dropout 0.3, emb 0.1, adamw, wd 0.02 |
| r3-gru | GRU vs LSTM decoder | --decoder gru, hidden 256, dropout 0.3, emb 0.1, adamw, wd 0.02 |
