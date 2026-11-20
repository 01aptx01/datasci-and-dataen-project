# Target / Label Pipeline

โมดูลนี้สร้าง `asset_volatility_labels` สำหรับ SPY, IEF และ GLD จาก `market_prices_daily` ที่ผ่าน Data Contract แล้ว ใช้ช่วงวันอ้างอิง `target.start_date` ถึง `target.end_date` ใน `config/target.yaml`; แถว warm-up ก่อน `start_date` ใช้ตรวจผลตอบแทน แต่ไม่ถูกเขียนเป็น Label

## สูตรและสถานะ

สำหรับวันอ้างอิง `t` ระบบเลือกผลตอบแทน Log Return ของ **5 วันซื้อขาย XNYS ถัดไป** ตั้งแต่ `t+1` ถึง `t+5` แล้วคำนวณ:

```text
sqrt((252 / 5) * sum(log_return[t+1:t+5] ** 2))
```

ระบบไม่รวมผลตอบแทนของ `t`, ไม่เลื่อนหน้าต่างเมื่อข้อมูลขาด และไม่เติมค่าที่หาย

- **Pending:** มีผลตอบแทนที่ตรวจผ่าน 0–4 วัน; Target และ `label_matured_at_utc` เป็น NULL
- **Mature:** มีผลตอบแทนที่ตรวจผ่านครบ 5 วัน; Target เป็น finite และไม่ติดลบ
- หากราคา anchor ไม่ผ่าน validation ระบบไม่สร้าง Label ให้ Ticker/วันนั้น; หากราคา หรือผลตอบแทนในหน้าต่างอนาคตขาดหรือไม่ผ่าน validation ระบบบันทึก Quality Finding ใน Run Manifest และคง Label ที่ได้รับผลกระทบเป็น Pending โดย Ticker อื่นที่ผ่านยังประมวลผลต่อได้

`record_created_at_utc` และ `label_matured_at_utc` ใช้เวลาประมวลผลจริง ไม่ได้จำลองเวลาที่ข้อมูลเคยรู้ได้ในอดีต ระบบรักษาเวลาเริ่มสร้างเดิมไว้เมื่อ Upsert และรักษาเวลาที่ Mature ครั้งแรกไว้เมื่อรันซ้ำ

## รัน Pipeline

จาก Repository root:

```powershell
python -m src.targets.run --config config/target.yaml
```

ตั้ง `target.start_date` และ `target.end_date` ให้เป็น XNYS sessions ในช่วงศึกษาที่ต้องการ ส่งข้อมูลก่อน `start_date` เข้ามาด้วยเพื่อให้ตรวจ `log_return` ของวันเริ่มต้นได้ ส่วนข้อมูลหลัง `end_date` ใช้ทำให้ Label ช่วงท้าย Mature ได้ แต่ไม่สร้าง Label เกิน `end_date`

เมื่อเพิ่มราคาใหม่และต้องขยายช่วงศึกษา ให้อัปเดต `target.end_date` แล้วรัน Pipeline ซ้ำ ระบบจะเติมแถวใหม่และอัปเดต Pending ตาม `(date, ticker)` โดยไม่สร้างแถวซ้ำ

### แก้ไข Label ที่มีอยู่

ค่าธุรกิจเดิมจะไม่ถูกแทนที่เงียบ ๆ หากมีการแก้ Source หรือ Target Version ที่เปลี่ยน Mature Label ให้ตรวจเหตุผลก่อน แล้วรันโดยระบุเหตุผล:

```powershell
python -m src.targets.run --config config/target.yaml --overwrite-conflicts --overwrite-reason "อธิบายแหล่งข้อมูลหรือการแก้ไขที่อนุมัติ"
```

## ไฟล์ผลลัพธ์และการกู้คืน

- `data/curated/asset_volatility_labels.parquet` — Logical Schema 12 คอลัมน์ตาม Data Dictionary; Primary Key คือ `(date, ticker)`
- `data/audit/targets/run_id=<run_id>/manifest.json` — Input/Config/Target version, checksums, Source Snapshots, ช่วงวัน, จำนวน Mature/Pending และ Quality Findings ของ Run
- `data/audit/targets/run_id=<run_id>/publish-transaction.json` — หลักฐานสถานะการเผยแพร่และการกู้คืนเมื่อเขียนไม่ครบ

Pipeline ตรวจ Schema, Primary Key, ราคา, Log Return, XNYS sessions และสถานะ Label ก่อนเผยแพร่ จากนั้น Stage Parquet และ Manifest แล้วแทนไฟล์เป็นชุดเดียว หากการเผยแพร่ล้มเหลวจะกู้ Parquet เดิมกลับก่อนจบ Run

## ขอบเขต

ขั้นนี้สร้าง Target เท่านั้น ไม่เปลี่ยน Feature หรือ EDA, ไม่สร้าง Training/Prediction/Evaluation/Portfolio Risk และไม่แก้ Contract หรือ Data Dictionary

รันทดสอบของโมดูล:

```powershell
python -m pytest src/targets -q
```
