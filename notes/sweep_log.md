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

## Round 1 — regularization vs capacity (running)
Hypothesis: the overfit calls for regularization or less capacity. Spread 4 ways,
all else equal (lr 2e-3, adam unless noted, no schedule):

| run | hypothesis | key args | best_val | rho | notes |
|-----|-----------|----------|---------:|----:|-------|
| r1-baseline | control (reproduce overfit, clean infra) | dropout 0.1 | … | … | |
| r1-wd | L2 on the big embeddings | adamw, weight_decay 0.05 | … | … | |
| r1-drop | activation + embedding dropout | dropout 0.3, emb_dropout 0.1 | … | … | |
| r1-small | cut capacity | hidden 128, d_lang/concept 32, dropout 0.2 | … | … | |

(results filled in when the round completes)
