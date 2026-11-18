from __future__ import annotations

import pytest

from src.targets.config import TargetConfigError, load_target_config


def _write_config(path, *, start_date: str, end_date: str) -> None:
    path.write_text(
        f"""
target:
  start_date: "{start_date}"
  end_date: "{end_date}"
  target_version: "2.0.0"
calendar:
  market: "XNYS"
paths:
  input: "data/curated/market_prices_daily.parquet"
  output: "data/curated/asset_volatility_labels.parquet"
  manifest_dir: "data/audit/targets"
publish:
  overwrite_conflicts: false
""",
        encoding="utf-8",
    )


def test_target_config_keeps_its_own_study_date_range(tmp_path) -> None:
    config_path = tmp_path / "target.yaml"
    _write_config(
        config_path,
        start_date="2021-09-27",
        end_date="2026-09-25",
    )

    config = load_target_config(config_path)

    assert config.start_date.isoformat() == "2021-09-27"
    assert config.end_date.isoformat() == "2026-09-25"
    assert config.market == "XNYS"
    assert config.target_version == "2.0.0"
    assert config.output_path.as_posix().endswith(
        "data/curated/asset_volatility_labels.parquet"
    )


def test_target_config_rejects_end_before_start(tmp_path) -> None:
    config_path = tmp_path / "target.yaml"
    _write_config(
        config_path,
        start_date="2026-09-25",
        end_date="2021-09-27",
    )

    with pytest.raises(TargetConfigError, match="end_date"):
        load_target_config(config_path)
