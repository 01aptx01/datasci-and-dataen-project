from __future__ import annotations

from datetime import date, datetime
from math import sqrt
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from src.ml_evaluation.config import MODEL_NAMES, EvaluationError
from src.ml_dataset.dataset import DatasetConfig
from src.features.pipeline import SUPPORTED_TICKERS


def _as_date(value: object, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise EvaluationError(f"{field} must be a valid market date") from error
    if pd.isna(parsed):
        raise EvaluationError(f"{field} must be a valid market date")
    return parsed.date()


def calculate_error_metrics(y_true: Sequence[float], y_pred: Sequence[float]) -> dict[str, float | int]:
    actual = np.asarray(y_true, dtype=float)
    predicted = np.asarray(y_pred, dtype=float)
    if actual.ndim != 1 or predicted.ndim != 1 or len(actual) != len(predicted):
        raise EvaluationError("y_true and y_pred must be aligned one-dimensional arrays")
    if not len(actual):
        return {"n": 0, "mae": np.nan, "rmse": np.nan}
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise EvaluationError("evaluation values must be finite")
    if (actual < 0).any() or (predicted < 0).any():
        raise EvaluationError("annualized volatility values must be nonnegative")
    errors = predicted - actual
    return {
        "n": int(len(actual)),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(np.square(errors)))),
    }


def build_forecast_audit(
    expected_anchors: pd.DataFrame,
    labels: pd.DataFrame,
    predictions: pd.DataFrame,
    forecast_failures: pd.DataFrame,
    *,
    cutoff: date,
    model_names: Sequence[str] = MODEL_NAMES,
    validation_start_date: date | None = None,
    test_end_date: date | None = None,
    tickers: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Join eligible anchors to immutable forecasts and cutoff-aware labels."""
    required_expected = {"prediction_date", "ticker", "split"}
    required_labels = {
        "date",
        "ticker",
        "target_start_date",
        "target_end_date",
        "target_obs_count",
        "target_realized_vol_5d",
        "is_label_mature",
        "target_version",
    }
    required_predictions = {
        "prediction_id",
        "prediction_date",
        "ticker",
        "model_name",
        "predicted_vol_annualized",
        "target_start_date",
        "target_end_date",
    }
    required_failures = {"prediction_date", "ticker", "model_name", "failure_type", "reason"}
    for frame, required, label in (
        (expected_anchors, required_expected, "expected anchors"),
        (labels, required_labels, "labels"),
        (predictions, required_predictions, "predictions"),
        (forecast_failures, required_failures, "forecast failures"),
    ):
        if not required.issubset(frame.columns):
            raise EvaluationError(f"{label} missing columns: {sorted(required - set(frame.columns))}")

    if validation_start_date is None or test_end_date is None:
        dataset_config = DatasetConfig()
        validation_start_date = (
            dataset_config.validation_start_date
            if validation_start_date is None
            else validation_start_date
        )
        test_end_date = dataset_config.test_end_date if test_end_date is None else test_end_date
    allowed_tickers = SUPPORTED_TICKERS if tickers is None else tickers

    expected = expected_anchors.loc[:, ["prediction_date", "ticker", "split"]].copy()
    expected["prediction_date"] = expected["prediction_date"].map(lambda value: _as_date(value, "expected date"))
    expected["ticker"] = expected["ticker"].astype(str)
    expected = expected.loc[
        expected["split"].isin(("validation", "test"))
        & expected["prediction_date"].between(validation_start_date, test_end_date)
    ].copy()
    if expected.duplicated(["prediction_date", "ticker", "split"]).any():
        raise EvaluationError("expected anchors must be unique by date, ticker, and split")
    if not set(expected["ticker"]).issubset(allowed_tickers):
        raise EvaluationError("expected anchors contain an unsupported ticker")

    label_frame = labels.loc[:, sorted(required_labels)].copy()
    label_frame["date"] = label_frame["date"].map(lambda value: _as_date(value, "label date"))
    label_frame["target_start_date"] = label_frame["target_start_date"].map(
        lambda value: None if pd.isna(value) else _as_date(value, "target start date")
    )
    label_frame["target_end_date"] = label_frame["target_end_date"].map(
        lambda value: None if pd.isna(value) else _as_date(value, "target end date")
    )
    if label_frame.duplicated(["date", "ticker"]).any():
        raise EvaluationError("labels must be unique by date and ticker")

    prediction_frame = predictions.copy()
    prediction_frame["prediction_date"] = prediction_frame["prediction_date"].map(
        lambda value: _as_date(value, "prediction date")
    )
    prediction_frame["ticker"] = prediction_frame["ticker"].astype(str)
    prediction_frame["model_name"] = prediction_frame["model_name"].astype(str)
    if prediction_frame.duplicated(["prediction_id"]).any() or prediction_frame.duplicated(
        ["prediction_date", "ticker", "model_name"]
    ).any():
        raise EvaluationError("predictions must be unique by prediction ID and date/ticker/model")
    if set(prediction_frame["model_name"]) - set(model_names):
        raise EvaluationError("predictions include a model outside the configured model suite")
    prediction_frame["target_start_date"] = prediction_frame["target_start_date"].map(
        lambda value: None if pd.isna(value) else _as_date(value, "prediction target start")
    )
    prediction_frame["target_end_date"] = prediction_frame["target_end_date"].map(
        lambda value: None if pd.isna(value) else _as_date(value, "prediction target end")
    )
    outside_expected = set(zip(prediction_frame["prediction_date"], prediction_frame["ticker"])) - set(
        zip(expected["prediction_date"], expected["ticker"])
    )
    if outside_expected:
        raise EvaluationError("immutable predictions contain anchors outside eligible Validation/Test features")

    failure_frame = forecast_failures.loc[:, sorted(required_failures)].copy()
    if not failure_frame.empty:
        failure_frame["prediction_date"] = failure_frame["prediction_date"].map(
            lambda value: _as_date(value, "failure prediction date")
        )
        failure_frame["ticker"] = failure_frame["ticker"].astype(str)
        failure_frame["model_name"] = failure_frame["model_name"].astype(str)
        if failure_frame.duplicated(["prediction_date", "ticker", "model_name"]).any():
            raise EvaluationError("forecast failures must be unique by date, ticker, and model")
        if set(failure_frame["model_name"]) - set(model_names):
            raise EvaluationError("forecast failures include a model outside the configured model suite")

    expected["_join"] = 1
    model_frame = pd.DataFrame({"model_name": tuple(model_names), "_join": 1})
    audit = expected.merge(model_frame, on="_join", how="inner").drop(columns="_join")
    audit = audit.merge(
        label_frame,
        left_on=["prediction_date", "ticker"],
        right_on=["date", "ticker"],
        how="left",
        validate="many_to_one",
    ).drop(columns="date")
    audit = audit.merge(
        prediction_frame,
        on=["prediction_date", "ticker", "model_name"],
        how="left",
        suffixes=("", "_prediction"),
        validate="one_to_one",
    )
    audit = audit.merge(
        failure_frame,
        on=["prediction_date", "ticker", "model_name"],
        how="left",
        validate="one_to_one",
    )
    has_label_and_prediction = audit["prediction_id"].notna() & audit["target_version"].notna()
    mismatched_windows = has_label_and_prediction & (
        audit["target_start_date"].ne(audit["target_start_date_prediction"])
        | audit["target_end_date"].ne(audit["target_end_date_prediction"])
    )
    if mismatched_windows.any():
        raise EvaluationError("forecast target windows do not match the joined Label Contract rows")
    label_status: list[str] = []
    forecast_status: list[str] = []
    for row in audit.itertuples(index=False):
        end_date = getattr(row, "target_end_date", None)
        # A saved forecast can carry target window metadata even if its label is absent.
        label_end = getattr(row, "target_end_date_prediction", None)
        if pd.isna(end_date):
            label_status.append("MISSING")
        else:
            try:
                target_end = _as_date(end_date, "label target end")
                obs_count = int(row.target_obs_count) if pd.notna(row.target_obs_count) else 0
                target_value = float(row.target_realized_vol_5d) if pd.notna(row.target_realized_vol_5d) else np.nan
                mature = bool(row.is_label_mature) and obs_count == 5 and np.isfinite(target_value) and target_value >= 0
                if target_end > cutoff or not bool(row.is_label_mature) and obs_count < 5:
                    label_status.append("PENDING")
                elif mature:
                    label_status.append("MATURE")
                else:
                    label_status.append("INVALID")
            except (TypeError, ValueError):
                label_status.append("INVALID")

        prediction_value = getattr(row, "predicted_vol_annualized", np.nan)
        prediction_id = getattr(row, "prediction_id", None)
        if pd.notna(prediction_id):
            try:
                numeric = float(prediction_value)
            except (TypeError, ValueError):
                numeric = np.nan
            forecast_status.append("VALID" if np.isfinite(numeric) and numeric >= 0 else "INVALID")
        elif pd.notna(getattr(row, "failure_type", None)):
            failure_type = str(row.failure_type).upper()
            forecast_status.append("INVALID" if "INVALID" in failure_type else "MISSING")
        else:
            forecast_status.append("MISSING")
    audit["label_status"] = label_status
    audit["forecast_status"] = forecast_status
    audit["evaluation_status"] = np.select(
        [
            audit["forecast_status"].eq("INVALID"),
            audit["forecast_status"].eq("MISSING"),
            audit["label_status"].eq("PENDING"),
            audit["label_status"].eq("MISSING"),
            audit["label_status"].eq("INVALID"),
        ],
        ["INVALID_FORECAST", "MISSING_FORECAST", "PENDING_LABEL", "MISSING_TARGET", "INVALID_TARGET"],
        default="EVALUABLE",
    )
    audit["absolute_error"] = np.nan
    audit["squared_error"] = np.nan
    evaluable = audit["evaluation_status"].eq("EVALUABLE")
    audit.loc[evaluable, "absolute_error"] = (
        audit.loc[evaluable, "predicted_vol_annualized"].astype(float)
        - audit.loc[evaluable, "target_realized_vol_5d"].astype(float)
    ).abs()
    audit.loc[evaluable, "squared_error"] = np.square(
        audit.loc[evaluable, "predicted_vol_annualized"].astype(float)
        - audit.loc[evaluable, "target_realized_vol_5d"].astype(float)
    )
    audit["label_available_by_cutoff"] = audit["label_status"].eq("MATURE")
    return audit.sort_values(["prediction_date", "ticker", "model_name"], kind="stable").reset_index(drop=True)


def _period_value(value: object, period: str) -> int | str:
    market_date = _as_date(value, "prediction_date")
    if period == "year":
        return market_date.year
    if period == "month":
        return market_date.strftime("%Y-%m")
    raise EvaluationError("period must be 'month' or 'year'")


def aggregate_period_metrics(
    expected_anchors: pd.DataFrame,
    evaluations: pd.DataFrame,
    *,
    period: str,
    model_names: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Aggregate matured evaluation rows without merging split membership."""
    required_expected = {"prediction_date", "ticker", "split"}
    required_evaluations = {
        "prediction_date",
        "ticker",
        "model_name",
        "split",
        "target_realized_vol_5d",
        "predicted_vol_annualized",
    }
    if not required_expected.issubset(expected_anchors.columns):
        raise EvaluationError(f"expected anchors missing columns: {sorted(required_expected - set(expected_anchors.columns))}")
    if not required_evaluations.issubset(evaluations.columns):
        raise EvaluationError(f"evaluation rows missing columns: {sorted(required_evaluations - set(evaluations.columns))}")
    expected = expected_anchors.loc[:, ["prediction_date", "ticker", "split"]].copy()
    evaluated = evaluations.loc[:, list(required_evaluations)].copy()
    expected["prediction_date"] = expected["prediction_date"].map(lambda value: _as_date(value, "expected date"))
    evaluated["prediction_date"] = evaluated["prediction_date"].map(lambda value: _as_date(value, "evaluation date"))
    if expected.duplicated(["prediction_date", "ticker", "split"]).any():
        raise EvaluationError("expected anchors must be unique by date, ticker, and split")
    models = tuple(model_names or sorted(evaluated["model_name"].astype(str).unique()))
    if not models:
        return pd.DataFrame(
            columns=["ticker", "model_name", "split", "period", "expected_anchor_count", "evaluable_count", "coverage", "mae", "rmse"]
        )
    expected["_key"] = 1
    model_frame = pd.DataFrame({"model_name": models, "_key": 1})
    expanded_expected = expected.merge(model_frame, on="_key", how="inner").drop(columns="_key")
    expanded_expected["period"] = expanded_expected["prediction_date"].map(
        lambda value: _period_value(value, period)
    )
    evaluated["period"] = evaluated["prediction_date"].map(lambda value: _period_value(value, period))
    if evaluated.duplicated(["prediction_date", "ticker", "model_name", "split"]).any():
        raise EvaluationError("evaluation rows must be unique by date, ticker, model, and split")

    period_column = "calendar_year" if period == "year" else "calendar_month"
    grouping = ["ticker", "model_name", "split", period_column]
    expanded_expected = expanded_expected.rename(columns={"period": period_column})
    evaluated = evaluated.rename(columns={"period": period_column})
    expected_counts = expanded_expected.groupby(grouping, as_index=False, sort=True).size()
    expected_counts = expected_counts.rename(columns={"size": "expected_anchor_count"})
    if evaluated.empty:
        metrics = pd.DataFrame(columns=[*grouping, "evaluable_count", "mae", "rmse"])
    else:
        evaluated["absolute_error"] = (
            evaluated["predicted_vol_annualized"].astype(float)
            - evaluated["target_realized_vol_5d"].astype(float)
        ).abs()
        evaluated["squared_error"] = np.square(
            evaluated["predicted_vol_annualized"].astype(float)
            - evaluated["target_realized_vol_5d"].astype(float)
        )
        metrics = (
            evaluated.groupby(grouping, as_index=False, sort=True)
            .agg(evaluable_count=("prediction_date", "nunique"), mae=("absolute_error", "mean"), mean_squared_error=("squared_error", "mean"))
        )
        metrics["rmse"] = np.sqrt(metrics.pop("mean_squared_error"))
    result = expected_counts.merge(metrics, on=grouping, how="left")
    result["evaluable_count"] = result["evaluable_count"].fillna(0).astype("int64")
    result["coverage"] = np.divide(
        result["evaluable_count"],
        result["expected_anchor_count"],
        out=np.zeros(len(result), dtype=float),
        where=result["expected_anchor_count"].to_numpy(dtype=float) > 0,
    )
    return result.sort_values(grouping, kind="stable").reset_index(drop=True)


def rolling_session_metrics(
    expected_anchors: pd.DataFrame,
    evaluations: pd.DataFrame,
    session_dates_by_split: Mapping[str, Sequence[date]],
    *,
    window_size: int = 20,
    minimum_evaluable: int = 10,
    model_names: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Compute split-local rolling errors on fixed XNYS-session windows."""
    if window_size < 1 or not 1 <= minimum_evaluable <= window_size:
        raise EvaluationError("rolling window and minimum evaluable count are invalid")
    required_expected = {"prediction_date", "ticker", "split"}
    required_eval = {"prediction_date", "ticker", "model_name", "split", "target_realized_vol_5d", "predicted_vol_annualized"}
    if not required_expected.issubset(expected_anchors.columns) or not required_eval.issubset(evaluations.columns):
        raise EvaluationError("rolling inputs do not satisfy the expected/evaluation schema")
    expected = expected_anchors.loc[:, ["prediction_date", "ticker", "split"]].copy()
    evaluated = evaluations.copy()
    expected["prediction_date"] = expected["prediction_date"].map(lambda value: _as_date(value, "expected date"))
    evaluated["prediction_date"] = evaluated["prediction_date"].map(lambda value: _as_date(value, "evaluation date"))
    models = tuple(model_names or sorted(evaluated["model_name"].astype(str).unique()))
    rows: list[dict[str, object]] = []
    for split, raw_sessions in session_dates_by_split.items():
        sessions = tuple(_as_date(value, "XNYS session") for value in raw_sessions)
        if len(set(sessions)) != len(sessions) or tuple(sorted(sessions)) != sessions:
            raise EvaluationError(f"{split} XNYS sessions must be unique and sorted")
        expected_split = expected.loc[expected["split"] == split]
        evaluated_split = evaluated.loc[evaluated["split"] == split]
        for ticker in sorted(expected_split["ticker"].astype(str).unique()):
            expected_dates = set(expected_split.loc[expected_split["ticker"] == ticker, "prediction_date"])
            for model_name in models:
                model_rows = evaluated_split.loc[
                    (evaluated_split["ticker"].astype(str) == ticker)
                    & (evaluated_split["model_name"].astype(str) == model_name)
                ]
                by_date = {
                    row.prediction_date: float(row.predicted_vol_annualized - row.target_realized_vol_5d)
                    for row in model_rows.itertuples(index=False)
                }
                for end_index in range(window_size - 1, len(sessions)):
                    window = sessions[end_index - window_size + 1 : end_index + 1]
                    expected_count = sum(session in expected_dates for session in window)
                    errors = [by_date[session] for session in window if session in by_date]
                    if len(errors) < minimum_evaluable:
                        continue
                    rows.append(
                        {
                            "split": split,
                            "ticker": ticker,
                            "model_name": model_name,
                            "window_start": window[0],
                            "window_end": window[-1],
                            "window_session_count": window_size,
                            "expected_anchor_count": expected_count,
                            "evaluable_count": len(errors),
                            "coverage": len(errors) / expected_count if expected_count else np.nan,
                            "mae": float(np.mean(np.abs(errors))),
                            "rmse": float(np.sqrt(np.mean(np.square(errors)))),
                        }
                    )
    return pd.DataFrame(
        rows,
        columns=[
            "split",
            "ticker",
            "model_name",
            "window_start",
            "window_end",
            "window_session_count",
            "expected_anchor_count",
            "evaluable_count",
            "coverage",
            "mae",
            "rmse",
        ],
    )
