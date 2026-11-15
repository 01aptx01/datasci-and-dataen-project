from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


REQUIRED_TICKERS = {"SPY", "IEF", "GLD"}


def load_config(config_path: str | Path) -> dict:
    """อ่านไฟล์ YAML แล้วตรวจค่าก่อนส่งให้ pipeline ใช้"""
    path = Path(config_path)

    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    validate_config(config)
    return config


def validate_config(config: dict) -> None:
    """ตรวจว่าค่าที่จำเป็นใน Config ถูกต้อง"""
    if not isinstance(config, dict):
        raise ValueError("CONFIG_ERROR: config must be a YAML mapping")

    try:
        tickers = set(config["source"]["tickers"])
        start_date = config["date_range"]["start_date"]
        end_date = config["date_range"]["end_date"]
        warmup_days = config["date_range"]["warmup_trading_days"]
        interval = config["source"]["interval"]
        auto_adjust = config["price"]["auto_adjust"]
        threshold = config["validation"]["simple_return_anomaly_threshold"]
        timezone = config["calendar"]["market_timezone"]
        mode = config["execution"]["mode"]
        max_attempts = config["execution"]["max_attempts"]
        timeout = config["execution"]["timeout_seconds"]
    except (KeyError, TypeError) as error:
        raise ValueError(f"CONFIG_ERROR: missing or invalid field: {error}") from error

    if tickers != REQUIRED_TICKERS:
        raise ValueError(
            "CONFIG_ERROR: source.tickers must contain SPY, IEF, and GLD"
        )

    if not isinstance(start_date, str) or not isinstance(end_date, str):
        raise ValueError("CONFIG_ERROR: dates must use YYYY-MM-DD format")

    if start_date > end_date:
        raise ValueError(
            "CONFIG_ERROR: start_date must not be after end_date"
        )

    if not isinstance(warmup_days, int) or warmup_days <= 0:
        raise ValueError(
            "CONFIG_ERROR: warmup_trading_days must be a positive integer"
        )

    if interval != "1d":
        raise ValueError("CONFIG_ERROR: source.interval must be '1d'")

    if auto_adjust is not True:
        raise ValueError("CONFIG_ERROR: price.auto_adjust must be true")

    if not isinstance(threshold, (int, float)) or not 0 < threshold < 1:
        raise ValueError(
            "CONFIG_ERROR: anomaly threshold must be between 0 and 1"
        )

    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, TypeError):
        raise ValueError(
            "CONFIG_ERROR: calendar.market_timezone is not a valid timezone"
        )

    if mode not in {"historical", "daily"}:
        raise ValueError(
            "CONFIG_ERROR: execution.mode must be 'historical' or 'daily'"
        )

    if not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError(
            "CONFIG_ERROR: max_attempts must be a positive integer"
        )

    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError(
            "CONFIG_ERROR: timeout_seconds must be greater than 0"
        )