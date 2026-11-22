"""Stage 04 Train-only model fitting and Validation selection."""

from src.ml_training.config import CandidateConfig, TrainingConfig, TrainingError
from src.ml_training.pipeline import (
    B4_MODEL_ID,
    B4_MODEL_NAME,
    B4_MODEL_VERSION,
    CandidateRun,
    TrainingSelectionResult,
    b4_state_sha256,
    evaluate_b4_validation,
    evaluate_candidate,
    fit_b4_ols,
    model_state_sha256,
    predict_baselines,
    run_training_selection,
    scaler_state_sha256,
)

__all__ = [
    "B4_MODEL_ID",
    "B4_MODEL_NAME",
    "B4_MODEL_VERSION",
    "CandidateConfig",
    "CandidateRun",
    "TrainingConfig",
    "TrainingError",
    "TrainingSelectionResult",
    "b4_state_sha256",
    "evaluate_b4_validation",
    "evaluate_candidate",
    "fit_b4_ols",
    "model_state_sha256",
    "predict_baselines",
    "run_training_selection",
    "scaler_state_sha256",
]
