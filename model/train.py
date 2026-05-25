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

# Force UTF-8 stdout/stderr: MLflow prints a "🏃 View run ..." line on finalize,
# which crashes on a Windows cp1252 console/redirect (UnicodeEncodeError) and would
# otherwise abort the run before test/probe/best-val metrics are recorded.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pytorch_lightning as pl  # noqa: E402
import torch  # noqa: E402
from pytorch_lightning.callbacks import EarlyStopping  # noqa: E402

from model import tracking  # noqa: E402
from model.data import synthetic_records  # noqa: E402
from model.datamodule import SwadeshDataModule  # noqa: E402
from model.decoder import ConditionalVocalicDecoder  # noqa: E402

# use Ada/Ampere tensor cores for fp32 matmuls when on GPU
torch.set_float32_matmul_precision("high")


def _accelerator_banner():
    if torch.cuda.is_available():
        print(f"accelerator: CUDA - {torch.cuda.get_device_name(0)} "
              f"(sm_{''.join(map(str, torch.cuda.get_device_capability(0)))})")
    else:
        print("accelerator: CPU (no CUDA device found)")


def _log_posthoc(logger, metrics):
    """Attach metrics computed AFTER fit (best_val_loss, test_loss, relatedness_*).
    PTL finalizes the MLflow run at fit/test teardown and the house server drops
    writes to a finished run, so reactivate the run via the client, log, re-finish."""
    client, rid = logger.experiment, logger.run_id
    try:
        client.update_run(rid, status="RUNNING")
        for k, v in metrics.items():
            client.log_metric(rid, k, float(v))
        client.update_run(rid, status="FINISHED")
        print("logged post-hoc:", {k: round(v, 4) for k, v in metrics.items()})
    except Exception as e:                                  # don't lose a finished run
        print(f"post-hoc metric logging failed: {e}")


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
    p.add_argument("--dropout", type=float, default=0.1,
                   help="dropout on input/output activations (regularization)")
    p.add_argument("--emb-dropout", type=float, default=0.0, help="dropout on z_lang/z_concept")
    p.add_argument("--label-smoothing", type=float, default=0.0)
    p.add_argument("--lr", type=float, default=2e-3)
    p.add_argument("--optimizer", default="adam", choices=["adam", "adamw"])
    p.add_argument("--weight-decay", type=float, default=0.0)
    p.add_argument("--lr-schedule", default="none", choices=["none", "cosine"])
    p.add_argument("--warmup-frac", type=float, default=0.0)
    p.add_argument("--patience", type=int, default=0,
                   help="EarlyStopping patience on val_loss (0 = off)")
    p.add_argument("--round", default=None, help="MLflow tag to group a beam-search round")
    p.add_argument("--val-frac", type=float, default=0.05)
    p.add_argument("--accelerator", default="auto",
                   help="PTL accelerator: auto|gpu|cpu (default auto -> GPU if present)")
    p.add_argument("--no-cache", action="store_true", help="bypass the encoded-tensor cache")
    p.add_argument("--test-frac", type=float, default=0.05, help="held-out test fraction")
    # MLflow tracking (mlflow.pbd.vc by default; smoke runs are never logged)
    p.add_argument("--no-mlflow", action="store_true", help="disable MLflow logging")
    p.add_argument("--mlflow-uri", default=None, help="tracking URI (default: house server)")
    p.add_argument("--experiment", default=tracking.DEFAULT_EXPERIMENT)
    p.add_argument("--run-name", default=None)
    p.add_argument("--no-probe", action="store_true",
                   help="skip the relatedness probe after training")
    return p


def main(argv=None):
    args = build_argparser().parse_args(argv)
    _accelerator_banner()

    if args.smoke:
        dm = SwadeshDataModule(records=synthetic_records(300, n_lang=12, n_concept=20),
                               batch_size=32, val_frac=0.1, test_frac=0.1)
        logger = None                                    # smoke runs are never logged
        trainer = pl.Trainer(fast_dev_run=True, accelerator=args.accelerator, logger=False,
                             enable_checkpointing=False, enable_model_summary=False)
    else:
        dm = SwadeshDataModule(batch_size=args.batch_size, limit=args.limit,
                               val_frac=args.val_frac, test_frac=args.test_frac,
                               use_cache=not args.no_cache)
        logger = tracking.make_mlflow_logger(
            stage="train", uri=args.mlflow_uri, experiment=args.experiment,
            run_name=args.run_name, enabled=not args.no_mlflow,
            tags={"round": str(args.round)} if args.round else None)
        if logger is not None:
            print(f"mlflow: logging to {tracking.resolve_uri(args.mlflow_uri)} "
                  f"(experiment '{args.experiment}')")
        callbacks = []
        if args.patience > 0:
            callbacks.append(EarlyStopping(monitor="val_loss", mode="min",
                                           patience=args.patience))
        trainer = pl.Trainer(max_epochs=args.max_epochs, accelerator=args.accelerator,
                             devices="auto", logger=logger or False, callbacks=callbacks,
                             enable_checkpointing=False, log_every_n_steps=25)

    dm.setup()
    print(f"data [{dm.source}]: {dm.n_lang} languages, {dm.n_concept} concepts, "
          f"field sizes {dm.field_sizes}")
    if logger is not None:
        logger.log_hyperparams({
            "n_lang": dm.n_lang, "n_concept": dm.n_concept, "batch_size": args.batch_size,
            "val_frac": args.val_frac, "test_frac": args.test_frac, "max_len": dm.max_len,
            "max_epochs": args.max_epochs, "data_source": dm.source,
            "accelerator": str(trainer.strategy.root_device)})
    model = ConditionalVocalicDecoder(
        field_sizes=dm.field_sizes, n_lang=dm.n_lang, n_concept=dm.n_concept,
        d_lang=args.d_lang, d_concept=args.d_concept, hidden=args.hidden,
        layers=args.layers, dropout=args.dropout, lr=args.lr,
        optimizer=args.optimizer, weight_decay=args.weight_decay,
        lr_schedule=args.lr_schedule, warmup_frac=args.warmup_frac,
        emb_dropout=args.emb_dropout, label_smoothing=args.label_smoothing)
    trainer.fit(model, dm)
    print(f"trained on device: {trainer.strategy.root_device}")

    # collect metrics computed after fit, then log them in one robust client call
    post = {}
    if not args.smoke and callbacks and callbacks[0].best_score is not None:
        post["best_val_loss"] = float(callbacks[0].best_score)
        print(f"best_val_loss: {post['best_val_loss']:.4f}")
    if not args.smoke and not args.no_probe:
        from model.eval import relatedness_report
        rep = relatedness_report(model.language_embeddings().numpy(), dm.lang_vocab)
        if rep.get("n_pairs"):
            post["relatedness_rho"] = float(rep["rho"])
            post["relatedness_n_lang"] = float(rep["n_lang"])
            if rep["same_code_total"]:
                post["relatedness_same_code_acc"] = rep["same_code_hits"] / rep["same_code_total"]
    if not args.smoke and len(dm.test_ds) > 0:
        res = trainer.test(model, dm, verbose=True)
        if res and "test_loss" in res[0]:
            post["test_loss"] = float(res[0]["test_loss"])
    if logger is not None and post:
        _log_posthoc(logger, post)

    z = model.language_embeddings()
    print(f"done. z_language matrix: {tuple(z.shape)}  (relatedness = distances here)")
    if args.smoke:
        print("smoke OK: pipeline wired (vocab -> collate -> conditional LSTM -> heads).")


if __name__ == "__main__":
    main()
