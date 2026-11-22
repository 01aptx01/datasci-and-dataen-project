import type { SnapshotState } from "./data/loadSnapshot.js";
import { renderMonitoringFeatureDrift, type FeatureDriftViewSelection } from "./featureDriftView.js";
import type { FeatureDriftState } from "./data/featureDrift.js";
import type { PolicySnapshotState } from "./data/policySnapshot.js";
import { renderPolicyMonitoringPanel } from "./policyView.js";
import { modelId } from "./data/schemas.js";

type ReadySnapshot = Extract<SnapshotState, { status: "ready" }>;
type OtherPage = "overview" | "models" | "monitoring" | "evidence";
const esc = (value: string) => value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char] ?? char);
const number = (value: number) => value !== 0 && Math.abs(value) < 0.0001 ? value.toExponential(2) : value.toLocaleString("en-US", { maximumFractionDigits: 4 });
const percent = (value: number) => (value * 100).toFixed(2);

function models(snapshot: ReadySnapshot): string {
  const rows = snapshot.modelMetrics.filter((row) => row.ticker === "MACRO");
  const best = [...rows].sort((a, b) => a.mae - b.mae)[0];
  const max = Math.max(...rows.map((row) => row.mae), 0.001);
  const bars = rows.map((row) => `<div class="st-compare-row"><div><strong>${modelId(row.modelName)}</strong><span>${esc(row.modelName.replaceAll("_", " "))}</span></div><div class="st-compare-track"><i style="width:${row.mae / max * 100}%"></i></div><strong>${percent(row.mae)} pp</strong></div>`).join("");
  const b4Macro = (snapshot.b4Comparisons ?? []).filter((row) => row.ticker === "MACRO");
  const b4Section = b4Macro.length ? `<section class="st-card"><div class="st-secondary-card-title"><div><h2>การเปรียบเทียบ B4 · HAR-X (OLS) แบบ Retrospective</h2><p>จับคู่วัน/สินทรัพย์บน Test (DeltaMAE = คู่เทียบ − B4 · ค่าบวกแปลว่า B4 error ต่ำกว่า · แยกจากสมมติฐาน H2/H3)</p></div></div><div class="st-table-wrap"><table class="st-table"><thead><tr><th>คู่เทียบ</th><th>Paired N</th><th>Coverage</th><th>B4 MAE (pp)</th><th>Comparator MAE (pp)</th><th>DeltaMAE (pp)</th><th>Rel. Impr.</th></tr></thead><tbody>${b4Macro.map((row) => `<tr><td><strong>${esc(row.comparisonId)}</strong> (B4 vs ${modelId(row.comparatorModel)})</td><td>${row.pairedN.toLocaleString()}</td><td>${(row.pairedCoverage * 100).toFixed(2)}%</td><td>${percent(row.b4Mae)}</td><td>${percent(row.comparatorMae)}</td><td>${row.deltaMaeComparatorMinusB4 >= 0 ? "+" : ""}${percent(row.deltaMaeComparatorMinusB4)}</td><td>${row.relativeImprovementPct >= 0 ? "+" : ""}${row.relativeImprovementPct.toFixed(2)}%</td></tr>`).join("")}</tbody></table></div></section>` : "";
  return `<div class="st-secondary-page"><section class="st-card st-secondary-head"><div><h1>${best ? `${modelId(best.modelName)} มี Macro MAE ต่ำสุดใน Test ชุดนี้` : "เปรียบเทียบโมเดล"}</h1><p>ผลจาก common panel · หน่วยจุดเปอร์เซ็นต์ · ยิ่งต่ำยิ่งดี</p></div><span class="st-secondary-badge">Official Test · ${best?.pairedN.toLocaleString() ?? "—"} คู่</span></section><section class="st-card st-compare"><div class="st-secondary-card-title"><div><h2>เปรียบเทียบค่าความคลาดเคลื่อน (Macro MAE)</h2><p>เฉลี่ยแต่ละ ETF ด้วยน้ำหนักเท่ากัน</p></div><a href="#/evidence">ดูผล H2/H3 →</a></div>${bars}</section>${b4Section}<div class="st-secondary-pair"><details class="st-card"><summary>ดูผลแยกตามสินทรัพย์และโมเดล</summary><div class="st-table-wrap"><table class="st-table"><thead><tr><th>สินทรัพย์</th><th>โมเดล</th><th>MAE (pp)</th><th>RMSE (pp)</th><th>จำนวนคู่</th></tr></thead><tbody>${snapshot.modelMetrics.map((row) => `<tr><td>${row.ticker}</td><td>${modelId(row.modelName)}</td><td>${percent(row.mae)}</td><td>${percent(row.rmse)}</td><td>${row.pairedN.toLocaleString()}</td></tr>`).join("")}</tbody></table></div></details><details class="st-card"><summary>ช่วงข้อมูลและ Coverage</summary><p>ผลนี้ใช้คะแนน Test ที่บันทึกไว้ ไม่เปลี่ยนผลทดสอบสมมติฐาน</p><p>แสดงคะแนน Test จาก snapshot ที่ตรวจสอบแล้ว</p></details></div></div>`;
}

function monitoringRollingMae20(snapshot: ReadySnapshot, selection: FeatureDriftViewSelection): string {
  const series = snapshot.rollingMae20.filter((row) => row.split === "test" && row.modelName === selection.model && row.ticker === selection.ticker).sort((a, b) => a.windowEnd.localeCompare(b.windowEnd));
  const max = Math.max(...series.map((row) => row.mae), 0.001) * 1.1;
  const points = series.map((row, i) => `${(48 + i * 892 / Math.max(series.length - 1, 1)).toFixed(1)},${(130 - row.mae / max * 110).toFixed(1)}`).join(" ");
  const query = new URLSearchParams({ date: selection.date, ticker: selection.ticker, model: selection.model, feature: selection.feature, window: String(selection.windowSize), metric: selection.metric, tab: selection.tab });
  const chart = series.length
    ? `<svg viewBox="0 0 960 165" role="img" aria-label="Rolling MAE20 ของ ${selection.ticker} จาก Test"><path d="M48 20H940 M48 75H940 M48 130H940" stroke="#e2e8f0"/><polyline points="${points}" fill="none" stroke="#2456c6" stroke-width="2.5"/><text x="48" y="155">${esc(series[0]!.windowEnd)}</text><text x="940" y="155" text-anchor="end">${esc(series[series.length - 1]!.windowEnd)}</text></svg>`
    : "<p>ไม่มีข้อมูลกราฟสำหรับตัวเลือกนี้</p>";
  return `<section class="st-card st-monitor-chart"><div class="st-secondary-card-title"><div><h2>Rolling MAE20 · ${selection.ticker} · ${modelId(selection.model)}</h2><p>ความคลาดเคลื่อนบน Test · หน้าต่าง 20 วันซื้อขาย · ${series.length.toLocaleString()} ช่วงที่บันทึกไว้</p></div><a href="#/replay?${esc(query.toString())}">เปิด Replay →</a></div>${chart}<p class="st-muted">กราฟแสดง MAE ที่คำนวณจาก label ซึ่งครบกำหนดแล้ว · เป็นตัวชี้วัด error ตามโมเดลและวันที่ที่เลือก</p></section>`;
}

function monitoring(
  snapshot: ReadySnapshot,
  drift: FeatureDriftState,
  selection: FeatureDriftViewSelection,
  policyState: PolicySnapshotState,
): string {
  const policyPanel = renderPolicyMonitoringPanel(policyState, { ticker: selection.ticker, date: selection.date });
  const policySummaryCard = policyState.status === "ready"
    ? (() => {
        const ops = policyState.operationsSummary.find((row) => row.ticker === selection.ticker);
        const initChamp = policyState.manifest.initialChampion[selection.ticker];
        return `<section class="st-card"><strong>Champion–Challenger Policy · ${selection.ticker}</strong><span>${ops ? `${ops.promotionCount} switches · ${ops.alertCount} alerts` : "พร้อมใช้งาน"}</span><p>Initial ${esc(initChamp)} → Final ${esc(ops?.finalChampionModelId ?? initChamp)} (${esc(ops?.finalChampionVersionId ?? "v001")}) · Exploratory v${esc(policyState.manifest.policyVersion)} (Simulated Replay)</p></section>`;
      })()
    : `<section class="st-card"><strong>Champion–Challenger Policy</strong><span>${policyState.status === "loading" ? "กำลังโหลด" : policyState.status === "error" ? "ตรวจไม่ผ่าน" : "ยังไม่มี sidecar"}</span><p>${policyState.status === "loading" ? "กำลังตรวจสอบ policy snapshot" : esc(policyState.message)}</p></section>`;
  return `<div class="st-secondary-page"><section class="st-card st-secondary-head"><div><h1>ติดตามข้อมูลและ Champion–Challenger Policy</h1><p>ตรวจ Feature Drift (W1/PSI), ความคลาดเคลื่อน Rolling MAE20 และสัญญาณ ADWIN ของ Champion ที่เสิร์ฟจริง</p></div><span class="st-secondary-badge">Test · ${esc(snapshot.manifest.strictCutoff)}</span></section>${renderMonitoringFeatureDrift(drift, selection, policyPanel)}${monitoringRollingMae20(snapshot, selection)}<div class="st-secondary-pair">${policySummaryCard}<section class="st-card"><strong>สถานะ B4 · HAR-X (OLS)</strong><span>Static (Frozen)</span><p>B4 คงที่หลัง Train ไม่มีการอัปเดตออนไลน์หรือ ADWIN drift stream</p></section></div><p class="st-muted">Simulated Historical Replay · Feature Drift และ Champion–Challenger Policy เป็นข้อมูลย้อนหลังจาก snapshot และแยกจากผลทดสอบสมมติฐาน H1–H3 · ยังไม่ยืนยันความพร้อมของข้อมูล ณ เวลาจริง</p></div>`;
}
function evidence(snapshot: ReadySnapshot): string {
  const rows = snapshot.hypothesisResults.map((row) => `<tr><td><strong>${row.hypothesisId}</strong></td><td>${row.datasetSplit} · ${row.tickerOrMacro}</td><td>${number(row.effectSize)}</td><td>[${number(row.confidenceInterval95[0])}, ${number(row.confidenceInterval95[1])}]</td><td>${number(row.adjustedPValue)}</td><td>${row.nPaired.toLocaleString()}</td><td>${esc(row.decision)}</td></tr>`).join("");
  return `<div class="st-secondary-page"><div class="st-secondary-title"><h1>หลักฐานและข้อมูล</h1><span>ผลการทดลอง · ที่มาข้อมูล · วิธีอ่านผล</span></div><section class="st-card"><h2>ผลการทดลอง (Hypothesis Tests)</h2><p>แยก Train (H1) ออกจาก Test (H2/H3) อย่างชัดเจน</p><div class="st-table-wrap"><table class="st-table"><thead><tr><th>สมมติฐาน</th><th>ชุดข้อมูล</th><th>Effect Size</th><th>95% CI</th><th>Adjusted p-value</th><th>Paired N</th><th>ผล</th></tr></thead><tbody>${rows}</tbody></table></div></section><section class="st-card"><h2>ที่มาข้อมูล (Data Lineage)</h2><p>ข้อมูลตลาด → ตรวจคุณภาพ → สร้าง features และ labels → Replay → Evaluation → Dashboard · cutoff ${esc(snapshot.manifest.strictCutoff)}</p><div class="st-secondary-triple"><div class="st-lineage-status"><span>สถานะตรวจไฟล์</span><strong>ตรวจสอบ schema และ checksum แล้ว</strong></div><div class="st-lineage-status"><span>สถานะ Evaluation</span><strong>Simulated Historical Replay</strong></div><div class="st-lineage-status"><span>สถานะรายงาน</span><strong>รออนุมัติ</strong></div></div><p>Evaluation ID <code>${esc(snapshot.manifest.evaluationId)}</code></p><p>Replay ID <code>${esc(snapshot.manifest.replayId)}</code></p><p>ยังไม่ได้ยืนยันความพร้อมของข้อมูลต้นทาง ณ เวลาจริง</p></section><section class="st-card"><h2>วิธีอ่านผล</h2><p>RV5 คือความผันผวนของ 5 วันซื้อขายถัดไป · Actual เปิดเมื่อ target ครบและมีผลประเมินจากต้นทาง</p></section></div>`;
}

export function renderOtherPage(
  snapshot: ReadySnapshot,
  page: OtherPage,
  featureDrift?: FeatureDriftState,
  driftSelection?: FeatureDriftViewSelection,
  policyState?: PolicySnapshotState,
): string {
  if (page === "models") return models(snapshot);
  if (page === "monitoring") return monitoring(
    snapshot,
    featureDrift ?? { status: "missing", message: "ยังไม่มี sidecar ของ Feature Drift" },
    driftSelection ?? { ticker: "SPY", date: "", feature: "ret_1d_t", windowSize: 60, metric: "wasserstein_normalized", tab: "feature", model: "ONLINE_SGD" },
    policyState ?? { status: "missing", message: "ยังไม่มี sidecar ของ Champion–Challenger Policy" },
  );
  if (page === "evidence") return evidence(snapshot);
  return `<div class="st-secondary-page"><section class="st-card st-secondary-head"><div><h1>Adaptive Portfolio Risk Lab</h1><p>สำรวจความผันผวนและความเสี่ยงพอร์ตจากข้อมูล Stage 06</p></div><span class="st-secondary-badge">ข้อมูลถึง ${esc(snapshot.manifest.strictCutoff)}</span></section><section class="st-card"><h2>เริ่มสำรวจพอร์ต</h2><p>ปรับน้ำหนักเพื่อคำนวณความเสี่ยงจาก covariance ที่บันทึกไว้ หรือเล่นย้อนหลังเพื่อเปรียบเทียบ Forecast และ Actual</p><a href="#/portfolio">พยากรณ์พอร์ต →</a>　<a href="#/replay">เล่นย้อนหลัง →</a></section>${models(snapshot)}</div>`;
}
