# DEDS Final Dashboard UX Acceptance Report

- **วันที่:** 2026-11-22 (Asia/Bangkok)
- **สาขา:** feat/dashboard-final-ux-acceptance
- **ฐาน D9:** e5b637c · **baseline audit:** b07637b · **UX implementation:** a654663
- **ผลการยอมรับ:** **NOT VERIFIED — ยังไม่ควร sign off**

## คำตัดสิน

UI และ regression checks ผ่านสำหรับเส้นทางที่ทดสอบจริง แต่หลักฐานยังไม่ครบตามเกณฑ์ P0 ของแผน จึงยังสรุปว่า Final UX Acceptance ผ่านไม่ได้ โดยเฉพาะ Replay ต่อเนื่อง 5 วันบน desktop, playback ที่ขอบเขตวัน และ layout ที่ browser zoom 200% ซึ่ง tab browser ที่ใช้ไม่ยอมเปลี่ยน zoom จริง การทดสอบ Scenario B ซ้ำสามครั้งก็ยังไม่ครบตาม UAT-06

ไม่พบ P0 blocker ใน flow ที่ได้ลอง แต่ยังมีเกณฑ์สำคัญที่ไม่มีผลทดสอบ จึงคงผลรวมเป็น **NOT VERIFIED** แทนการขยายข้อสรุปจาก test หรือการตรวจ CSS

## ขอบเขตและ implementation

คงไว้ 8 routes และใช้ frozen Stage 06 snapshot เดิม งานนี้ปรับเฉพาะ frontend, UI tests, README และเอกสารแนะนำผู้ใช้

- **Replay:** จัดปุ่มวันก่อน/ถัดไปไว้ติดกับวันที่และ context, เพิ่มกราฟ Forecast กับ Actual ที่เปิดเผยเมื่อมีสิทธิ์, marker วันที่เลือก, ตารางข้อมูลและ B0–B3 comparison; shared selection แสดง split, ticker, model และ As-of/Retrospective
- **Scenario Lab:** วาง editor, selected-day risk/delta และ budget ไว้ใน workbench เดียวกับ timeline; เพิ่มคำเตือนเมื่อน้ำหนักไม่ครบ 100% และ focus fallback หลัง render
- **การอ่านและ responsive:** ปรับ role tokens เป็น 12/13/14/15px และเพิ่มขนาด controls สำคัญเป็น 44–48px ในจุดหลัก
- **Provenance / Research / Drift:** เปิด source hashes เป็น disclosure, คัดลอก hash ได้, จัดผล H2/H3 และ Drift inspector ไว้กับ selection context
- **เอกสาร:** ปรับ README เป็น D1–D9 และปรับ D8 demo script ให้ตรงกับ Scenario Lab และ Replay UI ปัจจุบัน

การแก้ UI ไม่ได้เปลี่ยน Stage 01–06, model, source CSVs, official statistical outputs, snapshot IDs หรือ portfolio calculation contract

## Git และ snapshot

สาขา feat/dashboard-final-ux-acceptance แยกจาก D9 local HEAD e5b637c; ไม่มี upstream กำหนดไว้ สาขานี้มี baseline audit commit b07637b และ UX implementation commit a654663 ก่อน documentation commit งานทั้งหมดคงอยู่ local เท่านั้น ไม่มี push, merge, PR, release หรือ deploy

Pinned snapshot ตรวจผ่าน:

- Evaluation ID: 82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2
- Replay ID: 3cbf81eb9242d8894d2f67f39065a17ff1ef55a2e098773aead915949ab11b12
- ZIP SHA-256: 20dff91705ffbb60ab579f5c1f907537015ec2f52be001d5dfd24ea8978ae3f5
- Pending rows: 60

## Automated verification

รันจาก web หลังแก้ source ล่าสุด:

- **npm test** — 62/62 ผ่าน, รวม snapshot integrity, typecheck, compile, source contract, portfolio parity, Pending/as-of, selection round-trip และ UI rendering tests
- **npm run build** — ผ่าน; ใช้ Evaluation/Replay IDs และ ZIP SHA-256 เดิม
- **git diff --check** — ผ่าน; Git แสดงเพียงคำเตือน LF/CRLF สำหรับบางไฟล์บน Windows
- รายการ source ที่เปลี่ยนจำกัดอยู่ที่ web/; ไม่พบการแก้ Stage 01–06 หรือ frozen source artifacts

## Browser evidence

ใช้ local built preview ที่ http://127.0.0.1:4173/ ผ่าน in-app Chromium browser

| ขนาดที่ตรวจ | หลักฐาน |
|---|---|
| Desktop 1280×720 ที่ 100% | เปิดครบ 8 routes; headings และ selection context แสดง, ไม่พบ error state, page horizontal overflow หรือ console error/warn |
| Mobile 360×800 | Replay ไม่มี page overflow; top bar 58px และ bottom nav 67px; ปุ่มวันถัดไปทำงานขณะ sticky และ scrollY ไม่เปลี่ยน |
| Mobile 390×844 | ตรวจ Overview, Forecasts, Portfolio, Drift, Research, Provenance และ Guide; ทุกหน้าที่ตรวจมี scrollWidth = clientWidth |
| Mobile 430×932 | ตรวจ 7 routes เดียวกัน; ไม่พบ page-level horizontal overflow |
| Copy source | Provenance คัดลอก SHA-256 ของ evaluation.csv ได้ตรงกับค่าที่แสดง |
| Keyboard | ArrowRight เปลี่ยน Replay 2025-10-03 → 2025-10-06 และ URL ตาม; Tab ไป Portfolio CTA, Enter เปิด Portfolio โดยคง date/model/IDs; Scenario A keyboard edits คง focus |

ความกว้าง content ที่สังเกตได้บน mobile คือ 345/375/415px ตามลำดับ เพราะ browser scrollbar; ค่า viewport ที่ตั้งคือ 360/390/430px และไม่มี overflow เพิ่มจากหน้าเว็บ

**200% zoom ยังไม่ยืนยัน:** ทดลอง Control+Plus และ Control+Equal แล้วค่า devicePixelRatio=1 และ innerWidth=1280 คงเดิม จึงไม่ถือว่าเป็นการทดสอบที่ zoom 200%
**ภาพหน้าจอ:** ไม่มี screenshot ถูกบันทึกไว้ใน repository; browser control แสดงภาพสำหรับตรวจใน session แต่ไม่มี local file path ให้เก็บเป็น artifact ในรอบนี้

## ผล UAT 12 งาน

| UAT | ผล | หลักฐาน / ข้อจำกัด |
|---|---|---|
| UAT-01 | PASS | Overview card 01 · FORECAST เปิด Forecasts และคง shared selection |
| UAT-02 | PARTIAL | ArrowRight เปลี่ยนวันที่/URL หนึ่งครั้งและ mobile step คง scroll; ยังไม่ได้บันทึกชุด 5 วันบน desktop |
| UAT-03 | PASS | วันที่ยังไม่ครบ target ซ่อน Actual/Error; วันที่ครบเผย evaluation row; Pending ปลายช่วงยังไม่มี Actual/Error |
| UAT-04 | PASS | ตาราง 2025-10-03 แสดง 4 โมเดลและ source status ของวัน/สินทรัพย์เดียวกัน |
| UAT-05 | PASS | Enter บน CTA เปิด Portfolio ด้วย date, model และ pinned IDs เดิม |
| UAT-06 | PARTIAL | ทดสอบ A จาก 50/30/20 → invalid 60/30/20 → valid 60/20/20; ยังไม่ได้ทำรอบแก้ B ครบสามครั้งหรือจับเวลา scroll |
| UAT-07 | PASS | ตั้ง 8% แล้วล้าง; ค่าเริ่มต้นกลับเป็น “ยังไม่ได้ตั้ง” และไม่มี budget สมมติ |
| UAT-08 | PASS | เลือก 2025-10-03; URL, context และ inspector ใช้ SPY/B3/วันเดียวกัน; ไม่มี recorded alert |
| UAT-09 | PASS | effect, paired N, adjusted p และ scope อยู่ใน hypothesis cards เดียวกัน |
| UAT-10 | PASS | คัดลอก evaluation.csv SHA-256 แล้ว clipboard ตรงกับค่าที่แสดง |
| UAT-11 | PASS | ArrowRight, Tab และ Enter ทำงาน; Scenario A invalid/valid edit รักษา focus และอัปเดต URL |
| UAT-12 | PARTIAL | Mobile 360px ผ่าน flow และไม่ overflow; browser shortcut ไม่ได้เปลี่ยน zoom จริง |

UAT นี้เป็นการตรวจโดย operator ผ่าน browser ไม่ใช่การทดสอบกับผู้ใช้ครั้งแรก ผู้เข้าร่วม first-time user: **0 คน**; ไม่มีการอ้างผลว่าเป็น usability study

## ขอบเขตที่ยังไม่ได้ทดสอบ

ไม่ได้ตรวจ tablet 768×1024/1024×768, desktop 1366×768/1440×900/1920×1080, real-device touch, Firefox/Safari/Edge, หรือ NVDA/VoiceOver ผล responsive ที่รายงานจึงจำกัดอยู่ที่ in-app Chromium browser และ viewport ที่ระบุไว้เท่านั้น

## Final Acceptance Criteria

| AC | สถานะ | เหตุผล / หลักฐาน |
|---|---|---|
| 01 | PASS | บันทึก branch, base, commits, tests, snapshot IDs และข้อจำกัด |
| 02 | PASS | role tokens ที่มีความหมายเพิ่มจาก 10–11px; compact metadata แยกจากคำอธิบายหลัก |
| 03 | PARTIAL | viewport 360/390/430 ที่ตรวจไม่ overflow; ปุ่มหลัก 44–48px แต่ไม่ได้วัดทุก hit area |
| 04 | PARTIAL | sticky stepper ทำงานใน mobile flow และ controls/chart ใช้ selected date เดียวกัน; ยังไม่ได้ยืนยัน sightline ระหว่างเลื่อนหน้า desktop |
| 05 | PARTIAL | มี step test จริง แต่ไม่ได้ทดสอบ 5 ครั้งต่อเนื่องบน desktop |
| 06 | PASS | chart/table/inspector ยึดวัน, ticker, model และ view เดียวกัน |
| 07 | NOT VERIFIED | ไม่ได้ทดสอบ playback stop ที่วันแรก/วันสุดท้าย, visibility change และ navigation ครบ |
| 08 | PASS | slider และ Scenario A input เปลี่ยนค่าโดยคง focus; mobile step ไม่เปลี่ยน scrollY |
| 09 | PASS | mobile header/bottom nav และ Replay stepper ไม่ทับกันใน viewport ที่ลอง |
| 10 | PARTIAL | editor, selected-day delta, budget และ timeline อยู่ใน workbench; ยังไม่ได้วัด scroll reversals |
| 11 | PASS | risk ใช้ selected Test date/model; parity regression test ผ่าน |
| 12 | PASS | 50/30/20 parity และ numerical invariants ผ่าน test suite |
| 13 | PASS | invalid weights แสดง error โดยไม่ auto-normalize; source/contract tests ผ่าน |
| 14 | PASS | budget unset ชัดเจนและไม่แสดง count จนผู้ใช้กำหนดค่า |
| 15 | PASS | browser ตรวจ As-of/Retrospective และ Pending โดยไม่เปิด Actual/Error ก่อน eligibility |
| 16 | PASS | official source outputs ไม่ถูกแก้; snapshot/source regression tests ผ่าน |
| 17 | PARTIAL | shared selection ผ่าน navigation และ Back/Forward ที่ตรวจ; refresh/deep-link matrix ยังไม่ครบ |
| 18 | PASS | keyboard Replay → Portfolio และ field editing ผ่าน |
| 19 | PARTIAL | บันทึก desktop 1280×720 และ mobile 360/390/430; target desktop 1366/1440/1920 และ screenshot artifacts ยังไม่มี |
| 20 | PASS | npm test 62/62 และ npm run build ผ่านบน UX code commit |
| 21 | PASS | ไม่มี Stage 01–06, dataset, model หรือ snapshot artifact ในรายการเปลี่ยน |
| 22 | PASS | ไม่มี push, merge, PR, release หรือ deploy |
| 23 | PARTIAL | Models route อยู่ใน desktop route sweep; ไม่มีบันทึกละเอียดทุก chart/filter/metric grouping |
| 24 | PASS | Drift timeline/inspector ผูก selection; inspector รายงานค่าที่บันทึกและ zero alerts |
| 25 | PASS | H2/H3 effect, CI, adjusted p และ N จัดเป็นกลุ่มตามผล |
| 26 | PASS | Provenance disclosure แสดง source hashes และ copy behavior |
| 27 | PASS | Overview card 01 · FORECAST เปิด Forecasts ด้วย selection |
| 28 | PASS | Guide มี task-led Thai-first flow และ glossary |
| 29 | PASS | ไม่มีผู้ทดสอบ 3 คน; ข้อจำกัดและจำนวนผู้เข้าร่วม 0 คนถูกบันทึก |
| 30 | PASS | README และ D8 instructor demo script อธิบาย D1–D9 / Replay / Scenario Lab UI ปัจจุบัน |

## งานที่ยังต้องทำก่อน sign off

1. ทำ UAT-02 ซ้ำ 5 วันติดกันบน desktop โดยตรวจว่าไม่มี scroll-back เพื่อหาปุ่ม
2. ทดสอบ UAT-06 กับ Scenario A และ B ให้ครบสามครั้ง พร้อมบันทึก scroll reversals
3. ทดสอบ playback ที่วันแรก/วันสุดท้าย, tab visibility, navigation และ reduced motion
4. เปิด browser zoom จริงที่ 200% และตรวจ reflow, focus, overlay และข้อความ
5. ถ้าต้องการตามเกณฑ์ผู้ใช้ ให้ชวน first-time users อย่างน้อย 3 คนทำ UAT-02/05/06; อย่านำผลนี้ไปเรียก scientific UX study
6. เก็บ screenshots จริงลง web/evidence/ux-final/ เมื่อสามารถบันทึกไฟล์จาก browser ได้

จนกว่าจะปิดข้อ 1–4 ผลงานนี้เป็น **local review candidate ที่ automated checks และ browser smoke flows ผ่าน** แต่ Final UX Acceptance ยังเป็น **NOT VERIFIED**
