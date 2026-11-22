# แผนใหม่: Drift-triggered Champion–Challenger

> **สถานะ ณ 23 พฤศจิกายน 2026:** ไฟล์นี้เป็นบันทึกแผนและ acceptance checklist ดั้งเดิม ไม่ใช่รายการงานปัจจุบัน; ช่องที่ยังไม่ติ๊กไม่ได้แปลว่างานยังไม่ทำ ปัจจุบันมี policy replay/evaluation และ dashboard sidecar แล้ว ดู [ผล Champion ADWIN](../ml-results/06_champion_adwin_only.md), [handoff policy ล่าสุด](../ml-results/README.md) และ implementation ใน `src/ml_replay/` กับ `src/ml_evaluation/`. ผลบน Test เป็น retrospective exploratory study หลังมีการตรวจ Test เดิม; ไม่มี alert หรือ promotion ในผลจริงชุดที่รายงาน และไม่ยืนยันผลเชิง prospective

## เป้าหมายและขอบเขต
สร้าง policy จำลองราย ETF สำหรับเลือก B0/B1/B2 จาก Validation แล้วใช้ Champion จน ADWIN แจ้งเตือน จากนั้นเปรียบเทียบกับ B3 ที่อัปเดตแบบ shadow ด้วยข้อมูลที่ label mature แล้ว แสดงเหตุการณ์และโมเดลที่ใช้ในเว็บซึ่งปัจจุบันเป็น historical replay แบบ static snapshot ไม่ใช่ inference สด แผนนี้ไม่เปลี่ยนผลวิจัย B0–B4/H1–H3 เดิม และ B4 ไม่อยู่ในชุดเลือกของ policy นี้

## ข้อเท็จจริงและการออกแบบที่ต้องตรึงก่อนทดลอง
- B2 และ B3 เริ่มจาก estimator/scaler ที่ fit ชุดเดียวกันต่อ ETF จึงให้ forecast เท่ากันเมื่อรับ input เดียวกัน ณ initial state แต่ไม่เท่ากันเสมอเมื่อเริ่ม Test: B3 อาจได้รับ label ที่ mature ระหว่าง Validation และ update แล้ว ส่วน B1 เปลี่ยน forecast ตาม rv_20d แม้ไม่มีการฝึกใหม่
- เลือก initial champion ต่อ ETF ด้วย Validation MAE บนแถวที่ mature และ valid ครบทั้ง B0/B1/B2 ณ เวลาเริ่ม Test เท่านั้น ตรวจ cutoff/purge และ coverage; tie ใช้ลำดับ B0, B1, B2; หากข้อมูลไม่พอให้หยุดอย่างชัดเจน ห้ามใช้ Test เลือก นี่เป็น policy ใหม่ แยกจากการเลือก SGD hyperparameters เดิม
- ADWIN แยกต่อ ETF และรับ absolute error ของ forecast ที่ policy ส่งจริง เมื่อ label mature แล้วเท่านั้น เรียง deterministic ตามวันและ prediction ID พร้อมบันทึก prediction_date, target_end_date, detection_date และ policy/model version สัญญาณหมายถึงการเปลี่ยนแปลงของ error stream ไม่ใช่หลักฐานสาเหตุหรือรับประกัน error เพิ่ม ต้องระบุ direction และไม่ส่ง label ที่ pending หรือ invalid
- B3 shadow อัปเดตต่อเนื่องหลัง forecast จาก labels eligible ที่ mature ตามกติกา Stage 05 เดิม โดยไม่ขึ้นกับ drift ให้สร้างและเก็บ forecast shadow ณ เวลานั้นสำหรับ comparison ห้ามนำ state B3 ปัจจุบันไปทำนายย้อนหลังหรือประเมินด้วยอนาคต
- เมื่อมี alert ให้เปรียบเทียบ error แบบ paired ของ served champion กับ shadow B3 เฉพาะ forecast ที่ออกขณะ champion version ปัจจุบันยัง active และ label mature ณ วันตัดสิน ใช้หน้าต่างล่าสุด 60 คู่, ขั้นต่ำ 30 คู่; B3 ต้อง MAE ต่ำกว่าอย่างน้อย 5% เทียบ champion จึง promote; เสมอหรือข้อมูลไม่พอให้คงเดิมและบันทึกเหตุผล ตัวเลขเป็นค่าเริ่มต้นสำหรับ validation/sensitivity ไม่ใช่ข้อเท็จจริงที่พิสูจน์แล้ว ตรึงก่อนรัน Test และอย่า tune บน Test
- เมื่อ promote ให้ snapshot B3 state/scaler เป็น champion version ที่ frozen; shadow B3 แยกสำเนาและอัปเดตต่อเนื่อง เพื่อให้คำว่าใช้โมเดลเดิมจนเกิด alert มีความหมายชัดเจน แยก identity ของ state ทุกครั้ง และ ADWIN เริ่ม stream ใหม่เมื่อ champion version เปลี่ยน ป้องกันประวัติ error ต่างรุ่นปะปน B0/B2 frozen; B1 ใช้สูตรเดิมบน feature ของวัน
- มี alert ไม่เท่ากับ switch: outcome อาจเป็น retained, insufficient_pairs, invalid หรือ promoted; สำหรับ champion ที่เป็น B3 แล้ว สามารถเปรียบเทียบ shadow B3 รุ่นใหม่และ promote snapshot ใหม่ด้วยกติกาเดียวกัน บันทึก event แม้ไม่มี switch จำกัดซ้ำด้วย cooldown 20 sessions หลังการตัดสิน และบันทึก alert ระหว่าง cooldown ไม่ซ่อนเหตุการณ์ หากข้อมูลไม่พอ รอ alert ครั้งถัดไปตามกติกาที่ตรึง ไม่ใช้ข้อมูลอนาคต
- ลำดับวัน: forecast served และ shadow จาก state ก่อน update → mature/evaluate → feed served error เข้า ADWIN → ตัดสินจากคู่ที่ mature แล้ว → update shadow B3 → commit atomic; promotion ใช้ snapshot B3 ณ เวลาตัดสินก่อน update และมีผลตั้งแต่ session ถัดไป ไม่มีการแก้ forecast ที่สร้างแล้ว ต้องทดสอบกรณีมีหลาย label mature วันเดียวและกำหนดว่า alert แรกต่อ ETF ใน session เป็นตัวเริ่มตัดสิน โดยป้อน error ที่เหลือตามลำดับที่ตรึง
- โมเดลและ event มี run ID, ETF, state hash, วันที่มีผล, จำนวนคู่, window, MAE, threshold, detector configuration, reason และ lineage; แยก event policy ออกจาก drift ของ B3 เดิมและ Feature Drift (W1/PSI) ใช้ schema/version ใหม่ ตรวจ checksum/row counts; checkpoint ต้องครอบคลุม detector, champion snapshot, shadow, pending/ledger, comparison window, cooldown และ event IDs รวมทั้ง reject checkpoint รุ่นเก่าอย่างชัดเจน
- นโยบายนี้เลือกหลังเห็นผล Test เดิม จึงเป็น retrospective exploratory evaluation; เปรียบเทียบกับ B0–B4 เดิมและ fixed initial champion บนคู่วัน/ETF ที่ตรงกัน พร้อม coverage, MAE/RMSE, จำนวน alerts/switches, ระยะเวลาและความล่าช้า label ไม่อ้างผล confirmatory จนมี holdout ใหม่ที่ไม่เคยดู และ historical source availability ยังไม่ verified

## ความเสี่ยงและ gate
- Error ที่ mature ช้าหลาย session ทำให้ detection และ promotion ล่าช้า ต้องแสดงวัน forecast และวัน detect แยกกัน; overlap ของ target windows ทำให้ error ไม่อิสระ จึงห้ามตีความ 30/60 คู่เป็นนัยสำคัญทางสถิติ
- ADWIN ใช้ error ของ champion ที่เปลี่ยนรุ่น จึง reset หลัง switch และอาจมีช่วง warm-up ไม่มี detection; event ต้องแยก no signal, insufficient history และไม่มีข้อมูล
- Missing/invalid forecast ต้องไม่ถูกแทนหรือเลือกจาก reduced coverage แบบเงียบ ๆ; ตรวจผลกระทบและ fallback แบบ explicit ก่อน deploy
- Replay เดิมเริ่ม Validation ก่อน Test: ต้องตรึง cutover หลังข้อมูล Validation ที่ใช้เลือก mature จริง ห้ามย้าย state B3 หรือ detector ข้าม cutoff โดยไม่บันทึก lineage และต้องตรวจการ resume ทุกขอบเขต
- งาน UI แสดงย้อนหลังตาม snapshot เท่านั้น หากต้องการ inference สดต้องมี backend/service, durable state, scheduling, ingestion และ operational monitoring เป็นโครงการแยก

## ลำดับงาน
ดู checklist แบบ acceptance/verification/dependencies ด้านล่าง; ใช้ผลจริงและคำสั่งบันทึกใต้แต่ละ task ก่อนติ๊ก และสร้าง artifact/run ใหม่โดยไม่ทับ baseline


# Task: Drift-triggered Champion–Challenger

อ่านแผนและ policy ด้านบนก่อนเริ่ม ทุก task ต้องบันทึกคำสั่ง ผล artifact/run ID และ PASS/FAIL/BLOCKED; checkbox หมายถึงมีหลักฐานจริง ไม่แก้ output เดิม

## 1. ตรึง protocol และ baseline
- [ ] ตรวจ cutover ของ Validation/Test, maturity/purge, ตัวเลือก ETF และกำหนด Validation rows ที่พร้อมจริง ณ cutover พร้อม config/hash ของ policy และเกณฑ์ 30/60, 5%, cooldown; ถ้า coverage ไม่พอหยุดพร้อมเหตุผล
- [ ] ตรวจ baseline B0–B4, B3 state ณ initial และต้น Test, source lineage, replay snapshot และแยก experimental policy จาก H1–H3
- **ตรวจ:** ใช้ fixture เล็กตรวจ B2=B3 ก่อน update และอาจต่างหลัง update; ตรวจไม่มี Test label ใน initial selection
- **ขึ้นกับ:** ไม่มี | **ไฟล์:** `config/ml_training.yaml`, `config/ml_replay.yaml`, `src/ml_training/`, `docs/contract/`

## 2. เลือก champion เริ่มต้น
- [ ] สร้าง Validation predictions B0/B1/B2 แบบ point-in-time และเลือก per ETF ด้วย paired MAE/coverage ตามแผน; บันทึก scores, counts, cutoff, tie และ model identity
- [ ] ทดสอบ tie, invalid, label ล่าช้า/ไม่พอและ deterministic rerun โดยไม่แก้ selection SGD เดิม
- **ตรวจ:** `.venv\Scripts\python.exe -m pytest tests/test_ml_training.py tests/test_ml_contract_config.py -v` และตรวจ artifact ราย ETF
- **ขึ้นกับ:** 1 | **ไฟล์:** `src/ml_training/`, `tests/test_ml_training.py`, config และ contract

## 3. Replay policy และ shadow
- [ ] เพิ่ม policy version และ immutable served/shadow forecasts แยกจาก B0–B4 benchmark; B3 update ต่อเนื่องตาม maturity และ snapshot promotion ทำงานตั้งแต่ session ถัดไป
- [ ] เพิ่ม ADWIN บน served mature error และ paired window + promotion gate, cooldown และเหตุผลครบทุก outcome; บังคับ chronological ordering และไม่มี look-ahead
- **ตรวจ:** `.venv\Scripts\python.exe -m pytest tests/test_ml_replay.py -v`; fixture ครอบคลุม no drift, drift แต่ไม่ switch, promotion, B3-to-B3, pending/invalid และหลาย labels ต่อวัน
- **ขึ้นกับ:** 2 | **ไฟล์:** `src/ml_replay/pipeline.py`, `src/ml_replay/config.py`, `config/ml_replay.yaml`, `tests/test_ml_replay.py`

## 4. Checkpoint และ reproducibility
- [ ] version checkpoint เก็บ champion snapshot, shadow, detector, paired window, cooldown, pending และ processed ledgers; validate identity/checksum และปฏิเสธ checkpoint เก่าหรือ incompatible อย่างชัดเจน
- [ ] รองรับ atomic commit, replay/resume และ event deduplication แม้ interruption; บันทึก rollback target ใน audit สำหรับการพัฒนา live ภายหลัง
- **ตรวจ:** uninterrupted เทียบ stop/resume และ failure injection รอบ predict/evaluate/decision/update/commit ให้ผลเท่ากันยกเว้น run metadata; ตรวจไม่มี update หรือ event ซ้ำ
- **ขึ้นกับ:** 3 | **ไฟล์:** `src/ml_replay/`, `tests/test_ml_replay.py`

## Checkpoint A
- [ ] Tests focused ผ่าน, invariant ด้าน maturity/ไม่มี leakage และ output baseline B0–B4 เดิมไม่เปลี่ยนภายใต้ input/config เดียวกัน มีหลักฐาน artifact และ state hashes

## 5. ประเมิน policy
- [ ] สร้าง evaluation/version ใหม่ เปรียบเทียบ policy, fixed initial champion และ B0–B4 บน matched mature keys; รายงาน MAE/RMSE, coverage, alerts/switches และ latency ราย ETF/macro
- [ ] ตรวจผลไม่มี alerts, no promotion, insufficient sample และ forecast invalid; คง H1–H3 แยกจาก exploratory policy และระบุ Test reuse/PIT limitation
- **ตรวจ:** `.venv\Scripts\python.exe -m pytest tests/test_ml_evaluation.py -v`; ตรวจ join/count/metric ด้วย fixture คำนวณมือ และ reconciliation กับ replay event
- **ขึ้นกับ:** 4 | **ไฟล์:** `src/ml_evaluation/`, `tests/test_ml_evaluation.py`, `docs/contract/`

## 6. Export snapshot และตรวจ integrity
- [ ] ส่งออก policy forecast, detector stream, decision/switch events และ metadata/lineage แบบ versioned; อัปเดต manifest/checksums/counts และ prepare snapshot โดยคง snapshot เก่า
- [ ] ตรวจ validation ปฏิเสธ event ปลอม, hash/ID/version ไม่ตรง, duplicate และความสัมพันธ์วันที่/โมเดลผิด รวมทั้งรองรับ alert count ไม่เป็นศูนย์
- **ตรวจ:** `.venv\Scripts\python.exe -m pytest tests/test_ml_results_handoff_export.py -v` และรัน `scripts/web/prepare_snapshot.py` ตาม contract ใหม่
- **ขึ้นกับ:** 5 | **ไฟล์:** `scripts/export_ml_results_handoff.py`, `scripts/web/prepare_snapshot.py`, `web/snapshot.policy.json`, tests

## 7. แสดงผลในเว็บ
- [ ] แสดง champion ราย ETF ณ วันเลือก, วัน alert/วันที่ forecast มีผล, สถานะและเหตุผล retained/promoted/ข้อมูลไม่พอ, คะแนนเปรียบเทียบ/จำนวนคู่ และ timeline ของ model version
- [ ] แยก ADWIN served error จาก B3 monitor เดิมและ Feature Drift; แสดง empty/no-alert, pending และ error ของ snapshot โดยไม่สร้างเหตุการณ์สมมติ พร้อมระบุ simulated historical replay
- **ตรวจ:** `cd web; npm test; npm run build; npm run preview` และตรวจ flow เปลี่ยน ETF/วันที่, alert ที่ไม่ switch, promotion และไม่มี alert ด้วย fixture/snapshot ที่ตรวจสอบได้
- **ขึ้นกับ:** 6 | **ไฟล์:** `web/src/data/`, `web/src/` views, `web/tests/`

## 8. รันจริงและตรวจ end-to-end
- [ ] ใช้ source/config/revision ที่ตรึง รัน Training → Replay → Evaluation → Export → snapshot ใหม่; บันทึก commands, hashes, IDs, counts, cutoff และผลเปรียบเทียบโดยไม่ทับ baseline
- [ ] ตรวจ forecast → mature error → alert → decision → effective champion ถึงเว็บ รวมทั้ง no-alert case; หาก dataset จริงไม่มี alert ใช้ fixture พิสูจน์ flow และระบุว่าไม่ได้พบเหตุการณ์จริง ห้ามแต่ง alert
- **ตรวจ:** focused Python tests ข้างต้น, web tests/build และ browser preview; สรุป PASS/FAIL/BLOCKED พร้อมหลักฐานและข้อจำกัด simulated historical replay
- **ขึ้นกับ:** 7 | **ไฟล์:** `docs/ml-results/`, artifacts ของ run ใหม่



## แนวทางลงมือสำหรับ AI: ยึดโครงสร้างเดิม

### กติกาทั่วไป
- เริ่มด้วย `git status --short --branch` อ่านไฟล์จริงและ contract/tests ที่เกี่ยวข้องก่อนแก้ ห้ามทับงานผู้ใช้หรือสร้าง branch ใหม่ งานนี้อยู่บน `feature/drift-champion-challenger`
- ทำตามลำดับ task ใน `tasks/todo.md` ทีละขั้น ตั้งเป้าให้แต่ละขั้นรันได้ บันทึกไฟล์ที่แก้ คำสั่ง ผลจริง run ID และ PASS/FAIL/BLOCKED ใต้ task ห้ามติ๊กผ่านจากการอ่านโค้ดหรือการเดาผล หากพบ contract ขัดกันให้บันทึกและแก้ตามขอบเขตที่พิสูจน์ได้ ไม่เปลี่ยนนิยามผลเดิมแบบเงียบ ๆ
- ค้น `rg` หา implementation/utility เดิมก่อนเพิ่มของใหม่ รักษา public API และ style ที่มีอยู่ ห้ามเขียน pipeline, label maturity, ปฏิทิน, scaler, prediction validation, persistence หรือ CSV parser ซ้ำ หาก reuse ไม่ตรง contract ให้ปรับเฉพาะจุดที่เหมาะสมและทดสอบ caller เดิม
- เพิ่มฟังก์ชันเมื่อมีหน้าที่ชัดเจน มีการใช้ซ้ำ หรือทำให้ logic สำคัญทดสอบแยกได้ ห้ามแตก helper บรรทัดเดียวเพียงเพื่อย้ายโค้ด ห้ามสร้าง factory, class, service, registry หรือ generic framework เผื่ออนาคต ใช้ชื่อ domain ชัดเจน ข้อมูล state ที่สัมพันธ์กันเก็บแบบที่โครงการใช้อยู่ หลีกเลี่ยง mutable global
- แก้ไฟล์เท่าที่จำเป็น หลีกเลี่ยง refactor, rename และ format ทั่ว repo; ห้ามลบ benchmark, tests หรือ bypass validation เพื่อให้ผ่าน ห้ามเพิ่ม dependency ถ้าไลบรารีเดิมเพียงพอ และห้าม hardcode run ID, event, alert count หรือผลลัพธ์

### แผนที่โค้ดและความรับผิดชอบ
1. **Config และสัญญา:** ใช้ `config/ml_training.yaml` / `src/ml_training/config.py` สำหรับ initial selection และ `config/ml_replay.yaml` / `src/ml_replay/config.py` สำหรับ replay policy พร้อม `from_yaml`, `__post_init__`, `as_dict` และ fingerprint ตามรูปแบบเดิม ใส่ candidate order, window, minimum pairs, improvement, cooldown, detector และ policy version ใน config ที่เป็นเจ้าของจริง ไม่กระจาย magic numbers ใน pipeline/test/UI ค่าเริ่มต้น 60/30/5%/20 เป็น proposal ตรึงก่อน Test และบันทึก effective config ข้อสำคัญ `ReplayConfig` เดิมล็อก `monitor_only` และ `processing_order`: คง contract เดิมไว้โดยใช้ version/โหมดใหม่ที่แยกชัด หรือเลือกแนวทาง versioned ที่เข้ากันได้หลังตรวจ callers/tests; ห้ามเพียงปลด validation เดิม อย่าปรับ `config/models.yaml` ถ้าไม่ได้เปลี่ยนนิยาม B0–B4 ตรวจ `docs/contract/` และเพิ่ม contract ของ policy โดยไม่เปลี่ยนความหมาย benchmark เดิม
2. **Training:** ขยาย `src/ml_training/pipeline.py` และ artifact/manifest ที่มีอยู่สำหรับ Validation B0/B1/B2 และ initial champion โดยใช้ split, sample selector และ model prediction เดิม ตรวจว่า candidate scoring ใช้เฉพาะ labels ที่พร้อมจริงก่อน Test ไม่เอา Test มาเลือก hyperparameters/Champion อัปเดต `src/ml_training/README.md` และ tests ที่เกี่ยวข้อง รักษา objective การเลือก SGD เดิม อย่าสร้าง training pipeline ซ้อน
3. **Replay:** ต่อ `src/ml_replay/pipeline.py` ที่ runtime, daily loop, output schemas และ checkpoint เดิม สร้าง policy state แยกจาก benchmark และแยก B3 shadow จาก frozen champion snapshot ใช้ maturity/update ledger และ predict-before-update เดิม ADWIN เดิมของ B3 คง monitor-only; detector ใหม่ติดตาม error ของ served policy แยกกัน โดยใช้ความสามารถ River ที่มีอยู่ ไม่เขียน detector ใหม่ จัดลำดับ event ให้ชัดใน config/manifest; event decision หลัง forecast มีผล session ถัดไป
4. **Storage:** ใช้ `src/ml_replay/storage.py` และ atomic daily checkpoint เดิม เพิ่ม state และ outputs ที่จำเป็นลง manifest/checksums/version/fingerprint พร้อมตรวจ resume, incompatible และ ledger dedup ห้ามสร้าง persistence layer คู่ขนานหรือทับ committed run เก่า
5. **Evaluation:** ต่อ `src/ml_evaluation/pipeline.py`, `metrics.py` และ config ของ Stage 06 ตามหน้าที่ที่มีอยู่ ใช้ join/metric helpers เดิมเมื่อ semantics ตรง บันทึก policy comparison ใน output แยก/versioned รักษา H1–H3 และ baseline แสดงจำนวนคู่/coverage ต่อ ETF และ macro อย่าใช้ข้อมูล Test มาจูน policy
6. **Export และเว็บ:** ต่อ `scripts/export_ml_results_handoff.py`, `scripts/web/prepare_snapshot.py`, `web/snapshot.policy.json`, `web/src/data/schemas.ts`, `loadSnapshot.ts`, และ view ที่มีอยู่ตามข้อมูลจริง รักษาการตรวจ identity, headers, checksum และ row relations ของ snapshot เดิม เพิ่ม sidecar/schema ที่ตรวจได้เมื่อจำเป็น ตรวจจุดที่ hardcode ไม่มี alert ใน `loadSnapshot.ts` โดยเปลี่ยนให้ตรวจ count ตาม manifest แทน ห้ามเพียงลบ guard; แยก Feature Drift, B3 monitor และ policy ADWIN ให้ชัด UI แสดง snapshot/replay ไม่อ้างว่าทำนายสด
7. **Tests:** เริ่มจาก test files เดิม `tests/test_ml_training.py`, `test_ml_replay.py`, `test_ml_contract_config.py`, `test_ml_evaluation.py`, `test_ml_results_handoff_export.py` และ `web/tests/` ใช้ fixture เดิมเท่าที่เหมาะ เพิ่มเฉพาะ test ของพฤติกรรม observable/no leakage, decision, mismatch, resume และ UI states ไม่ยืนยัน private helper หรือเขียน test ที่ลอก implementation อัปเดต README/contract ควบคู่กับ behavior

### รายละเอียดที่ต้องตัดสินด้วยหลักฐานก่อนเขียน
- initial selection ใช้ Validation forecasts และ label availability ที่พิสูจน์ได้ ณ cutover ตรวจว่าช่วง Validation ล่าสุดมี label ไม่ mature กี่แถว กำหนด expected eligible panel ก่อนคำนวณ coverage และ fail อย่างชัดเจนหากไม่ครบ ห้ามคัดแถวที่ valid แล้วเรียก coverage 100% โดยไม่รายงาน denominator
- paired comparison ต้อง join forecast ของ champion version ที่ active ณ วันทำนายกับ B3 shadow forecast ที่สร้างในวันเดียวกัน และใช้ label ที่ mature ณ decision date เท่านั้น; ระบุจำนวน expected, valid, missing และ windows นอกจากนี้ historical shadow forecasts มาจาก B3 หลาย state จึงเป็นหลักฐานของ **shadow process** ไม่ใช่การพิสูจน์ performance ของ snapshot ล่าสุดโดยตรง บันทึก state hash ของ snapshot ที่ promote และอธิบายข้อจำกัดนี้ในรายงาน/UI
- ตรึง handling กรณี champion MAE เป็นศูนย์, invalid/zero denominator, duplicate, หลาย alerts วันเดียว, cooldown และ labels ของ champion เก่าที่มา mature หลัง switch ก่อน implement; ไม่ feed error ของ champion เก่าเข้า detector รุ่นใหม่หรือทำ promotion จากคู่ข้ามรุ่น นับและบันทึกเหตุการณ์ที่ข้ามพร้อมเหตุผล
- ระบุ policy identity/config/hash ในทุก output ที่จำเป็น และทดสอบว่า baseline mode ให้ผลเทียบเดิมได้ภายใต้ข้อมูล/config เดียวกัน รวมทั้ง no alert ไม่เท่ากับ no drift
- รันจริงจาก data/config ที่พร้อม ถ้าข้อมูลจริงไม่มี alert ให้ใช้ fixture ที่ตรวจสอบได้สำหรับ flow alert/promotion และรายงานแยกจากผลจริง ถ้าขาดข้อมูลหรือคำสั่งไม่ผ่านให้ BLOCKED พร้อมสิ่งที่ขาด ไม่แก้ source pins เพื่อปกปิดปัญหา

## Prompt — ทำฟีเจอร์ Drift-triggered Champion–Challenger

คัดลอก prompt นี้เพื่อให้ AI ทำงานทั้งแผนต่อเนื่อง โดยไม่ข้าม gate:

```text
ทำฟีเจอร์ Drift-triggered Champion–Challenger ให้เสร็จตาม tasks/plan.md และส่วน Task: Drift-triggered Champion–Challenger ใน tasks/todo.md บน branch ปัจจุบัน อย่าสร้าง branch ใหม่ เริ่มด้วยตรวจ git status และอ่าน AGENTS.md, config, contract, source และ tests ที่เกี่ยวข้อง รักษางานที่มีอยู่

ทำ task 1–8 ตามลำดับ dependency ตรวจและบันทึก PASS/FAIL/BLOCKED พร้อมคำสั่ง ผลจริง และ artifact/run IDs ลง tasks/todo.md หลังแต่ละ task ห้ามติ๊กผ่านหากยังไม่มีหลักฐาน ทำงานต่อเนื่องและแก้ปัญหาที่แก้เองได้ หากติดสิ่งที่ต้องใช้ข้อมูลหรือสิทธิ์จากฉันจริง ๆ ให้ระบุสิ่งที่ขาดและผลที่ทำได้แล้ว

ยึดกติกา 'แนวทางลงมือสำหรับ AI: ยึดโครงสร้างเดิม' ใน tasks/plan.md: ใช้ pipeline, config loader/validation, maturity/ledger, checkpoint/storage, export, snapshot parser และ test patterns เดิม แยก policy version ใหม่จาก contract และ benchmark เดิม ห้ามปลด validation, hardcode alert/ผล, สร้าง framework หรือแตกฟังก์ชันพร่ำเพรื่อ ใส่ค่าที่ปรับได้ใน config และบันทึก effective config/fingerprint ตรวจ no leakage, delayed labels, pair coverage, no alert, retained, promotion, state identity และ resume ให้ครบ

เว็บปัจจุบันเป็น historical replay snapshot ให้แสดงหลักฐานจริงโดยไม่อ้าง live inference หรือสร้าง alert จำลองในผลจริง ถ้าข้อมูลจริงไม่มี alert ใช้ fixture ทดสอบแยกและระบุระดับหลักฐาน รักษา H1–H3 และ B0–B4 baseline เดิม รัน focused tests หลังแต่ละขั้นและ build/test/browser check เมื่อเชื่อมเว็บแล้ว สรุปสิ่งที่เปลี่ยน วิธีตรวจ ผลจริง และข้อจำกัดเมื่อจบ ห้ามอ้าง PASS หากไม่ได้ตรวจจริง
```

