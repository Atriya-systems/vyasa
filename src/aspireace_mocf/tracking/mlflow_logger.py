from __future__ import annotations

from pathlib import Path
from typing import Any

from aspireace_mocf.settings import Settings


def log_run(settings: Settings, run_id: str, params: dict[str, Any], metrics: dict[str, float], artifacts: list[Path]) -> None:
    try:
        import mlflow
    except Exception as exc:
        raise RuntimeError("MLflow is not installed. Install requirements-training.txt to enable tracking.") from exc

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment)
    with mlflow.start_run(run_name=run_id):
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        for artifact in artifacts:
            if artifact.exists():
                mlflow.log_artifact(str(artifact))
