# คู่มือรัน Pipeline และ Dashboard

คู่มือนี้สรุปลำดับการทำงานจาก repository root สำหรับการทดลองซ้ำ ไม่ใช่บริการพยากรณ์สด ศึกษาเงื่อนไขและตัวอย่างฉบับเต็มในคู่มือแต่ละขั้นก่อนใช้งาน ผล replay เป็นการจำลองย้อนหลังจาก snapshot ที่ดาวน์โหลดภายหลัง จึงไม่ได้ยืนยันว่า source มีอยู่จริง ณ วันย้อนหลัง และผล Test ไม่รับรองผลในอนาคต

## เตรียม environment และข้อมูล

- ใช้ Python 3.10 ตาม `pyproject.toml` และ `.python-version` ติดตั้งด้วย `uv sync`; เพิ่ม `--group eda` หากต้องการ notebook และ `--group dev` สำหรับเครื่องมือทดสอบ ดูรายละเอียดใน [README หลัก](../README.md)
- `data/` เป็นข้อมูลที่สร้างในเครื่องและไม่ได้รวมผลรันใน Git การ clone ใหม่ไม่มี curated tables หรือ artifacts ของ Stage 03–06 ต้องสร้างจากขั้นต้นหรือจัดเตรียมชุดข้อมูลที่เชื่อถือได้พร้อม manifest และ transaction ที่ตรงกัน
- Config ภายใต้ `config/` ตรึงช่วงศึกษา วัน cutoff และ run ID บางตัวเป็นของเครื่องเดิม ก่อนรันให้ตรวจ input paths, วัน, lineage และ output paths โดยเฉพาะ `paths` ใน `config/ml_evaluation.yaml` และ `sources` ใน `config/feature_drift.yaml` การเปลี่ยนข้อมูลหรือ config อาจทำให้ไม่ตรงกับ frozen snapshot ของเว็บ
- การดึงราคาต้องใช้เครือข่ายและ Yahoo Finance; ผลที่ได้ภายหลังอาจไม่เหมือน snapshot เดิม ห้ามโหลด `joblib` หรือ pickle จากแหล่งที่ไม่เชื่อถือ

## ลำดับการทำงาน

1. **Ingestion** — ตรวจ `config/ingestion.yaml` แล้วรัน `python -m src.ingestion.run --config config/ingestion.yaml` เพื่อสร้างราคาที่ผ่านการตรวจและ raw snapshot คำสั่ง scheduler เป็นทางเลือกแยกต่างหาก ดู [ภาพรวม pipeline](pipeline.md)
2. **Features และ Target** — ตรวจช่วงวันใน config แล้วรัน `python -m src.features.run --config config/features.yaml` และ `python -m src.targets.run --config config/target.yaml` ตรวจ manifest และ publish transaction ของทั้งสองรันก่อนนำไปใช้ ดู [features](../src/features/README.md) และ [targets](../src/targets/README.md)
3. **Stage 03: Dataset และ H1** — ใช้ Python API `load_validated_inputs`, `prepare_ml_dataset` และ `analyze_h1` พร้อมระบุ Parquet, manifest และ `publish-transaction.json` จากรันที่ตรงกัน ขั้นนี้เตรียม dataset ในหน่วยความจำและเขียน H1 evidence; ดูตัวอย่าง argument ใน [คู่มือ dataset](../src/ml_dataset/README.md)
4. **Stage 04: Training** — ส่ง `prepared` และ `inputs.labels` ให้ `run_training_selection` พร้อม `artifact_dir` ใหม่ที่ยังไม่มีอยู่ ระบบเลือก hyperparameters บน Validation และบันทึกโมเดลเริ่มต้น ดู [คู่มือ training](../src/ml_training/README.md)
5. **Stage 05: Replay** — ส่ง dataset และ labels เดิมให้ `run_final_replay` โดยระบุ Stage 04 `initial_model_artifact_dir` และ `output_root` ใช้ค่า cutoff ปริยายสำหรับ Final Replay; ตัวเลือก policy และ resume มีเงื่อนไขตาม [คู่มือ replay](../src/ml_replay/README.md) ทั้ง Stage 03–05 เป็น Python API ไม่ใช่ CLI ที่เรียกด้วย `python -m` ตามชื่อ package
6. **Stage 06: Evaluation** — ปรับ run-specific paths ใน `config/ml_evaluation.yaml` ให้ชี้ H1, Training, Replay และ manifest/transaction ที่สอดคล้องกัน แล้วรัน `python -m src.ml_evaluation.run --config config/ml_evaluation.yaml` ดู [คู่มือ evaluation](../src/ml_evaluation/README.md) และตรวจ lineage/checksums ของผล
7. **Feature Drift (ทางเลือก)** — เมื่อ inputs และหลักฐานตรงกับ snapshot ที่กำหนดใน `config/feature_drift.yaml` แล้ว รัน `python -m src.ml_diagnostics.run --repo-root . --config config/feature_drift.yaml` ระบบตรวจ identity และ checksum ก่อนสร้าง diagnostic; หากเพิ่งสร้าง Stage ใหม่ ต้องตรวจและปรับ source pins ให้ตรง ไม่ใช่เพียงเปลี่ยนชื่อ path
8. **Dashboard** — เว็บอ่าน frozen snapshot จาก ZIP ที่ pin ไว้ ไม่ได้เรียก Python pipeline หรือฝึกโมเดล เมื่อเตรียม Python และ Node แล้วให้ทำตาม [คู่มือ dashboard](../web/DASHBOARD_GUIDE.md) การรันขั้น 1–7 ใหม่ไม่ได้เปลี่ยน snapshot ของเว็บโดยอัตโนมัติ

## ตรวจสอบ

จาก root รัน `python -m pytest` หลังติดตั้งกลุ่ม dev สำหรับเว็บให้รัน `npm test` ใน `web/` ตามคู่มือ dashboard ผลทดสอบใช้ตรวจโค้ดและ snapshot ที่ระบุ ไม่ใช่การรับรองผลทดลองหรือการอนุมัติรายงาน
