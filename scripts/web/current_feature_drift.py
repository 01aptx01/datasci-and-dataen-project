"""Build a standalone distribution summary from the locally available features."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = ("ret_1d_t", "ret_lag_1d", "ret_lag_2d", "ret_trailing_5d", "ret_trailing_20d", "rv_5d", "rv_20d", "rv_60d")


def build_current_feature_drift(source: Path, destination: Path) -> bool:
    if not source.is_file():
        return False
    frame = pd.read_parquet(source)
    frame = frame.loc[frame["is_model_ready"]].copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date")
    rows = []
    for ticker in ("SPY", "IEF", "GLD"):
        data = frame.loc[frame["ticker"] == ticker]
        reference = data.loc[data["date"].between("2021-09-27", "2024-09-30")]
        current = data.tail(60)
        if len(reference) < 60 or len(current) < 60:
            continue
        for feature in FEATURES:
            ref = reference[feature].to_numpy(dtype=float)
            cur = current[feature].to_numpy(dtype=float)
            if not np.isfinite(ref).all() or not np.isfinite(cur).all():
                continue
            iqr = float(np.quantile(ref, .75) - np.quantile(ref, .25))
            if iqr <= 0:
                continue
            values = np.sort(np.concatenate((ref, cur)))
            ref_sorted, cur_sorted = np.sort(ref), np.sort(cur)
            distance = np.sum(np.abs(np.searchsorted(ref_sorted, values[:-1], side="right") / len(ref) - np.searchsorted(cur_sorted, values[:-1], side="right") / len(cur)) * np.diff(values))
            edges = np.concatenate(([-np.inf], np.unique(np.quantile(ref, np.arange(1, 10) / 10)), [np.inf]))
            a = np.histogram(ref, edges)[0] + .5
            b = np.histogram(cur, edges)[0] + .5
            a, b = a / a.sum(), b / b.sum()
            rows.append({"ticker": ticker, "feature": feature, "w1": float(distance / iqr), "psi": float(np.sum((b-a)*np.log(b/a))), "date": current["date"].max().date().isoformat(), "windowStart": current["date"].min().date().isoformat()})
    if not rows:
        return False
    payload = {"sourceRunIds": sorted(frame["run_id"].dropna().astype(str).unique().tolist()), "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(), "referenceStart": "2021-09-27", "referenceEnd": "2024-09-30", "rows": rows}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
    return True
