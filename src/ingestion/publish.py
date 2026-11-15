import json
import os
from pathlib import Path
from typing import Any

import pandas as pd


KEY_COLUMNS = ["date", "ticker"]


def publish_market_prices(
    validated_data: pd.DataFrame,
    ticker_summary: dict[str, dict[str, Any]],
    run_id: str,
    table_path: str = "data/curated/market_prices_daily.parquet",
    audit_root: str = "data/audit",
) -> dict[str, Any]:
    """Upsert ข้อมูล ticker ที่ผ่าน validation ลงตาราง Parquet หลัก"""

    table = Path(table_path)
    table.parent.mkdir(parents=True, exist_ok=True)

    # เลือกเฉพาะ ticker ที่ validation ผ่านและได้รับอนุญาตให้ publish
    allowed_tickers = [
        ticker
        for ticker, result in ticker_summary.items()
        if result.get("publish_status") == "PUBLISHED"
    ]

    incoming = validated_data[
        validated_data["ticker"].isin(allowed_tickers)
    ].copy()

    if not incoming.empty and incoming.duplicated(KEY_COLUMNS).any():
        raise ValueError("PUBLISH_ERROR: duplicate (date, ticker) keys")

    old_data = (
        pd.read_parquet(table)
        if table.exists()
        else pd.DataFrame(columns=incoming.columns)
    )

    # นับ insert, update และ unchanged โดยเทียบข้อมูลตาม primary key
    inserted = updated = unchanged = 0

    if not incoming.empty and not old_data.empty:
        old_indexed = old_data.set_index(KEY_COLUMNS)
        incoming_indexed = incoming.set_index(KEY_COLUMNS)

        for key, new_row in incoming_indexed.iterrows():
            if key not in old_indexed.index:
                inserted += 1
            else:
                old_row = old_indexed.loc[key]

                # ถ้าพบ key ซ้ำในตารางเดิม ให้หยุดแทนการเดาว่าแถวไหนถูก
                if isinstance(old_row, pd.DataFrame):
                    raise ValueError(
                        f"PUBLISH_ERROR: duplicate key already in table: {key}"
                    )

                if new_row.equals(old_row.reindex(new_row.index)):
                    unchanged += 1
                else:
                    updated += 1

    elif not incoming.empty:
        inserted = len(incoming)

    # upsert: เก็บแถวเดิมที่ไม่อยู่ใน incoming แล้วแทน key ที่เข้ามาใหม่
    if not old_data.empty and not incoming.empty:
        old_data = old_data.merge(
            incoming[KEY_COLUMNS].drop_duplicates(),
            on=KEY_COLUMNS,
            how="left",
            indicator=True,
        )
        old_data = old_data.loc[
            old_data["_merge"] == "left_only"
        ].drop(columns="_merge")

    combined = pd.concat(
        [old_data, incoming],
        ignore_index=True,
    )

    if not combined.empty:
        combined = combined.sort_values(KEY_COLUMNS).reset_index(drop=True)

        if combined.duplicated(KEY_COLUMNS).any():
            raise ValueError("PUBLISH_ERROR: duplicate keys after upsert")

    # เขียนไฟล์ใหม่ก่อน แล้วค่อยแทนไฟล์หลัก เพื่อลดโอกาสเขียนค้างครึ่งไฟล์
    temp_table = table.with_suffix(".tmp.parquet")
    combined.to_parquet(temp_table, index=False)
    os.replace(temp_table, table)

    audit = {
        "run_id": run_id,
        "table": str(table),
        "tickers_published": allowed_tickers,
        "tickers_blocked": [
            ticker
            for ticker, result in ticker_summary.items()
            if result.get("publish_status") != "PUBLISHED"
        ],
        "rows_inserted": inserted,
        "rows_updated": updated,
        "rows_unchanged": unchanged,
        "rows_in_table": len(combined),
        "portfolio_ready": all(
            result.get("publish_status") == "PUBLISHED"
            for result in ticker_summary.values()
        ),
    }

    audit_dir = Path(audit_root) / f"run_id={run_id}"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "publish_report.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return audit