"""Download and read the independent price snapshots used in notebook 00."""

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

TIINGO = "https://api.tiingo.com/tiingo/daily"


def download_price_evidence(project_root, start_date, end_date):
    cache = project_root / "data/external/eda"
    key_file = project_root / "data/.tiingo.env"
    settings = dict(
        line.split("=", 1) for line in key_file.read_text(encoding="utf-8-sig").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    key = settings.get("TIINGO_API_KEY", "").strip().strip('"').strip("'")
    if not key:
        raise ValueError("Set TIINGO_API_KEY in data/.tiingo.env before refreshing.")
    query = urlencode(dict(startDate=start_date, endDate=end_date, resampleFreq="daily"))
    cache.mkdir(parents=True, exist_ok=True)
    for ticker in ("SPY", "IEF", "GLD"):
        request = Request(
            f"{TIINGO}/{ticker.lower()}/prices?{query}",
            headers={"Authorization": f"Token {key}"},
        )
        with urlopen(request, timeout=30) as response:
            payload = response.read()
        if not json.loads(payload):
            raise ValueError(f"Tiingo returned no prices for {ticker}.")
        (cache / f"tiingo_{ticker}.json").write_bytes(payload)


def read_tiingo_adjusted_close(cache: Path, ticker: str) -> pd.Series:
    if ticker not in ("SPY", "IEF", "GLD"):
        raise ValueError(f"Unsupported ticker: {ticker}")

    path = cache / f"tiingo_{ticker}.json"
    frame = pd.read_json(path, convert_dates=False)
    missing = {"date", "adjClose"}.difference(frame.columns)
    if missing:
        raise ValueError(f"Tiingo {ticker} snapshot is missing columns: {sorted(missing)}")

    dates = pd.to_datetime(frame["date"], utc=True).dt.tz_localize(None).dt.normalize()
    adjusted_close = pd.to_numeric(frame["adjClose"], errors="raise")
    result = pd.Series(
        adjusted_close.to_numpy(), index=dates, name="tiingo_adjClose"
    ).dropna()
    result = result.loc[result.index.notna()]
    if result.empty or not result.index.is_unique or not result.gt(0).all():
        raise ValueError(
            f"{ticker} Tiingo adjusted-close snapshot is empty, has duplicate dates, "
            "or contains non-positive prices."
        )
    return result
