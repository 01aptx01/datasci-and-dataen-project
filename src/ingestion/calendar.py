from datetime import date, timedelta
from typing import Any

import pandas_market_calendars as mcal


def build_ingestion_window(config: dict[str, Any]) -> dict[str, Any]:
    """
    คำนวณวันเริ่มดึงข้อมูลย้อนหลังตาม warm-up,
    วันสิ้นสุดสำหรับ API และวันซื้อขายที่คาดหวัง
    """
    try:
        date_config = config["date_range"]
        calendar_name = config["calendar"]["market"]

        start_date = date.fromisoformat(date_config["start_date"])
        end_date = date.fromisoformat(date_config["end_date"])
        warmup_days = date_config["warmup_trading_days"]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"CONFIG_ERROR: Config ไม่ถูกต้อง: {error}") from error

    if start_date > end_date:
        raise ValueError("CONFIG_ERROR: start_date ต้องไม่อยู่หลัง end_date")

    if isinstance(warmup_days, bool) or not isinstance(warmup_days, int) or warmup_days <= 0:
        raise ValueError(
            "CONFIG_ERROR: warmup_trading_days ต้องเป็นจำนวนเต็มบวก"
        )

    try:
        calendar = mcal.get_calendar(calendar_name)
    except (KeyError, RuntimeError, ValueError) as error:
        raise ValueError(
            f"CONFIG_ERROR: ไม่พบ market calendar: {calendar_name}"
        ) from error

    # ดึงปฏิทินย้อนหลังให้มากพอ แล้วเลือกวันซื้อขายก่อน start_date
    lookback_years = max(2, warmup_days // 150 + 2)

    while True:
        calendar_start = start_date - timedelta(days=lookback_years * 366)
        prior_schedule = calendar.schedule(
            start_date=calendar_start.isoformat(),
            end_date=(start_date - timedelta(days=1)).isoformat(),
        )

        if len(prior_schedule) >= warmup_days:
            break

        lookback_years *= 2

    # วันซื้อขายลำดับที่ warmup_days ก่อนวันเริ่มวิเคราะห์
    fetch_start_date = prior_schedule.index[-warmup_days].date()

    # สร้างรายการวันซื้อขายตั้งแต่วันเริ่มดึงจริงถึงวันสิ้นสุด
    expected_schedule = calendar.schedule(
        start_date=fetch_start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
    expected_trading_days = [
        session.date().isoformat()
        for session in expected_schedule.index
    ]

    return {
        "config_start_date": start_date.isoformat(),
        "config_end_date": end_date.isoformat(),
        "actual_fetch_start_date": fetch_start_date.isoformat(),
        # end ของ yfinance เป็น exclusive จึงบวกหนึ่งวันปฏิทิน
        "api_end_date": (end_date + timedelta(days=1)).isoformat(),
        "warmup_trading_days": warmup_days,
        "expected_trading_days": expected_trading_days,
        "expected_trading_day_count": len(expected_trading_days),
        "calendar": calendar_name,
    }