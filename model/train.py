"""Train (or smoke-test) the conditional vocalic decoder.

  uv run python -m model.train --smoke              # synthetic data, fast_dev_run
  uv run python -m model.train --limit 5000 --max-epochs 3
  uv run python -m model.train                      # full corpus

`--smoke` exercises the whole pipeline (vocab, collate, model fwd/bwd, one train +
one val batch) on random data, so wiring is verifiable without the corpus.
"""
from __future__ import annotations

import argparse
import os
import sys

# make `model` importable whether run as `-m model.train` or `python model/train.py`
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytorch_lightning as pl  # noqa: E402

from model.data import synthetic_records  # noqa: E402
from model.datamodule import SwadeshDataModule  # noqa: E402
from model.decoder import ConditionalVocalicDecoder  # noqa: E402


def build_argparser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--smoke", action="store_true", help="synthetic data + fast_dev_run")
    p.add_argument("--limit", type=int, default=None, help="cap #records (quick runs)")
    p.add_argument("--max-epochs", type=int, default=10)
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--d-lang", type=int, default=64)
    p.add_argument("--d-concept", type=int, default=64)
    p.add_argument("--hidden", type=int, default=256)
    p.add_argument("--layers", type=int, default=1)
    p.add_argument("--lr", type=float, default=2e-3)
    p.add_argument("--val-frac", type=float, default=0.05)
    return p


def main(argv=None):
    args = build_argparser().parse_args(argv)

    if args.smoke:
        dm = SwadeshDataModule(records=synthetic_records(300, n_lang=12, n_concept=20),
                               batch_size=32, val_frac=0.1)
        trainer = pl.Trainer(fast_dev_run=True, accelerator="cpu", logger=False,
                             enable_checkpointing=False, enable_model_summary=False)
    else:
        dm = SwadeshDataModule(batch_size=args.batch_size, limit=args.limit,
                               val_frac=args.val_frac)
        trainer = pl.Trainer(max_epochs=args.max_epochs, accelerator="auto",
                             logger=False, enable_checkpointing=False,
                             log_every_n_steps=25)

    dm.setup()
    print(f"data: {dm.n_lang} languages, {dm.n_concept} concepts, "
          f"field sizes {dm.field_sizes}")
    model = ConditionalVocalicDecoder(
        field_sizes=dm.field_sizes, n_lang=dm.n_lang, n_concept=dm.n_concept,
        d_lang=args.d_lang, d_concept=args.d_concept, hidden=args.hidden,
        layers=args.layers, lr=args.lr)
    trainer.fit(model, dm)

    z = model.language_embeddings()
    print(f"done. z_language matrix: {tuple(z.shape)}  (relatedness = distances here)")
    if args.smoke:
        print("smoke OK: pipeline wired (vocab -> collate -> conditional LSTM -> heads).")


if __name__ == "__main__":
    main()
