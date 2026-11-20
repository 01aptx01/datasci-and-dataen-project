from __future__ import annotations

import argparse
import json

from src.ml_evaluation.pipeline import run_from_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the approved DEDS Stage 06 final evaluation.")
    parser.add_argument(
        "--config",
        default="config/ml_evaluation.yaml",
        help="Path to the Stage 06 YAML configuration (default: config/ml_evaluation.yaml)",
    )
    args = parser.parse_args()
    result = run_from_config(args.config)
    summary = {
        "evaluation_id": result.evaluation_id,
        "artifact_dir": str(result.artifact_dir),
        "test_evaluable_rows": int(len(result.evaluation)),
        "test_coverage_rows": int(result.coverage.loc[result.coverage["split"] == "test"].shape[0]),
        "hypothesis_rows": int(len(result.hypothesis_results)),
        "portfolio_rows": int(len(result.portfolio_risk)),
        "status": result.manifest.get("status"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
