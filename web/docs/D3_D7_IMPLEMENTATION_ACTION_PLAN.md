# DEDS Dashboard D3–D7 Implementation Action Plan

**สถานะ:** แผนงานถัดจาก D1–D2  
**อ้างอิง:** `DEDS_Dashboard_Planning_UIUX_Blueprint_v1.1` ส่วน 4–5, 9–11 และบันทึกตรวจ D1–D2  
**หลักการ:** read-only dashboard จาก Frozen Snapshot ที่ตรวจสอบแล้วเท่านั้น

## 1. จุดเริ่มต้นที่ยืนยันแล้ว

- Branch ปัจจุบัน: `feat/dashboard-d1-d2`
- D1–D2 อยู่ใน commits `240b444` (`feat(web): add verified D1-D2 dashboard`) และ `6de5e61` (`docs(web): document D1-D2 handoff and verification`)
- Handoff ที่ pin ไว้: `docs/ml-results/downloads/ml-results-handoff-82572c84.zip`
- ZIP SHA-256: `20dff91705ffbb60ab579f5c1f907537015ec2f52be001d5dfd24ea8978ae3f5`
- Evaluation ID: `82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2`
- Replay ID: `3cbf81eb9242d8894d2f67f39065a17ff1ef55a2e098773aead915949ab11b12`
- Adapter ที่รันได้ใน D1–D2 อนุญาต CSV เพียง `forecast_audit.csv` และ `evaluation.csv` พร้อม JSON ระบุตัวตน/manifest 3 ไฟล์ ส่วน metrics, portfolio, drift และ research CSV ใน Blueprint ยังต้องตรวจสมาชิกจริงและ schema ก่อนนำมาใช้
- Snapshot เป็น **Simulated Historical Replay**; point-in-time source availability ยังไม่ยืนยัน และ report approval ยังเป็น `PENDING`

## 2. ขอบเขตที่ห้ามข้าม

- ใช้ snapshot ZIP และ IDs ที่ pin ไว้เท่านั้น หาก identity หรือ checksum ไม่ผ่าน ให้ fail closed และไม่แสดงผลจาก snapshot นั้น
- ห้ามเรียก Train, `partial_fit`, Replay, Hypothesis inference หรือแก้ผล/logic ของ Stage 06
- ห้ามคำนวณ forecast, label, MAE/RMSE, p-value, CI, high-vol threshold หรือ ADWIN alert ขึ้นใหม่ใน browser
- ยอมให้ browser คำนวณได้เฉพาะ portfolio what-if จาก covariance ที่บันทึกไว้ โดยไม่เปลี่ยน model, source hash หรือ snapshot identity
- ไม่แสดงคำว่า live/current performance; คงคำอธิบาย Simulated Historical Replay, review-ready และ approval pending ไว้
- คง Python `src/`, model configs, logical table contracts และ source artifacts เดิมไว้ไม่แก้
- ส่งออกเฉพาะข้อมูลที่ผ่านการคัดเลือก พร้อม metadata แยกจาก source columns; ห้ามใส่ path ภายในเครื่อง, secrets, checkpoint หรือ ZIP ต้นฉบับใน public output

## 3. ลำดับงานและจุดตรวจ

### G0 — ขยาย Data Adapter อย่างมีหลักฐาน (ก่อนทำกราฟ D3–D5)

1. ตรวจ ZIP ที่ pin ไว้และทำ inventory ของไฟล์ใน `approved_results/`; ใช้รายชื่อใน Blueprint เป็น candidate list ไม่ถือว่าไฟล์มีอยู่จริงจนตรวจพบใน ZIP
2. สำหรับทุกไฟล์ที่จะใช้ ตรวจ member SHA-256, header, ชนิดข้อมูล, จำนวนแถว, null/empty/pending/error rows และรูปแบบ JSON ที่ฝังใน CSV
3. ตรวจว่า `evaluation_id`, `final_replay_experiment_id`, cutoff และเวอร์ชันสอดคล้องกับ identity/manifest ที่ยืนยันแล้ว หากไฟล์ไม่มี ID ในตัว ให้ผูกกับ ZIP/member hash ที่ตรวจได้และบันทึกใน generated manifest
4. เพิ่มเฉพาะไฟล์ที่มีจริงและจำเป็นเข้า `web/snapshot.policy.json`, typed schemas, parser/loader และ public allowlist; ห้ามคัดลอกไฟล์อื่นทั้งหมดจาก ZIP โดยอัตโนมัติ
5. เพิ่ม negative tests อย่างน้อยสำหรับไฟล์ที่ต้องใช้แต่หายไป, checksum ผิด, Evaluation/Replay ID ผิด, schema/header เปลี่ยน, malformed JSON และ Pending row ที่มี actual/error
6. Build และ unit tests ต้องผ่านก่อนเริ่มผูก chart กับข้อมูล

**แหล่ง candidate ตาม Blueprint ส่วน 5:** `model_metrics.csv`, `pair_comparisons.csv`, `coverage.csv`, `rolling_mae20.csv`, `drift_error_timeline.csv`, `H1_scatter_data.csv`, `H1_results.csv`, `H1_sensitivity.csv`, `hypothesis_results.csv`, `bootstrap_diagnostics.csv`, `high_volatility_metrics.csv`, `portfolio_risk.csv`, `monthly_metrics.csv`, `yearly_metrics.csv`, `source_identity.json`, `execution_manifest.json`, `stage05_experiment_manifest.json` และ `CHECKSUMS.sha256` ตรวจชื่อจริงและ schema ก่อนใช้ทุกครั้ง

**ผ่าน G0 เมื่อ:** adapter ปฏิเสธ snapshot ที่ผิดได้, IDs และ hashes ถูกผูกไว้ชัดเจน, public output มีเฉพาะ allowlist, tests/build ผ่าน และ UI แสดง empty/error state เมื่อไม่มี source ที่จำเป็น

### D3 — Overview, Models, Forecasts และ Coverage

**งาน**

- ทำ Overview จากผลที่อ่านได้จาก snapshot; แสดง Evaluation/Replay ID, split, cutoff, หน่วย, N และสถานะ review
- ทำ Models จาก `model_metrics.csv` และ `pair_comparisons.csv`; แยก `MACRO` aggregate ออกจาก ETF และแสดง paired N/metric ใน tooltip และตาราง
- ขยาย Forecasts จาก stepper D2 ให้เลือก asset/model/date และดู forecast-vs-actual จาก `forecast_audit.csv` + `evaluation.csv`; stepper ยังคงเดินได้เฉพาะวันที่บันทึกไว้
- ทำ Coverage จาก `coverage.csv` หรือข้อมูล `forecast_audit.csv` ตาม schema ที่ตรวจจริง โดยแสดง pending, failed และ denominator แยกกัน
- ใส่ source footer ทุก chart/table: filename, split, selection, N, units และ Evaluation ID

**ตรวจรับ**

- ค่า Test Macro MAE ของ B0–B3 และจำนวน forecast/evaluable/Pending ตรง source เมื่อ Evaluation ID ตรงเท่านั้น: B0 `0.075854`, B1 `0.059340`, B2 `0.052479`, B3 `0.048892`; expected/valid `2,976`, mature/evaluable `2,916`, Pending `60`
- Pending แสดง forecast ได้เมื่อ source ระบุว่าถูกต้อง แต่ actual/error เป็น `—` และ tooltip ระบุว่า label ยัง pending; ห้ามเติมค่าประมาณ
- ตัวกรองและตารางให้ค่า N ตรงกับ selection; มี empty/loading/error state; ไม่มี hardcoded metric fallback
- stepper ไม่มีปุ่ม/ข้อความที่สื่อว่ากำลังฝึกหรืออัปเดตโมเดล

**Commit เมื่อผ่าน:** `feat(web): add model and forecast views`

### D4 — Portfolio Lab

**งาน**

- ตรวจ `portfolio_risk.csv` จริงก่อนใช้ ทั้ง header, การ serialize `covariance_matrix`, `missing_inputs`, model/date และ status
- สร้าง pure function สำหรับ `sqrt(wᵀΣw)` โดยรับเฉพาะ covariance ที่บันทึกในแถวเดียวกับวันที่และ model forecast
- เพิ่มตัวเลือกวันที่/model และตัวปรับ weights; แสดง source portfolio value คู่กับ what-if value และระบุชัดว่าเป็นการคำนวณจาก covariance ที่เก็บไว้
- ปฏิเสธน้ำหนักติดลบ, NaN/Infinity, ผลรวมน้ำหนักไม่เท่ากับ 1, covariance/forecast ไม่ครบ หรือ `portfolio_status` ที่ไม่พร้อม

**ตรวจรับ**

- น้ำหนักเริ่มต้น 50/30/20 ให้ผลตรงกับ Stage 06 row ที่เลือกภายใน `1e-10`
- แถวที่ข้อมูลไม่ครบให้ no-result พร้อมเหตุผล; ไม่มีการใช้ correlation/covariance จากคนละวันหรือคนละ model
- การเปลี่ยนน้ำหนักไม่ทำ network call, inference, replay หรือเปลี่ยน IDs/hash

**Commit เมื่อผ่าน:** `feat(web): add stored covariance portfolio lab`

### D5 — Drift และ Research

**งาน**

- Rolling MAE20 จาก `rolling_mae20.csv` พร้อม filter model/asset/range และระบุว่าเป็น fixed 20 XNYS sessions ตาม source
- ADWIN จาก `drift_error_timeline.csv`; แสดง Test B3 error timeline และ alert ตาม `drift_detected`/`alert_record_present` ที่บันทึกไว้เท่านั้น
- H1 ใช้ `H1_scatter_data.csv`, `H1_results.csv`, `H1_sensitivity.csv`; แยก Train scatter และ primary HAC lag 5 ออกจาก sensitivity lag 10/20
- H2/H3 ใช้ `hypothesis_results.csv` และ `bootstrap_diagnostics.csv`; แสดงเฉพาะ MACRO/Test ที่ source ระบุ พร้อม effect, N, p, CI, decision และ method
- High-vol subset จาก `high_volatility_metrics.csv`; ใช้ threshold ที่บันทึกจาก Train และห้ามแสดง IEF Test ที่ n=0 เป็น MAE ศูนย์

**ตรวจรับ**

- จำนวน ADWIN alert ใน snapshot ตรง source (Blueprint ระบุ 0); ไม่มี marker หรือ alert ที่สร้างจาก client-side rule
- H1 เป็น Train เท่านั้น; H2/H3 เป็น Test เท่านั้น; p-value, CI และ decision ตรง source แบบไม่คำนวณซ้ำ
- IEF high-vol Test แสดง `Insufficient Evidence (n=0)` โดยไม่มี zero-score bar
- ทุกการกรองแยก visualization subset N ออกจาก hypothesis N ต้นฉบับ

**Commit เมื่อผ่าน:** `feat(web): add drift and research views`

### D6 — Provenance, Guide และ Export Metadata

**งาน**

- Provenance แสดง source ZIP/member hashes, handoff commit, baseline commit, Evaluation/Replay IDs, cutoff, report approval และสถานะ source verification
- แยก source checksum กับ hash ของไฟล์ export ให้เห็นว่า export เป็นผลคัดกรองจาก UI ไม่ใช่ source artifact
- เติม Guide/glossary เป็นภาษาง่ายและคำช่วยภาษาไทย/อังกฤษสำหรับ RV5, Pending, B0–B3, split, leakage, ADWIN, MAE/RMSE และ portfolio covariance
- เพิ่มข้อจำกัดของงานและ source link ตาม Blueprint; export รักษาชื่อคอลัมน์ต้นทางและแนบ metadata แยกส่วน

**ตรวจรับ**

- IDs ตรงกันทุกหน้าและใน export metadata; ไม่มีการอ้าง report approval ว่าอนุมัติแล้ว
- ผู้ใช้แยก source hash กับ export hash และเข้าใจว่านี่ไม่ใช่ live dashboard ได้จากข้อความบนหน้า

**Commit เมื่อผ่าน:** `feat(web): add provenance and result guidance`

### D7 — Release Readiness (ตรวจในเครื่องเท่านั้น)

**งาน**

- ทำ Playwright coverage สำหรับทั้ง 8 routes, deep link/reload, missing/tampered snapshot, Pending, invalid portfolio controls และ export metadata
- ตรวจ desktop 1440px และ mobile 390px พร้อมบันทึก screenshot ที่เปิดดูซ้ำได้ใน `web/evidence/`; เพิ่ม 1280px และ 360/430px เป็น responsive regression ตาม Blueprint
- ตรวจ keyboard/focus, accessible names, screen-reader table alternative, color-safe series และ controls ที่ใช้งานได้โดยไม่พึ่ง hover
- ตรวจ horizontal overflow, chart labels/axes, mobile filter/table/slider และ nested static path สำหรับ hosting แบบ static
- บันทึกคำสั่งและผล build/unit/e2e, screenshot paths, browser/version และ known limitations ใน verification record

**ตรวจรับ**

- P0 acceptance AC-01–AC-20 ใน Blueprint ผ่านหรือมีข้อจำกัดที่บันทึกชัดเจน
- `git diff` ของ `src/`, model configs, logical table contracts และผล Stage 06 ว่าง
- Build, unit และ browser tests ผ่าน; ไม่มี console error ที่เกี่ยวกับแอป; all routes ใช้งานได้และไม่มีตัวเลขสมมติ
- จัดทำ static deployment guide ได้ แต่ยังไม่ deploy/publish

**Commit เมื่อผ่าน:** `test(web): verify dashboard release readiness`

## 4. ลำดับและ dependency

| ลำดับ | งาน | Dependency | Gate ก่อนเริ่ม |
|---:|---|---|---|
| 1 | G0: ตรวจและขยาย adapter | D2 | exact ZIP, member hashes, IDs และ schema ผ่าน |
| 2 | D3: Model/Forecast | G0 | source metrics/coverage มีจริงและ typed schema ผ่าน |
| 3 | D4: Portfolio | G0 | covariance กับ source portfolio row ผ่าน parity test |
| 4 | D5: Drift/Research | G0 | ทุก source file และ Train/Test labels ผ่าน schema checks |
| 5 | D6: Provenance/Guide | D3–D5 | ชื่อ source, hashes และสถานะทุกหน้าคงที่ |
| 6 | D7: Release readiness | D1–D6 | route และ P0 acceptance ครบ |

ถ้า G0 พบว่าไฟล์ source ที่จำเป็นไม่มีหรือ schema ไม่ตรง ให้คงหน้าใน Empty State พร้อมระบุไฟล์/ข้อมูลที่ขาด และหยุดส่วนที่พึ่งข้อมูลนั้น ห้ามสร้าง fixture ที่ดูเหมือนผลจริงเพื่อให้กราฟเต็ม

## 5. Git และการส่งมอบ

- ทำงานต่อใน local feature branch ที่แยกจาก `main`; ใช้ commit เล็กตาม milestone ข้างต้นและ Conventional Commits
- ก่อนแต่ละ commit ตรวจ `git status`, staged diff, รายชื่อไฟล์ที่ stage และผล checks ที่เกี่ยวข้อง; ห้าม stage snapshot ส่วนตัว, secrets, generated `dist/` หรือ raw artifact ที่ไม่อยู่ใน allowlist
- ห้าม amend/reset/rewrite ประวัติเดิม และห้าม push, PR, merge, release หรือ deploy
- เมื่อจบ ให้รายงาน branch, commit SHA/message, working-tree status, tests/build, screenshot paths, sources/schema ที่ใช้ และงานค้าง

## 6. Definition of Done รวม

- D3–D7 ใช้ผลจาก Frozen Snapshot เดียวกันและระบุตัวตน/ข้อจำกัดอย่างตรงไปตรงมา
- ทุก source ที่แสดงผลผ่าน checksum, identity และ runtime schema validation; กรณีไม่ผ่านไม่แสดงตัวเลข
- มี build/unit/browser verification และ screenshot desktop 1440px กับ mobile 390px ที่เก็บเป็นไฟล์
- การคำนวณเฉพาะที่อนุญาตคือ portfolio what-if จาก stored covariance; ไม่มี ML execution หรือการเปลี่ยน Stage 06
- commits อยู่บน local feature branch; ไม่มีการเผยแพร่หรือแก้ remote
