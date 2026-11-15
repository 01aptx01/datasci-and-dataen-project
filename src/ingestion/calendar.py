from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal


def get_effective_end_date(
    calendar: Any,
    requested_end_date: date,
    market_timezone: str = "America/New_York",
    as_of: datetime | None = None,
) -> date:
    """
    คำนวณ effective_end_date ไม่ให้เกินวันซื้อขายล่าสุดที่ข้อมูลราคาปิดพร้อมจริง
    ตาม Data Contract ข้อ 2.1
    """
    tz = ZoneInfo(market_timezone)
    now = (as_of or datetime.now(timezone.utc)).astimezone(tz)

    lookback_start = now.date() - timedelta(days=14)
    schedule = calendar.schedule(
        start_date=lookback_start.isoformat(),
        end_date=now.date().isoformat(),
    )
    if schedule.empty:
        return requested_end_date

    latest_closed_session = None
    for idx, row in schedule.iterrows():
        close_time = row["market_close"].to_pydatetime()
        if close_time.tzinfo is None:
            close_time = close_time.replace(tzinfo=timezone.utc)
        close_ny = close_time.astimezone(tz)
        if now >= close_ny:
            latest_closed_session = idx.date()

    if latest_closed_session is None:
        prior = calendar.schedule(
            start_date=(lookback_start - timedelta(days=14)).isoformat(),
            end_date=(lookback_start - timedelta(days=1)).isoformat(),
        )
        if not prior.empty:
            latest_closed_session = prior.index[-1].date()
        else:
            return requested_end_date

    if requested_end_date > latest_closed_session:
        return latest_closed_session

    return requested_end_date


def build_ingestion_window(
    config: dict[str, Any],
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """
    คำนวณวันเริ่มดึงข้อมูลย้อนหลังตาม warm-up,
    วันสิ้นสุดที่ใช้จริง (effective_end_date), วันสิ้นสุดสำหรับ API และวันซื้อขายที่คาดหวัง
    """
    try:
        date_config = config["date_range"]
        calendar_name = config["calendar"]["market"]
        market_tz = config["calendar"].get("market_timezone", "America/New_York")

        start_date = date.fromisoformat(date_config["start_date"])
        end_date = date.fromisoformat(date_config["end_date"])
        warmup_days = date_config["warmup_trading_days"]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"CONFIG_ERROR: Config ไม่ถูกต้อง: {error}") from error

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

    effective_end_date = get_effective_end_date(
        calendar=calendar,
        requested_end_date=end_date,
        market_timezone=market_tz,
        as_of=as_of,
    )

    if start_date > effective_end_date:
        raise ValueError(
            f"CONFIG_ERROR: start_date ({start_date}) ต้องไม่อยู่หลัง effective_end_date ({effective_end_date})"
        )

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

    # สร้างรายการวันซื้อขายตั้งแต่วันเริ่มดึงจริงถึงวันสิ้นสุดที่มีราคาพร้อมจริง (effective_end_date)
    expected_schedule = calendar.schedule(
        start_date=fetch_start_date.isoformat(),
        end_date=effective_end_date.isoformat(),
    )
    expected_trading_days = [
        session.date().isoformat()
        for session in expected_schedule.index
    ]

    return {
        "config_start_date": start_date.isoformat(),
        "config_end_date": end_date.isoformat(),
        "effective_end_date": effective_end_date.isoformat(),
        "actual_fetch_start_date": fetch_start_date.isoformat(),
        # end ของ yfinance เป็น exclusive จึงบวกหนึ่งวันปฏิทิน
        "api_end_date": (effective_end_date + timedelta(days=1)).isoformat(),
        "warmup_trading_days": warmup_days,
        "expected_trading_days": expected_trading_days,
        "expected_trading_day_count": len(expected_trading_days),
        "calendar": calendar_name,
    }