import { filterForecastRows, loadSnapshot, selectRecordedSessions, type SnapshotState } from "./data/loadSnapshot.js";
import { computePortfolioVolatility, portfolioRiskSourceDates, validateScenarioWeights, type PortfolioWeights } from "./data/portfolio.js";
import { resolveAsOfLabelView, selectSameDateForecasts } from "./data/replay.js";
import { modelId, type ForecastAuditRow, type ModelName, type Ticker } from "./data/schemas.js";
import { renderOtherPage } from "./stitchOther.js";
import { CANVA_PRESENTATION_URL } from "./config.js";

type Page = "overview" | "forecasts" | "replay" | "portfolio" | "models" | "monitoring" | "evidence";
type ReadySnapshot = Extract<SnapshotState, { status: "ready" }>;
type ForecastStatusFilter = "all" | "mature" | "pending" | "invalid";
const pages: Page[] = ["overview", "forecasts", "replay", "portfolio", "models", "monitoring", "evidence"];
const tickers: Ticker[] = ["SPY", "IEF", "GLD"];
const models: ModelName[] = ["CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD", "HAR_X_OLS"];
const tickerLabel: Record<Ticker, string> = { SPY: "SPY · หุ้นสหรัฐ", IEF: "IEF · Treasury", GLD: "GLD · ทองคำ" };
const modelLabel: Record<ModelName, string> = { CONSTANT_BASELINE: "B0 · Constant baseline", ROLLING_20D_BASELINE: "B1 · Rolling 20D", STATIC_SGD: "B2 · Static SGD", ONLINE_SGD: "B3 · Online SGD", HAR_X_OLS: "B4 · HAR-X (OLS)" };
const pageLabel: Record<Page, string> = {
  overview: "ภาพรวม", forecasts: "พยากรณ์", replay: "เล่นย้อนหลัง", portfolio: "ทดลองพอร์ต",
  models: "โมเดล", monitoring: "ติดตาม", evidence: "หลักฐาน",
};

interface State {
  snapshot: SnapshotState;
  page: Page;
  forecast: { split: "test" | "validation"; ticker: Ticker; model: ModelName; status: ForecastStatusFilter; from: string; to: string; asOf: string; reveal: boolean };
  replay: { ticker: Ticker; model: ModelName; date: string; asOf: string; reveal: boolean; view: "monthly" | "daily"; month: string; scale: "five-day" | "annualized" };
  portfolio: { model: ModelName; date: string; weights: PortfolioWeights };
}

function esc(value: unknown): string {
  return String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] ?? character);
}
function isTicker(value: string): value is Ticker { return tickers.includes(value as Ticker); }
function isModel(value: string): value is ModelName { return models.includes(value as ModelName); }
function currentPage(): Page {
  const id = window.location.hash.slice(1).split("?")[0]?.replace(/^\/+/, "");
  return pages.find((page) => page === id) ?? "portfolio";
}
function applyRouteSelection(state: State): void {
  const queryText = window.location.hash.split("?")[1] ?? "";
  const query = new URLSearchParams(queryText);
  const date = query.get("date");
  const ticker = query.get("ticker");
  const model = query.get("model");
  if (date) {
    state.portfolio.date = date;
    state.replay.date = date;
    state.replay.month = monthKey(date);
  }
  if (ticker && isTicker(ticker)) state.replay.ticker = ticker;
  if (model && isModel(model)) {
    state.portfolio.model = model;
    state.replay.model = model;
  }
}
function selectOptions(values: string[], labels: Record<string, string>, selected: string): string {
  return values.map((value) => "<option value=\"" + esc(value) + "\"" + (value === selected ? " selected" : "") + ">" + esc(labels[value] ?? value) + "</option>").join("");
}
function risk(value: number | null): string { return value === null || !Number.isFinite(value) ? "—" : (value * 100).toFixed(3) + "%"; }
function replayRisk(value: number | null, scale: State["replay"]["scale"]): string {
  if (value === null) return "—";
  return risk(scale === "five-day" ? value * Math.sqrt(5 / 252) : value);
}
function monthKey(date: string): string { return date.slice(0, 7); }
function monthLabel(key: string): string {
  const monthNames = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."];
  const [year, month] = key.split("-");
  const index = Number(month) - 1;
  return (monthNames[index] ?? key) + " " + year;
}
function statusClass(row: ForecastAuditRow): string {
  return row.evaluationStatus === "PENDING_LABEL" ? "st-row-status st-pending"
    : row.evaluationStatus === "EVALUABLE" ? "st-row-status st-evaluable" : "st-row-status st-neutral";
}
function labelValues(row: ForecastAuditRow, snapshot: ReadySnapshot, asOf: string, reveal: boolean): { actual: number | null; error: number | null; text: string } {
  if (row.split === "test") {
    const view = resolveAsOfLabelView(row, asOf, reveal, snapshot.evaluations.get(row.predictionId));
    if (view.status === "revealed") return { actual: view.actual, error: view.absoluteError, text: "Actual แสดงแล้ว" };
    if (view.status === "source-pending") return { actual: null, error: null, text: "Pending · ยังไม่มี Actual" };
    if (view.status === "awaiting-target-end") return { actual: null, error: null, text: "รอ target ครบ" };
    if (view.status === "eligible-reveal-required") return { actual: null, error: null, text: "ครบกำหนด · กดเปิด Actual" };
    return { actual: null, error: null, text: "ต้นทางประเมินไม่ได้" };
  }
  if (row.evaluationStatus === "PENDING_LABEL" || row.labelStatus === "PENDING") return { actual: null, error: null, text: "Pending · ยังไม่มี Actual" };
  if (row.evaluationStatus !== "EVALUABLE" || row.targetRealizedVol5d === null) return { actual: null, error: null, text: "ต้นทางประเมินไม่ได้" };
  if (row.targetEndDate > asOf) return { actual: null, error: null, text: "รอ target ครบ" };
  return reveal ? { actual: row.targetRealizedVol5d, error: row.absoluteError, text: "Actual แสดงแล้ว" } : { actual: null, error: null, text: "ครบกำหนด · กดเปิด Actual" };
}
function nonReady(snapshot: Exclude<SnapshotState, { status: "ready" }>): string {
  if (snapshot.status === "loading") return "<section class=\"st-card st-loading\" role=\"status\"><h2>กำลังตรวจสอบ snapshot</h2><p>โหลดเฉพาะไฟล์ Stage 06 ที่ผ่านการตรึง hash</p></section>";
  return "<section class=\"st-card st-error\" role=\"alert\"><h2>โหลด snapshot ไม่สำเร็จ</h2><p>" + esc(snapshot.message) + "</p><button class=\"st-button\" data-action=\"retry\">ลองอีกครั้ง</button></section>";
}
function forecastPage(snapshot: ReadySnapshot, state: State): string {
  const rows = filterForecastRows(snapshot.forecasts, {
    split: state.forecast.split, ticker: state.forecast.ticker, models: [state.forecast.model], status: state.forecast.status,
    from: state.forecast.from, to: state.forecast.to,
  });
  const asOf = state.forecast.asOf || snapshot.manifest.strictCutoff;
  const shown = rows.slice(0, 100).map((row) => {
    const values = labelValues(row, snapshot, asOf, state.forecast.reveal);
    return "<tr><td>" + esc(row.predictionDate) + "</td><td>" + risk(row.predictedVolAnnualized) + "</td><td>" + risk(values.actual) + "</td><td>" + risk(values.error) + "</td><td>" + esc(row.targetEndDate) + "</td><td><span class=\"" + statusClass(row) + "\">" + esc(values.text) + "</span></td></tr>";
  }).join("");
  return "<section class=\"st-card\"><div class=\"st-section-heading\"><div><h2>ตัวกรอง Forecast</h2><p>ตัวกรองเปลี่ยนแถวที่แสดง ไม่ได้คำนวณ Stage 06 ใหม่</p></div><span class=\"st-readonly-tag\">Read-only snapshot</span></div>"
    + "<div class=\"st-controls\"><label class=\"st-field\">ชุดข้อมูล<select data-field=\"forecast-split\">" + selectOptions(["test", "validation"], {}, state.forecast.split) + "</select></label>"
    + "<label class=\"st-field\">สินทรัพย์<select data-field=\"forecast-ticker\">" + selectOptions(tickers, tickerLabel, state.forecast.ticker) + "</select></label>"
    + "<label class=\"st-field\">โมเดล<select data-field=\"forecast-model\">" + selectOptions(models, modelLabel, state.forecast.model) + "</select></label>"
    + "<label class=\"st-field\">สถานะ<select data-field=\"forecast-status\">" + selectOptions(["all", "mature", "pending", "invalid"], { all: "ทุกสถานะ", mature: "ประเมินได้", pending: "Pending", invalid: "ผิดปกติ / ขาดข้อมูล" }, state.forecast.status) + "</select></label>"
    + "<label class=\"st-field\">As-of date<input type=\"date\" data-field=\"forecast-as-of\" max=\"" + esc(snapshot.manifest.strictCutoff) + "\" value=\"" + esc(asOf) + "\"></label>"
    + "<label class=\"st-field\">ตั้งแต่<input type=\"date\" data-field=\"forecast-from\" value=\"" + esc(state.forecast.from) + "\"></label><label class=\"st-field\">ถึง<input type=\"date\" data-field=\"forecast-to\" value=\"" + esc(state.forecast.to) + "\"></label>"
    + "<label class=\"st-check-field\"><input type=\"checkbox\" data-field=\"forecast-reveal\"" + (state.forecast.reveal ? " checked" : "") + "> เปิด Actual ที่ครบกำหนด</label></div>"
    + "<div class=\"st-kpis\"><div><span>แถวตามตัวกรอง</span><strong>" + rows.length.toLocaleString() + "</strong></div><div><span>Pending</span><strong>" + rows.filter((row) => row.evaluationStatus === "PENDING_LABEL").length.toLocaleString() + "</strong></div><div><span>Cutoff</span><strong>" + esc(snapshot.manifest.strictCutoff) + "</strong></div></div></section>"
    + "<section class=\"st-card\"><div class=\"st-section-heading\"><div><h2>Forecast · Actual · Error</h2><p>Pending และ target ที่ยังไม่ครบจะแสดงค่า Actual/Error ว่าง</p></div><span class=\"st-result-count\">" + Math.min(rows.length, 100).toLocaleString() + " / " + rows.length.toLocaleString() + "</span></div>"
    + (rows.length ? "<div class=\"st-table-wrap\"><table class=\"st-table\"><thead><tr><th>Prediction date</th><th>Forecast RV5</th><th>Actual RV5</th><th>Absolute error</th><th>Target end</th><th>สถานะ</th></tr></thead><tbody>" + shown + "</tbody></table></div>" : "<div class=\"st-empty\"><strong>ไม่พบแถวตามตัวกรอง</strong><span>ลองปรับสถานะหรือช่วงวันที่</span></div>")
    + "<p class=\"st-source-note\">Source: forecast_audit.csv" + (state.forecast.split === "test" ? " + evaluation.csv" : "") + " · หน่วย annualized percent</p></section>";
}
interface ReplayChartPoint {
  row: ForecastAuditRow;
  forecast: number | null;
  actual: number | null;
  actualStatus: string;
}

function replayChart(points: ReplayChartPoint[], selectedDate: string): string {
  const validValues = points.flatMap((point) => [point.forecast, point.actual])
    .filter((value): value is number => value !== null && Number.isFinite(value) && value >= 0);
  if (points.length === 0 || validValues.length === 0) {
    return "<div class=\"st-empty\" role=\"status\">ไม่มี Forecast หรือ Actual ที่ใช้วาดกราฟในชุดที่เลือก</div>";
  }
  const width = 880;
  const height = 246;
  const left = 64;
  const right = 848;
  const top = 34;
  const bottom = 204;
  const maxValue = Math.max(...validValues) * 1.08 || 1;
  const x = (index: number) => left + index * ((right - left) / Math.max(points.length - 1, 1));
  const y = (value: number) => bottom - (value / maxValue) * (bottom - top);
  const lines = (key: "forecast" | "actual", className: string, color: string) => {
    const segments: string[] = [];
    let segment: string[] = [];
    points.forEach((point, index) => {
      const value = point[key];
      if (value === null || !Number.isFinite(value) || value < 0) {
        if (segment.length > 1) segments.push("<polyline class=\"" + className + "\" fill=\"none\" stroke=\"" + color + "\" stroke-width=\"2\" points=\"" + segment.join(" ") + "\"/>");
        segment = [];
        return;
      }
      segment.push(x(index).toFixed(1) + "," + y(value).toFixed(1));
    });
    if (segment.length > 1) segments.push("<polyline class=\"" + className + "\" fill=\"none\" stroke=\"" + color + "\" stroke-width=\"2\" points=\"" + segment.join(" ") + "\"/>");
    return segments.join("");
  };
  const dots = points.map((point, index) => {
    const selected = point.row.predictionDate === selectedDate;
    const marker = selected ? "<line class=\"st-replay-chart-marker\" x1=\"" + x(index).toFixed(1) + "\" y1=\"" + top + "\" x2=\"" + x(index).toFixed(1) + "\" y2=\"" + bottom + "\" stroke=\"#d28a2f\" stroke-dasharray=\"4 3\"/>" : "";
    const forecast = point.forecast === null ? "" : "<circle class=\"st-replay-forecast-dot" + (selected ? " st-replay-selected-dot" : "") + "\" cx=\"" + x(index).toFixed(1) + "\" cy=\"" + y(point.forecast).toFixed(1) + "\" r=\"" + (selected ? "5" : "2.4") + "\" fill=\"#2e62a5\"><title>" + esc(point.row.predictionDate) + " · Forecast " + risk(point.forecast) + " · " + esc(point.row.predictionId) + "</title></circle>";
    const actual = point.actual === null ? "" : "<circle class=\"st-replay-actual-dot" + (selected ? " st-replay-selected-dot" : "") + "\" cx=\"" + x(index).toFixed(1) + "\" cy=\"" + y(point.actual).toFixed(1) + "\" r=\"" + (selected ? "4.5" : "2.8") + "\" fill=\"#b36b22\"><title>" + esc(point.row.predictionDate) + " · Actual " + risk(point.actual) + " · " + esc(point.row.predictionId) + "</title></circle>";
    return marker + forecast + actual;
  }).join("");
  const rows = points.map((point) => "<tr" + (point.row.predictionDate === selectedDate ? " class=\"st-selected-row\"" : "") + "><th scope=\"row\">" + esc(point.row.predictionDate) + "</th><td>" + risk(point.forecast) + "</td><td>" + risk(point.actual) + "</td><td><span class=\"" + (point.row.evaluationStatus === "PENDING_LABEL" ? "st-replay-status st-replay-pending" : point.actual !== null ? "st-replay-status st-replay-evaluable" : "st-replay-status") + "\">" + esc(point.actualStatus) + "</span></td><td><code>" + esc(point.row.predictionId.slice(0, 12)) + "</code></td></tr>").join("");
  const actualLegend = points.some((point) => point.actual !== null)
    ? "Actual ที่เปิดเผยผ่านสถานะประเมินแล้ว"
    : "Actual ซ่อนไว้จน target ครบและกดเปิดเผย";
  return "<div class=\"st-replay-chart-wrap\"><svg class=\"st-replay-chart\" viewBox=\"0 0 " + width + " " + height + "\" role=\"img\" aria-label=\"Forecast ที่บันทึกไว้และ Actual ที่เปิดเผยแล้วของ Replay\">"
    + "<line class=\"st-replay-chart-axis\" x1=\"" + left + "\" y1=\"" + bottom + "\" x2=\"" + right + "\" y2=\"" + bottom + "\" stroke=\"#cbd5e1\"/><line class=\"st-replay-chart-axis\" x1=\"" + left + "\" y1=\"" + top + "\" x2=\"" + left + "\" y2=\"" + bottom + "\" stroke=\"#cbd5e1\"/>"
    + "<line class=\"st-replay-chart-gridline\" x1=\"" + left + "\" y1=\"" + ((top + bottom) / 2) + "\" x2=\"" + right + "\" y2=\"" + ((top + bottom) / 2) + "\" stroke=\"#e4e9f0\"/>"
    + "<text class=\"st-replay-chart-label\" x=\"8\" y=\"" + (top + 4) + "\">" + risk(maxValue) + "</text><text class=\"st-replay-chart-label\" x=\"8\" y=\"" + bottom + "\">0%</text>"
    + "<text class=\"st-replay-chart-date\" x=\"" + left + "\" y=\"" + (height - 7) + "\">" + esc(points[0]!.row.predictionDate) + "</text><text class=\"st-replay-chart-date\" x=\"" + right + "\" y=\"" + (height - 7) + "\" text-anchor=\"end\">" + esc(points[points.length - 1]!.row.predictionDate) + "</text>"
    + lines("forecast", "st-replay-forecast-line", "#2e62a5") + lines("actual", "st-replay-actual-line", "#b36b22") + dots + "</svg>"
    + "<div class=\"st-replay-legend\"><span class=\"st-replay-chip\"><i class=\"st-replay-forecast-key\"></i>Forecast ที่บันทึกไว้</span><span class=\"st-replay-chip\"><i class=\"st-replay-actual-key\"></i>" + actualLegend + "</span><span>" + points.length.toLocaleString() + " วัน · เส้นเลือกวันที่ตรงกับแถวด้านข้าง</span></div></div>"
    + "<details class=\"st-source-details\"><summary>ดูค่ากราฟในตาราง (" + points.length.toLocaleString() + " วัน)</summary><div class=\"st-table-wrap\"><table class=\"st-table\"><thead><tr><th>Prediction date</th><th>Forecast</th><th>Actual</th><th>สถานะจาก source</th><th>Prediction ID</th></tr></thead><tbody>" + rows + "</tbody></table></div></details>";
}

function replayPage(snapshot: ReadySnapshot, state: State): string {
  const sessions = selectRecordedSessions(snapshot.sessions, state.replay.ticker, state.replay.model);
  if (!sessions.length) return "<section class=\"st-card st-empty\"><strong>ไม่พบ session ที่บันทึกไว้</strong></section>";
  const row = sessions.find((item) => item.predictionDate === state.replay.date) ?? sessions[sessions.length - 1]!;
  const selectedIndex = Math.max(0, sessions.findIndex((item) => item.predictionDate === row.predictionDate));
  const asOf = state.replay.asOf || row.predictionDate;
  const reveal = labelValues(row, snapshot, asOf, state.replay.reveal);
  const comparisons = selectSameDateForecasts(snapshot.sessions, state.replay.ticker, row.predictionDate).map((item) => {
    const values = labelValues(item, snapshot, asOf, state.replay.reveal);
    const visibleForecast = item.predictionDate <= asOf ? item.predictedVolAnnualized : null;
    return "<tr><th>" + modelId(item.modelName) + " · " + esc(item.modelName) + "</th><td>" + replayRisk(visibleForecast, state.replay.scale) + "</td><td>" + replayRisk(values.actual, state.replay.scale) + "</td><td>" + replayRisk(values.error, state.replay.scale) + "</td><td><span class=\"" + statusClass(item) + "\">" + esc(values.text) + "</span></td></tr>";
  }).join("");
  const months = [...new Set(sessions.map((item) => monthKey(item.predictionDate)))];
  const activeMonth = months.includes(state.replay.month) ? state.replay.month : monthKey(row.predictionDate);
  const monthSessions = sessions.filter((item) => monthKey(item.predictionDate) === activeMonth);
  const options = monthSessions.map((item) => "<option value=\"" + esc(item.predictionDate) + "\"" + (item.predictionDate === row.predictionDate ? " selected" : "") + ">" + esc(item.predictionDate) + "</option>").join("");
  const chartRows = monthSessions.length ? monthSessions : [row];
  const chartPoints: ReplayChartPoint[] = chartRows.map((session) => {
    const resolved = resolveAsOfLabelView(session, asOf, state.replay.reveal, snapshot.evaluations.get(session.predictionId));
    return {
      row: session,
      forecast: session.forecastStatus === "VALID" && session.predictionDate <= asOf
        ? (state.replay.scale === "five-day" && session.predictedVolAnnualized !== null ? session.predictedVolAnnualized * Math.sqrt(5 / 252) : session.predictedVolAnnualized)
        : null,
      actual: resolved.status === "revealed"
        ? (state.replay.scale === "five-day" ? resolved.actual * Math.sqrt(5 / 252) : resolved.actual)
        : null,
      actualStatus: resolved.status === "revealed" ? "EVALUABLE" : session.evaluationStatus === "PENDING_LABEL" ? "Pending · Actual ซ่อนอยู่" : resolved.status,
    };
  });
  const monthsHtml = months.map((month) => "<button class=\"st-replay-month" + (month === activeMonth ? " st-active" : "") + "\" type=\"button\" data-action=\"replay-month\" data-month=\"" + esc(month) + "\" aria-pressed=\"" + (month === activeMonth) + "\">" + esc(monthLabel(month)) + "</button>").join("");
  const replayStatus = row.evaluationStatus === "PENDING_LABEL" ? "st-replay-status st-replay-pending"
    : reveal.actual !== null ? "st-replay-status st-replay-evaluable" : "st-replay-status";
  const visibleForecast = row.predictionDate <= asOf ? row.predictedVolAnnualized : null;
  const datesInMonth = monthSessions.map((item) => item.predictionDate);
  const drift = snapshot.driftTimeline.filter((item) => item.ticker === state.replay.ticker && item.predictionDate >= (datesInMonth[0] ?? row.predictionDate) && item.predictionDate <= (datesInMonth[datesInMonth.length - 1] ?? row.predictionDate));
  const driftAlerts = drift.filter((item) => item.driftDetected || item.alertRecordPresent).length;
  const tickerButtons = tickers.map((ticker) => "<button class=\"st-replay-ticker" + (ticker === state.replay.ticker ? " st-active" : "") + "\" type=\"button\" data-action=\"replay-ticker\" data-ticker=\"" + ticker + "\" aria-pressed=\"" + (ticker === state.replay.ticker) + "\">" + ticker + "</button>").join("");
  return "<section class=\"st-replay-toolbar\"><div class=\"st-replay-view-toggle\" role=\"group\" aria-label=\"รูปแบบมุมมอง\">"
    + "<button class=\"st-button" + (state.replay.view === "monthly" ? " st-active" : "") + "\" type=\"button\" data-action=\"replay-view\" data-view=\"monthly\" aria-pressed=\"" + (state.replay.view === "monthly") + "\">มุมมองรายเดือน</button>"
    + "<button class=\"st-button" + (state.replay.view === "daily" ? " st-active" : "") + "\" type=\"button\" data-action=\"replay-view\" data-view=\"daily\" aria-pressed=\"" + (state.replay.view === "daily") + "\">มุมมองรายวัน</button></div>"
    + (state.replay.view === "monthly" ? "<div class=\"st-replay-monthly-strip\" aria-label=\"เลือกเดือน\">" + monthsHtml + "</div>" : "") + "<div class=\"st-replay-options\"><div class=\"st-replay-tickers\" role=\"group\" aria-label=\"เลือก ETF\">" + tickerButtons + "</div>"
    + "<label class=\"st-field st-replay-model-field\">โมเดล<select data-field=\"replay-model\">" + selectOptions(models, modelLabel, state.replay.model) + "</select></label>"
    + "<div class=\"st-replay-scale\" role=\"group\" aria-label=\"หน่วยความเสี่ยง\"><button type=\"button\" class=\"st-button" + (state.replay.scale === "five-day" ? " st-active" : "") + "\" data-action=\"replay-scale\" data-scale=\"five-day\" aria-pressed=\"" + (state.replay.scale === "five-day") + "\">สเกล 5 วัน</button><button type=\"button\" class=\"st-button" + (state.replay.scale === "annualized" ? " st-active" : "") + "\" data-action=\"replay-scale\" data-scale=\"annualized\" aria-pressed=\"" + (state.replay.scale === "annualized") + "\">สเกลรายปี</button></div>"
    + (state.replay.scale === "five-day" ? "<small class=\"st-replay-scale-note\">สเกล 5 วันเป็นค่าประมาณจากรายปี × √(5/252)</small>" : "") + "</div></section>"
    + (state.replay.view === "daily" ? "<section class=\"st-replay-daily-controls\"><button class=\"st-button st-button-quiet\" type=\"button\" data-action=\"replay-view\" data-view=\"monthly\">← กลับมุมมองรายเดือน</button><label class=\"st-field\">วันพยากรณ์<select data-field=\"replay-date\">" + options + "</select></label>"
    + "<div class=\"st-replay-step-controls\"><button class=\"st-button st-button-quiet\" type=\"button\" data-action=\"replay-step\" data-direction=\"previous\"" + (selectedIndex === 0 ? " disabled" : "") + " aria-label=\"วันก่อนหน้า\">‹ ก่อนหน้า</button><input class=\"st-replay-slider\" type=\"range\" min=\"0\" max=\"" + (sessions.length - 1) + "\" step=\"1\" value=\"" + selectedIndex + "\" data-field=\"replay-index\" aria-label=\"เลือกวันพยากรณ์\" aria-valuetext=\"" + esc(row.predictionDate) + ", วันที่ " + (selectedIndex + 1) + " จาก " + sessions.length + "\"><button class=\"st-button st-button-quiet\" type=\"button\" data-action=\"replay-step\" data-direction=\"next\"" + (selectedIndex >= sessions.length - 1 ? " disabled" : "") + " aria-label=\"วันถัดไป\">ถัดไป ›</button></div>"
    + "<label class=\"st-field st-replay-asof-field\">ดูข้อมูล ณ วันที่<input type=\"date\" data-field=\"replay-as-of\" min=\"" + esc(sessions[0]!.predictionDate) + "\" value=\"" + esc(asOf) + "\"></label>"
    + "<button class=\"st-button st-button-quiet\" type=\"button\" data-action=\"replay-asof-target\">ถึงสิ้นสุด Target</button><button class=\"st-button st-button-primary\" type=\"button\" data-action=\"replay-toggle-reveal\" aria-pressed=\"" + state.replay.reveal + "\">" + (state.replay.reveal ? "ซ่อน Actual" : "เปิดเผย Actual") + "</button></section>" : "")
    + "<div class=\"st-replay-layout\"><section class=\"st-card st-replay-chart-panel\"><div class=\"st-replay-chart-heading\"><div><h2>ความผันผวน " + (state.replay.scale === "five-day" ? "5 วันข้างหน้า" : "รายปี") + " · " + esc(monthLabel(activeMonth)) + " (" + state.replay.ticker + ")</h2><p>Prediction " + esc(datesInMonth[0] ?? row.predictionDate) + " – " + esc(datesInMonth[datesInMonth.length - 1] ?? row.predictionDate) + " · โมเดล " + esc(modelId(state.replay.model)) + "</p></div><span>เส้นทึบ = Forecast · เส้นประ = Actual</span></div>" + replayChart(chartPoints, row.predictionDate)
    + "<div class=\"st-replay-history\"><strong>ประวัติการสลับรุ่น</strong><span>ยังไม่มีประวัติการสลับรุ่นใน snapshot นี้</span></div></section>"
    + "<aside class=\"st-replay-sidebar\"><section class=\"st-card st-replay-inspector\"><div class=\"st-replay-heading\"><div><span>วันที่เลือก (" + state.replay.ticker + ")</span><h2>" + esc(row.predictionDate) + "</h2></div><span class=\"" + replayStatus + "\">" + esc(reveal.text) + "</span></div>"
    + "<div class=\"st-replay-target\"><span>ช่วงเป้าหมาย t+1…t+5</span><strong>" + esc(row.targetStartDate) + " – " + esc(row.targetEndDate) + "</strong></div>"
    + "<div class=\"st-replay-metrics\"><div class=\"st-replay-metric\"><span class=\"st-replay-metric-label\">Forecast</span><strong class=\"st-replay-metric-value\">" + replayRisk(visibleForecast, state.replay.scale) + "</strong></div><div class=\"st-replay-metric\"><span class=\"st-replay-metric-label\">Actual</span><strong class=\"st-replay-metric-value\">" + replayRisk(reveal.actual, state.replay.scale) + "</strong></div><div class=\"st-replay-metric\"><span class=\"st-replay-metric-label\">Abs Error</span><strong class=\"st-replay-metric-value\">" + replayRisk(reveal.error, state.replay.scale) + "</strong></div></div>"
    + "<div class=\"st-source-meta\"><span>Forecast ที่บันทึก: <strong>" + esc(modelId(state.replay.model)) + " " + esc(state.replay.model.replaceAll("_", " ")) + "</strong></span><span>สถานะ source: " + esc(row.forecastStatus) + " / " + esc(row.labelStatus) + " / " + esc(row.evaluationStatus) + "</span><span>Prediction ID <code>" + esc(row.predictionId) + "</code></span></div><p class=\"st-source-note\">" + (row.evaluationStatus === "PENDING_LABEL" ? "แถวนี้ยัง Pending จากต้นทาง จึงไม่มี Actual หรือ error ให้เปิดเผย" : "Actual แสดงจาก evaluation row ที่ตรงกับ prediction ID เมื่อ target ครบและกดเปิดเผย") + "</p></section></aside></div>"
    + "<div class=\"st-replay-lower-grid\"><section class=\"st-card\"><div class=\"st-section-heading\"><h2>Feature Drift</h2><span>ไม่มีข้อมูลใน snapshot</span></div><p>ชุดข้อมูลนี้ไม่มีผลตรวจ Feature Drift</p></section><section class=\"st-card\"><div class=\"st-section-heading\"><h2>Error Drift · ADWIN</h2><span>" + driftAlerts + " เหตุการณ์</span></div><p>พบ " + driftAlerts + " alerts ในช่วง " + esc(monthLabel(activeMonth)) + " · " + drift.length.toLocaleString() + " observations จาก snapshot</p></section><section class=\"st-card\"><div class=\"st-section-heading\"><h2>Online Update · " + modelId(state.replay.model) + "</h2><span>ไม่มีข้อมูลใน snapshot</span></div><p>ไม่มีบันทึก Online Update รายวันในชุดข้อมูลนี้</p></section></div>"
    + "<details class=\"st-source-details\"><summary>เปรียบเทียบทุกโมเดลในวันเดียวกัน</summary><div class=\"st-table-wrap\"><table class=\"st-table\"><thead><tr><th>โมเดล</th><th>Forecast</th><th>Actual</th><th>Abs Error</th><th>สถานะ</th></tr></thead><tbody>" + comparisons + "</tbody></table></div></details>"
    + "<p class=\"st-source-note\">Replay เป็นการจำลองย้อนหลังจากข้อมูลที่บันทึกไว้ · Actual จะแสดงเมื่อถึง target end และกดเปิดเผย · แถว Pending จะคงซ่อน Actual เสมอ</p>";
}
function portfolioPage(snapshot: ReadySnapshot, state: State): string {
  const dates = portfolioRiskSourceDates(snapshot.portfolioRisk, state.portfolio.model);
  const date = dates.includes(state.portfolio.date) ? state.portfolio.date : dates[dates.length - 1] ?? "";
  const row = snapshot.portfolioRisk.find((item) => item.split === "test" && item.predictionDate === date && item.modelName === state.portfolio.model);
  const valid = validateScenarioWeights(state.portfolio.weights);
  const enabled = row && valid.status === "valid" && row.status === "OK" && row.covariance && row.forecastStatuses.every((status) => status === "VALID");
  const portfolioVol = enabled && row.covariance ? computePortfolioVolatility(row.covariance, valid.weights) : null;
  const weights = state.portfolio.weights;
  const labels = ["หุ้นสหรัฐ", "พันธบัตรรัฐบาลสหรัฐฯ", "ทองคำ"];
  const colors = ["st-spy", "st-ief", "st-gld"];
  const weightRows = tickers.map((ticker, index) => {
    const weight = weights[index];
    const numeric = Number.isFinite(weight) ? Math.round(weight * 100) : "";
    return "<div class=\"st-portfolio-weight-row " + colors[index] + "\"><div class=\"st-portfolio-weight-heading\"><span class=\"st-portfolio-ticker\"><i></i><strong>" + ticker + "</strong><small>" + labels[index] + "</small></span><label class=\"st-portfolio-weight-value\"><input type=\"number\" min=\"0\" max=\"100\" step=\"1\" inputmode=\"numeric\" data-field=\"portfolio-weight\" data-index=\"" + index + "\" value=\"" + numeric + "\" aria-label=\"น้ำหนัก " + ticker + " เป็นเปอร์เซ็นต์\"><span>%</span></label></div><input class=\"st-portfolio-slider\" type=\"range\" min=\"0\" max=\"100\" step=\"1\" data-field=\"portfolio-weight\" data-index=\"" + index + "\" value=\"" + (Number.isFinite(weight) ? numeric : 0) + "\" aria-label=\"ปรับน้ำหนัก " + ticker + "\" aria-valuetext=\"" + (Number.isFinite(weight) ? numeric + "%" : "ค่าว่าง") + "\"></div>";
  }).join("");
  const assetCards = tickers.map((ticker, index) => "<article class=\"st-portfolio-etf-card " + colors[index] + "\"><div class=\"st-portfolio-etf-heading\"><span><i></i><strong>" + ticker + "</strong></span><small>" + (Number.isFinite(weights[index]) ? (weights[index] * 100).toFixed(0) : "—") + "%</small></div><strong class=\"st-portfolio-etf-risk\">" + risk(row?.forecastStatuses[index] === "VALID" ? row.forecastVols[index] : null) + "</strong><span>ความผันผวนบนสินทรัพย์รายปี</span></article>").join("");
  const matrix = row?.covariance ? "<div class=\"st-table-wrap\"><table class=\"st-table st-covariance-table\"><thead><tr><th>Σ</th><th>SPY</th><th>IEF</th><th>GLD</th></tr></thead><tbody>" + row.covariance.map((values, index) => "<tr><th>" + tickers[index] + "</th>" + values.map((value) => "<td>" + value.toExponential(3) + "</td>").join("") + "</tr>").join("") + "</tbody></table></div>" : "<div class=\"st-empty\"><strong>ไม่มี covariance ที่ใช้คำนวณได้</strong><span>" + esc(row?.missingInputs.join(" · ") ?? "ไม่มี source row") + "</span></div>";
  const total = weights.reduce((sum, value) => sum + (Number.isFinite(value) ? value : 0), 0);
  const sumOk = valid.status === "valid";
  const query = new URLSearchParams({ date, model: state.portfolio.model, ticker: "SPY" }).toString();
  const datesHtml = dates.map((item) => "<option value=\"" + esc(item) + "\"" + (item === date ? " selected" : "") + ">" + esc(item) + "</option>").join("");
  return "<section class=\"st-portfolio-toolbar\"><label class=\"st-field\">วันที่พยากรณ์<select data-field=\"portfolio-date\">" + datesHtml + "</select></label><label class=\"st-field\">โมเดล<select data-field=\"portfolio-model\">" + selectOptions(models, modelLabel, state.portfolio.model) + "</select></label><span class=\"st-readonly-tag\">Stage 06 · " + esc(snapshot.manifest.strictCutoff) + "</span><span class=\"st-portfolio-source-status\">" + (row?.status === "OK" ? "ข้อมูลต้นทางพร้อม" : "ข้อมูลต้นทางไม่ครบ") + "</span></section>"
    + "<div class=\"st-portfolio-layout\"><section class=\"st-card st-portfolio-editor\"><div class=\"st-section-heading\"><div><h2>ปรับน้ำหนักพอร์ต</h2><p>เลื่อนแถบหรือพิมพ์สัดส่วน SPY, IEF และ GLD รวมกันได้ 100%</p></div><button class=\"st-button st-button-quiet st-portfolio-reset\" type=\"button\" data-action=\"portfolio-reset\">↻ ค่าตั้งต้น</button></div>"
    + "<div class=\"st-portfolio-weights\">" + weightRows + "</div><div class=\"st-portfolio-total\"><span>น้ำหนักรวมพอร์ต</span><strong class=\"" + (sumOk ? "st-weight-valid" : "st-weight-invalid") + "\">" + (Number.isFinite(total) ? (total * 100).toFixed(0) : "—") + "% " + (sumOk ? "✓" : "· ต้องรวม 100%") + "</strong></div></section>"
    + "<section class=\"st-card st-portfolio-result\"><div class=\"st-section-heading\"><div><h2>ความผันผวนพอร์ต <span class=\"st-portfolio-horizon\">5 วันซื้อขายถัดไป</span></h2><p>วันพยากรณ์: " + esc(row?.predictionDate ?? date) + " · โมเดล " + esc(modelId(state.portfolio.model)) + "</p></div><span class=\"st-readonly-tag\">คำนวณจาก covariance</span></div>"
    + "<div class=\"st-portfolio-risk-card\"><div><strong>" + risk(portfolioVol) + "</strong><span>ต่อปี</span><p>" + (sumOk ? "ความเสี่ยงพอร์ตจากน้ำหนักที่เลือก" : "ปรับน้ำหนักให้รวมกันเท่ากับ 100% เพื่อคำนวณ") + "</p></div><span class=\"st-portfolio-ready\">" + (portfolioVol !== null ? "✓ พร้อมใช้งาน" : "ตรวจน้ำหนักและข้อมูล") + "</span></div>"
    + "<div class=\"st-portfolio-etf-title\"><strong>ความผันผวนรายตัวของ ETF ที่ประกอบเป็นพอร์ต</strong><span>รายปี</span></div><div class=\"st-portfolio-etf-grid\">" + assetCards + "</div>"
    + "<div class=\"st-portfolio-footer\"><span>ส่งต่อวันที่และโมเดลที่เลือกไปดูกราฟและผลย้อนหลัง</span><a class=\"st-button st-button-primary st-portfolio-replay-link\" href=\"#/replay?" + esc(query) + "\">▷ ดูค่าพยากรณ์วันนี้ใน Replay</a></div></section></div>"
    + "<details class=\"st-card st-portfolio-source\"><summary>ดู covariance matrix และข้อมูลต้นทาง</summary><p>Status " + esc(row?.status ?? "ไม่มีแถว") + " · Correlation 20D " + (row?.correlationReady ? "พร้อม" : "ยังไม่พร้อม") + " · Replay run <code>" + esc(row?.replayRunId.slice(0, 12) ?? "—") + "</code></p>"
    + matrix + "<p class=\"st-source-note\">สูตรความเสี่ยง: √(wᵀΣw) · เมทริกซ์ covariance จาก portfolio_risk.csv · ปรับเฉพาะน้ำหนัก ไม่สร้าง forecast ใหม่</p></details>";
}
function otherPage(snapshot: ReadySnapshot, page: Page): string {
  switch (page) {
    case "overview": return renderOtherPage(snapshot, "overview");
    case "models": return renderOtherPage(snapshot, "models");
    case "monitoring": return renderOtherPage(snapshot, "monitoring");
    case "evidence": return renderOtherPage(snapshot, "evidence");
    default: return "";
  }
}
function content(state: State): string {
  if (state.snapshot.status !== "ready") return nonReady(state.snapshot);
  if (state.page === "forecasts") return forecastPage(state.snapshot, state);
  if (state.page === "replay") return replayPage(state.snapshot, state);
  if (state.page === "portfolio") return portfolioPage(state.snapshot, state);
  return otherPage(state.snapshot, state.page);
}
function render(root: HTMLElement, state: State): void {
  const active = document.activeElement instanceof HTMLElement && root.contains(document.activeElement)
    ? {
      field: document.activeElement.dataset.field,
      action: document.activeElement.dataset.action,
      scenario: document.activeElement.dataset.scenario,
      index: document.activeElement.dataset.index,
      direction: document.activeElement.dataset.direction,
      view: document.activeElement.dataset.view,
      month: document.activeElement.dataset.month,
      ticker: document.activeElement.dataset.ticker,
      scale: document.activeElement.dataset.scale,
      tagName: document.activeElement.tagName,
      inputType: document.activeElement instanceof HTMLInputElement ? document.activeElement.type : "",
    }
    : null;
  const snapshot = state.snapshot;
  const title = state.page === "forecasts" ? "สำรวจ Forecast" : state.page === "replay" ? "เล่นย้อนหลัง" : state.page === "portfolio" ? "ทดลองน้ำหนักพอร์ต" : state.page === "models" ? "เปรียบเทียบโมเดล" : state.page === "monitoring" ? "ติดตามโมเดล" : state.page === "evidence" ? "หลักฐานและข้อมูล" : "Adaptive Portfolio Risk Lab";
  const subtitle = state.page === "replay" ? "Forecast ที่บันทึกไว้ · Actual แสดงเมื่อ target ครบกำหนด" : state.page === "portfolio" ? "ปรับสัดส่วนพอร์ตและคำนวณจาก covariance ที่ตรึงไว้" : "สำรวจข้อมูล Stage 06 snapshot · ไม่ใช่ข้อมูลสด";
  const showHeading = state.page === "forecasts";
  const nav = pages.map((page) => "<a class=\"st-nav-link" + (page === state.page ? " st-active" : "") + "\" href=\"#/" + page + "\"" + (page === state.page ? " aria-current=\"page\"" : "") + ">" + esc(pageLabel[page]) + "</a>").join("");
  const status = snapshot.status === "ready" ? "Stage 06 · cutoff " + esc(snapshot.manifest.strictCutoff) : snapshot.status === "loading" ? "กำลังโหลด snapshot" : "ตรวจ snapshot";
  const presentationLink = CANVA_PRESENTATION_URL
    ? "<a class=\"st-presentation-link\" href=\"" + esc(CANVA_PRESENTATION_URL) + "\" target=\"_blank\" rel=\"noopener noreferrer\">เปิด Canva Presentation ↗</a>"
    : "<button class=\"st-presentation-link\" type=\"button\" disabled title=\"ยังไม่ได้ตั้งค่าลิงก์ Canva Presentation\">เปิด Canva Presentation ↗</button>";
  root.innerHTML = "<div class=\"st-app\"><header class=\"st-header\"><a class=\"st-brand\" href=\"#/overview\"><span class=\"st-brand-mark\">R</span><span><strong>Risk Lab</strong><small>DEDS · Research snapshot</small></span></a><span class=\"st-status\">" + status + "</span><nav class=\"st-nav\" aria-label=\"หน้าหลัก\">" + nav + "</nav>" + presentationLink + "</header>"
    + "<main class=\"st-main\">" + (showHeading ? "<div class=\"st-page-title\"><div><h1>" + title + "</h1><p>" + subtitle + "</p></div></div>" : "") + content(state) + "</main><footer class=\"st-footer\"><span>Simulated Historical Replay · ไม่ใช่คำแนะนำการลงทุน</span><a href=\"#/evidence\">ดูที่มาและข้อจำกัดของข้อมูล →</a></footer></div>";
  if (active) {
    const candidates = Array.from(root.querySelectorAll<HTMLElement>("[data-field], [data-action]"));
    candidates.find((element) => element.dataset.field === active.field && element.dataset.action === active.action
      && element.dataset.scenario === active.scenario && element.dataset.index === active.index
      && element.dataset.direction === active.direction && element.dataset.view === active.view
      && element.dataset.month === active.month && element.dataset.ticker === active.ticker
      && element.dataset.scale === active.scale && element.tagName === active.tagName
      && (element instanceof HTMLInputElement ? element.type : "") === active.inputType)?.focus({ preventScroll: true });
  }
}
function pageWeight(state: State, index: number, value: number): void {
  const next = [...state.portfolio.weights] as PortfolioWeights;
  next[index] = value;
  state.portfolio.weights = next;
}
export function startStitch(root: HTMLElement): void {
  const state: State = {
    snapshot: { status: "loading" }, page: currentPage(),
    forecast: { split: "test", ticker: "SPY", model: "ONLINE_SGD", status: "all", from: "", to: "", asOf: "", reveal: false },
    replay: { ticker: "SPY", model: "ONLINE_SGD", date: "", asOf: "", reveal: false, view: "daily", month: "", scale: "five-day" },
    portfolio: { model: "ONLINE_SGD", date: "", weights: [0.5, 0.3, 0.2] },
  };
  applyRouteSelection(state);
  const updatePage = () => { state.page = currentPage(); applyRouteSelection(state); render(root, state); };
  window.addEventListener("hashchange", updatePage);
  root.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target.closest<HTMLElement>("[data-action]") : null;
    if (target?.dataset.action === "retry") {
      state.snapshot = { status: "loading" }; render(root, state);
      void loadSnapshot().then((snapshot) => { state.snapshot = snapshot; render(root, state); });
      return;
    }
    if (!target || state.snapshot.status !== "ready") return;
    const action = target.dataset.action;
    if (action === "replay-toggle-reveal") {
      state.replay.reveal = !state.replay.reveal;
    } else if (action === "portfolio-reset") {
      state.portfolio.weights = [0.5, 0.3, 0.2];
    } else if (action === "replay-view" && (target.dataset.view === "monthly" || target.dataset.view === "daily")) {
      state.replay.view = target.dataset.view;
    } else if (action === "replay-scale" && (target.dataset.scale === "five-day" || target.dataset.scale === "annualized")) {
      state.replay.scale = target.dataset.scale;
    } else if (action === "replay-month" && target.dataset.month) {
      state.replay.month = target.dataset.month;
      const sessions = state.snapshot.status === "ready" ? selectRecordedSessions(state.snapshot.sessions, state.replay.ticker, state.replay.model) : [];
      const firstInMonth = sessions.find((session) => monthKey(session.predictionDate) === target.dataset.month);
      if (firstInMonth) state.replay.date = firstInMonth.predictionDate;
    } else if (action === "replay-ticker" && isTicker(target.dataset.ticker ?? "")) {
      state.replay.ticker = target.dataset.ticker as Ticker;
      const sessions = state.snapshot.status === "ready" ? selectRecordedSessions(state.snapshot.sessions, state.replay.ticker, state.replay.model) : [];
      const matching = sessions.find((session) => session.predictionDate === state.replay.date) ?? sessions[sessions.length - 1];
      if (matching) {
        state.replay.date = matching.predictionDate;
        state.replay.month = monthKey(matching.predictionDate);
      }
    } else if (action === "replay-asof-prediction" || action === "replay-asof-target" || action === "replay-step") {
      const sessions = selectRecordedSessions(state.snapshot.sessions, state.replay.ticker, state.replay.model);
      const foundIndex = sessions.findIndex((session) => session.predictionDate === state.replay.date);
      const currentIndex = foundIndex >= 0 ? foundIndex : sessions.length - 1;
      const selected = sessions[currentIndex];
      if (!selected) return;
      if (action === "replay-asof-prediction") state.replay.asOf = selected.predictionDate;
      else if (action === "replay-asof-target") state.replay.asOf = selected.targetEndDate;
      else {
        const nextIndex = target.dataset.direction === "previous" ? currentIndex - 1 : currentIndex + 1;
        const next = sessions[nextIndex];
        if (!next) return;
        state.replay.date = next.predictionDate;
        state.replay.month = monthKey(next.predictionDate);
      }
    } else {
      return;
    }
    render(root, state);
  });
  root.addEventListener("change", (event) => {
    const target = event.target;
    if (target instanceof HTMLSelectElement) {
      const field = target.dataset.field;
      if (field === "forecast-split" && (target.value === "test" || target.value === "validation")) state.forecast.split = target.value;
      else if (field === "forecast-ticker" && isTicker(target.value)) state.forecast.ticker = target.value;
      else if (field === "forecast-model" && isModel(target.value)) state.forecast.model = target.value;
      else if (field === "forecast-status" && ["all", "mature", "pending", "invalid"].includes(target.value)) state.forecast.status = target.value as ForecastStatusFilter;
      else if (field === "replay-ticker" && isTicker(target.value)) state.replay.ticker = target.value;
      else if (field === "replay-model" && isModel(target.value)) {
        state.replay.model = target.value;
        const sessions = state.snapshot.status === "ready" ? selectRecordedSessions(state.snapshot.sessions, state.replay.ticker, state.replay.model) : [];
        const matching = sessions.find((session) => session.predictionDate === state.replay.date) ?? sessions[sessions.length - 1];
        if (matching) {
          state.replay.date = matching.predictionDate;
          state.replay.month = monthKey(matching.predictionDate);
        }
      }
      else if (field === "replay-date") {
        state.replay.date = target.value;
        state.replay.month = monthKey(target.value);
      }
      else if (field === "portfolio-model" && isModel(target.value)) {
        state.portfolio.model = target.value;
        state.portfolio.date = "";
      }
      else if (field === "portfolio-date") state.portfolio.date = target.value;
    } else if (target instanceof HTMLInputElement) {
      const field = target.dataset.field;
      if (field === "forecast-as-of") state.forecast.asOf = target.value;
      else if (field === "forecast-from") state.forecast.from = target.value;
      else if (field === "forecast-to") state.forecast.to = target.value;
      else if (field === "forecast-reveal") state.forecast.reveal = target.checked;
      else if (field === "replay-as-of") state.replay.asOf = target.value;
      else if (field === "replay-reveal") state.replay.reveal = target.checked;
      else if (field === "replay-index" && state.snapshot.status === "ready") {
        const sessions = selectRecordedSessions(state.snapshot.sessions, state.replay.ticker, state.replay.model);
        const selected = sessions[target.valueAsNumber];
        if (selected) {
          state.replay.date = selected.predictionDate;
          state.replay.month = monthKey(selected.predictionDate);
        }
      }
      else if (field === "portfolio-weight") {
        const index = Number(target.dataset.index);
        if (Number.isInteger(index) && index >= 0 && index < 3) pageWeight(state, index, target.valueAsNumber / 100);
      }
    }
    render(root, state);
  });
  if (!window.location.hash) window.location.hash = "/portfolio";
  render(root, state);
  void loadSnapshot().then((snapshot) => { state.snapshot = snapshot; render(root, state); });
}
