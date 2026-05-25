"""MLflow tracking helper.

Logs standard training stats (train/val/test loss) and quantitative eval outputs
(the relatedness probe's Spearman rho etc.) to the house MLflow server. Uses
Lightning's MLFlowLogger so `self.log(...)` metrics flow through automatically.

Tracking URI resolution (first non-empty wins): explicit `uri` arg ->
$MLFLOW_TRACKING_URI -> the house default. Auth, if the server requires it, is
read by mlflow from the standard env vars ($MLFLOW_TRACKING_USERNAME /
$MLFLOW_TRACKING_PASSWORD or $MLFLOW_TRACKING_TOKEN) -- never hardcoded here.
"""
from __future__ import annotations

import os

DEFAULT_URI = "https://mlflow.pbd.vc"
DEFAULT_EXPERIMENT = "swadesh-vocalic-decoder"


def resolve_uri(uri=None):
    return uri or os.environ.get("MLFLOW_TRACKING_URI") or DEFAULT_URI


def make_mlflow_logger(stage, uri=None, experiment=DEFAULT_EXPERIMENT,
                       run_name=None, enabled=True, tags=None):
    """Return a configured MLFlowLogger, or None when disabled (-> Trainer logger=False)."""
    if not enabled:
        return None
    from pytorch_lightning.loggers import MLFlowLogger
    return MLFlowLogger(
        experiment_name=experiment,
        tracking_uri=resolve_uri(uri),
        run_name=run_name,
        tags={"stage": stage, **(tags or {})},
        log_model=False,
    )
