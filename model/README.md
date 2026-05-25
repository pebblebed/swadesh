# model — conditional vocalic decoder

The model the IPA pipeline feeds (see `../TODO.md` MODELING DIRECTION + `../notes/`).
Learn latent representations of each **language** and each **concept**, then decode
the phonetic form — a sequence of articulatory **feature bundles** — conditioned on
both. Language relatedness = distances between the learned language embeddings.

```
z_lang    = LanguageEmbedding(language)     # language = list identifier (doculect)
z_concept = ConceptEmbedding(concept)       # concept  = canonical gloss
cond      = [z_lang ; z_concept]
LSTM(init=(h0,c0)←cond, input=prev_segment ⊕ cond) → per-FIELD softmax heads
```

Each segment is a bundle of categorical fields (`kind, manner, place, voice, height,
backness, rounding, length, nasal`); the loss is the sum of the field cross-entropies
over non-pad positions. This is the factored output of `notes/asjp.html` (the rich
feature tensor is the target; ASJP would be a coarse backbone, not the bottleneck).

## Layout
- `data.py` — **pure python, torch-free**: feature extraction + vocabularies (unit-tested via `python model/data.py`).
- `datamodule.py` — `SwadeshDataModule` + Dataset + teacher-forcing collate.
- `decoder.py` — `ConditionalVocalicDecoder` (the `LightningModule`).
- `train.py` — CLI / smoke entry point.

## Run (uv-managed env)
```bash
uv sync                                            # create .venv, install torch (CUDA) + lightning
uv run python model/data.py                        # torch-free data self-test
uv run python -m model.eval --selftest             # probe math self-test
uv run python -m model.train --smoke               # full pipeline on synthetic data (fast_dev_run)
uv run python -m model.train --limit 8000 --max-epochs 3   # quick real-data run
uv run python -m model.train                       # full corpus
uv run python -m model.eval --epochs 4             # train + relatedness probe (Spearman z vs ASJP-LDN)
```

**GPU.** torch is pinned to the CUDA `cu128` build (`pyproject.toml` `[tool.uv]` index;
the local RTX driver/CUDA 13.1 runs the 12.8 runtime). Training uses Lightning's
`accelerator="auto"`, so an NVIDIA GPU is used automatically — startup prints
`accelerator: CUDA - <device>` and Lightning logs `GPU available: True ... used: True`.
Force CPU with `--accelerator cpu`. On a fresh/CPU-only box, `uv sync` still installs the
`cu128` wheel; it falls back to CPU at runtime if no GPU is present.

**Tracking (MLflow).** `model.train` (non-smoke) logs to the house server
`https://mlflow.pbd.vc` via Lightning's `MLFlowLogger` (experiment
`swadesh-vocalic-decoder`): `train_loss_step/_epoch`, `val_loss`, `test_loss`, the
relatedness probe's `relatedness_rho` (+ `n_lang`/`n_pairs`/`same_code_acc`), and the
hyperparameters. Override with `--mlflow-uri` / `$MLFLOW_TRACKING_URI` (a local path or
`file:` URI works for offline runs), `--experiment`, `--run-name`; disable with
`--no-mlflow`; skip the probe with `--no-probe`. If the server needs auth, set the
standard `$MLFLOW_TRACKING_USERNAME`/`$MLFLOW_TRACKING_PASSWORD` or
`$MLFLOW_TRACKING_TOKEN` (never hardcoded). `model.eval` stays a standalone probe (no
logging); `model.train` is the canonical logged pipeline (fit -> probe -> test).

Source = `data/normalized/ipa.jsonl` (regenerate with `python scripts/to_ipa.py`);
segments via `scripts/ipa_features.segments`. Skeleton status — wired + loss-decreasing;
not yet tuned. Next: alignment/eval, the ASJP backbone head, and `z_language` readout.
