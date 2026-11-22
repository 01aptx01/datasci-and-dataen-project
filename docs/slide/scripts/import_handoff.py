"""Bundle the frozen Test data used by the presentation's interactive slides."""

import csv
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile


APP_ROOT = Path(__file__).resolve().parents[1]
SOURCE = APP_ROOT.parent / "ml-results" / "downloads" / "ml-results-handoff-82572c84.zip"
DESTINATION = APP_ROOT / "public" / "data"
EXPECTED_SHA256 = "20dff91705ffbb60ab579f5c1f907537015ec2f52be001d5dfd24ea8978ae3f5"


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"Missing handoff archive: {SOURCE}")
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(f"Unexpected handoff SHA-256: {digest}")

    DESTINATION.mkdir(parents=True, exist_ok=True)
    counts = {}
    with ZipFile(SOURCE) as archive:
        for name in ("forecast_audit", "portfolio_risk", "drift_error_timeline", "H1_scatter_data"):
            path = f"approved_results/{name}.csv"
            with archive.open(path) as source:
                reader = csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig", newline=""))
                if reader.fieldnames is None:
                    raise SystemExit(f"Missing CSV header: {path}")
                split = "train" if name == "H1_scatter_data" else "test"
                rows = [row for row in reader if row.get("split", split).lower() == split]
                if name == "portfolio_risk":
                    rows = [row for row in rows if row.get("model_name") == "ONLINE_SGD"]
                if not rows:
                    raise SystemExit(f"No {split} rows: {path}")
                with (DESTINATION / f"{name}.csv").open("w", encoding="utf-8", newline="") as target:
                    writer = csv.DictWriter(target, fieldnames=reader.fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                counts[name] = len(rows)

    (DESTINATION / "source.json").write_text(
        json.dumps(
            {"source_archive": SOURCE.name, "sha256": digest, "scope": "frozen_test_and_H1_train", "rows": counts},
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(counts)


if __name__ == "__main__":
    main()
