import { filterForecastRows, loadSnapshot, selectRecordedSessions, type ForecastFilter, type SnapshotState } from "./data/loadSnapshot.js";
import { modelId, modelLabel, type CoverageRow, type DriftTimelineRow, type ForecastAuditRow, type H1ScatterRow, type ModelMetricRow, type ModelName, type PortfolioRiskRow, type RollingMae20Row, type Ticker } from "./data/schemas.js";
import { computePortfolioVolatility } from "./data/portfolio.js";
import { buildExportMetadata, buildForecastCsv } from "./data/export.js";

interface RouteDefinition {
  path: string;
  label: string;
  thai: string;
  description: string;
  icon: string;
}

const routes: RouteDefinition[] = [
  { path: "/overview", label: "Overview", thai: "ภาพรวม", description: "สถานะและขอบเขตของชุดผลที่ตรวจแล้ว", icon: "overview" },
  { path: "/models", label: "Models", thai: "เปรียบเทียบโมเดล", description: "ผลเปรียบเทียบ B0–B3 จาก snapshot", icon: "models" },
  { path: "/forecasts", label: "Forecasts", thai: "สำรวจ Forecast", description: "อ่านเฉพาะ forecast ที่บันทึกไว้", icon: "forecasts" },
  { path: "/portfolio", label: "Portfolio", thai: "ทดลองน้ำหนักพอร์ต", description: "ความเสี่ยงพอร์ตจาก covariance ที่บันทึกไว้", icon: "portfolio" },
  { path: "/drift", label: "Drift", thai: "Online Learning & ADWIN", description: "ผล monitor จากชุดทดลองที่ตรึงไว้", icon: "drift" },
  { path: "/research", label: "Research", thai: "หลักฐาน H1–H3", description: "หลักฐานสถิติที่คำนวณไว้ใน Stage 06", icon: "research" },
  { path: "/provenance", label: "Provenance", thai: "ที่มาและคุณภาพข้อมูล", description: "IDs, hashes และข้อจำกัดของ snapshot", icon: "provenance" },
  { path: "/guide", label: "Guide", thai: "คู่มือวิธีอ่านผล", description: "ความหมายของข้อมูลและข้อจำกัด", icon: "guide" },
];

const modelNames: ModelName[] = ["CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD"];
const tickerNames: Ticker[] = ["SPY", "IEF", "GLD"];
const metricTickerNames: (Ticker | "MACRO")[] = ["MACRO", "SPY", "IEF", "GLD"];
const tickerLabel: Record<Ticker, string> = { SPY: "SPY · US equities", IEF: "IEF · Treasury bonds", GLD: "GLD · Gold" };
const modelColors: Record<ModelName, string> = {
  CONSTANT_BASELINE: "#8798ad",
  ROLLING_20D_BASELINE: "#c38a36",
  STATIC_SGD: "#518d7f",
  ONLINE_SGD: "#2e62a5",
};
type DisplayUnit = "decimal" | "percent";
type MetricName = "mae" | "rmse";
const iconShapes: Record<string, string> = {
  overview: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  models: '<path d="M4 19V5M4 19h17"/><rect x="7" y="11" width="3" height="5" rx="1"/><rect x="13" y="7" width="3" height="9" rx="1"/><rect x="19" y="4" width="2" height="12" rx="1"/>',
  forecasts: '<path d="M3 12h4l3-7 4 14 3-7h4"/><circle cx="10" cy="5" r="1"/><circle cx="14" cy="19" r="1"/>',
  portfolio: '<path d="M12 3v9h9M20.5 15A9 9 0 1 1 9 3.5M15 3.5A9 9 0 0 1 20.5 9"/>',
  drift: '<path d="M3 12c3-8 6 8 9 0s6 8 9 0M3 5h18M3 19h18"/>',
  research: '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3M8 15h8"/>',
  provenance: '<path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z"/><path d="m9 12 2 2 4-4"/>',
  guide: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 0 4 22zM4 5v17M8 7h8M8 11h7"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  arrowLeft: '<path d="m14 18-6-6 6-6"/>',
  arrowRight: '<path d="m10 18 6-6-6-6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  lock: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
};

interface ViewState {
  snapshot: SnapshotState;
  routePath: string;
  mobileMenuOpen: boolean;
  moreOpen: boolean;
  ticker: Ticker;
  model: ModelName;
  sessionIndex: number;
  unit: DisplayUnit;
  metric: MetricName;
  modelTicker: Ticker | "MACRO";
  forecastTicker: Ticker;
  forecastSplit: "test" | "validation";
  forecastModels: ModelName[];
  forecastStatus: ForecastFilter["status"];
  forecastFrom: string;
  forecastTo: string;
  portfolioDate: string;
  portfolioModel: ModelName;
  portfolioWeights: [number, number, number];
  driftTicker: Ticker;
  driftModel: ModelName;
  driftFrom: string;
  driftTo: string;
  researchTicker: Ticker;
  attempt: number;
}

function icon(name: string, size = 20): string {
  return `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${iconShapes[name] ?? ""}</svg>`;
}

function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] ?? character);
}

function currentRoute(): string {
  const route = window.location.hash.replace(/^#/, "");
  return routes.some((item) => item.path === route) ? route : "/overview";
}

function navLink(route: RouteDefinition, active: boolean, extraClass = ""): string {
  return `<a class="nav-link${active ? " active" : ""}${extraClass ? ` ${extraClass}` : ""}" href="#${route.path}" ${active ? 'aria-current="page"' : ""}>${icon(route.icon, 19)}<span>${route.label}</span>${active ? '<span class="nav-active-mark" aria-hidden="true"></span>' : ""}</a>`;
}

function loadingState(): string {
  return `<section aria-live="polite" class="state-panel loading-state"><div class="loading-mark" aria-hidden="true"><span></span><span></span><span></span></div><div><h3>กำลังตรวจสอบ Frozen Snapshot</h3><p>กำลังตรวจ hash, Evaluation ID, Replay ID และ schema ก่อนแสดงข้อมูล</p></div></section>`;
}

function emptyState(title: string, message: string, action = ""): string {
  return `<section class="empty-state" role="status"><div class="empty-state-icon">${icon("lock", 22)}</div><div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p>${action}</div></section>`;
}

function errorState(message: string, title = "หยุดแสดงผลเพื่อป้องกันข้อมูลผิดชุด"): string {
  return `<section class="error-state" role="alert"><div class="error-icon">!</div><div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p><button class="button button-secondary" type="button" data-action="retry">ตรวจอีกครั้ง</button></div></section>`;
}

function snapshotBanner(snapshot: SnapshotState): string {
  if (snapshot.status === "loading") return `<section class="snapshot-banner loading" aria-live="polite"><div class="snapshot-banner-icon"><span class="pulse-dot"></span></div><div class="snapshot-banner-copy"><strong>กำลังตรวจสอบ snapshot</strong><span>ตรวจ SHA-256, source IDs และ schema ก่อนเปิดข้อมูล</span></div><div class="snapshot-banner-badges"><span class="pill pill-neutral">ไม่ใช่ข้อมูลสด</span></div></section>`;
  if (snapshot.status === "missing") return `<section class="snapshot-banner missing" aria-live="polite"><div class="snapshot-banner-icon">!</div><div class="snapshot-banner-copy"><strong>ยังโหลด snapshot ไม่ได้</strong><span>${escapeHtml(snapshot.message)}</span></div><div class="snapshot-banner-badges"><span class="pill pill-neutral">ไม่ใช่ข้อมูลสด</span></div></section>`;
  if (snapshot.status === "error") return `<section class="snapshot-banner error" aria-live="polite"><div class="snapshot-banner-icon">!</div><div class="snapshot-banner-copy"><strong>หยุดแสดงผล · ตรวจพบปัญหา</strong><span>${escapeHtml(snapshot.message)}</span></div><div class="snapshot-banner-badges"><span class="pill pill-neutral">ไม่ใช่ข้อมูลสด</span></div></section>`;
  const evaluationId = snapshot.manifest.evaluationId;
  const replayId = snapshot.manifest.replayId;
  const identity = `<div class="snapshot-banner-ids" aria-label="Pinned snapshot identifiers"><span title="${escapeHtml(evaluationId)}" aria-label="Evaluation ID ${escapeHtml(evaluationId)}">Evaluation <code>${escapeHtml(evaluationId.slice(0, 12))}…</code></span><span title="${escapeHtml(replayId)}" aria-label="Replay ID ${escapeHtml(replayId)}">Replay <code>${escapeHtml(replayId.slice(0, 12))}…</code></span></div>`;
  return `<section class="snapshot-banner ready" aria-live="polite"><div class="snapshot-banner-icon">${icon("check", 18)}</div><div class="snapshot-banner-copy"><strong>REVIEW READY · ตรวจ Frozen Snapshot ผ่าน</strong><span>${escapeHtml(snapshot.manifest.mode)} · Review snapshot · รายงานยังรออนุมัติ</span></div>${identity}<div class="snapshot-banner-badges"><span class="pill pill-neutral">ไม่ใช่ข้อมูลสด</span><span class="pill pill-pending">Report approval pending</span></div></section>`;
}

function formatVol(value: number | null | undefined, unit: DisplayUnit, digits = 4): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return unit === "percent" ? `${(value * 100).toFixed(2)}%` : value.toFixed(digits);
}

function metricValue(row: ModelMetricRow, metric: MetricName): number {
  return metric === "mae" ? row.mae : row.rmse;
}

function metricName(metric: MetricName): string {
  return metric === "mae" ? "MAE" : "RMSE";
}

function sourceFooter(filename: string, split: string, selection: string, n: number, units: string, evaluationId: string): string {
  return `<div class="data-source-footer"><span>Source <code>${escapeHtml(filename)}</code></span><span>Split <strong>${escapeHtml(split)}</strong></span><span>Selection <strong>${escapeHtml(selection)}</strong></span><span>N <strong>${n.toLocaleString()}</strong></span><span>Units <strong>${escapeHtml(units)}</strong></span><span>Evaluation <code>${escapeHtml(evaluationId.slice(0, 12))}…</code></span></div>`;
}

function chartDataTable(caption: string, headers: string[], rows: string[]): string {
  if (rows.length === 0) return "";
  const headerCells = headers.map((header) => `<th scope="col">${escapeHtml(header)}</th>`).join("");
  return `<details class="chart-data-details"><summary>ดูข้อมูลกราฟเป็นตาราง · ${rows.length.toLocaleString()} แถว</summary><div class="table-scroll"><table class="data-table"><caption class="visually-hidden">${escapeHtml(caption)}</caption><thead><tr>${headerCells}</tr></thead><tbody>${rows.join("")}</tbody></table></div></details>`;
}

function metricChart(rows: ModelMetricRow[], metric: MetricName, unit: DisplayUnit, title: string): string {
  const ordered = modelNames.map((name) => rows.find((row) => row.modelName === name)).filter((row): row is ModelMetricRow => row !== undefined);
  if (ordered.length === 0) return emptyState("ไม่มี metric สำหรับตัวเลือกนี้", "ไม่พบ source row ที่ตรงกับ split และ asset ที่เลือก");
  const valueMax = Math.max(...ordered.map((row) => metricValue(row, metric)), Number.EPSILON);
  const width = 760;
  const labelWidth = 54;
  const plotWidth = width - labelWidth - 95;
  const rowHeight = 45;
  const chartHeight = ordered.length * rowHeight + 20;
  const bars = ordered.map((row, index) => {
    const value = metricValue(row, metric);
    const y = 14 + index * rowHeight;
    const barWidth = Math.max(2, plotWidth * value / valueMax);
    return `<g><text class="chart-model-label" x="0" y="${y + 20}">${modelId(row.modelName)}</text><rect x="${labelWidth}" y="${y + 5}" width="${barWidth}" height="20" rx="5" fill="${modelColors[row.modelName]}"><title>${modelId(row.modelName)} ${metricName(metric)} ${formatVol(value, unit)} · paired N ${row.pairedN}</title></rect><text class="chart-value-label" x="${labelWidth + barWidth + 9}" y="${y + 20}">${formatVol(value, unit)}</text></g>`;
  }).join("");
  const tableRows = ordered.map((row) => `<tr><th scope="row">${modelId(row.modelName)}</th><td>${formatVol(metricValue(row, metric), unit)}</td><td>${row.pairedN.toLocaleString()}</td><td>${row.expectedEligibleAnchorCount.toLocaleString()}</td></tr>`);
  return `<div class="chart-scroll"><svg class="metric-bar-chart" role="img" aria-label="${escapeHtml(title)}" viewBox="0 0 ${width} ${chartHeight}" preserveAspectRatio="xMinYMin meet">${bars}</svg></div>${chartDataTable(`${title} values`, ["Model", metricName(metric), "Paired N", "Expected anchors"], tableRows)}`;
}

function coverageRowsFor(snapshot: Extract<SnapshotState, { status: "ready" }>, ticker: Ticker): CoverageRow[] {
  return snapshot.coverage.filter((row) => row.split === "test" && row.ticker === ticker).sort((left, right) => modelNames.indexOf(left.modelName) - modelNames.indexOf(right.modelName));
}

function selectedPortfolioRow(snapshot: Extract<SnapshotState, { status: "ready" }>, date: string, model: ModelName): PortfolioRiskRow | undefined {
  const selectedDate = date || snapshot.manifest.strictCutoff;
  return snapshot.portfolioRisk.find((row) => row.split === "test" && row.predictionDate === selectedDate && row.modelName === model && row.status === "OK" && row.covariance !== null && row.portfolioVol !== null && row.missingInputs.length === 0);
}

function coverageTable(snapshot: Extract<SnapshotState, { status: "ready" }>, ticker: Ticker, evaluationId: string): string {
  const rows = coverageRowsFor(snapshot, ticker);
  if (rows.length === 0) return emptyState("Coverage ยังไม่มีข้อมูล", `ไม่พบ Test coverage สำหรับ ${ticker}`);
  const tableRows = rows.map((row) => {
    const evaluableWidth = row.expectedEligiblePredictionAnchors ? row.matureEvaluableCount / row.expectedEligiblePredictionAnchors * 100 : 0;
    const pendingWidth = row.expectedEligiblePredictionAnchors ? row.pendingLabelCount / row.expectedEligiblePredictionAnchors * 100 : 0;
    return `<tr><th scope="row"><span class="model-chip" style="--model-color:${modelColors[row.modelName]}">${modelId(row.modelName)}</span></th><td>${row.forecastSuccessCount.toLocaleString()} / ${row.expectedEligiblePredictionAnchors.toLocaleString()}</td><td>${row.matureEvaluableCount.toLocaleString()}</td><td>${row.pendingLabelCount.toLocaleString()}</td><td>${(row.invalidForecastCount + row.missingForecastCount).toLocaleString()}</td><td><div class="coverage-meter" role="img" aria-label="${row.matureEvaluableCount} evaluable and ${row.pendingLabelCount} Pending of ${row.expectedEligiblePredictionAnchors} expected"><span class="coverage-evaluable" style="width:${evaluableWidth}%"></span><span class="coverage-pending" style="width:${pendingWidth}%"></span></div></td></tr>`;
  }).join("");
  return `<div class="table-scroll"><table class="data-table coverage-table"><caption class="visually-hidden">Test forecast and evaluation coverage for ${ticker}</caption><thead><tr><th scope="col">Model</th><th scope="col">Forecast valid / expected</th><th scope="col">Evaluable</th><th scope="col">Pending</th><th scope="col">Invalid / missing</th><th scope="col">Label status share</th></tr></thead><tbody>${tableRows}</tbody></table></div>${sourceFooter("coverage.csv", "Test", `${ticker} · per model row`, rows[0]?.expectedEligiblePredictionAnchors ?? 0, "anchor count / share", evaluationId)}`;
}

function forecastActual(row: ForecastAuditRow, snapshot: Extract<SnapshotState, { status: "ready" }>): { actual: number | null; error: number | null } {
  if (row.evaluationStatus !== "EVALUABLE") return { actual: null, error: null };
  if (row.split === "test") {
    const evaluation = snapshot.evaluations.get(row.predictionId);
    return evaluation ? { actual: evaluation.targetRealizedVol5d, error: evaluation.absoluteError } : { actual: null, error: null };
  }
  return { actual: row.targetRealizedVol5d, error: row.absoluteError };
}

function miniForecastChart(state: ViewState): string {
  const snapshot = state.snapshot;
  if (snapshot.status !== "ready") return "";
  const rows = snapshot.sessions.filter((row) => row.ticker === state.forecastTicker && row.modelName === "ONLINE_SGD").slice(-50);
  const points = rows.flatMap((row, index) => {
    const actual = forecastActual(row, snapshot).actual;
    return [
      row.forecastStatus === "VALID" && row.predictedVolAnnualized !== null ? { index, value: row.predictedVolAnnualized, label: `${row.predictionDate} · Forecast ${formatVol(row.predictedVolAnnualized, state.unit)}`, series: "Forecast" } : null,
      actual !== null ? { index, value: actual, label: `${row.predictionDate} · Actual ${formatVol(actual, state.unit)}`, series: "Actual" } : null,
    ].filter((point): point is { index: number; value: number; label: string; series: string } => point !== null);
  });
  if (rows.length === 0) return emptyState("ไม่มี recorded observation", `ไม่พบ Test forecast สำหรับ ${state.forecastTicker} · B3`);
  const maxValue = Math.max(...points.map((point) => point.value), 0.000001);
  const xy = (index: number, value: number) => `${38 + index * (560 / Math.max(rows.length - 1, 1))},${145 - value / maxValue * 116}`;
  const forecastPoints = rows.flatMap((row, index) => row.forecastStatus === "VALID" && row.predictedVolAnnualized !== null ? [{ index, value: row.predictedVolAnnualized, label: `${row.predictionDate} · Forecast ${formatVol(row.predictedVolAnnualized, state.unit)}` }] : []);
  const actualPoints = rows.flatMap((row, index) => { const actual = forecastActual(row, snapshot).actual; return actual === null ? [] : [{ index, value: actual, label: `${row.predictionDate} · Actual ${formatVol(actual, state.unit)}` }]; });
  const circles = (values: typeof forecastPoints, color: string) => values.map((point) => { const [cx, cy] = xy(point.index, point.value).split(","); return `<circle cx="${cx}" cy="${cy}" r="2.5" fill="${color}"><title>${escapeHtml(point.label)}</title></circle>`; }).join("");
  const tableRows = rows.map((row) => {
    const actual = forecastActual(row, snapshot).actual;
    return `<tr><th scope="row">${escapeHtml(row.predictionDate)}</th><td>${formatVol(row.predictedVolAnnualized, state.unit)}</td><td>${formatVol(actual, state.unit)}</td><td>${escapeHtml(row.targetEndDate)}</td><td>${row.evaluationStatus === "PENDING_LABEL" ? "Pending · not scored" : "Evaluable"}</td></tr>`;
  });
  return `<div class="chart-scroll"><svg class="forecast-mini-chart" viewBox="0 0 630 185" role="img" aria-label="${state.forecastTicker} B3 recorded Test forecast and actual RV5"><line x1="38" y1="145" x2="600" y2="145" class="chart-axis"/><line x1="38" y1="29" x2="38" y2="145" class="chart-axis"/><polyline points="${forecastPoints.map((point) => xy(point.index, point.value)).join(" ")}" fill="none" stroke="${modelColors.ONLINE_SGD}" stroke-width="2"/>${circles(forecastPoints, modelColors.ONLINE_SGD)}<polyline points="${actualPoints.map((point) => xy(point.index, point.value)).join(" ")}" fill="none" stroke="#34455e" stroke-width="1.6" stroke-dasharray="4 3"/>${circles(actualPoints, "#34455e")}<text x="38" y="169" class="chart-date-label">${escapeHtml(rows[0].predictionDate)}</text><text x="600" y="169" text-anchor="end" class="chart-date-label">${escapeHtml(rows[rows.length - 1].predictionDate)}</text><text x="6" y="34" class="chart-date-label">${formatVol(maxValue, state.unit, 2)}</text></svg></div><div class="chart-legend"><span><i style="--legend-color:${modelColors.ONLINE_SGD}"></i>B3 Forecast</span><span><i style="--legend-color:#34455e"></i>Actual · evaluable only</span><span>${points.length.toLocaleString()} plotted values</span></div>${chartDataTable(`${state.forecastTicker} B3 recorded Test forecast and actual RV5`, ["Prediction date", "Forecast", "Actual · evaluable only", "Target end", "Label status"], tableRows)}`;
}

function overviewPage(state: ViewState): string {
  const snapshot = state.snapshot;
  if (snapshot.status === "loading") return loadingState();
  if (snapshot.status === "missing") return emptyState("ยังไม่มี Frozen Snapshot", "ไม่มีตัวเลขหรือกราฟแสดงจนกว่า source ZIP จะผ่านการตรวจสอบและโหลดไฟล์ครบ");
  if (snapshot.status === "error") return emptyState("ข้อมูลถูกซ่อนไว้ระหว่างตรวจสอบ", "ตัวตรวจพบความไม่ตรงกัน จึงหยุดแสดงผลจาก snapshot นี้");
  const manifest = snapshot.manifest;
  const macroRows = snapshot.modelMetrics.filter((row) => row.ticker === "MACRO");
  const b3Metric = macroRows.find((row) => row.modelName === "ONLINE_SGD");
  const b2Delta = snapshot.pairComparisons.find((row) => row.comparisonId === "H2" && row.ticker === "MACRO");
  const testCoverage = snapshot.coverage.filter((row) => row.split === "test");
  const expected = testCoverage.reduce((sum, row) => sum + row.expectedEligiblePredictionAnchors, 0);
  const evaluable = testCoverage.reduce((sum, row) => sum + row.matureEvaluableCount, 0);
  const pending = testCoverage.reduce((sum, row) => sum + row.pendingLabelCount, 0);
  const valid = testCoverage.reduce((sum, row) => sum + row.forecastSuccessCount, 0);
  const routeCards = routes.filter((route) => route.path !== "/overview").map((route, index) => `<button class="route-card" type="button" data-route="${route.path}"><span class="route-card-icon route-color-${index}">${icon(route.icon, 19)}</span><span class="route-card-title"><strong>${escapeHtml(route.thai)}</strong><small>${escapeHtml(route.label)}</small></span><span class="route-card-arrow">${icon("arrowRight", 17)}</span></button>`).join("");
  const overviewMetrics = [
    { label: "B3 Test Macro MAE", value: formatVol(b3Metric?.mae, state.unit), detail: `paired N ${b3Metric?.pairedN.toLocaleString() ?? "—"}`, href: "/models", source: "model_metrics.csv" },
    { label: "B3 vs B2 · ΔMAE", value: formatVol(b2Delta?.deltaMaeBaselineMinusOnline, state.unit), detail: `paired N ${b2Delta?.pairedN.toLocaleString() ?? "—"}`, href: "/research", source: "pair_comparisons.csv" },
    { label: "Test evaluable / expected", value: `${evaluable.toLocaleString()} / ${expected.toLocaleString()}`, detail: `${expected ? (evaluable / expected * 100).toFixed(1) : "—"}% evaluated · ${pending.toLocaleString()} Pending`, href: "/provenance", source: "coverage.csv" },
  ].map((card) => `<a class="metric-summary-card" href="#${card.href}" title="${card.source} · ${card.detail} · ${manifest.evaluationId}"><span>${card.label}</span><strong>${card.value}</strong><small>${card.detail}</small><code>${card.source} · ${card.href === "/models" ? metricName(state.metric) : card.source === "pair_comparisons.csv" ? "H2 paired" : "Test"}</code></a>`).join("");
  const selectedMetricRows = snapshot.modelMetrics.filter((row) => row.ticker === state.modelTicker);
  const conclusion = `B3 (Online SGD) has the lowest stored Test Macro ${metricName(state.metric)} among B0–B3 in this frozen sample. The comparison is descriptive, paired on ${b3Metric?.pairedN.toLocaleString() ?? "—"} mature valid anchors. It does not guarantee future performance; report approval remains pending.`;
  return `
    <section class="hero-card">
      <div class="hero-copy"><div class="hero-badge"><span class="hero-badge-dot"></span> EXPERIMENT SNAPSHOT VERIFIED</div><h2>สำรวจความผันผวน<br class="desktop-break" />จากผลทดลองที่บันทึกไว้</h2><p>พื้นที่อ่านผลแบบ read-only สำหรับ SPY, IEF และ GLD ใช้ข้อมูล Frozen Snapshot ชุดเดียวตลอดการสำรวจ</p><button class="button button-primary" type="button" data-route="/forecasts">เปิด Recorded Session ${icon("arrowRight", 17)}</button><span class="hero-action-note">เลื่อนดู observation ที่บันทึกไว้ ไม่ได้เปลี่ยนหรือรันโมเดล</span></div>
      <div class="hero-graphic" aria-hidden="true"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="hero-orbit-core"><span>RV5</span><small>FROZEN</small></div><span class="orbit-point point-spy">SPY</span><span class="orbit-point point-ief">IEF</span><span class="orbit-point point-gld">GLD</span><div class="hero-graphic-caption">XNYS · 5 trading sessions</div></div>
    </section>
    <section class="metric-summary-grid" aria-label="Experiment summary">${overviewMetrics}</section>
    <div class="analysis-grid">
      <section class="analysis-card"><div class="section-card-heading"><div><span class="section-overline">COMMON TEST PANEL</span><h3>B0–B3 ${metricName(state.metric)} · ${state.modelTicker}</h3></div><a class="subtle-link" href="#/models">รายละเอียด →</a></div><div class="inline-controls"><label class="field-label">Metric<select data-field="metric"><option value="mae" ${state.metric === "mae" ? "selected" : ""}>MAE</option><option value="rmse" ${state.metric === "rmse" ? "selected" : ""}>RMSE</option></select></label><label class="field-label">Breakdown<select data-field="model-ticker">${metricTickerNames.map((ticker) => `<option value="${ticker}" ${state.modelTicker === ticker ? "selected" : ""}>${ticker}</option>`).join("")}</select></label></div>${metricChart(selectedMetricRows, state.metric, state.unit, `Stored Test ${state.modelTicker} ${metricName(state.metric)} by model`)}${sourceFooter("model_metrics.csv", "Test", `${state.modelTicker} · B0–B3`, selectedMetricRows[0]?.pairedN ?? 0, `annualized decimal (${state.unit}) · paired N per row`, manifest.evaluationId)}</section>
      <section class="analysis-card"><div class="section-card-heading"><div><span class="section-overline">COVERAGE · TEST</span><h3>Forecast และ label status</h3></div><span class="pill pill-neutral">valid ${valid.toLocaleString()} / ${expected.toLocaleString()}</span></div><label class="field-label coverage-ticker-control">Asset<select data-field="coverage-ticker">${tickerNames.map((ticker) => `<option value="${ticker}" ${ticker === state.forecastTicker ? "selected" : ""}>${ticker}</option>`).join("")}</select></label>${coverageTable(snapshot, state.forecastTicker, manifest.evaluationId)}</section>
      <section class="analysis-card analysis-card-wide"><div class="section-card-heading"><div><span class="section-overline">RECORDED TEST OBSERVATIONS</span><h3>${state.forecastTicker} · B3 Forecast vs actual</h3></div><button class="text-button" type="button" data-route="/forecasts">เปิด Forecast Explorer →</button></div>${miniForecastChart(state)}<p class="chart-note">Actual แสดงเฉพาะ mature/evaluable labels; Pending forecast ยังไม่ถูกให้คะแนน ณ cutoff ${manifest.strictCutoff}.</p>${sourceFooter("forecast_audit.csv + evaluation.csv", "Test", `${state.forecastTicker} · B3`, snapshot.sessions.filter((row) => row.ticker === state.forecastTicker && row.modelName === "ONLINE_SGD").length, `annualized decimal (${state.unit})`, manifest.evaluationId)}</section>
      <section class="study-conclusion"><span class="section-overline">STUDY CONCLUSION · FROZEN SAMPLE</span><p>${escapeHtml(conclusion)}</p><a href="#/research">ดูวิธีและหลักฐานที่บันทึกใน Stage 06 →</a><div class="limitation-inline">ข้อมูลนี้เป็น Simulated Historical Replay ไม่ใช่ forecast สด และยังรออนุมัติรายงาน</div></section>
    </div>
    <div class="overview-grid">
      <section class="overview-section-card identity-overview-card"><div class="section-card-heading"><div><span class="section-overline">SOURCE IDENTITY</span><h3>ชุดข้อมูลที่กำลังอ่าน</h3></div><span class="verified-badge">${icon("check", 13)} VERIFIED</span></div><div class="identity-pair"><span>Evaluation ID</span><code>${escapeHtml(manifest.evaluationId)}</code></div><div class="identity-pair"><span>Replay ID</span><code>${escapeHtml(manifest.replayId)}</code></div><div class="identity-meta-row"><span>Strict cutoff</span><strong>${escapeHtml(manifest.strictCutoff)}</strong><span class="meta-divider"></span><span>Source mode</span><strong>Simulated Historical Replay</strong></div></section>
      <section class="overview-section-card phase-card"><div class="section-card-heading"><div><span class="section-overline">REVIEW STATE</span><h3>อ่านผลจากชุดที่ตรวจแล้ว</h3></div><span class="phase-index">D3</span></div><p>ตัวเลขในหน้า Overview และ Models มาจาก metric rows ที่บันทึกไว้ ไม่คำนวณซ้ำใน browser</p><div class="phase-check-list"><span>${icon("check", 15)} Snapshot checksum และ schema ผ่าน</span><span>${icon("check", 15)} มี ${valid.toLocaleString()} forecast ที่ valid</span><span class="phase-next">${pending.toLocaleString()} Pending · ยังไม่ใช่ forecast ที่ผิด</span></div></section>
    </div>
    <section class="route-preview-section"><div class="section-heading-row"><div><span class="section-overline">EXPLORE THE LAB</span><h3>เลือกพื้นที่สำรวจ</h3></div><span class="route-count">08 PAGES</span></div><div class="route-card-grid">${routeCards}</div></section>`;
}

function sessionCard(state: ViewState): string {
  if (state.snapshot.status === "loading") return loadingState();
  if (state.snapshot.status === "missing") return emptyState("Recorded sessions ยังไม่พร้อม", "เมื่อ snapshot files ไม่ครบ จะไม่สร้างวันที่หรือ forecast ขึ้นมาแทน");
  if (state.snapshot.status === "error") return errorState(state.snapshot.message);
  const available = selectRecordedSessions(state.snapshot.sessions, state.ticker, state.model);
  const index = Math.max(0, Math.min(state.sessionIndex, available.length - 1));
  const row = available[index];
  const modelOptions = modelNames.map((model) => `<option value="${model}" ${state.model === model ? "selected" : ""}>${modelId(model)} · ${escapeHtml(modelLabel(model))}</option>`).join("");
  const tickerOptions = tickerNames.map((ticker) => `<option value="${ticker}" ${state.ticker === ticker ? "selected" : ""}>${ticker}</option>`).join("");
  const dateOptions = available.map((session, sessionIndex) => `<option value="${sessionIndex}" ${index === sessionIndex ? "selected" : ""}>${escapeHtml(session.predictionDate)}</option>`).join("");
  if (!row) return `<section class="session-card"><div class="eyebrow"><span class="eyebrow-dot"></span> RECORDED SESSION · TEST</div><h2 id="session-title">สำรวจผลที่บันทึกไว้</h2><div class="session-filters"><label class="field-label">สินทรัพย์<select data-field="ticker">${tickerOptions}</select></label><label class="field-label">โมเดล<select data-field="model">${modelOptions}</select></label></div>${emptyState("ไม่มีบันทึกสำหรับตัวกรองนี้", "ไม่พบแถวใน snapshot ที่ผ่านการตรวจสอบสำหรับสินทรัพย์และโมเดลที่เลือก ลองเปลี่ยนตัวกรอง")}</section>`;
  const evaluation = state.snapshot.evaluations.get(row.predictionId);
  const pending = row.evaluationStatus === "PENDING_LABEL";
  const isEvaluable = row.evaluationStatus === "EVALUABLE" && evaluation !== undefined;
  const validForecast = row.forecastStatus === "VALID" && row.predictedVolAnnualized !== null;
  const format = (value: number | null | undefined) => value === null || value === undefined ? "—" : value.toFixed(6);
  const statusClass = pending ? "status-pending" : isEvaluable ? "status-evaluable" : "status-neutral";
  const statusLabel = pending ? "PENDING · ยังไม่ครบช่วงเป้าหมาย" : isEvaluable ? "EVALUABLE · ประเมินได้" : row.evaluationStatus;
  const pendingTooltip = pending ? "Not scored: target pending by cutoff" : "";
  const actualLabel = pending ? "Target ยังไม่ mature ณ cutoff" : "Annualized decimal · evaluation.csv";
  const errorLabel = pending ? "ยังไม่ให้คะแนน" : "ค่าที่บันทึกใน Stage 06";
  const noActualWarning = row.evaluationStatus === "EVALUABLE" && !evaluation ? '<p class="error-inline">ไม่พบแถวประเมินที่จับคู่กับ prediction ID นี้ จึงซ่อน actual/error</p>' : "";
  const noForecastWarning = !validForecast ? '<p class="error-inline">ไม่มีค่าพยากรณ์ที่ใช้แสดงได้ตามสถานะใน source row</p>' : "";
  return `
    <section class="session-card" aria-labelledby="session-title">
      <div class="session-head"><div><div class="eyebrow"><span class="eyebrow-dot"></span> RECORDED SESSION · TEST</div><h2 id="session-title">สำรวจผลที่บันทึกไว้</h2><p>เลื่อนไปยังวัน XNYS ที่มีอยู่ใน Frozen Snapshot เท่านั้น การเปลี่ยนวันไม่เรียก Replay หรือคำนวณโมเดลใหม่</p></div><span class="readonly-pill">${icon("lock", 14)} ดูอย่างเดียว</span></div>
      <div class="session-filters"><label class="field-label">สินทรัพย์<select data-field="ticker">${tickerOptions}</select></label><label class="field-label">โมเดล<select data-field="model">${modelOptions}</select></label><label class="field-label">วันที่บันทึกไว้<select aria-label="เลือกวันที่บันทึกไว้" data-field="date">${dateOptions}</select></label></div>
      <div class="session-date-row"><button class="icon-button" type="button" aria-label="วันก่อนหน้า" data-action="previous" ${index === 0 ? "disabled" : ""}>${icon("arrowLeft")}</button><div class="session-date"><span>วันทำนาย · XNYS</span><strong>${escapeHtml(row.predictionDate)}</strong><small>บันทึกที่ ${index + 1} จาก ${available.length}</small></div><button class="icon-button" type="button" aria-label="วันถัดไป" data-action="next" ${index >= available.length - 1 ? "disabled" : ""}>${icon("arrowRight")}</button></div>
      <div class="session-status-row"><span class="status-chip ${statusClass}" ${pending ? `title="${pendingTooltip}" aria-label="${pendingTooltip}"` : ""}>${escapeHtml(statusLabel)}</span><span class="status-chip status-outline">Forecast · ${escapeHtml(row.forecastStatus)}</span><span class="session-horizon">ช่วงเป้าหมาย ${escapeHtml(row.targetStartDatePrediction)} → ${escapeHtml(row.targetEndDatePrediction)}</span></div>
      <div class="session-values"><div class="session-value-card"><span>Forecast RV5</span><strong>${validForecast ? format(row.predictedVolAnnualized) : "—"}</strong><small>Annualized decimal · จาก forecast_audit.csv</small></div><div class="session-value-card${pending ? " muted-value" : ""}"><span>Actual RV5</span><strong ${pending ? `title="${pendingTooltip}" aria-label="Actual RV5 · ${pendingTooltip}"` : ""}>${pending ? "—" : format(evaluation?.targetRealizedVol5d)}</strong><small>${actualLabel}</small></div><div class="session-value-card${pending ? " muted-value" : ""}"><span>Absolute error</span><strong ${pending ? `title="${pendingTooltip}" aria-label="Absolute error · ${pendingTooltip}"` : ""}>${pending ? "—" : format(evaluation?.absoluteError)}</strong><small>${errorLabel}</small></div></div>
      ${pending ? '<p class="pending-note"><span>i</span> Target ยังไม่ครบ 5 วันซื้อขายก่อน strict cutoff จึงไม่แสดง actual หรือ error เป็นศูนย์</p>' : ""}${noActualWarning}${noForecastWarning}
      <div class="session-footer"><span>Prediction ID <code>${escapeHtml(row.predictionId)}</code></span><span>${escapeHtml(tickerLabel[state.ticker])} · ${modelId(state.model)}</span></div>
      <div class="session-actions"><span>เปลี่ยนเฉพาะการเลือก observation ที่บันทึกไว้</span><button type="button" class="text-button" data-action="reset">Reset ไปวันแรก</button></div>
    </section>`;
}

function modelsPage(state: ViewState): string {
  const snapshot = state.snapshot;
  if (snapshot.status === "loading") return loadingState();
  if (snapshot.status === "missing") return emptyState("Model metrics ยังโหลดไม่ได้", "ต้องมี frozen snapshot ที่ผ่านการตรวจสอบก่อนแสดงผล");
  if (snapshot.status === "error") return errorState(snapshot.message);
  const rows = snapshot.modelMetrics.filter((row) => row.ticker === state.modelTicker);
  const pairRows = snapshot.pairComparisons.filter((row) => row.ticker === state.modelTicker).sort((left, right) => ["B0", "B1", "B2", "H2", "H3"].indexOf(left.comparisonId) - ["B0", "B1", "B2", "H2", "H3"].indexOf(right.comparisonId));
  const metricRows = modelNames.map((model) => rows.find((row) => row.modelName === model)).filter((row): row is ModelMetricRow => row !== undefined);
  const pairTable = pairRows.length
    ? `<div class="table-scroll"><table class="data-table"><caption class="visually-hidden">Paired B3 comparison results for ${state.modelTicker}</caption><thead><tr><th scope="col">Comparison</th><th scope="col">Baseline → B3</th><th scope="col">ΔMAE</th><th scope="col">Relative improvement</th><th scope="col">Paired N</th></tr></thead><tbody>${pairRows.map((row) => `<tr><th scope="row"><span class="status-chip status-outline">${row.comparisonId}</span></th><td>${modelId(row.baselineModel)} → B3</td><td title="Baseline MAE minus B3 MAE">${formatVol(row.deltaMaeBaselineMinusOnline, state.unit)}</td><td>${row.relativeImprovementPct.toFixed(2)}%</td><td>${row.pairedN.toLocaleString()}</td></tr>`).join("")}</tbody></table></div>${sourceFooter("pair_comparisons.csv", "Test · paired", `${state.modelTicker} · per comparison`, pairRows[0]?.pairedN ?? 0, `annualized decimal (${state.unit}) · paired N per row`, snapshot.manifest.evaluationId)}`
    : emptyState("ไม่มี paired comparison สำหรับตัวเลือกนี้", "แสดงเฉพาะ comparison ที่อยู่ใน frozen source.");
  return `<div class="page-stack">
    <section class="analysis-card"><div class="section-card-heading"><div><span class="section-overline">STAGE 06 · TEST-ONLY SCORES</span><h2 class="analysis-title">เปรียบเทียบ B0–B3 บน common panel</h2><p>ใช้ค่าที่บันทึกไว้ใน source; paired N และ panel แสดงตามแถว Stage 06 โดยตรง</p></div><span class="readonly-pill">${icon("lock", 14)} Frozen result</span></div><div class="inline-controls"><label class="field-label">Asset / aggregate<select data-field="model-ticker">${metricTickerNames.map((ticker) => `<option value="${ticker}" ${state.modelTicker === ticker ? "selected" : ""}>${ticker === "MACRO" ? "MACRO · equal ETF aggregate" : ticker}</option>`).join("")}</select></label><label class="field-label">Metric<select data-field="metric"><option value="mae" ${state.metric === "mae" ? "selected" : ""}>MAE</option><option value="rmse" ${state.metric === "rmse" ? "selected" : ""}>RMSE</option></select></label></div>${metricChart(metricRows, state.metric, state.unit, `Stored Test ${state.modelTicker} ${metricName(state.metric)} by model`)}<div class="model-definition-grid">${modelNames.map((model) => `<article class="model-definition" style="--model-color:${modelColors[model]}"><span class="model-chip">${modelId(model)}</span><strong>${escapeHtml(modelLabel(model))}</strong><small>${model === "ONLINE_SGD" ? "B3 · online model" : `${modelId(model)} · comparator`}</small></article>`).join("")}</div><div class="comparison-note"><strong>Common-panel caveat</strong><span>ค่าทั้งสี่แถวใช้ paired matured-valid anchors ตามค่า comparison_panel; MACRO เป็นค่าที่ Stage 06 บันทึก ไม่ได้นำ RMSE ราย ETF มาเฉลี่ยใน browser.</span></div>${sourceFooter("model_metrics.csv", "Test", `${state.modelTicker} · B0–B3`, metricRows[0]?.pairedN ?? 0, `annualized decimal (${state.unit}) · paired N per row`, snapshot.manifest.evaluationId)}</section>
    <section class="analysis-card"><div class="section-card-heading"><div><span class="section-overline">PAIRED DESCRIPTIVE DELTAS</span><h3>B3 เทียบกับ baseline</h3></div><span class="pill pill-neutral">Positive ΔMAE = B3 error lower</span></div>${pairTable}</section>
    <section class="limitation-card"><span class="limitation-mark">i</span><p>ผลนี้อธิบาย frozen Test sample เท่านั้น ไม่ยืนยันความเหนือกว่าในอนาคต และไม่ใช่ผล Validation หรือผลคาดการณ์สด</p></section>
  </div>`;
}

function portfolioPage(state: ViewState): string {
  const snapshot = state.snapshot;
  if (snapshot.status === "loading") return loadingState();
  if (snapshot.status !== "ready") return snapshot.status === "error" ? errorState(snapshot.message) : emptyState("Portfolio source ยังโหลดไม่ได้", "ต้องตรวจสอบ portfolio_risk.csv และ stored covariance ให้ครบก่อน");
  const testRows = snapshot.portfolioRisk.filter((row) => row.split === "test" && row.status === "OK");
  const dates = [...new Set(testRows.map((row) => row.predictionDate))].sort((left, right) => right.localeCompare(left));
  const date = state.portfolioDate && dates.includes(state.portfolioDate) ? state.portfolioDate : snapshot.manifest.strictCutoff;
  const row = selectedPortfolioRow(snapshot, date, state.portfolioModel);
  if (!row || !row.covariance || row.portfolioVol === null) return emptyState("ไม่พบ portfolio row ที่พร้อมคำนวณ", `ไม่พบ Test covariance ที่ผ่านการตรวจสำหรับ ${date} · ${modelId(state.portfolioModel)}`, sourceFooter("portfolio_risk.csv", "Test", `${date} · ${modelId(state.portfolioModel)}`, 0, "annualized decimal", snapshot.manifest.evaluationId));
  let whatIfValue: number | null = null;
  let validationMessage = "";
  try { whatIfValue = computePortfolioVolatility(row.covariance, state.portfolioWeights); }
  catch (error) { validationMessage = error instanceof Error ? error.message : "Weights are invalid"; }
  const names = ["SPY", "IEF", "GLD"] as const;
  const weightInputs = names.map((ticker, index) => {
    const weight = state.portfolioWeights[index];
    const validSliderWeight = Number.isFinite(weight) && weight >= 0 && weight <= 1;
    const safeSliderWeight = Number.isFinite(weight) ? Math.min(1, Math.max(0, weight)) : 0;
    return `<div class="weight-field"><label class="field-label" for="portfolio-weight-${index}">${ticker} weight</label><div class="weight-slider-row"><input type="range" min="0" max="1" step="0.01" data-field="portfolio-weight-slider" data-index="${index}" value="${safeSliderWeight}" aria-label="${ticker} portfolio weight slider" aria-valuetext="${Math.round(safeSliderWeight * 100)}% of portfolio" /><output data-portfolio-weight-percent="${index}">${validSliderWeight ? `${Math.round(weight * 100)}%` : "Invalid"}</output></div><input id="portfolio-weight-${index}" type="number" min="0" max="1" step="0.01" data-field="portfolio-weight" data-index="${index}" value="${Number.isFinite(weight) ? escapeHtml(String(weight)) : ""}" aria-label="${ticker} portfolio weight" /></div>`;
  }).join("");
  const forecastCards = names.map((ticker, index) => `<div class="portfolio-input-row"><span>${ticker}</span><strong>${formatVol(row.forecastVols[index], state.unit)}</strong><small>${row.forecastStatuses[index]}</small></div>`).join("");
  const storedWeights = row.sourceWeights.map((weight, index) => `${names[index]} ${weight.toFixed(2)}`).join(" · ");
  return `<div class="page-stack">
    <section class="analysis-card"><div class="section-card-heading"><div><span class="section-overline">STORED COVARIANCE · LOCAL WHAT-IF</span><h2 class="analysis-title">Portfolio Lab</h2><p>คำนวณ √(wᵀΣw) จาก covariance ที่บันทึกไว้ในแถวเดียวกับวันที่และ model ที่เลือกเท่านั้น</p></div><span class="readonly-pill">${icon("lock", 14)} No inference</span></div>
      <div class="inline-controls"><label class="field-label">Recorded date<select data-field="portfolio-date">${dates.map((value) => `<option value="${value}" ${value === date ? "selected" : ""}>${value}</option>`).join("")}</select></label><label class="field-label">Model<select data-field="portfolio-model">${modelNames.map((model) => `<option value="${model}" ${model === state.portfolioModel ? "selected" : ""}>${modelId(model)} · ${escapeHtml(modelLabel(model))}</option>`).join("")}</select></label></div>
      <div class="portfolio-controls"><div class="weight-control-grid">${weightInputs}</div><p class="field-help ${validationMessage ? "weight-error" : ""}" role="${validationMessage ? "alert" : "status"}" aria-live="polite" data-portfolio-weight-status>${validationMessage ? `No result · ${escapeHtml(validationMessage)}` : `Weight total ${(state.portfolioWeights.reduce((sum, value) => sum + value, 0) * 100).toFixed(1)}%`}</p><div class="portfolio-results"><article class="portfolio-result-card"><span>Stored Stage 06 portfolio value</span><strong>${formatVol(row.portfolioVol, state.unit)}</strong><small>Source weights · ${escapeHtml(storedWeights)}</small></article><article class="portfolio-result-card portfolio-whatif-card"><span>Local what-if value</span><strong data-portfolio-whatif>${whatIfValue === null ? "—" : formatVol(whatIfValue, state.unit)}</strong><small>Recalculated from this row’s stored covariance</small></article></div></div>
      <div class="portfolio-input-grid">${forecastCards}</div><p class="chart-note">Covariance and forecast inputs come from the same source row: ${escapeHtml(row.predictionDate)} · ${modelId(row.modelName)}. Changing weights performs a local calculation and leaves the frozen snapshot identity unchanged.</p>${sourceFooter("portfolio_risk.csv", "Test", `${row.predictionDate} · ${modelId(row.modelName)}`, 1, `annualized volatility (${state.unit})`, snapshot.manifest.evaluationId)}</section>
    <section class="limitation-card"><span class="limitation-mark">i</span><p>Portfolio risk is a historical source calculation, not a live portfolio estimate or investment recommendation.</p></section>
  </div>`;
}

function rollingMaeChart(rows: RollingMae20Row[], state: ViewState): string {
  if (rows.length === 0) return emptyState("ไม่พบ rolling window ตามตัวกรอง", "เลือก model, asset หรือช่วงวันที่ที่มีข้อมูลใน source");
  const values = [...rows].sort((left, right) => left.windowEnd.localeCompare(right.windowEnd));
  const maxValue = Math.max(...values.map((row) => row.mae), Number.EPSILON);
  const points = values.map((row, index) => `${44 + index * (760 / Math.max(values.length - 1, 1))},${182 - row.mae / maxValue * 145}`).join(" ");
  const circles = values.map((row, index) => `<circle cx="${44 + index * (760 / Math.max(values.length - 1, 1))}" cy="${182 - row.mae / maxValue * 145}" r="2.2" fill="${modelColors[row.modelName]}"><title>${row.windowEnd} · ${modelId(row.modelName)} MAE ${formatVol(row.mae, state.unit)} · N=${row.evaluableCount}/${row.expectedAnchorCount} · fixed ${row.windowSessionCount} XNYS sessions</title></circle>`).join("");
  const tableRows = values.map((row) => `<tr><th scope="row">${escapeHtml(row.windowEnd)}</th><td>${modelId(row.modelName)}</td><td>${formatVol(row.mae, state.unit)}</td><td>${row.evaluableCount.toLocaleString()}</td><td>${row.expectedAnchorCount.toLocaleString()}</td><td>${row.windowSessionCount}</td></tr>`);
  return `<div class="chart-scroll"><svg class="trend-chart" role="img" aria-label="Rolling MAE20 for ${state.driftTicker} ${modelId(state.driftModel)}" viewBox="0 0 840 218"><line x1="44" y1="182" x2="804" y2="182" class="chart-axis"/><line x1="44" y1="37" x2="44" y2="182" class="chart-axis"/><polyline points="${points}" fill="none" stroke="${modelColors[state.driftModel]}" stroke-width="2"/>${circles}<text x="44" y="206" class="chart-date-label">${escapeHtml(values[0].windowEnd)}</text><text x="804" y="206" text-anchor="end" class="chart-date-label">${escapeHtml(values[values.length - 1].windowEnd)}</text><text x="5" y="42" class="chart-date-label">${formatVol(maxValue, state.unit, 2)}</text></svg></div><div class="chart-legend"><span><i style="--legend-color:${modelColors[state.driftModel]}"></i>${modelId(state.driftModel)} · source rolling MAE20</span><span>${values.length.toLocaleString()} fixed windows</span></div>${chartDataTable(`Rolling MAE20 values for ${state.driftTicker} ${modelId(state.driftModel)}`, ["Window end", "Model", "MAE", "Evaluable N", "Expected anchors", "Window sessions"], tableRows)}`;
}

function adwinTimelineChart(rows: DriftTimelineRow[], ticker: Ticker, unit: DisplayUnit): string {
  if (rows.length === 0) return emptyState("ไม่มี ADWIN row ตามตัวกรอง", "เลือกช่วงวันที่ที่อยู่ใน verified B3 Test timeline");
  const values = [...rows].sort((left, right) => left.predictionDate.localeCompare(right.predictionDate));
  const maxValue = Math.max(...values.map((row) => row.absoluteErrorAdwin), Number.EPSILON);
  const points = values.map((row, index) => `${44 + index * (760 / Math.max(values.length - 1, 1))},${182 - row.absoluteErrorAdwin / maxValue * 145}`).join(" ");
  const circles = values.map((row, index) => `<circle cx="${44 + index * (760 / Math.max(values.length - 1, 1))}" cy="${182 - row.absoluteErrorAdwin / maxValue * 145}" r="${row.driftDetected ? 4 : 2.1}" fill="${row.driftDetected ? "#b54545" : "#496b88"}"><title>${row.predictionDate} · ${ticker} · B3 error ${formatVol(row.absoluteErrorAdwin, unit)} · drift_detected=${row.driftDetected} · alert_record_present=${row.alertRecordPresent}</title></circle>`).join("");
  const alerts = values.filter((row) => row.driftDetected || row.alertRecordPresent).length;
  const tableRows = values.map((row) => `<tr><th scope="row">${escapeHtml(row.predictionDate)}</th><td>${formatVol(row.absoluteErrorAdwin, unit)}</td><td>${row.driftDetected ? "Yes" : "No"}</td><td>${row.alertRecordPresent ? "Yes" : "No"}</td></tr>`);
  return `<div class="chart-scroll"><svg class="trend-chart" role="img" aria-label="Recorded B3 ADWIN error timeline for ${ticker}; ${alerts} recorded alerts" viewBox="0 0 840 218"><line x1="44" y1="182" x2="804" y2="182" class="chart-axis"/><line x1="44" y1="37" x2="44" y2="182" class="chart-axis"/><polyline points="${points}" fill="none" stroke="#496b88" stroke-width="1.8"/>${circles}<text x="44" y="206" class="chart-date-label">${escapeHtml(values[0].predictionDate)}</text><text x="804" y="206" text-anchor="end" class="chart-date-label">${escapeHtml(values[values.length - 1].predictionDate)}</text><text x="5" y="42" class="chart-date-label">${formatVol(maxValue, unit, 2)}</text></svg></div><div class="chart-legend"><span><i style="--legend-color:#496b88"></i>Recorded absolute_error_adwin</span><span>${alerts} source-recorded alerts</span></div>${chartDataTable(`Recorded B3 ADWIN error values for ${ticker}`, ["Prediction date", "Absolute error", "Drift detected", "Alert record present"], tableRows)}`;
}

function driftPage(state: ViewState): string {
  const snapshot = state.snapshot;
  if (snapshot.status === "loading") return loadingState();
  if (snapshot.status !== "ready") return snapshot.status === "error" ? errorState(snapshot.message) : emptyState("Drift sources ยังโหลดไม่ได้", "rolling_mae20.csv และ drift_error_timeline.csv ต้องผ่าน verification ก่อน");
  const rolling = snapshot.rollingMae20.filter((row) => row.split === "test" && row.ticker === state.driftTicker && row.modelName === state.driftModel && (!state.driftFrom || row.windowEnd >= state.driftFrom) && (!state.driftTo || row.windowEnd <= state.driftTo));
  const timeline = snapshot.driftTimeline.filter((row) => row.ticker === state.driftTicker && (!state.driftFrom || row.predictionDate >= state.driftFrom) && (!state.driftTo || row.predictionDate <= state.driftTo));
  const alertCount = snapshot.driftTimeline.filter((row) => row.driftDetected || row.alertRecordPresent).length;
  const filters = `<div class="forecast-filters"><label class="field-label">Asset<select data-field="drift-ticker">${tickerNames.map((ticker) => `<option value="${ticker}" ${ticker === state.driftTicker ? "selected" : ""}>${ticker}</option>`).join("")}</select></label><label class="field-label">Rolling model<select data-field="drift-model">${modelNames.map((model) => `<option value="${model}" ${model === state.driftModel ? "selected" : ""}>${modelId(model)} · ${escapeHtml(modelLabel(model))}</option>`).join("")}</select></label><label class="field-label">From<input type="date" data-field="drift-from" value="${escapeHtml(state.driftFrom)}"></label><label class="field-label">To<input type="date" data-field="drift-to" value="${escapeHtml(state.driftTo)}"></label></div>`;
  return `<div class="page-stack"><section class="analysis-card"><div class="section-card-heading"><div><span class="section-overline">FIXED 20 XNYS SESSIONS · SOURCE VALUES</span><h2 class="analysis-title">Rolling MAE20</h2><p>ทุกจุดอ่านจาก rolling_mae20.csv; N และ coverage ใช้ค่าที่บันทึกในแต่ละ window</p></div></div>${filters}${rollingMaeChart(rolling, state)}${sourceFooter("rolling_mae20.csv", "Test", `${state.driftTicker} · ${modelId(state.driftModel)}`, rolling.length, `annualized decimal · 20 XNYS sessions`, snapshot.manifest.evaluationId)}</section>
    <section class="analysis-card"><div class="section-card-heading"><div><span class="section-overline">RECORDED ADWIN · TEST B3 ONLY</span><h3>Error timeline</h3><p>แสดงเฉพาะ error และ flag ที่บันทึกไว้ใน Stage 06; ไม่มี client-side alert rule</p></div><span class="pill pill-neutral">${alertCount} recorded alerts</span></div>${adwinTimelineChart(timeline, state.driftTicker, state.unit)}${sourceFooter("drift_error_timeline.csv", "Test · B3", state.driftTicker, timeline.length, `absolute error (${state.unit})`, snapshot.manifest.evaluationId)}</section></div>`;
}

function scatterChart(rows: H1ScatterRow[], ticker: Ticker): string {
  if (rows.length === 0) return emptyState("ไม่มี H1 Train points", `ไม่พบแถว Train สำหรับ ${ticker}`);
  const xValues = rows.map((row) => row.rv5);
  const yValues = rows.map((row) => row.targetRealizedVol5d);
  const xMin = Math.min(...xValues), xMax = Math.max(...xValues), yMin = Math.min(...yValues), yMax = Math.max(...yValues);
  const x = (value: number) => 42 + (value - xMin) / Math.max(xMax - xMin, Number.EPSILON) * 690;
  const y = (value: number) => 190 - (value - yMin) / Math.max(yMax - yMin, Number.EPSILON) * 154;
  const circles = rows.map((row) => `<circle cx="${x(row.rv5)}" cy="${y(row.targetRealizedVol5d)}" r="2.2" fill="#2e62a5" fill-opacity="0.48"><title>${row.date} · ${ticker} Train · RV5 ${row.rv5.toFixed(4)} · Forward RV5 ${row.targetRealizedVol5d.toFixed(4)} · target end ${row.targetEndDate}</title></circle>`).join("");
  const tableRows = rows.map((row) => `<tr><th scope="row">${escapeHtml(row.date)}</th><td>${row.rv5.toFixed(6)}</td><td>${row.targetRealizedVol5d.toFixed(6)}</td><td>${escapeHtml(row.targetEndDate)}</td></tr>`);
  return `<div class="chart-scroll"><svg class="scatter-chart" role="img" aria-label="H1 Train scatter plot for ${ticker}" viewBox="0 0 770 236"><line x1="42" y1="190" x2="742" y2="190" class="chart-axis"/><line x1="42" y1="36" x2="42" y2="190" class="chart-axis"/>${circles}<text x="390" y="222" text-anchor="middle" class="chart-date-label">RV5 predictor · annualized decimal</text><text x="10" y="40" class="chart-date-label">Forward RV5</text><text x="42" y="207" class="chart-date-label">${xMin.toFixed(2)}</text><text x="742" y="207" text-anchor="end" class="chart-date-label">${xMax.toFixed(2)}</text><text x="735" y="43" text-anchor="end" class="chart-date-label">${rows.length.toLocaleString()} Train anchors</text></svg></div>${chartDataTable(`H1 Train scatter values for ${ticker}`, ["Prediction date", "RV5 predictor", "Forward RV5", "Target end"], tableRows)}`;
}

function researchPage(state: ViewState): string {
  const snapshot = state.snapshot;
  if (snapshot.status === "loading") return loadingState();
  if (snapshot.status !== "ready") return snapshot.status === "error" ? errorState(snapshot.message) : emptyState("Research sources ยังโหลดไม่ได้", "H1–H3 tables, bootstrap diagnostics และ high-vol metrics ต้องผ่าน verification ก่อน");
  const scatterRows = snapshot.h1Scatter.filter((row) => row.ticker === state.researchTicker);
  const h1Rows = snapshot.h1Results.filter((row) => row.ticker === state.researchTicker);
  const sensitivity = snapshot.h1Sensitivity.filter((row) => row.ticker === state.researchTicker).sort((left, right) => left.hacMaxlags - right.hacMaxlags);
  const macroHypotheses = snapshot.hypothesisResults.filter((row) => row.hypothesisId === "H2" || row.hypothesisId === "H3");
  const bootstrapRows = snapshot.bootstrapDiagnostics;
  const highVol = snapshot.highVolatilityMetrics.filter((row) => row.split === "test" && row.ticker === state.researchTicker).sort((left, right) => modelNames.indexOf(left.modelName) - modelNames.indexOf(right.modelName));
  const h1Result = h1Rows[0];
  const h1Table = h1Result ? `<div class="table-scroll"><table class="data-table"><caption class="visually-hidden">H1 Train primary HAC lag 5 result for ${state.researchTicker}</caption><thead><tr><th scope="col">Split</th><th scope="col">N</th><th scope="col">Beta</th><th scope="col">95% CI</th><th scope="col">HAC lag</th><th scope="col">Adjusted p</th><th scope="col">Decision</th></tr></thead><tbody><tr><th scope="row">Train</th><td>${h1Result.n.toLocaleString()}</td><td>${h1Result.beta.toFixed(6)}</td><td>[${h1Result.ci95.map((value) => value.toFixed(6)).join(", ")}]</td><td>${h1Result.hacLag}</td><td>${h1Result.pHolm.toExponential(3)}</td><td>${escapeHtml(h1Result.decision)}</td></tr></tbody></table></div><p class="chart-note">${escapeHtml(h1Result.interpretation)}</p>` : emptyState("H1 primary result unavailable", "No verified H1_results.csv row matches this ticker.");
  const h2h3Table = `<div class="table-scroll"><table class="data-table research-results-table"><caption class="visually-hidden">H2 and H3 Test hypothesis results from source</caption><thead><tr><th scope="col">Hypothesis</th><th scope="col">Split</th><th scope="col">Effect ΔMAE</th><th scope="col">95% CI</th><th scope="col">Paired N</th><th scope="col">Adjusted p</th><th scope="col">Decision</th><th scope="col">Method</th></tr></thead><tbody>${macroHypotheses.map((row) => `<tr><th scope="row">${row.hypothesisId} · MACRO</th><td>${escapeHtml(row.datasetSplit)}</td><td>${formatVol(row.effectSize, state.unit)}</td><td>[${row.confidenceInterval95.map((value) => formatVol(value, state.unit)).join(", ")}]</td><td>${row.nPaired.toLocaleString()}</td><td>${row.adjustedPValue.toExponential(3)}</td><td>${escapeHtml(row.decision)}</td><td>${escapeHtml(row.method)}</td></tr>`).join("")}</tbody></table></div>`;
  const bootstrapTable = `<div class="table-scroll"><table class="data-table"><caption class="visually-hidden">Bootstrap sensitivity diagnostics from source</caption><thead><tr><th scope="col">Hypothesis</th><th scope="col">Block length</th><th scope="col">Replicates</th><th scope="col">SE</th><th scope="col">95% CI</th><th scope="col">p (raw)</th><th scope="col">N by ETF</th></tr></thead><tbody>${bootstrapRows.map((row) => `<tr><th scope="row">${row.hypothesisId} sensitivity</th><td>${row.blockLength} XNYS</td><td>${row.replicates.toLocaleString()}</td><td>${formatVol(row.standardError, state.unit)}</td><td>[${row.ci95.map((value) => formatVol(value, state.unit)).join(", ")}]</td><td>${row.pRaw.toExponential(3)}</td><td>${escapeHtml(Object.entries(row.nByTicker).map(([ticker, n]) => `${ticker} ${n}`).join(" · "))}</td></tr>`).join("")}</tbody></table></div>`;
  const highVolTable = `<div class="table-scroll"><table class="data-table"><caption class="visually-hidden">Test high-volatility subset metrics for ${state.researchTicker}</caption><thead><tr><th scope="col">Model</th><th scope="col">Train p80 threshold</th><th scope="col">High-vol N</th><th scope="col">Common evaluable N</th><th scope="col">MAE</th><th scope="col">RMSE</th></tr></thead><tbody>${highVol.map((row) => `<tr><th scope="row">${modelId(row.modelName)}</th><td>${formatVol(row.trainThreshold, state.unit)}</td><td>${row.highVolAnchorCount}</td><td>${row.highVolCommonEvaluableN}</td><td>${row.highVolCommonEvaluableN === 0 ? "Insufficient Evidence (n=0)" : formatVol(row.mae, state.unit)}</td><td>${row.highVolCommonEvaluableN === 0 ? "—" : formatVol(row.rmse, state.unit)}</td></tr>`).join("")}</tbody></table></div><p class="chart-note">The high-volatility threshold is stored from Train. A zero-size Test subset has no MAE or RMSE score.</p>`;
  return `<div class="page-stack"><section class="analysis-card"><div class="section-card-heading"><div><span class="section-overline">H1 · TRAIN ONLY · PRIMARY HAC LAG 5</span><h2 class="analysis-title">RV5 association evidence</h2><p>Scatter uses recorded Train observations. Results, p-values, intervals, and decisions are read from Stage 06.</p></div></div><label class="field-label">Asset<select data-field="research-ticker">${tickerNames.map((ticker) => `<option value="${ticker}" ${ticker === state.researchTicker ? "selected" : ""}>${ticker}</option>`).join("")}</select></label>${scatterChart(scatterRows, state.researchTicker)}${sourceFooter("H1_scatter_data.csv", "Train", state.researchTicker, scatterRows.length, "annualized decimal", snapshot.manifest.evaluationId)}${h1Table}${sourceFooter("H1_results.csv", "Train · primary HAC lag 5", state.researchTicker, h1Result?.n ?? 0, "beta in annualized decimal", snapshot.manifest.evaluationId)}<h3>Lag sensitivity</h3><div class="table-scroll"><table class="data-table"><caption class="visually-hidden">H1 HAC lag sensitivity</caption><thead><tr><th scope="col">HAC maxlags</th><th scope="col">N</th><th scope="col">Beta</th><th scope="col">95% CI</th><th scope="col">p (raw)</th></tr></thead><tbody>${sensitivity.map((row) => `<tr><th scope="row">${row.hacMaxlags}${row.hacMaxlags === 5 ? " · primary" : " · sensitivity"}</th><td>${row.n}</td><td>${row.beta.toFixed(6)}</td><td>[${row.ci95.map((value) => value.toFixed(6)).join(", ")}]</td><td>${row.pRaw.toExponential(3)}</td></tr>`).join("")}</tbody></table></div>${sourceFooter("H1_sensitivity.csv", "Train", `${state.researchTicker} · HAC 5/10/20`, sensitivity.length, "stored statistics", snapshot.manifest.evaluationId)}</section>
    <section class="analysis-card"><div class="section-card-heading"><div><span class="section-overline">H2 / H3 · TEST ONLY · MACRO</span><h3>Hypothesis results</h3><p>Effect, paired N, p-value, CI, decision, and method are source fields; no inference is run in the browser.</p></div></div>${h2h3Table}${sourceFooter("hypothesis_results.csv", "Test", "H2/H3 · MACRO", macroHypotheses.length, "annualized decimal effect / p-value", snapshot.manifest.evaluationId)}<h3>Bootstrap diagnostics · sensitivity</h3>${bootstrapTable}${sourceFooter("bootstrap_diagnostics.csv", "Test · sensitivity", "H2/H3 · block lengths 5 and 20", bootstrapRows.length, "annualized decimal effect / p-value", snapshot.manifest.evaluationId)}</section>
    <section class="analysis-card"><div class="section-card-heading"><div><span class="section-overline">HIGH-VOLATILITY TEST SUBSET</span><h3>${state.researchTicker} · Train p80 threshold</h3><p>Threshold is learned and pinned from Train; rows with n=0 remain unscored.</p></div></div>${highVolTable}${sourceFooter("high_volatility_metrics.csv", "Test", `${state.researchTicker} · B0–B3`, highVol.length, `annualized decimal · threshold ${state.unit}`, snapshot.manifest.evaluationId)}</section><section class="limitation-card"><span class="limitation-mark">i</span><p>These are results from one frozen experiment snapshot. p-values, confidence intervals, and decisions are displayed from the saved source and are not recomputed here.</p></section></div>`;
}

function forecastExplorerChart(rows: ForecastAuditRow[], state: ViewState): string {
  if (rows.length === 0) return emptyState("ไม่พบแถวตามตัวกรอง", "ลองเปลี่ยน split, model, date range หรือ target status.");
  const dates = [...new Set(rows.map((row) => row.predictionDate))].sort();
  const dateIndex = new Map(dates.map((date, index) => [date, index]));
  const selectedModels = state.forecastModels;
  const points = rows.flatMap((row) => {
    const forecast = row.forecastStatus === "VALID" ? row.predictedVolAnnualized : null;
    const actual = forecastActual(row, state.snapshot as Extract<SnapshotState, { status: "ready" }>).actual;
    return [forecast, actual].filter((value): value is number => value !== null && Number.isFinite(value));
  });
  const maxValue = Math.max(...points, 0.000001);
  const x = (date: string) => 58 + (dateIndex.get(date) ?? 0) * (790 / Math.max(dates.length - 1, 1));
  const y = (value: number) => 210 - value / maxValue * 170;
  const series = selectedModels.map((model) => {
    const values = rows.filter((row) => row.modelName === model && row.forecastStatus === "VALID" && row.predictedVolAnnualized !== null);
    const polyline = values.map((row) => `${x(row.predictionDate)},${y(row.predictedVolAnnualized as number)}`).join(" ");
    const circles = values.map((row) => `<circle cx="${x(row.predictionDate)}" cy="${y(row.predictedVolAnnualized as number)}" r="2.1" fill="${modelColors[model]}"><title>${escapeHtml(row.predictionDate)} · ${modelId(model)} forecast ${formatVol(row.predictedVolAnnualized, state.unit)} · ${escapeHtml(row.predictionId)}</title></circle>`).join("");
    return `<g><polyline points="${polyline}" fill="none" stroke="${modelColors[model]}" stroke-width="1.8"/>${circles}</g>`;
  }).join("");
  const actualByDate = new Map<string, { actual: number; row: ForecastAuditRow }>();
  for (const row of rows) {
    const actual = forecastActual(row, state.snapshot as Extract<SnapshotState, { status: "ready" }>).actual;
    if (actual !== null && !actualByDate.has(row.predictionDate)) actualByDate.set(row.predictionDate, { actual, row });
  }
  const actualPoints = [...actualByDate].sort(([left], [right]) => left.localeCompare(right));
  const actualLine = actualPoints.map(([date, point]) => `${x(date)},${y(point.actual)}`).join(" ");
  const actualCircles = actualPoints.map(([date, point]) => `<circle cx="${x(date)}" cy="${y(point.actual)}" r="2.8" fill="#34455e"><title>${escapeHtml(date)} · Actual ${formatVol(point.actual, state.unit)} · ${escapeHtml(point.row.targetEndDate)}</title></circle>`).join("");
  const legends = [...selectedModels.map((model) => `<span><i style="--legend-color:${modelColors[model]}"></i>${modelId(model)} · forecast</span>`), `<span><i style="--legend-color:#34455e"></i>Actual · mature only</span>`].join("");
  const tableRows = rows.map((row) => {
    const actual = forecastActual(row, state.snapshot as Extract<SnapshotState, { status: "ready" }>).actual;
    const forecast = row.forecastStatus === "VALID" ? row.predictedVolAnnualized : null;
    const pendingTooltip = row.evaluationStatus === "PENDING_LABEL" ? "Not scored: target pending by cutoff" : "";
    return `<tr><th scope="row">${escapeHtml(row.predictionDate)}</th><td>${escapeHtml(row.ticker)}</td><td>${modelId(row.modelName)}</td><td>${formatVol(forecast, state.unit)}</td><td title="${pendingTooltip}">${formatVol(actual, state.unit)}</td><td title="${pendingTooltip}">${pendingTooltip ? `<span title="${pendingTooltip}" aria-label="${pendingTooltip}">Pending · not scored</span>` : row.evaluationStatus === "EVALUABLE" ? "Evaluable" : escapeHtml(row.evaluationStatus)}</td></tr>`;
  });
  return `<div class="chart-scroll"><svg class="forecast-chart" viewBox="0 0 880 246" role="img" aria-label="Forecast and mature actual RV5 by recorded prediction date"><line x1="58" y1="210" x2="848" y2="210" class="chart-axis"/><line x1="58" y1="38" x2="58" y2="210" class="chart-axis"/><line x1="58" y1="124" x2="848" y2="124" class="chart-gridline"/><text x="5" y="42" class="chart-date-label">${formatVol(maxValue, state.unit, 2)}</text><text x="58" y="231" class="chart-date-label">${escapeHtml(dates[0])}</text><text x="848" y="231" text-anchor="end" class="chart-date-label">${escapeHtml(dates[dates.length - 1])}</text>${series}<polyline points="${actualLine}" fill="none" stroke="#34455e" stroke-width="1.8" stroke-dasharray="5 4"/>${actualCircles}</svg></div><div class="chart-legend">${legends}</div>${actualPoints.length === 0 ? '<p class="pending-note"><span>i</span> Forecast recorded; actual unavailable by cutoff for the selected rows.</p>' : ""}${chartDataTable(`Filtered forecast chart values for ${state.forecastTicker} in ${state.forecastSplit}`, ["Prediction date", "Ticker", "Model", "Forecast", "Actual · evaluable only", "Label status"], tableRows)}`;
}

function forecastExplorerPage(state: ViewState): string {
  const snapshot = state.snapshot;
  if (snapshot.status === "loading") return loadingState();
  if (snapshot.status === "missing") return emptyState("Recorded sessions ยังไม่พร้อม", "เมื่อ snapshot files ไม่ครบ จะไม่สร้างวันที่หรือ forecast ขึ้นมาแทน");
  if (snapshot.status === "error") return errorState(snapshot.message);
  const filter: ForecastFilter = {
    split: state.forecastSplit, ticker: state.forecastTicker, models: state.forecastModels,
    status: state.forecastStatus, from: state.forecastFrom, to: state.forecastTo,
  };
  const rows = filterForecastRows(snapshot.forecasts, filter);
  const tableRows = rows.slice(0, 100).map((row) => {
    const { actual, error } = forecastActual(row, snapshot);
    const forecast = row.forecastStatus === "VALID" ? row.predictedVolAnnualized : null;
    const status = row.evaluationStatus === "PENDING_LABEL" ? "Pending · not scored" : row.evaluationStatus === "EVALUABLE" ? "Evaluable" : row.evaluationStatus;
    const pendingTooltip = row.evaluationStatus === "PENDING_LABEL" ? "Not scored: target pending by cutoff" : "";
    return `<tr><td>${escapeHtml(row.predictionDate)}</td><td>${escapeHtml(row.ticker)}</td><td><span class="model-chip" style="--model-color:${modelColors[row.modelName]}">${modelId(row.modelName)}</span></td><td>${formatVol(forecast, state.unit)}</td><td title="${pendingTooltip}">${formatVol(actual, state.unit)}</td><td title="${pendingTooltip}">${formatVol(error, state.unit)}</td><td><span class="status-chip ${row.evaluationStatus === "PENDING_LABEL" ? "status-pending" : row.evaluationStatus === "EVALUABLE" ? "status-evaluable" : "status-neutral"}" ${pendingTooltip ? `title="${pendingTooltip}" aria-label="${pendingTooltip}"` : ""}>${escapeHtml(status)}</span></td><td>${escapeHtml(row.forecastStatus)}</td><td title="${escapeHtml(row.predictionId)}"><button class="table-link" type="button" data-action="open-session" data-prediction-id="${escapeHtml(row.predictionId)}">${escapeHtml(row.predictionId.slice(0, 12))}…</button></td><td>${escapeHtml(row.targetEndDate)}</td></tr>`;
  }).join("");
  const modelOptions = modelNames.map((model) => `<option value="${model}" ${state.forecastModels.includes(model) ? "selected" : ""}>${modelId(model)} · ${escapeHtml(modelLabel(model))}</option>`).join("");
  const selectedModelsLabel = state.forecastModels.map(modelId).join(", ") || "none";
  return `<div class="page-stack forecasts-page">
    <section class="analysis-card"><div class="section-card-heading"><div><span class="section-overline">RECORDED FORECASTS · NO INFERENCE</span><h2 class="analysis-title">Forecast Explorer</h2><p>ตัวกรองเลือกเฉพาะแถวที่บันทึกไว้ใน audit; ไม่มีการเรียก Train หรือ Replay<br>กด Export CSV และ Export metadata แยกกัน โดยคงตัวกรองเดิมไว้เพื่อให้ hash ตรงกัน</p></div><div class="forecast-export-actions"><span class="readonly-pill">${icon("lock", 14)} ${snapshot.manifest.strictCutoff} cutoff</span><button class="button button-secondary export-button" type="button" data-action="export-forecasts-csv" ${rows.length === 0 ? "disabled" : ""}>Export CSV</button><button class="button button-secondary export-button" type="button" data-action="export-forecasts-metadata" ${rows.length === 0 ? "disabled" : ""}>Export metadata</button></div></div>
      <div class="forecast-filters"><label class="field-label">Split<select data-field="forecast-split"><option value="test" ${state.forecastSplit === "test" ? "selected" : ""}>Test</option><option value="validation" ${state.forecastSplit === "validation" ? "selected" : ""}>Validation</option></select></label><label class="field-label">Asset<select data-field="forecast-ticker">${tickerNames.map((ticker) => `<option value="${ticker}" ${state.forecastTicker === ticker ? "selected" : ""}>${ticker}</option>`).join("")}</select></label><label class="field-label">Models<select data-field="forecast-models" multiple size="4" aria-describedby="model-filter-help">${modelOptions}</select><small id="model-filter-help">เลือกหลายโมเดลได้ด้วย Ctrl/Command</small></label><label class="field-label">Label status<select data-field="forecast-status"><option value="all" ${state.forecastStatus === "all" ? "selected" : ""}>All</option><option value="mature" ${state.forecastStatus === "mature" ? "selected" : ""}>Mature / evaluable</option><option value="pending" ${state.forecastStatus === "pending" ? "selected" : ""}>Pending</option><option value="invalid" ${state.forecastStatus === "invalid" ? "selected" : ""}>Invalid / missing</option></select></label><label class="field-label">From<input type="date" data-field="forecast-from" value="${escapeHtml(state.forecastFrom)}"></label><label class="field-label">To<input type="date" data-field="forecast-to" value="${escapeHtml(state.forecastTo)}"></label></div>
      <div class="chart-heading-row"><div><h3>${state.forecastSplit} · ${state.forecastTicker}</h3><p>Target window t+1…t+5 trading sessions · annualized volatility</p></div><span class="result-count">${rows.length.toLocaleString()} rows · ${selectedModelsLabel}</span></div>${forecastExplorerChart(rows, state)}${sourceFooter("forecast_audit.csv + evaluation.csv", state.forecastSplit, `${state.forecastTicker} · ${selectedModelsLabel}`, rows.length, `annualized decimal (${state.unit})`, snapshot.manifest.evaluationId)}</section>
    <section class="analysis-card"><div class="section-card-heading"><div><span class="section-overline">FILTERED SOURCE ROWS</span><h3>ข้อมูลราย observation</h3><p>แสดง ${Math.min(rows.length, 100).toLocaleString()} จาก ${rows.length.toLocaleString()} แถวแรก เรียงตามวันและโมเดล</p></div><span class="pill pill-neutral">Source columns retained</span></div>${rows.length === 0 ? emptyState("ไม่พบแถวตามตัวกรอง", "ลองปรับตัวกรองด้านบน.") : `<div class="table-scroll"><table class="data-table forecast-data-table"><caption class="visually-hidden">Filtered recorded forecasts for ${state.forecastTicker} in ${state.forecastSplit}</caption><thead><tr><th scope="col">Prediction date</th><th scope="col">Ticker</th><th scope="col">Model</th><th scope="col">Forecast</th><th scope="col">Actual</th><th scope="col">Absolute error</th><th scope="col">Evaluation</th><th scope="col">Forecast</th><th scope="col">Prediction ID</th><th scope="col">Target end</th></tr></thead><tbody>${tableRows}</tbody></table></div>`}${sourceFooter("forecast_audit.csv + evaluation.csv", state.forecastSplit, `${state.forecastTicker} · ${selectedModelsLabel}`, rows.length, `annualized decimal (${state.unit})`, snapshot.manifest.evaluationId)}</section>
    ${sessionCard(state)}
  </div>`;
}

function provenancePage(snapshot: SnapshotState): string {
  if (snapshot.status === "loading") return loadingState();
  if (snapshot.status !== "ready") return emptyState("ยังไม่มี provenance ที่ผ่านการตรวจ", "ซ่อน Source IDs และ checksums จนกว่า adapter จะยืนยัน snapshot ได้");
  const { manifest } = snapshot;
  const files = Object.entries(manifest.files).map(([, file]) => `<div class="source-file-row"><div class="file-type-mark">CSV</div><div class="source-file-details"><strong>${escapeHtml(file.path)}</strong><small>${file.rowCount.toLocaleString()} source rows · ${file.headers.length} columns</small></div><code>${escapeHtml(file.sha256)}</code></div>`).join("");
  return `<div class="page-stack"><section class="provenance-summary-card"><div class="provenance-summary-top"><div><span class="section-overline">FROZEN SOURCE</span><h2>ที่มาและขอบเขต</h2></div><span class="verified-badge">${icon("check", 13)} SOURCE VERIFIED</span></div><p>ไฟล์ CSV ที่แสดงมาจาก handoff ZIP ที่ pin ไว้ ตรวจ outer SHA-256, manifest ภายใน ZIP และ member hashes ก่อนอ่านข้อมูล</p><div class="provenance-pills"><span class="pill pill-neutral">${escapeHtml(manifest.mode)}</span><span class="pill pill-pending">Report approval pending</span><span class="pill pill-neutral">Point-in-time source not verified</span></div><div class="identity-pair"><span>Evaluation ID</span><code>${escapeHtml(manifest.evaluationId)}</code></div><div class="identity-pair"><span>Replay ID</span><code>${escapeHtml(manifest.replayId)}</code></div><div class="identity-pair"><span>Source repository</span><a href="https://github.com/${escapeHtml(manifest.sourceRepository)}" target="_blank" rel="noopener noreferrer">${escapeHtml(manifest.sourceRepository)}</a></div><div class="identity-pair"><span>Handoff commit</span><a href="https://github.com/${escapeHtml(manifest.sourceRepository)}/commit/${escapeHtml(manifest.sourceHandoffCommit)}" target="_blank" rel="noopener noreferrer"><code>${escapeHtml(manifest.sourceHandoffCommit)}</code></a></div><div class="identity-pair"><span>Baseline commit</span><code>${escapeHtml(manifest.baselineGitCommit)}</code></div><div class="identity-pair"><span>ZIP SHA-256</span><code>${escapeHtml(manifest.sourceZipSha256)}</code></div><div class="identity-pair"><span>Strict cutoff</span><code>${escapeHtml(manifest.strictCutoff)}</code></div><div class="identity-pair"><span>Report approval</span><strong>PENDING · not approved</strong></div></section><section class="source-file-card"><div class="section-card-heading"><div><span class="section-overline">PUBLIC DATA SUBSET</span><h3>ไฟล์ CSV ที่ใช้โดย dashboard</h3></div><span class="pill pill-neutral">CSV · READ ONLY</span></div>${files}<p class="source-footnote">Manifest JSON และ handoff identity ใช้ตอน build เพื่อตรวจสอบ IDs; hash ของไฟล์ export แสดงใน metadata แยกจาก hashes ของ source CSV</p></section><section class="limitation-card"><span class="limitation-mark">i</span><p>Snapshot นี้เป็นผลจาก Simulated Historical Replay ไม่ยืนยันว่าข้อมูลตลาดแต่ละรายการเข้าถึงได้ ณ วันที่จำลอง และยังไม่ใช่รายงานที่ได้รับอนุมัติ</p></section></div>`;
}

function guidePage(): string {
  const definitions = [
    ["RV5 · annualized volatility", "ความผันผวนจากผลตอบแทนจริงใน 5 วันซื้อขายถัดไป (Forward RV5) แสดงเป็น annualized decimal หรือ percent; ทั้งสองแบบเป็นหน่วยเดียวกันคนละรูปแบบ"],
    ["Pending label · ป้ายที่ยังไม่ครบ", "มี forecast แล้ว แต่ข้อมูล target ยังไม่ครบช่วง 5 วัน ณ strict cutoff จึงแสดง actual/error เป็นค่าว่าง และยังไม่ให้คะแนน"],
    ["B0–B3 · model family", "B0 คือ constant baseline, B1 คือ rolling 20D baseline, B2 คือ Static SGD และ B3 คือ Online SGD; dashboard อ่านค่าที่ Stage 06 บันทึกไว้"],
    ["Split · Train / Validation / Test", "Train ใช้สร้างหรือศึกษารูปแบบ, Validation ใช้เลือกการตั้งค่า และ Test ใช้ประเมินชุด holdout; อย่านำผล Test ไปเลือกหรือปรับ model"],
    ["Leakage · การรั่วไหลของข้อมูล", "เกิดเมื่อข้อมูลจากอนาคตหรือ target ที่ควรเก็บไว้ทดสอบไหลไปสู่การสร้าง feature หรือเลือก model; หน้านี้ไม่ยืนยันเรื่องดังกล่าวเพิ่มเติมนอกเหนือจาก source audit"],
    ["ADWIN · drift monitor", "ตัวตรวจการเปลี่ยนแปลงของ error ในสตรีม; หน้านี้แสดง error และ drift/alert flags ที่บันทึกไว้เท่านั้น ไม่มี rule ที่สร้าง alert ใหม่ใน browser"],
    ["MAE / RMSE · error scores", "MAE คือค่าเฉลี่ย absolute error; RMSE ให้น้ำหนัก error ที่ใหญ่กว่า ทั้งคู่ใช้หน่วย annualized volatility และอ่านจาก source ที่บันทึกไว้"],
    ["Portfolio covariance · ความแปรปรวนร่วม", "เมทริกซ์ที่เก็บความแปรปรวนและ covariance ของ forecast ทั้งสามสินทรัพย์; Portfolio Lab เปลี่ยนได้เฉพาะน้ำหนักในสูตร √(wᵀΣw) ของแถวที่เลือก"],
    ["MACRO · aggregate", "ค่า aggregate ที่ Stage 06 บันทึกไว้สำหรับ ETF panel; dashboard ไม่สร้างค่า RMSE หรือคำนวณค่า aggregate ใหม่ใน browser"],
    ["Simulated Historical Replay", "ผลย้อนหลังจาก frozen snapshot ไม่ยืนยันว่า source market data เข้าถึงได้จริง ณ วันจำลอง และไม่ใช่ข้อมูลสด"],
  ];
  return `<div class="page-stack"><section class="guide-intro"><span class="section-overline">READ THE EVIDENCE</span><h2>วิธีอ่านผลโดยไม่ตีความเกินข้อมูล</h2><p>Dashboard นี้เป็นพื้นที่สำรวจผลจากการทดลองที่ตรึงไว้ ตัวกรองและ Portfolio Lab ทำงานกับข้อมูลใน snapshot ที่ตรวจแล้วเท่านั้น</p></section><div class="glossary-grid">${definitions.map(([term, definition], index) => `<article class="glossary-card"><span class="glossary-number">${String(index + 1).padStart(2, "0")}</span><h3>${term}</h3><p>${definition}</p></article>`).join("")}</div><div class="limitation-card"><span class="limitation-mark">!</span><p>ผล Test เป็นหลักฐานจาก frozen sample เท่านั้น ไม่ยืนยัน point-in-time source availability ไม่รับรองผลในอนาคต และไม่ใช่คำแนะนำซื้อขาย</p></div></div>`;
}

function pageContent(state: ViewState): string {
  if (state.routePath === "/overview") return overviewPage(state);
  if (state.routePath === "/forecasts") return forecastExplorerPage(state);
  if (state.routePath === "/provenance") return provenancePage(state.snapshot);
  if (state.routePath === "/guide") return guidePage();
  if (state.routePath === "/models") return modelsPage(state);
  if (state.routePath === "/portfolio") return portfolioPage(state);
  if (state.routePath === "/drift") return driftPage(state);
  return researchPage(state);
}

function shell(state: ViewState): string {
  const route = routes.find((item) => item.path === state.routePath) ?? routes[0];
  const identity = state.snapshot.status === "ready" ? "VERIFIED REVIEW SNAPSHOT" : state.snapshot.status === "loading" ? "VERIFYING SNAPSHOT" : "SNAPSHOT NOT LOADED";
  const snapshotId = state.snapshot.status === "ready" ? state.snapshot.manifest.evaluationId : "ID withheld until verification";
  const sidebarLinks = routes.map((item) => navLink(item, item.path === state.routePath)).join("");
  const mobilePrimary = routes.slice(0, 3).map((item) => navLink(item, item.path === state.routePath)).join("");
  const secondaryRoutes = routes.slice(3);
  const mobileDrawer = state.mobileMenuOpen ? `<div class="mobile-nav-overlay" data-action="close-menu"><nav class="mobile-drawer" aria-label="เมนูทั้งหมด"><div class="drawer-heading"><strong>ไปยังหน้า</strong><button class="icon-button" type="button" data-action="close-menu" aria-label="ปิดเมนู">×</button></div>${sidebarLinks}</nav></div>` : "";
  const morePanel = state.moreOpen ? `<div class="mobile-more-panel" aria-label="More pages">${secondaryRoutes.map((item) => navLink(item, item.path === state.routePath)).join("")}</div>` : "";
  return `<div class="app-frame">
    <aside class="sidebar" aria-label="Main navigation"><div class="brand-lockup"><div class="brand-mark">A</div><div><strong>Adaptive Risk Lab</strong><span>DEDS · RESEARCH WORKBENCH</span></div></div><div class="sidebar-section-label">WORKSPACE</div><nav class="sidebar-nav">${sidebarLinks}</nav><div class="sidebar-bottom"><div class="sidebar-status-mark">${icon("lock", 16)}<span>Read-only snapshot</span></div><div class="sidebar-caption">ผลลัพธ์ที่ตรึงไว้สำหรับทบทวน<br />ไม่มีการเรียก ML pipeline</div><span class="version-label">D1–D2 FOUNDATION</span></div></aside>
    <div class="app-main"><header class="mobile-topbar"><a class="mobile-brand" href="#/overview"><span class="brand-mark small">A</span><strong>Adaptive Risk Lab</strong></a><button class="icon-button mobile-menu-button" type="button" aria-label="เปิดเมนู" aria-expanded="${state.mobileMenuOpen}" data-action="toggle-menu">${icon("menu")}</button></header>${mobileDrawer}<main class="workspace"><div class="top-identity-row"><div class="breadcrumbs"><span>DEDS</span><span class="breadcrumb-separator">/</span><strong>Adaptive Portfolio Risk Lab</strong></div><div class="identity-state"><span class="identity-dot ${state.snapshot.status}"></span>${identity}</div></div><div class="page-heading-row"><div><div class="page-kicker">RESEARCH WORKBENCH <span>·</span> FROZEN DATASET</div><h1>${escapeHtml(route.thai)}</h1><p>${escapeHtml(route.description)}</p></div><div class="page-tools"><label class="unit-control"><span>Units</span><select aria-label="Display units" data-field="unit"><option value="decimal" ${state.unit === "decimal" ? "selected" : ""}>Decimal</option><option value="percent" ${state.unit === "percent" ? "selected" : ""}>Percent</option></select></label><button class="snapshot-id-button" type="button" title="คัดลอก Evaluation ID และ Replay ID ที่ pin ไว้" data-action="copy-id"><span class="snapshot-id-icon">${icon("lock", 15)}</span><span><small>PINNED EVALUATION</small><strong>${escapeHtml(snapshotId.slice(0, 12))}${state.snapshot.status === "ready" ? "…" : ""}</strong></span><span class="copy-hint">COPY</span></button></div></div>${snapshotBanner(state.snapshot)}${state.snapshot.status === "missing" ? errorState(state.snapshot.message, "ยังไม่มีไฟล์ snapshot ที่ตรวจสอบแล้ว") : state.snapshot.status === "error" ? errorState(state.snapshot.message) : ""}<div class="page-content">${pageContent(state)}</div><footer class="app-footer"><span>DEDS · Adaptive Portfolio Risk Lab</span><span>${icon("lock", 13)} Read-only · No live forecast</span></footer></main><nav class="mobile-bottom-nav" aria-label="Navigation">${mobilePrimary}<button class="nav-link mobile-more-link${state.moreOpen ? " active" : ""}" type="button" aria-expanded="${state.moreOpen}" data-action="toggle-more">${icon("menu", 19)}<span>More</span></button></nav>${morePanel}</div>
  </div>`;
}

function render(root: HTMLElement, state: ViewState): void {
  root.innerHTML = shell(state);
  const route = routes.find((item) => item.path === state.routePath);
  document.title = `${route?.label ?? "Overview"} · Adaptive Portfolio Risk Lab`;
}

function updatePortfolioWeightPreview(root: HTMLElement, state: ViewState, changedIndex?: number, changedControl?: "number" | "slider"): void {
  if (state.snapshot.status !== "ready" || state.routePath !== "/portfolio") return;
  const sliders = root.querySelectorAll<HTMLInputElement>('input[data-field="portfolio-weight-slider"]');
  const numbers = root.querySelectorAll<HTMLInputElement>('input[data-field="portfolio-weight"]');
  const percentages = root.querySelectorAll<HTMLOutputElement>("output[data-portfolio-weight-percent]");
  state.portfolioWeights.forEach((weight, index) => {
    const valid = Number.isFinite(weight) && weight >= 0 && weight <= 1;
    if (valid) sliders[index].value = String(weight);
    sliders[index].setAttribute("aria-valuetext", `${Math.round(Number(sliders[index].value) * 100)}% of portfolio`);
    percentages[index].textContent = valid ? `${Math.round(weight * 100)}%` : "Invalid";
    if (changedControl === "slider" && changedIndex === index || changedControl !== "number" || changedIndex !== index) {
      numbers[index].value = Number.isFinite(weight) ? String(weight) : "";
    }
  });
  const status = root.querySelector<HTMLElement>("[data-portfolio-weight-status]");
  const result = root.querySelector<HTMLElement>("[data-portfolio-whatif]");
  if (!status || !result) return;
  const total = state.portfolioWeights.reduce((sum, weight) => sum + weight, 0);
  try {
    const row = selectedPortfolioRow(state.snapshot, state.portfolioDate, state.portfolioModel);
    if (!row?.covariance) throw new Error("No verified covariance row is selected");
    const value = computePortfolioVolatility(row.covariance, state.portfolioWeights);
    status.textContent = `Weight total ${(total * 100).toFixed(1)}%`;
    status.classList.remove("weight-error");
    status.setAttribute("role", "status");
    result.textContent = formatVol(value, state.unit);
  } catch (error) {
    status.textContent = `No result · ${error instanceof Error ? error.message : "Weights are invalid"}`;
    status.classList.add("weight-error");
    status.setAttribute("role", "alert");
    result.textContent = "—";
  }
}

async function reload(root: HTMLElement, state: ViewState): Promise<void> {
  state.snapshot = { status: "loading" };
  state.attempt += 1;
  render(root, state);
  state.snapshot = await loadSnapshot();
  render(root, state);
}

function downloadTextFile(filename: string, contents: string, mimeType: string): void {
  const url = URL.createObjectURL(new Blob([contents], { type: mimeType }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function prepareForecastExport(state: ViewState) {
  if (state.snapshot.status !== "ready") return;
  const snapshot = state.snapshot;
  const filter: ForecastFilter = { split: state.forecastSplit, ticker: state.forecastTicker, models: state.forecastModels, status: state.forecastStatus, from: state.forecastFrom, to: state.forecastTo };
  const rows = filterForecastRows(snapshot.forecasts, filter);
  if (rows.length === 0) return;
  const csv = buildForecastCsv(rows, snapshot.evaluations);
  const sourceFiles = ["forecastAudit", "evaluation"] as const;
  return { snapshot, filter, rows, csv, sourceFiles };
}

function exportForecastCsv(state: ViewState): void {
  const prepared = prepareForecastExport(state);
  if (!prepared) return;
  downloadTextFile("filtered_forecasts.csv", prepared.csv, "text/csv;charset=utf-8");
}

async function exportForecastMetadata(state: ViewState): Promise<void> {
  const prepared = prepareForecastExport(state);
  if (!prepared) return;
  const metadata = await buildExportMetadata({
    manifest: prepared.snapshot.manifest,
    filters: prepared.filter,
    rowCount: prepared.rows.length,
    sourceFiles: prepared.sourceFiles.map((key) => ({ path: prepared.snapshot.manifest.files[key].path, sha256: prepared.snapshot.manifest.files[key].sha256 })),
  }, prepared.csv);
  downloadTextFile("filtered_forecasts_metadata.json", `${JSON.stringify(metadata, null, 2)}\n`, "application/json;charset=utf-8");
}

export function startApp(root: HTMLElement): void {
  const state: ViewState = {
    snapshot: { status: "loading" },
    routePath: currentRoute(),
    mobileMenuOpen: false,
    moreOpen: false,
    ticker: "SPY",
    model: "ONLINE_SGD",
    sessionIndex: 0,
    unit: "percent",
    metric: "mae",
    modelTicker: "MACRO",
    forecastTicker: "SPY",
    forecastSplit: "test",
    forecastModels: ["ONLINE_SGD"],
    forecastStatus: "all",
    forecastFrom: "",
    forecastTo: "",
    portfolioDate: "",
    portfolioModel: "ONLINE_SGD",
    portfolioWeights: [0.5, 0.3, 0.2],
    driftTicker: "SPY",
    driftModel: "ONLINE_SGD",
    driftFrom: "",
    driftTo: "",
    researchTicker: "SPY",
    attempt: 0,
  };

  const updateRoute = () => {
    state.routePath = currentRoute();
    state.mobileMenuOpen = false;
    state.moreOpen = false;
    state.sessionIndex = 0;
    render(root, state);
  };
  window.addEventListener("hashchange", updateRoute);
  root.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const button = target?.closest<HTMLElement>("[data-action], [data-route]");
    if (!button) return;
    const route = button.dataset.route;
    if (route) { window.location.hash = route; return; }
    switch (button.dataset.action) {
      case "toggle-menu": state.mobileMenuOpen = !state.mobileMenuOpen; render(root, state); break;
      case "close-menu": if (target === button || button.classList.contains("mobile-nav-overlay")) { state.mobileMenuOpen = false; render(root, state); } break;
      case "toggle-more": state.moreOpen = !state.moreOpen; render(root, state); break;
      case "previous": state.sessionIndex = Math.max(0, state.sessionIndex - 1); render(root, state); break;
      case "next": state.sessionIndex += 1; render(root, state); break;
      case "reset": state.sessionIndex = 0; render(root, state); break;
      case "open-session": {
        const predictionId = button.dataset.predictionId;
        if (state.snapshot.status === "ready" && predictionId) {
          const row = state.snapshot.sessions.find((session) => session.predictionId === predictionId);
          if (row) {
            state.ticker = row.ticker;
            state.model = row.modelName;
            state.sessionIndex = selectRecordedSessions(state.snapshot.sessions, row.ticker, row.modelName).findIndex((session) => session.predictionId === predictionId);
            render(root, state);
          }
        }
        break;
      }
      case "retry": void reload(root, state); break;
      case "copy-id": {
        if (state.snapshot.status === "ready") void navigator.clipboard?.writeText(`Evaluation ID: ${state.snapshot.manifest.evaluationId}\nReplay ID: ${state.snapshot.manifest.replayId}`);
        break;
      }
      case "export-forecasts-csv": exportForecastCsv(state); break;
      case "export-forecasts-metadata": void exportForecastMetadata(state); break;
    }
  });
  root.addEventListener("change", (event) => {
    const target = event.target;
    if (target instanceof HTMLSelectElement) {
      if (target.dataset.field === "ticker" && tickerNames.includes(target.value as Ticker)) { state.ticker = target.value as Ticker; state.sessionIndex = 0; }
      if (target.dataset.field === "model" && modelNames.includes(target.value as ModelName)) { state.model = target.value as ModelName; state.sessionIndex = 0; }
      if (target.dataset.field === "date") state.sessionIndex = Number(target.value);
      if (target.dataset.field === "unit" && ["decimal", "percent"].includes(target.value)) state.unit = target.value as DisplayUnit;
      if (target.dataset.field === "metric" && ["mae", "rmse"].includes(target.value)) state.metric = target.value as MetricName;
      if (target.dataset.field === "model-ticker" && metricTickerNames.includes(target.value as Ticker | "MACRO")) state.modelTicker = target.value as Ticker | "MACRO";
      if (target.dataset.field === "coverage-ticker" && tickerNames.includes(target.value as Ticker)) state.forecastTicker = target.value as Ticker;
      if (target.dataset.field === "forecast-ticker" && tickerNames.includes(target.value as Ticker)) state.forecastTicker = target.value as Ticker;
      if (target.dataset.field === "forecast-split" && ["test", "validation"].includes(target.value)) state.forecastSplit = target.value as "test" | "validation";
      if (target.dataset.field === "forecast-status" && ["all", "mature", "pending", "invalid"].includes(target.value)) state.forecastStatus = target.value as ForecastFilter["status"];
      if (target.dataset.field === "forecast-models") state.forecastModels = Array.from(target.selectedOptions).map((option) => option.value).filter((model): model is ModelName => modelNames.includes(model as ModelName));
      if (target.dataset.field === "portfolio-date") state.portfolioDate = target.value;
      if (target.dataset.field === "portfolio-model" && modelNames.includes(target.value as ModelName)) state.portfolioModel = target.value as ModelName;
      if (target.dataset.field === "drift-ticker" && tickerNames.includes(target.value as Ticker)) state.driftTicker = target.value as Ticker;
      if (target.dataset.field === "drift-model" && modelNames.includes(target.value as ModelName)) state.driftModel = target.value as ModelName;
      if (target.dataset.field === "research-ticker" && tickerNames.includes(target.value as Ticker)) state.researchTicker = target.value as Ticker;
    }
    if (target instanceof HTMLInputElement) {
      if (target.dataset.field === "forecast-from") state.forecastFrom = target.value;
      if (target.dataset.field === "forecast-to") state.forecastTo = target.value;
      if (target.dataset.field === "drift-from") state.driftFrom = target.value;
      if (target.dataset.field === "drift-to") state.driftTo = target.value;
      if (target.dataset.field === "portfolio-weight" || target.dataset.field === "portfolio-weight-slider") {
        const index = Number(target.dataset.index);
        if (Number.isInteger(index) && index >= 0 && index < 3) {
          state.portfolioWeights[index] = target.value.trim() ? Number(target.value) : Number.NaN;
          updatePortfolioWeightPreview(root, state, index, target.dataset.field === "portfolio-weight-slider" ? "slider" : "number");
          return;
        }
      }
    }
    render(root, state);
  });
  root.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement) || (target.dataset.field !== "portfolio-weight" && target.dataset.field !== "portfolio-weight-slider")) return;
    const index = Number(target.dataset.index);
    if (!Number.isInteger(index) || index < 0 || index > 2) return;
    state.portfolioWeights[index] = target.value.trim() ? Number(target.value) : Number.NaN;
    updatePortfolioWeightPreview(root, state, index, target.dataset.field === "portfolio-weight-slider" ? "slider" : "number");
  });
  root.addEventListener("keydown", (event) => {
    if (!(event instanceof KeyboardEvent) || !(event.target instanceof Element) || !event.target.closest(".session-date-row")) return;
    if (event.key === "ArrowLeft") { event.preventDefault(); state.sessionIndex = Math.max(0, state.sessionIndex - 1); render(root, state); }
    if (event.key === "ArrowRight") { event.preventDefault(); state.sessionIndex += 1; render(root, state); }
  });
  if (!window.location.hash) window.location.hash = "/overview";
  render(root, state);
  void loadSnapshot().then((snapshot) => { state.snapshot = snapshot; render(root, state); });
}
