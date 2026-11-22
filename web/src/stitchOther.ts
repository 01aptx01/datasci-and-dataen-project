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

function bestModelSummary(rows: ReadySnapshot["modelMetrics"]): string {
  const best = rows[0];
  if (!best) return `<section class="st-card st-secondary-head"><h1>ยังไม่มีคะแนน Macro MAE</h1></section>`;
  const winners = rows.filter((row) => row.mae === best.mae).map((row) => modelId(row.modelName)).join(" และ ");
  return `<section class="st-card st-secondary-head st-model-winner"><div><span class="st-winner-label">ผลดีที่สุดในชุด Test · Macro MAE ต่ำสุด</span><h1>${esc(winners)} · ${percent(best.mae)} pp</h1><p>เฉลี่ยความคลาดเคลื่อนของแต่ละ ETF ด้วยน้ำหนักเท่ากัน · ยิ่งต่ำยิ่งดี</p></div><span class="st-secondary-badge">ข้อมูลเปรียบเทียบ ${best.pairedN.toLocaleString()} คู่</span></section>`;
}
function comparisonChart(metrics: ReadySnapshot["modelMetrics"], metric: "mae" | "rmse"): string {
  const rows = metrics.filter((row) => row.ticker === "MACRO").sort((a, b) => a[metric] - b[metric]);
  const best = rows[0];
  const max = Math.max(...rows.map((row) => row[metric]), 0.001);
  const bars = rows.map((row, index) => `<div class="st-compare-row${row[metric] === best?.[metric] ? " st-compare-best" : ""}"><div class="st-compare-name"><strong>${modelId(row.modelName)}</strong><span>${esc(row.modelName.replaceAll("_", " "))}<small>${row[metric] === best?.[metric] ? "ต่ำสุด" : `อันดับ ${index + 1}`}</small></span></div><div class="st-compare-track" aria-hidden="true"><i style="width:${row[metric] / max * 100}%"></i></div><strong>${percent(row[metric])} pp</strong></div>`).join("");
  const label = metric.toUpperCase();
  return `<section class="st-card st-compare"><div class="st-secondary-card-title"><div><h2>เปรียบเทียบ Macro ${label}</h2><p>เรียงจากน้อยไปมาก · แท่งสั้นหมายถึงค่าคลาดเคลื่อนต่ำ · หน่วยจุดเปอร์เซ็นต์ (pp)</p><p>${metric === "mae" ? "MAE: ค่าคลาดเคลื่อนสัมบูรณ์เฉลี่ย" : "RMSE: ให้น้ำหนักกับความคลาดเคลื่อนที่มากเป็นพิเศษ"} · เฉลี่ยแต่ละ ETF ด้วยน้ำหนักเท่ากัน</p></div></div>${bars || "<p>ไม่มีข้อมูลเปรียบเทียบ</p>"}</section>`;
}
function models(snapshot: ReadySnapshot): string {
  const rows = snapshot.modelMetrics.filter((row) => row.ticker === "MACRO").sort((a, b) => a.mae - b.mae);
  const testDates = snapshot.sessions.filter((row) => row.split === "test").map((row) => row.predictionDate).sort();
  const coverageRows = snapshot.coverage.filter((row) => row.split === "test");
  const coverageTable = coverageRows.map((row) => `<tr><td>${esc(modelId(row.modelName))}</td><td>${esc(row.ticker)}</td><td>${row.expectedEligiblePredictionAnchors.toLocaleString()}</td><td>${row.forecastSuccessCount.toLocaleString()} (${(row.forecastCoverage * 100).toFixed(1)}%)</td><td>${row.matureEvaluableCount.toLocaleString()} (${(row.evaluationCoverage * 100).toFixed(1)}%)</td><td>${row.pendingLabelCount.toLocaleString()}</td><td>${row.commonPanelCount.toLocaleString()}</td></tr>`).join("");
  return `<div class="st-secondary-page">${bestModelSummary(rows)}${comparisonChart(snapshot.modelMetrics, "mae")}${comparisonChart(snapshot.modelMetrics, "rmse")}<div class="st-model-details"><details class="st-card"><summary>ดูผลแยกตามสินทรัพย์และโมเดล</summary><p>จัดกลุ่มตามโมเดล · MAE และ RMSE ยิ่งต่ำยิ่งดี · MACRO คือค่าเฉลี่ยของสินทรัพย์</p><div class="st-table-wrap"><table class="st-table st-model-metrics"><thead><tr><th>สินทรัพย์</th><th>โมเดล</th><th>MAE (pp)</th><th>RMSE (pp)</th><th>จำนวนคู่</th></tr></thead>${[...new Set(snapshot.modelMetrics.map((row) => row.modelName))].map((model) => `<tbody><tr class="st-model-group"><th colspan="5" scope="colgroup">โมเดล ${modelId(model)}</th></tr>${snapshot.modelMetrics.filter((row) => row.modelName === model).map((row) => `<tr class="${row.ticker === "MACRO" ? "st-model-macro" : ""}"><td>${row.ticker}</td><td>${modelId(row.modelName)}</td><td>${percent(row.mae)}</td><td>${percent(row.rmse)}</td><td>${row.pairedN.toLocaleString()}</td></tr>`).join("")}</tbody>`).join("")}</table></div></details><details class="st-card"><summary>ช่วงข้อมูลและ Coverage</summary><p>วันพยากรณ์ในชุด Test: ${esc(testDates[0] ?? "—")} – ${esc(testDates[testDates.length - 1] ?? "—")} · cutoff ${esc(snapshot.manifest.strictCutoff)}</p><p>Coverage แสดงแยกต่อโมเดลและสินทรัพย์: จำนวนพยากรณ์สำเร็จและประเมินได้เทียบกับจำนวนวันที่เข้าเกณฑ์ ส่วนรอผลคือเป้าหมายที่ยังไม่ครบกำหนด</p><div class="st-table-wrap"><table class="st-table"><thead><tr><th>โมเดล</th><th>สินทรัพย์</th><th>วันที่เข้าเกณฑ์</th><th>พยากรณ์สำเร็จ</th><th>ประเมินได้</th><th>รอผล</th><th>Common panel</th></tr></thead><tbody>${coverageTable || `<tr><td colspan="7">ไม่มีข้อมูล Coverage สำหรับชุด Test</td></tr>`}</tbody></table></div></details></div></div>`;
}

function monitoring(
  snapshot: ReadySnapshot,
  drift: FeatureDriftState,
  selection: FeatureDriftViewSelection,
  policyState: PolicySnapshotState,
): string {
  const policyPanel = renderPolicyMonitoringPanel(policyState, { ticker: selection.ticker, date: selection.date });
  return `<div class="st-secondary-page"><section class="st-card st-secondary-head"><div><h1>ติดตามข้อมูลและ Champion–Challenger Policy</h1><p>ตรวจ Feature Drift (W1/PSI) และสัญญาณ ADWIN ของ Champion ที่เสิร์ฟจริง</p></div><span class="st-secondary-badge">Test · ${esc(snapshot.manifest.strictCutoff)}</span></section>${renderMonitoringFeatureDrift(drift, selection, policyPanel)}</div>`;
}
function evidence(snapshot: ReadySnapshot): string {
  const tableRows = (split: "train" | "test") => snapshot.hypothesisResults.filter((row) => row.datasetSplit.toLowerCase() === split).map((row) => `<tr><td><strong>${row.hypothesisId}</strong></td><td>${row.datasetSplit} · ${row.tickerOrMacro}</td><td>${number(row.effectSize)}</td><td>[${number(row.confidenceInterval95[0])}, ${number(row.confidenceInterval95[1])}]</td><td>${number(row.adjustedPValue)}</td><td>${row.nPaired.toLocaleString()}</td><td>${esc(row.decision)}</td></tr>`).join("");
  return `<div class="st-secondary-page"><div class="st-secondary-title"><h1>หลักฐานและข้อมูล</h1><span>ผลการทดลอง · ที่มาข้อมูล · วิธีอ่านผล</span></div><section class="st-card"><h2>ผลการทดลอง (Hypothesis Tests)</h2><p>แยก Train (H1) ออกจาก Test (H2/H3) อย่างชัดเจน</p>${(["train", "test"] as const).map((split) => `<div class="st-evidence-group"><div class="st-evidence-group-head"><strong>${split === "train" ? "ชุด Train · H1" : "ชุด Test · H2 และ H3"}</strong><span>${split === "train" ? "ผลวิเคราะห์ข้อมูลฝึก" : "ผลประเมินข้อมูลทดสอบ"}</span></div><div class="st-table-wrap"><table class="st-table"><thead><tr><th>สมมติฐาน</th><th>ชุดข้อมูล / สินทรัพย์</th><th>Effect Size</th><th>95% CI</th><th>Adjusted p-value</th><th>จำนวนคู่</th><th>ผล</th></tr></thead><tbody>${tableRows(split) || `<tr><td colspan="7">ไม่มีผลในชุดข้อมูลนี้</td></tr>`}</tbody></table></div></div>`).join("")}</section><section class="st-card st-evidence-lineage"><h2>ที่มาข้อมูล (Data Lineage)</h2><p>ข้อมูลตลาด → ตรวจคุณภาพ → สร้าง features และ labels → Replay → Evaluation → Dashboard · cutoff ${esc(snapshot.manifest.strictCutoff)}</p><div class="st-secondary-triple"><div class="st-lineage-status"><span>สถานะตรวจไฟล์</span><strong>ตรวจสอบ schema และ checksum แล้ว</strong></div><div class="st-lineage-status"><span>สถานะ Evaluation</span><strong>Simulated Historical Replay</strong></div><div class="st-lineage-status"><span>สถานะรายงาน</span><strong>รออนุมัติ</strong></div></div><details class="st-evidence-ids"><summary>รหัสอ้างอิงข้อมูล</summary><p>Evaluation ID <code>${esc(snapshot.manifest.evaluationId)}</code></p><p>Replay ID <code>${esc(snapshot.manifest.replayId)}</code></p></details><p>ยังไม่ได้ยืนยันความพร้อมของข้อมูลต้นทาง ณ เวลาจริง</p></section><section class="st-card"><h2>วิธีอ่านผล</h2><p>Effect Size คือขนาดของผล · 95% CI คือช่วงความเชื่อมั่น · Adjusted p-value คือค่า p ที่ปรับแล้ว · Reject H₀ คือปฏิเสธสมมติฐานศูนย์ตามเกณฑ์ของการทดลอง<br>RV5 คือความผันผวนของ 5 วันซื้อขายถัดไป ส่วนผลจริงจะแสดงเมื่อครบช่วงเป้าหมายและมีผลประเมินจากต้นทาง</p></section></div>`;
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
  return `<div class="st-secondary-page"><section class="st-card st-secondary-head"><div><h1>Future Portfolio Volatility</h1><p>สำรวจความผันผวนและความเสี่ยงพอร์ตจากข้อมูล Stage 06</p></div><span class="st-secondary-badge">ข้อมูลถึง ${esc(snapshot.manifest.strictCutoff)}</span></section><section class="st-card"><h2>เริ่มสำรวจพอร์ต</h2><p>ปรับน้ำหนักเพื่อคำนวณความเสี่ยงจาก covariance ที่บันทึกไว้ หรือเล่นย้อนหลังเพื่อเปรียบเทียบ Forecast และ Actual</p><a href="#/portfolio">พยากรณ์พอร์ต →</a>　<a href="#/replay">เล่นย้อนหลัง →</a></section>${models(snapshot)}</div>`;
}
