"""Download and read the independent price snapshots used in notebook 00."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZipFile

import pandas as pd

TIINGO = "https://api.tiingo.com/tiingo/daily"
SPDR = "https://api.spdrgoldshares.com/api/v1/historical-archive?exchange=NYSE&lang=en&product=gld"


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
    for ticker in ("SPY", "IEF"):
        request = Request(
            f"{TIINGO}/{ticker.lower()}/prices?{query}",
            headers={"Authorization": f"Token {key}"},
        )
        with urlopen(request, timeout=30) as response:
            payload = response.read()
        if not json.loads(payload):
            raise ValueError(f"Tiingo returned no prices for {ticker}.")
        (cache / f"tiingo_{ticker}.json").write_bytes(payload)
    with urlopen(SPDR, timeout=30) as response:
        payload = response.read()
    (cache / "spdr_gld.xlsx").write_bytes(payload)


def read_independent_close(cache: Path, ticker: str) -> pd.Series:
    if ticker in ("SPY", "IEF"):
        frame = pd.read_json(cache / f"tiingo_{ticker}.json", convert_dates=False)
        dates = pd.to_datetime(frame["date"], utc=True).dt.tz_localize(None).dt.normalize()
        close = pd.to_numeric(frame["adjClose"], errors="raise")
    elif ticker == "GLD":
        with ZipFile(cache / "spdr_gld.xlsx") as workbook:
            strings = [
                "".join(item.itertext())
                for item in ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            ]
            archive = ET.fromstring(workbook.read("xl/worksheets/sheet2.xml"))
        rows = []
        for row in archive.findall(".//{*}sheetData/{*}row"):
            values = {}
            for cell in row:
                column = cell.attrib["r"].rstrip("0123456789")
                value = cell.find("{*}v")
                if column in ("A", "B") and value is not None:
                    values[column] = strings[int(value.text)] if cell.get("t") == "s" else value.text
            rows.append(values)
        frame = pd.DataFrame(rows)
        if tuple(frame.loc[0, ["A", "B"]]) != ("Date", "Closing Price"):
            raise ValueError("Unexpected date or close headers in the GLD archive.")
        dates = pd.to_datetime(frame["A"], format="%d-%b-%Y", errors="coerce")
        close = pd.to_numeric(frame["B"], errors="coerce")
    else:
        raise ValueError(f"Unsupported ticker: {ticker}")

    result = pd.Series(close.to_numpy(), index=dates, name="external_close").dropna()
    result = result.loc[result.index.notna()]
    if result.empty or not result.index.is_unique:
        raise ValueError(f"{ticker} snapshot is empty or has duplicate dates.")
    return result
