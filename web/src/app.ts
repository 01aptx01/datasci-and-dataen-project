import { filterForecastRows, loadSnapshot, selectRecordedSessions, type ForecastFilter, type SnapshotState } from "./data/loadSnapshot.js";
import { modelId, modelLabel, type CoverageRow, type DriftTimelineRow, type ForecastAuditRow, type H1ScatterRow, type ModelMetricRow, type ModelName, type PortfolioRiskRow, type RollingMae20Row, type Ticker } from "./data/schemas.js";
import { createDefaultFinancialScenarioState, parseFinancialDecisionParams, portfolioRiskSourceDates, serializeFinancialDecisionHash, setScenarioRemainderAsset, updateScenarioRemainderWeight, validateScenarioWeights, type FinancialScenarioState, type ScenarioAsset, type ScenarioRemainderAsset } from "./data/decisionLab.js";
import { buildExportMetadata, buildForecastCsv } from "./data/export.js";
import { resolveAsOfLabelView, selectSameDateForecasts } from "./data/replay.js";
import { calculateDescriptiveRangeMetrics } from "./data/rangeMetrics.js";
import { defaultExperimentSelection, isIsoCalendarDate, parseExperimentSelection, parseHashRoute, serializeSelectionHash, validateExperimentSelection, type ExperimentSelection, type SelectionSource } from "./data/selection.js";
import { renderFinancialDecisionLab } from "./ui/financialDecisionLab.js";
import { hypothesisDecisionThai, hypothesisMethodThai, renderHypothesisResultCard, summarizeH1EvidenceThai } from "./ui/researchEvidence.js";
import { renderSessionChart } from "./ui/sessionChart.js";

interface RouteDefinition {
  path: string;
  label: string;
  thai: string;
  description: string;
  icon: string;
}

const routes: RouteDefinition[] = [
  { path: "/overview", label: "Overview", thai: "ภาพรวม", description: "ผลสรุปจากชุดข้อมูลที่ตรวจแล้ว", icon: "overview" },
  { path: "/models", label: "Models", thai: "เปรียบเทียบโมเดล", description: "คะแนน Test ของ B0–B3 และผลเปรียบเทียบคู่", icon: "models" },
  { path: "/forecasts", label: "Forecasts", thai: "สำรวจ Forecast", description: "ค่าพยากรณ์ที่บันทึกไว้และผลประเมิน", icon: "forecasts" },
  { path: "/portfolio", label: "Portfolio", thai: "ทดลองน้ำหนักพอร์ต", description: "ปรับสัดส่วน SPY, IEF และ GLD แล้วดูความเสี่ยงร่วม", icon: "portfolio" },
  { path: "/drift", label: "Drift", thai: "ติดตามความคลาดเคลื่อน", description: "ดูสัญญาณการเปลี่ยนแปลงจากข้อมูลที่บันทึกไว้", icon: "drift" },
  { path: "/research", label: "Research", thai: "หลักฐาน H1–H3", description: "หลักฐานสถิติที่คำนวณไว้ใน Stage 06", icon: "research" },
  { path: "/provenance", label: "Provenance", thai: "ที่มาและคุณภาพข้อมูล", description: "IDs, hashes และข้อจำกัดของ snapshot", icon: "provenance" },
  { path: "/guide", label: "Guide", thai: "คู่มือวิธีอ่านผล", description: "ความหมายของข้อมูลและข้อจำกัด", icon: "guide" },
];

const modelNames: ModelName[] = ["CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD"];
const tickerNames: Ticker[] = ["SPY", "IEF", "GLD"];
const metricTickerNames: (Ticker | "MACRO")[] = ["MACRO", "SPY", "IEF", "GLD"];
const tickerLabel: Record<Ticker, string> = { SPY: "SPY (US equities)", IEF: "IEF (Treasury bonds)", GLD: "GLD (Gold)" };
const modelColors: Record<ModelName, string> = {
  CONSTANT_BASELINE: "#8798ad",
  ROLLING_20D_BASELINE: "#c38a36",
  STATIC_SGD: "#518d7f",
  ONLINE_SGD: "#2e62a5",
};
type DisplayUnit = "decimal" | "percent";
type MetricName = "mae" | "rmse";
interface TourRecord { ticker: Ticker; predictionDate: string; asOfDate: string; predictionId: string }
interface TourStop { route: string; label: string; title: string; what: string; why: string; tryThis: string; source: string }
const tourStops: TourStop[] = [
  { route: "/guide", label: "คำถามวิจัย", title: "โมเดลคาดการณ์อะไร?", what: "เป้าหมายคือ Forward RV5 หรือความผันผวนของ 5 วันซื้อขายถัดไป ไม่ใช่ราคาและผลตอบแทน", why: "รู้เป้าหมายก่อน จะช่วยให้อ่าน Forecast และ error ได้ถูกต้อง", tryThis: "อ่านนิยาม RV5 และข้อจำกัดใน Guide", source: "target contract, 5 XNYS sessions" },
  { route: "/forecasts", label: "เปรียบเทียบโมเดล", title: "เทียบ B0–B3 ในวันเดียวกัน", what: "Replay แสดงค่าทำนายของทั้งสี่โมเดล สำหรับสินทรัพย์และวันเดียวกัน", why: "ใช้วันเดียวกันเพื่อลดผลจากความต่างของช่วงตลาด", tryThis: "ดู Forecast และสถานะของ B0, B1, B2, B3", source: "forecast_audit.csv, same prediction date and ticker" },
  { route: "/forecasts", label: "สถานะ Actual", title: "ทำไม Actual ยังไม่แสดง?", what: "ระบบแสดง Actual หลังครบ 5 XNYS sessions และ source row มีสถานะ EVALUABLE", why: "ช่วงเป้าหมายต้องจบก่อนจึงให้คะแนนได้ มุมมอง as-of ใช้ดูสถานะ ไม่ใช่หลักฐานข้อมูล ณ วันนั้น", tryThis: "เลื่อน as-of ถึงวันสิ้นสุด target แล้วดู Actual/Error", source: "target_end_date, evaluation.csv, Pending source stays hidden" },
  { route: "/models", label: "ช่วงข้อมูลและคะแนน", title: "คะแนนช่วงย่อยต่างจาก Test ที่บันทึกไว้อย่างไร?", what: "คะแนน Test ใช้ช่วงที่กำหนดไว้ ส่วนช่วงที่เลือกใช้สำรวจผลจากวันข้อมูลร่วม", why: "จำนวนวันร่วมและคะแนนเปลี่ยนตามช่วงได้ แต่ผล H1–H3 และค่า p ไม่เปลี่ยน", tryThis: "เลือกช่วง 20 วันล่าสุดหรือกำหนดช่วง แล้วดูจำนวนวันข้อมูลร่วม", source: "model_metrics.csv, evaluation.csv, common panel" },
  { route: "/drift", label: "Online และ drift", title: "Monitor แสดงอะไร?", what: "ชุดนี้บันทึก Rolling MAE20 และ ADWIN error ไว้ มี alert 0 รายการ", why: "ไม่พบ alert ไม่ได้ยืนยันว่าไม่มี drift และ handoff ไม่มีประวัติ update/checkpoint", tryThis: "เลือกจุดบนกราฟเพื่อดูค่าจาก ADWIN", source: "rolling_mae20.csv, drift_error_timeline.csv" },
  { route: "/portfolio", label: "ความเสี่ยงพอร์ต", title: "ปรับน้ำหนักโดยไม่ฝึกโมเดลใหม่", what: "ใช้ Forecast และค่าความแปรปรวนร่วมที่บันทึกไว้คำนวณ √(wᵀΣw) แล้วปรับเฉพาะน้ำหนัก", why: "ความเสี่ยงพอร์ตขึ้นกับทั้งความเสี่ยงของสินทรัพย์และการเคลื่อนไหวร่วมกัน", tryThis: "ลองน้ำหนัก 60/20/20 เทียบกับ 50/30/20", source: "portfolio_risk.csv, selected date and model" },
];
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
  selection: ExperimentSelection | null;
  selectionError: string;
  mobileMenuOpen: boolean;
  moreOpen: boolean;
  sessionSpeedMs: number;
  sessionPlaying: boolean;
  sessionTimer: number | null;
  unit: DisplayUnit;
  metric: MetricName;
  modelTicker: Ticker | "MACRO";
  rangeTicker: Ticker | "MACRO";
  rangeMetric: MetricName;
  rangePreset: "all-test" | "last20" | "custom";
  rangeFrom: string;
  rangeTo: string;
  forecastTicker: Ticker;
  forecastSplit: "test" | "validation";
  forecastModels: ModelName[];
  forecastStatus: ForecastFilter["status"];
  forecastFrom: string;
  forecastTo: string;
  financialDecision: FinancialScenarioState;
  riskBudgetDraft: string;
  riskBudgetError: string;
  driftFrom: string;
  driftTo: string;
  researchTicker: Ticker;
  guidedActive: boolean;
  guidedStep: number;
  tourRecord: TourRecord | null;
  presentationMode: boolean;
  attempt: number;
}

function selectionSource(snapshot: Extract<SnapshotState, { status: "ready" }>): SelectionSource {
  return {
    evaluationId: snapshot.manifest.evaluationId,
    replayId: snapshot.manifest.replayId,
    forecasts: snapshot.forecasts,
    portfolioRisk: snapshot.portfolioRisk,
  };
}

function routeFallbackSelection(snapshot: Extract<SnapshotState, { status: "ready" }>, routePath: string): ExperimentSelection | null {
  const source = selectionSource(snapshot);
  if (routePath !== "/drift") return defaultExperimentSelection(source);
  const observations = snapshot.driftTimeline
    .sort((left, right) => right.predictionDate.localeCompare(left.predictionDate));
  for (const row of observations) {
    const candidate: ExperimentSelection = {
      evaluationId: snapshot.manifest.evaluationId,
      replayId: snapshot.manifest.replayId,
      split: "test",
      predictionDate: row.predictionDate,
      modelName: "ONLINE_SGD",
      ticker: row.ticker,
      asOfDate: row.predictionDate,
      view: "as-of",
    };
    const result = validateExperimentSelection(candidate, source);
    if (result.status === "valid") return result.selection;
  }
  return defaultExperimentSelection(source);
}

function commonRangeDates(snapshot: Extract<SnapshotState, { status: "ready" }>): string[] {
  return [...new Set(snapshot.sessions
    .filter((row) => row.split === "test" && row.isCommonPanel && row.evaluationStatus === "EVALUABLE" && row.forecastStatus === "VALID")
    .map((row) => row.predictionDate))]
    .sort((left, right) => left.localeCompare(right));
}

function selectionSessions(snapshot: Extract<SnapshotState, { status: "ready" }>, selection: ExperimentSelection): ForecastAuditRow[] {
  return selectRecordedSessions(snapshot.sessions, selection.ticker, selection.modelName)
    .filter((row) => row.split === selection.split);
}

function sameSplitForecasts(rows: ForecastAuditRow[], selection: ExperimentSelection, predictionDate: string): ForecastAuditRow[] {
  return rows
    .filter((row) => row.split === selection.split && row.ticker === selection.ticker && row.predictionDate === predictionDate)
    .sort((left, right) => modelNames.indexOf(left.modelName) - modelNames.indexOf(right.modelName));
}

function applyLocationSelection(state: ViewState, hash: string): void {
  const route = parseHashRoute(hash);
  state.routePath = routes.some((item) => item.path === route.path) ? route.path : "/overview";
  state.selection = null;
  state.selectionError = "";
  if (state.snapshot.status !== "ready") return;

  if (state.routePath === "/portfolio") {
    const decision = parseFinancialDecisionParams(route.params);
    if (decision.status === "invalid") {
      state.selectionError = decision.message;
      return;
    }
    state.financialDecision = decision.status === "valid" ? decision.state : createDefaultFinancialScenarioState();
    state.riskBudgetDraft = state.financialDecision.budgetAnnualizedDecimal === null ? "" : String(state.financialDecision.budgetAnnualizedDecimal * 100);
    state.riskBudgetError = "";
  }

  const parsed = parseExperimentSelection(route.params);
  let candidate: ExperimentSelection | null;
  if (parsed.status === "invalid") {
    state.selectionError = parsed.message;
    return;
  }
  if (parsed.status === "absent") {
    candidate = defaultExperimentSelection(selectionSource(state.snapshot));
    if (!candidate) {
      state.selectionError = "ไม่พบ recorded forecast และ portfolio row ที่ใช้เป็นค่าเริ่มต้น";
      return;
    }
    if (state.routePath === "/models") {
      const start = route.params.get("dateStart") ?? undefined;
      const end = route.params.get("dateEnd") ?? undefined;
      if (start || end) {
        if ((start && !isIsoCalendarDate(start)) || (end && !isIsoCalendarDate(end)) || (start && end && start > end)) {
          state.selectionError = "ช่วงวันที่ในลิงก์ Models ไม่ถูกต้อง";
          return;
        }
        candidate = { ...candidate, ...(start ? { rangeStart: start } : {}), ...(end ? { rangeEnd: end } : {}), rangePreset: "custom" };
      }
    }
  } else {
    candidate = parsed.selection;
  }

  if (["/portfolio", "/drift"].includes(state.routePath) && candidate.split !== "test") {
    state.selectionError = `${state.routePath} รองรับ recorded Test sessions เท่านั้น`;
    return;
  }
  const result = validateExperimentSelection(candidate, selectionSource(state.snapshot), state.routePath === "/portfolio");
  if (result.status === "invalid") {
    state.selectionError = result.message;
    return;
  }
  state.selection = result.selection;
  if (state.routePath === "/models") {
    if (candidate.rangePreset === "last20") {
      const dates = commonRangeDates(state.snapshot);
      state.rangePreset = "last20";
      state.rangeFrom = candidate.rangeStart ?? dates[Math.max(0, dates.length - 20)] ?? "";
      state.rangeTo = candidate.rangeEnd ?? dates[dates.length - 1] ?? "";
    } else if (candidate.rangePreset === "custom" || candidate.rangeStart || candidate.rangeEnd) {
      state.rangePreset = "custom";
      state.rangeFrom = candidate.rangeStart ?? "";
      state.rangeTo = candidate.rangeEnd ?? "";
    } else {
      state.rangePreset = "all-test";
      state.rangeFrom = "";
      state.rangeTo = "";
    }
  }
}

function selectionUnavailable(state: ViewState): string {
  const fallback = state.snapshot.status === "ready" ? routeFallbackSelection(state.snapshot, state.routePath) : null;
  const fallbackCopy = fallback
    ? `session ที่ใช้ได้: ${fallback.predictionDate}, ${fallback.ticker}, ${modelId(fallback.modelName)}`
    : "กลับไปภาพรวมเพื่อตรวจชุดข้อมูลที่มี";
  return `<section class="selection-unavailable" role="alert"><h2>เปิด session นี้ไม่ได้</h2><p>ตัวเลือกที่ขอไม่ตรงกับข้อมูลชุดนี้: ${escapeHtml(state.selectionError || "ไม่พบ session ที่เลือก")}</p><p>${escapeHtml(fallbackCopy)}</p>${fallback ? '<button class="button button-primary" type="button" data-action="reset-selection">เปิด session นี้</button>' : '<a class="button button-primary" href="#/overview">กลับไปภาพรวม</a>'}</section>`;
}

function routeHash(path: string, state: ViewState): string {
  if (!state.selection) return `#${path}`;
  const selectionHash = serializeSelectionHash(path, state.selection);
  if (path !== "/portfolio") return selectionHash;
  const decision = validateFinancialDecisionState(state.financialDecision);
  return serializeFinancialDecisionHash(selectionHash, decision ? state.financialDecision : createDefaultFinancialScenarioState());
}

function navigateRoute(state: ViewState, path: string): void {
  const hash = routeHash(path, state);
  if (hash !== window.location.hash) window.location.hash = hash;
}

function publishSelection(root: HTMLElement, state: ViewState, selection: ExperimentSelection, historyMode: "push" | "replace" = "push"): void {
  let hash = serializeSelectionHash(state.routePath, selection);
  if (state.routePath === "/portfolio") {
    const decision = validateFinancialDecisionState(state.financialDecision);
    hash = serializeFinancialDecisionHash(hash, decision ? state.financialDecision : createDefaultFinancialScenarioState());
  }
  if (historyMode === "replace") {
    state.selection = selection;
    state.selectionError = "";
    window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}${hash}`);
    render(root, state);
    return;
  }
  if (hash === window.location.hash) {
    applyLocationSelection(state, hash);
    render(root, state);
  } else {
    state.selection = selection;
    state.selectionError = "";
    window.history.pushState(window.history.state, "", `${window.location.pathname}${window.location.search}${hash}`);
    render(root, state);
  }
}

function publishRangeSelection(root: HTMLElement, state: ViewState): void {
  if (!state.selection || state.routePath !== "/models") return;
  const rangeStart = state.rangePreset === "all-test" ? undefined : state.rangeFrom || undefined;
  const rangeEnd = state.rangePreset === "all-test" ? undefined : state.rangeTo || undefined;
  if (rangeStart && rangeEnd && rangeStart > rangeEnd) return;
  const rangePreset = state.rangePreset === "all-test" ? undefined : state.rangePreset;
  publishSelection(root, state, { ...state.selection, rangeStart, rangeEnd, rangePreset });
}

function selectionContextSummary(state: ViewState): string {
  const selection = state.selection;
  if (!selection || state.snapshot.status !== "ready") return "";
  const view = selection.view === "as-of" ? `ตามข้อมูล ณ ${selection.asOfDate ?? selection.predictionDate}` : "ดูย้อนหลัง";
  return `<section class="selection-context" aria-label="Session ที่เลือก"><div><strong>${escapeHtml(selection.predictionDate)}, ${selection.split.toUpperCase()}, ${escapeHtml(selection.ticker)}, ${modelId(selection.modelName)}</strong><small>${escapeHtml(view)}</small></div></section>`;
}

function validateFinancialDecisionState(state: FinancialScenarioState): boolean {
  return validateScenarioWeights(state.scenarioA).status === "valid" &&
    validateScenarioWeights(state.scenarioB).status === "valid" &&
    ["SPY", "IEF", "GLD"].includes(state.remainderAssetA) &&
    ["SPY", "IEF", "GLD"].includes(state.remainderAssetB) &&
    (state.budgetAnnualizedDecimal === null || (Number.isFinite(state.budgetAnnualizedDecimal) && state.budgetAnnualizedDecimal >= 0)) &&
    ["risk", "drivers", "scenarios"].includes(state.activeTab) &&
    ["A", "B"].includes(state.activeScenario);
}

function applyScenarioWeightInput(root: HTMLElement, state: ViewState, target: HTMLInputElement): { scenario: "A" | "B"; valid: boolean } | null {
  const scenario = target.dataset.scenario;
  const index = Number(target.dataset.index);
  if ((scenario !== "A" && scenario !== "B") || !Number.isInteger(index) || index < 0 || index >= tickerNames.length) return null;
  const weightsKey = scenario === "A" ? "scenarioA" : "scenarioB";
  const remainderKey = scenario === "A" ? "remainderAssetA" : "remainderAssetB";
  const remainderAsset = state.financialDecision[remainderKey];
  const asset = tickerNames[index] as ScenarioAsset;
  if (asset === remainderAsset) return null;

  const decimal = target.value.trim() ? Number(target.value) / 100 : Number.NaN;
  const next = updateScenarioRemainderWeight(state.financialDecision[weightsKey], remainderAsset, asset, decimal);
  state.financialDecision[weightsKey] = next;

  const remainderIndex = tickerNames.indexOf(remainderAsset);
  const remainderOutput = root.querySelector<HTMLOutputElement>(`[data-scenario-remainder-value="${scenario}"]`);
  const remainderWeight = next[remainderIndex];
  if (remainderOutput) remainderOutput.textContent = Number.isFinite(remainderWeight) ? `${Math.round(remainderWeight * 100)}%` : "—";

  const pairedField = target.dataset.field === "scenario-weight" ? "scenario-weight-slider" : "scenario-weight";
  const pairedControl = root.querySelector<HTMLInputElement>(`[data-field="${pairedField}"][data-scenario="${scenario}"][data-index="${index}"]`);
  if (pairedControl) pairedControl.value = target.dataset.field === "scenario-weight-slider"
    ? target.value
    : Number.isFinite(decimal) ? String(decimal * 100) : "0";

  const editableIndices = tickerNames.map((_, itemIndex) => itemIndex).filter((itemIndex) => itemIndex !== remainderIndex);
  for (const editableIndex of editableIndices) {
    const otherIndex = editableIndices.find((itemIndex) => itemIndex !== editableIndex);
    const otherWeight = otherIndex === undefined ? Number.NaN : next[otherIndex];
    const maxPercent = Number.isFinite(otherWeight) ? Math.max(0, Math.min(100, (1 - otherWeight) * 100)) : 0;
    const currentWeight = next[editableIndex];
    const sliderMax = Number.isFinite(currentWeight) && currentWeight >= 0 && currentWeight <= 1 ? Math.max(maxPercent, currentWeight * 100) : maxPercent;
    const numberInput = root.querySelector<HTMLInputElement>(`[data-field="scenario-weight"][data-scenario="${scenario}"][data-index="${editableIndex}"]`);
    const slider = root.querySelector<HTMLInputElement>(`[data-field="scenario-weight-slider"][data-scenario="${scenario}"][data-index="${editableIndex}"]`);
    numberInput?.setAttribute("max", String(maxPercent));
    slider?.setAttribute("max", String(sliderMax));
    if (slider) slider.disabled = !Number.isFinite(currentWeight) || currentWeight < 0 || currentWeight > 1;
  }

  const validation = validateScenarioWeights(next);
  const totalOutput = root.querySelector<HTMLElement>(`[data-scenario-total="${scenario}"]`);
  if (totalOutput) {
    const total = next.reduce((sum, weight) => sum + (Number.isFinite(weight) ? weight : 0), 0);
    totalOutput.textContent = `รวม ${(total * 100).toFixed(2)}%${validation.status === "invalid" ? ` · ${validation.message}` : " · น้ำหนักครบ 100%"}`;
    totalOutput.classList.toggle("weight-error", validation.status === "invalid");
    totalOutput.setAttribute("role", validation.status === "invalid" ? "alert" : "status");
  }
  return { scenario, valid: validation.status === "valid" };
}

function publishFinancialDecision(root: HTMLElement, state: ViewState, focusFallback: HTMLElement | null = null): void {
  if (!state.selection || state.routePath !== "/portfolio" || !validateFinancialDecisionState(state.financialDecision)) {
    render(root, state, focusFallback);
    return;
  }
  const baseHash = serializeSelectionHash("/portfolio", state.selection);
  const hash = serializeFinancialDecisionHash(baseHash, state.financialDecision);
  state.riskBudgetError = "";
  if (hash === window.location.hash) render(root, state, focusFallback);
  else {
    window.history.pushState(window.history.state, "", `${window.location.pathname}${window.location.search}${hash}`);
    render(root, state, focusFallback);
  }
}

function icon(name: string, size = 20): string {
  return `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${iconShapes[name] ?? ""}</svg>`;
}

function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] ?? character);
}

function forecastStatusThai(status: ForecastAuditRow["forecastStatus"]): string {
  if (status === "VALID") return "ใช้ได้";
  if (status === "INVALID") return "ผิดรูปแบบ";
  return "ไม่มีค่า";
}

function currentRoute(): string {
  const route = parseHashRoute(window.location.hash).path;
  return routes.some((item) => item.path === route) ? route : "/overview";
}

function navLink(route: RouteDefinition, active: boolean, extraClass = "", selection: ExperimentSelection | null = null): string {
  const href = selection ? serializeSelectionHash(route.path, selection) : `#${route.path}`;
  return `<a class="nav-link${active ? " active" : ""}${extraClass ? ` ${extraClass}` : ""}" href="${escapeHtml(href)}" ${active ? 'aria-current="page"' : ""}>${icon(route.icon, 19)}<span>${route.label}</span>${active ? '<span class="nav-active-mark" aria-hidden="true"></span>' : ""}</a>`;
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
  if (snapshot.status === "loading") return `<section class="snapshot-banner loading" aria-live="polite"><div class="snapshot-banner-icon"><span class="pulse-dot"></span></div><div class="snapshot-banner-copy"><strong>กำลังตรวจชุดข้อมูล</strong><span>ตรวจ SHA-256, source IDs และ schema ก่อนแสดงผล</span></div><div class="snapshot-banner-badges"><span class="pill pill-neutral">ไม่ใช่ข้อมูลสด</span></div></section>`;
  if (snapshot.status === "missing") return `<section class="snapshot-banner missing" aria-live="polite"><div class="snapshot-banner-icon">!</div><div class="snapshot-banner-copy"><strong>ยังไม่มีชุดข้อมูล</strong><span>${escapeHtml(snapshot.message)}</span></div><div class="snapshot-banner-badges"><span class="pill pill-neutral">ไม่ใช่ข้อมูลสด</span></div></section>`;
  if (snapshot.status === "error") return `<section class="snapshot-banner error" aria-live="polite"><div class="snapshot-banner-icon">!</div><div class="snapshot-banner-copy"><strong>ตรวจพบปัญหา</strong><span>${escapeHtml(snapshot.message)}</span></div><div class="snapshot-banner-badges"><span class="pill pill-neutral">ไม่ใช่ข้อมูลสด</span></div></section>`;
  return `<details class="snapshot-banner ready snapshot-details"><summary><span class="snapshot-banner-icon">${icon("check", 18)}</span><strong>ชุดข้อมูลผ่านการตรวจ</strong><span class="snapshot-banner-summary">อ่านอย่างเดียว, รออนุมัติ</span><span class="snapshot-details-cue">ดูรายละเอียด</span></summary><div class="snapshot-details-content"><p>${escapeHtml(snapshot.manifest.mode)} ผ่านการตรวจ SHA-256, source IDs และ schema</p></div></details>`;
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
  return `<details class="data-source-footer"><summary>ที่มาข้อมูล: ${escapeHtml(filename)}, ${n.toLocaleString()} รายการ</summary><div class="data-source-footer-body"><span>ชุดข้อมูล <strong>${escapeHtml(split)}</strong></span><span>ตัวเลือก <strong>${escapeHtml(selection)}</strong></span><span>จำนวน <strong>${n.toLocaleString()}</strong></span><span>หน่วย <strong>${escapeHtml(units)}</strong></span><span>Evaluation <code>${escapeHtml(evaluationId.slice(0, 12))}…</code></span></div></details>`;
}

function researchSourceFooter(filename: string, split: string, selection: string, n: number, units: string, evaluationId: string): string {
  return `<details class="data-source-footer"><summary>ที่มาข้อมูล: ${escapeHtml(filename)}, ${n.toLocaleString()} รายการ</summary><div class="data-source-footer-body"><span>ชุดข้อมูล <strong>${escapeHtml(split)}</strong></span><span>ตัวเลือก <strong>${escapeHtml(selection)}</strong></span><span>จำนวน <strong>${n.toLocaleString()}</strong></span><span>หน่วย <strong>${escapeHtml(units)}</strong></span><span>Evaluation <code>${escapeHtml(evaluationId.slice(0, 12))}…</code></span></div></details>`;
}

function copyValueButton(value: string, label: string): string {
  return `<button class="copy-value-button" type="button" data-action="copy-source-value" data-copy-value="${escapeHtml(value)}" data-copy-label="${escapeHtml(label)}" aria-label="คัดลอก ${escapeHtml(label)}"><span data-copy-status>คัดลอก</span></button>`;
}

function chartDataTable(caption: string, headers: string[], rows: string[]): string {
  if (rows.length === 0) return "";
  const headerCells = headers.map((header) => `<th scope="col">${escapeHtml(header)}</th>`).join("");
  return `<details class="chart-data-details"><summary>ดูข้อมูลกราฟเป็นตาราง (${rows.length.toLocaleString()} แถว)</summary><div class="table-scroll"><table class="data-table"><caption class="visually-hidden">${escapeHtml(caption)}</caption><thead><tr>${headerCells}</tr></thead><tbody>${rows.join("")}</tbody></table></div></details>`;
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
  return snapshot.portfolioRisk.find((row) => row.split === "test" && row.predictionDate === date && row.modelName === model && row.status === "OK" && row.covariance !== null && row.portfolioVol !== null && row.missingInputs.length === 0);
}

function recordedPortfolioRow(snapshot: Extract<SnapshotState, { status: "ready" }>, date: string, model: ModelName): PortfolioRiskRow | undefined {
  return snapshot.portfolioRisk.find((row) => row.split === "test" && row.predictionDate === date && row.modelName === model);
}

function findTourRecord(snapshot: Extract<SnapshotState, { status: "ready" }>): TourRecord | null {
  const candidates = snapshot.sessions
    .filter((row) => row.isCommonPanel && row.forecastStatus === "VALID" && row.evaluationStatus === "EVALUABLE")
    .sort((left, right) => left.predictionDate.localeCompare(right.predictionDate));
  for (const candidate of candidates) {
    const sameDate = selectSameDateForecasts(snapshot.sessions, candidate.ticker, candidate.predictionDate);
    if (sameDate.length !== modelNames.length || !modelNames.every((model) => sameDate.some((row) => row.modelName === model && row.forecastStatus === "VALID" && row.evaluationStatus === "EVALUABLE" && snapshot.evaluations.has(row.predictionId)))) continue;
    if (!sameDate.every((row) => row.targetEndDate === candidate.targetEndDate)) continue;
    if (!selectedPortfolioRow(snapshot, candidate.predictionDate, "ONLINE_SGD")) continue;
    const asOfDate = [...new Set(snapshot.sessions.filter((row) => row.ticker === candidate.ticker).map((row) => row.predictionDate))]
      .filter((date) => date >= candidate.targetEndDate)
      .sort((left, right) => left.localeCompare(right))[0];
    if (!asOfDate) continue;
    const online = sameDate.find((row) => row.modelName === "ONLINE_SGD");
    if (!online) continue;
    return { ticker: candidate.ticker, predictionDate: candidate.predictionDate, asOfDate, predictionId: online.predictionId };
  }
  return null;
}

function applyGuidedTourSelection(state: ViewState): void {
  const stop = tourStops[state.guidedStep];
  if (!stop) return;
  state.routePath = stop.route;
  stopSessionPlayback(state);
  const record = state.tourRecord;
  if ((state.guidedStep === 1 || state.guidedStep === 2) && state.snapshot.status === "ready" && record) {
    state.forecastTicker = record.ticker;
    state.selection = {
      evaluationId: state.snapshot.manifest.evaluationId,
      replayId: state.snapshot.manifest.replayId,
      split: "test",
      predictionDate: record.predictionDate,
      modelName: "ONLINE_SGD",
      ticker: record.ticker,
      asOfDate: state.guidedStep === 2 ? record.asOfDate : record.predictionDate,
      view: "as-of",
    };
    state.selectionError = "";
  }
  if (state.guidedStep === 3) {
    state.modelTicker = "MACRO";
    state.rangeTicker = record?.ticker ?? "MACRO";
    state.rangeMetric = "mae";
    const dates = state.snapshot.status === "ready" ? commonRangeDates(state.snapshot) : [];
    state.rangePreset = dates.length > 0 ? "last20" : "all-test";
    state.rangeFrom = dates.length > 0 ? dates[Math.max(0, dates.length - 20)] : "";
    state.rangeTo = dates[dates.length - 1] ?? "";
    if (state.selection) {
      state.selection = {
        ...state.selection,
        rangeStart: state.rangePreset === "last20" ? state.rangeFrom : undefined,
        rangeEnd: state.rangePreset === "last20" ? state.rangeTo : undefined,
        rangePreset: state.rangePreset === "last20" ? "last20" : undefined,
      };
    }
  }
  if (state.guidedStep === 4) {
    state.driftFrom = record?.predictionDate ?? "";
    state.driftTo = record?.predictionDate ?? "";
  }
  if (state.guidedStep === 5) {
    state.financialDecision = createDefaultFinancialScenarioState();
    state.riskBudgetDraft = "";
    state.riskBudgetError = "";
  }
}

function setGuidedStep(root: HTMLElement, state: ViewState, step: number): void {
  const nextStep = Math.max(0, Math.min(step, tourStops.length - 1));
  state.guidedStep = nextStep;
  const targetRoute = tourStops[nextStep].route;
  applyGuidedTourSelection(state);
  const hash = routeHash(targetRoute, state);
  if (window.location.hash !== hash) {
    window.location.hash = hash;
    return;
  }
  render(root, state);
}

function exitGuidedTour(root: HTMLElement, state: ViewState): void {
  state.guidedActive = false;
  state.tourRecord = null;
  render(root, state);
}

function guidedTourPanel(state: ViewState): string {
  if (!state.guidedActive) return "";
  const stop = tourStops[state.guidedStep];
  if (!stop) return "";
  const progress = (state.guidedStep + 1) / tourStops.length * 100;
  return `<aside class="guided-tour-panel" role="dialog" aria-label="คำแนะนำ: ${escapeHtml(stop.label)}"><div class="guided-tour-top"><span>ขั้นที่ ${state.guidedStep + 1} จาก ${tourStops.length}</span><button type="button" class="guided-tour-close" data-action="exit-guided-tour" aria-label="ออกจากคำแนะนำ">×</button></div><div class="guided-tour-progress"><i style="width:${progress}%"></i></div><small class="guided-tour-step-label">${escapeHtml(stop.label)}</small><h2>${escapeHtml(stop.title)}</h2><p><strong>ดูอะไร</strong>${escapeHtml(stop.what)}</p><p><strong>ทำไมสำคัญ</strong>${escapeHtml(stop.why)}</p><p class="guided-tour-try"><strong>ลองทำ</strong>${escapeHtml(stop.tryThis)}</p><div class="guided-tour-evidence">หลักฐาน: ${escapeHtml(stop.source)}${state.snapshot.status === "ready" ? ` · Evaluation ${escapeHtml(state.snapshot.manifest.evaluationId.slice(0, 10))}…` : ""}</div>${state.guidedStep > 0 && !state.tourRecord ? '<p class="guided-tour-limitation">Snapshot นี้ไม่มีตัวอย่างที่ผ่านเงื่อนไขครบทุกข้อ จึงแสดงเฉพาะข้อมูลที่ยืนยันได้</p>' : ""}<div class="guided-tour-actions"><button type="button" class="tour-skip-button" data-action="exit-guided-tour">ข้ามคำแนะนำ</button><span></span><button type="button" class="tour-nav-button" data-action="guided-previous" ${state.guidedStep === 0 ? "disabled" : ""}>ย้อนกลับ</button><button type="button" class="tour-nav-button tour-next-button" data-action="guided-next">${state.guidedStep === tourStops.length - 1 ? "เสร็จสิ้น" : "ถัดไป"}</button></div></aside>`;
}

function coverageTable(snapshot: Extract<SnapshotState, { status: "ready" }>, ticker: Ticker, evaluationId: string): string {
  const rows = coverageRowsFor(snapshot, ticker);
  if (rows.length === 0) return emptyState("Coverage ยังไม่มีข้อมูล", `ไม่พบ Test coverage สำหรับ ${ticker}`);
  const tableRows = rows.map((row) => {
    const evaluableWidth = row.expectedEligiblePredictionAnchors ? row.matureEvaluableCount / row.expectedEligiblePredictionAnchors * 100 : 0;
    const pendingWidth = row.expectedEligiblePredictionAnchors ? row.pendingLabelCount / row.expectedEligiblePredictionAnchors * 100 : 0;
    return `<tr><th scope="row"><span class="model-chip" style="--model-color:${modelColors[row.modelName]}">${modelId(row.modelName)}</span></th><td>${row.forecastSuccessCount.toLocaleString()} / ${row.expectedEligiblePredictionAnchors.toLocaleString()}</td><td>${row.matureEvaluableCount.toLocaleString()}</td><td>${row.pendingLabelCount.toLocaleString()}</td><td>${(row.invalidForecastCount + row.missingForecastCount).toLocaleString()}</td><td><div class="coverage-meter" role="img" aria-label="${row.matureEvaluableCount} evaluable and ${row.pendingLabelCount} Pending of ${row.expectedEligiblePredictionAnchors} expected"><span class="coverage-evaluable" style="width:${evaluableWidth}%"></span><span class="coverage-pending" style="width:${pendingWidth}%"></span></div></td></tr>`;
  }).join("");
  return `<div class="table-scroll"><table class="data-table coverage-table"><caption class="visually-hidden">Test forecast and evaluation coverage for ${ticker}</caption><thead><tr><th scope="col">โมเดล</th><th scope="col">Forecast ที่ใช้ได้ / ทั้งหมด</th><th scope="col">ประเมินได้</th><th scope="col">รอข้อมูลครบ</th><th scope="col">ผิดรูปแบบ / ไม่มีข้อมูล</th><th scope="col">สถานะเป้าหมาย</th></tr></thead><tbody>${tableRows}</tbody></table></div>${sourceFooter("coverage.csv", "Test", `${ticker} · per model row`, rows[0]?.expectedEligiblePredictionAnchors ?? 0, "anchor count / share", evaluationId)}`;
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
    return `<tr><th scope="row">${escapeHtml(row.predictionDate)}</th><td>${formatVol(row.predictedVolAnnualized, state.unit)}</td><td>${formatVol(actual, state.unit)}</td><td>${escapeHtml(row.targetEndDate)}</td><td>${row.evaluationStatus === "PENDING_LABEL" ? "รอข้อมูลครบ" : "ประเมินได้"}</td></tr>`;
  });
  return `<div class="chart-scroll"><svg class="forecast-mini-chart" viewBox="0 0 630 185" role="img" aria-label="${state.forecastTicker} B3 recorded Test forecast and actual RV5"><line x1="38" y1="145" x2="600" y2="145" class="chart-axis"/><line x1="38" y1="29" x2="38" y2="145" class="chart-axis"/><polyline points="${forecastPoints.map((point) => xy(point.index, point.value)).join(" ")}" fill="none" stroke="${modelColors.ONLINE_SGD}" stroke-width="2"/>${circles(forecastPoints, modelColors.ONLINE_SGD)}<polyline points="${actualPoints.map((point) => xy(point.index, point.value)).join(" ")}" fill="none" stroke="#34455e" stroke-width="1.6" stroke-dasharray="4 3"/>${circles(actualPoints, "#34455e")}<text x="38" y="169" class="chart-date-label">${escapeHtml(rows[0].predictionDate)}</text><text x="600" y="169" text-anchor="end" class="chart-date-label">${escapeHtml(rows[rows.length - 1].predictionDate)}</text><text x="6" y="34" class="chart-date-label">${formatVol(maxValue, state.unit, 2)}</text></svg></div><div class="chart-legend"><span><i style="--legend-color:${modelColors.ONLINE_SGD}"></i>B3 Forecast</span><span><i style="--legend-color:#34455e"></i>Actual (evaluable only)</span><span>${points.length.toLocaleString()} plotted values</span></div>${chartDataTable(`${state.forecastTicker} B3 recorded Test forecast and actual RV5`, ["Prediction date", "Forecast", "Actual (evaluable only)", "Target end", "Label status"], tableRows)}`;
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
  const overviewMetrics = [
    { label: "B3 Test MAE รวม ETF", value: formatVol(b3Metric?.mae, state.unit), detail: `วันข้อมูลร่วม ${b3Metric?.pairedN.toLocaleString() ?? "—"} วัน`, href: "/models", source: "model_metrics.csv" },
    { label: "B3 เทียบ B2: ΔMAE", value: formatVol(b2Delta?.deltaMaeBaselineMinusOnline, state.unit), detail: `วันข้อมูลร่วม ${b2Delta?.pairedN.toLocaleString() ?? "—"} วัน`, href: "/research", source: "pair_comparisons.csv" },
    { label: "Test ประเมินได้ / ทั้งหมด", value: `${evaluable.toLocaleString()} / ${expected.toLocaleString()}`, detail: `${expected ? (evaluable / expected * 100).toFixed(1) : "—"}% ประเมินแล้ว · รอข้อมูล ${pending.toLocaleString()}`, href: "/provenance", source: "coverage.csv" },
  ].map((card) => `<a class="metric-summary-card" href="${escapeHtml(routeHash(card.href, state))}" title="${card.source} · ${card.detail} · ${manifest.evaluationId}"><span>${card.label}</span><strong>${card.value}</strong><small>${card.detail}</small><code>${card.source} · ${card.href === "/models" ? metricName(state.metric) : card.source === "pair_comparisons.csv" ? "H2 paired" : "Test"}</code></a>`).join("");
  const selectedMetricRows = snapshot.modelMetrics.filter((row) => row.ticker === state.modelTicker);
  const conclusion = `B3 (Online SGD) มี Test Macro ${metricName(state.metric)} ต่ำสุดในกลุ่ม B0–B3 จากชุดข้อมูลนี้ · เทียบจากวันร่วม ${b3Metric?.pairedN.toLocaleString() ?? "—"} วัน`;
  return `
    <section class="hero-card">
      <div class="hero-copy"><h2>Forecast RV5 ช่วยอ่านความเสี่ยงพอร์ตได้แค่ไหน?</h2><p>RV5 คือความผันผวนจริงใน 5 วันซื้อขายถัดไป ดูผลเมื่อจัดเป็นพอร์ต SPY, IEF และ GLD</p><div class="hero-action-row"><button class="button button-primary" type="button" data-action="start-guided-tour">เริ่มแนะนำการใช้งาน ${icon("arrowRight", 17)}</button><button class="button button-secondary" type="button" data-route="/forecasts">ดู Forecast ที่บันทึก</button></div></div>
      <div class="hero-graphic" aria-hidden="true"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="hero-orbit-core"><span>RV5</span><small>FROZEN</small></div><span class="orbit-point point-spy">SPY</span><span class="orbit-point point-ief">IEF</span><span class="orbit-point point-gld">GLD</span><div class="hero-graphic-caption">XNYS, 5 trading sessions</div></div>
    </section>
    <section class="question-entry-grid" aria-label="เลือกสิ่งที่อยากเรียนรู้"><button class="question-entry-card" type="button" data-route="/forecasts"><strong>Forecast ต่างกันอย่างไร?</strong><small>ดูค่าที่บันทึกไว้และสถานะ Actual ว่าพร้อมประเมินหรือยัง</small><span class="question-entry-link">ดู Forecast →</span></button><button class="question-entry-card" type="button" data-route="/portfolio"><strong>น้ำหนักพอร์ตเปลี่ยนความเสี่ยงอย่างไร?</strong><small>ใช้วันและโมเดลเดียวกับ Replay แล้วลองปรับน้ำหนัก SPY, IEF และ GLD</small><span class="question-entry-link">ลองปรับน้ำหนัก →</span></button><button class="question-entry-card" type="button" data-route="/models"><strong>ผลที่วัดได้บอกอะไร?</strong><small>ดูผล Test จำนวนวันข้อมูลร่วม และข้อจำกัดของข้อมูลที่บันทึกไว้</small><span class="question-entry-link">อ่านผลโมเดล →</span></button></section>
    <section class="metric-summary-grid" aria-label="Experiment summary">${overviewMetrics}</section>
    <div class="analysis-grid">
      <section class="analysis-card"><div class="section-card-heading"><div><h3>B0–B3 ${metricName(state.metric)} · ${state.modelTicker}</h3></div><a class="subtle-link" href="${escapeHtml(routeHash("/models", state))}">รายละเอียด →</a></div><div class="inline-controls"><label class="field-label">Metric<select data-field="metric"><option value="mae" ${state.metric === "mae" ? "selected" : ""}>MAE</option><option value="rmse" ${state.metric === "rmse" ? "selected" : ""}>RMSE</option></select></label><label class="field-label">Breakdown<select data-field="model-ticker">${metricTickerNames.map((ticker) => `<option value="${ticker}" ${state.modelTicker === ticker ? "selected" : ""}>${ticker}</option>`).join("")}</select></label></div>${metricChart(selectedMetricRows, state.metric, state.unit, `Stored Test ${state.modelTicker} ${metricName(state.metric)} by model`)}${sourceFooter("model_metrics.csv", "Test", `${state.modelTicker} · B0–B3`, selectedMetricRows[0]?.pairedN ?? 0, `annualized decimal (${state.unit}) · paired N per row`, manifest.evaluationId)}</section>
      <section class="analysis-card"><div class="section-card-heading"><div><h3>สถานะ Forecast ในชุด Test</h3></div><span class="pill pill-neutral">valid ${valid.toLocaleString()} / ${expected.toLocaleString()}</span></div><label class="field-label coverage-ticker-control">สินทรัพย์<select data-field="coverage-ticker">${tickerNames.map((ticker) => `<option value="${ticker}" ${ticker === state.forecastTicker ? "selected" : ""}>${ticker}</option>`).join("")}</select></label>${coverageTable(snapshot, state.forecastTicker, manifest.evaluationId)}</section>
      <section class="analysis-card analysis-card-wide"><div class="section-card-heading"><div><h3>${state.forecastTicker} · B3 Forecast เทียบ Actual</h3></div><button class="text-button" type="button" data-route="/forecasts">ดู Forecast ทั้งหมด →</button></div>${miniForecastChart(state)}<p class="chart-note">แสดง Actual เมื่อ label ครบกำหนดและประเมินได้ · Pending ยังไม่ถูกให้คะแนน ณ cutoff ${manifest.strictCutoff}</p>${sourceFooter("forecast_audit.csv + evaluation.csv", "Test", `${state.forecastTicker} · B3`, snapshot.sessions.filter((row) => row.ticker === state.forecastTicker && row.modelName === "ONLINE_SGD").length, `annualized decimal (${state.unit})`, manifest.evaluationId)}</section>
      <section class="study-conclusion"><p>${escapeHtml(conclusion)}</p><a href="${escapeHtml(routeHash("/research", state))}">ดูวิธีและหลักฐานที่บันทึกใน Stage 06 →</a><div class="limitation-inline">ผลเป็นการเปรียบเทียบเชิงพรรณนา ไม่รับประกันอนาคต · เป็นข้อมูลย้อนหลัง ไม่ใช่ Forecast สด · รายงานรออนุมัติ</div></section>
    </div>
    <div class="overview-grid">
      <section class="overview-section-card identity-overview-card"><div class="section-card-heading"><div><h3>ชุดข้อมูลที่กำลังอ่าน</h3></div><span class="verified-badge">${icon("check", 13)} VERIFIED</span></div><div class="identity-pair"><span>Evaluation ID</span><code>${escapeHtml(manifest.evaluationId)}</code></div><div class="identity-pair"><span>Replay ID</span><code>${escapeHtml(manifest.replayId)}</code></div><div class="identity-meta-row"><span>Strict cutoff</span><strong>${escapeHtml(manifest.strictCutoff)}</strong><span class="meta-divider"></span><span>Source mode</span><strong>Simulated Historical Replay</strong></div></section>
      <section class="overview-section-card phase-card"><div class="section-card-heading"><div><h3>อ่านผลจากชุดที่ตรวจแล้ว</h3></div><span class="phase-index">D3</span></div><p>ตัวเลขในหน้า Overview และ Models มาจาก metric rows ที่บันทึกไว้ ไม่คำนวณซ้ำใน browser</p><div class="phase-check-list"><span>${icon("check", 15)} Snapshot checksum และ schema ผ่าน</span><span>${icon("check", 15)} มี ${valid.toLocaleString()} forecast ที่ valid</span><span class="phase-next">${pending.toLocaleString()} Pending · ยังไม่ใช่ forecast ที่ผิด</span></div></section>
    </div>
    `;
}

function sessionCard(state: ViewState): string {
  if (state.snapshot.status === "loading") return loadingState();
  if (state.snapshot.status === "missing") return emptyState("ยังไม่มี Forecast ที่บันทึก", "ถ้าไฟล์ snapshot ไม่ครบ ระบบจะไม่สร้างข้อมูลขึ้นมาแทน");
  if (state.snapshot.status === "error") return errorState(state.snapshot.message);
  const snapshot = state.snapshot;
  const selection = state.selection;
  if (!selection) return selectionUnavailable(state);
  const available = selectionSessions(snapshot, selection);
  const index = available.findIndex((session) => session.predictionDate === selection.predictionDate);
  const row = available[index];
  const modelOptions = modelNames.map((model) => `<option value="${model}" ${selection.modelName === model ? "selected" : ""}>${modelId(model)} · ${escapeHtml(modelLabel(model))}</option>`).join("");
  const tickerOptions = tickerNames.map((ticker) => `<option value="${ticker}" ${selection.ticker === ticker ? "selected" : ""}>${ticker}</option>`).join("");
  if (!row) return selectionUnavailable({ ...state, selectionError: `ไม่มี recorded forecast สำหรับ ${selection.ticker} · ${selection.modelName} · ${selection.predictionDate}` });
  const evaluation = snapshot.evaluations.get(row.predictionId);
  const pending = row.evaluationStatus === "PENDING_LABEL";
  const isEvaluable = row.evaluationStatus === "EVALUABLE" && evaluation !== undefined;
  const validForecast = row.forecastStatus === "VALID" && row.predictedVolAnnualized !== null;
  const asOfDates = [...new Set(snapshot.sessions.filter((item) => item.split === selection.split && item.ticker === selection.ticker).map((item) => item.predictionDate))]
    .filter((date) => date >= row.predictionDate)
    .sort((left, right) => left.localeCompare(right));
  const asOfDate = selection.asOfDate ?? row.predictionDate;
  const labelAsOfDate = selection.view === "retrospective" ? row.targetEndDate : asOfDate;
  const labelView = resolveAsOfLabelView(row, labelAsOfDate, true, evaluation);
  const revealed = labelView.status === "revealed";
  const overlayMessage: Record<typeof labelView.status, string> = {
    "source-pending": "ต้นทางยังไม่ประเมินแถวนี้ จึงไม่แสดงค่าจริงหรือความคลาดเคลื่อน แม้เลือกวันหลังจากนั้น",
    "source-not-evaluable": "ต้นทางไม่อนุญาตให้ประเมินแถวนี้ จึงไม่มีค่าจริงหรือความคลาดเคลื่อนให้แสดง",
    "awaiting-target-end": `ช่วงเป้าหมายสิ้นสุดวันที่ ${row.targetEndDate} จึงยังไม่มีผลประเมิน`,
    "eligible-reveal-required": `ช่วงเป้าหมายครบถึง ${row.targetEndDate} แล้ว เลือกย้อนหลังเพื่อดูผลที่บันทึกไว้`,
    "missing-evaluation": "ไม่พบผลประเมินที่ตรงกับแถวพยากรณ์ จึงซ่อนค่าจริงและความคลาดเคลื่อน",
    revealed: "ค่าจริงและความคลาดเคลื่อนมาจากผลประเมินที่ตรงกับ ID พยากรณ์ หลังช่วงเป้าหมายครบแล้ว",
  };
  const overlayClass = revealed ? "asof-status-ready" : labelView.status === "source-pending" ? "asof-status-pending" : "asof-status-waiting";
  const maturityHeading = selection.view === "retrospective"
    ? `ย้อนหลังถึงวันตัดข้อมูล ${snapshot.manifest.strictCutoff}`
    : labelView.status === "revealed" ? `ประเมินได้ ณ ${asOfDate}` : labelView.status === "source-pending" ? `ต้นทางยังรอผล ณ ${asOfDate}` : `ยังไม่ถึงวันสิ้นสุดช่วง ${row.targetEndDate}`;
  const format = (value: number | null | undefined) => formatVol(value, state.unit, 6);
  const statusClass = pending ? "status-pending" : isEvaluable ? "status-evaluable" : "status-neutral";
  const statusLabel = pending ? "รอข้อมูลครบ" : row.evaluationStatus === "EVALUABLE" ? "ประเมินได้" : "ตรวจสอบไม่ได้";
  const pendingTooltip = pending ? "ยังไม่ให้คะแนน เพราะช่วงเป้าหมายยังไม่ครบภายในวันตัดข้อมูล" : "";
  const actualLabel = revealed ? "ค่าจริงจากผลประเมิน หลังช่วงเป้าหมายครบ" : "รอให้ถึงวันสิ้นสุดช่วงเป้าหมาย";
  const errorLabel = revealed ? "ค่าที่บันทึกไว้ใน Stage 06" : "ยังไม่มีในมุมมองตามวันที่เลือก";
  const comparisonRows = sameSplitForecasts(snapshot.sessions, selection, row.predictionDate);
  const comparisonTableRows = comparisonRows.map((comparison) => {
    const comparisonEvaluation = snapshot.evaluations.get(comparison.predictionId);
    const comparisonAsOfDate = selection.view === "retrospective" ? comparison.targetEndDate : asOfDate;
    const comparisonView = resolveAsOfLabelView(comparison, comparisonAsOfDate, true, comparisonEvaluation);
    const forecast = comparison.forecastStatus === "VALID" ? comparison.predictedVolAnnualized : null;
    return `<tr><th scope="row"><span class="model-chip" style="--model-color:${modelColors[comparison.modelName]}">${modelId(comparison.modelName)}</span></th><td>${formatVol(forecast, state.unit)}</td><td>${comparisonView.status === "revealed" ? formatVol(comparisonView.actual, state.unit) : "—"}</td><td>${comparisonView.status === "revealed" ? formatVol(comparisonView.absoluteError, state.unit) : "—"}</td><td><span class="status-chip ${comparison.evaluationStatus === "PENDING_LABEL" ? "status-pending" : comparison.evaluationStatus === "EVALUABLE" ? "status-evaluable" : "status-neutral"}">${escapeHtml(comparison.evaluationStatus)}</span></td><td><button class="table-link" type="button" data-action="open-session" data-prediction-id="${escapeHtml(comparison.predictionId)}">ดูแถวนี้</button></td></tr>`;
  });
  const chartPoints = available.map((session) => {
    const sessionEvaluation = snapshot.evaluations.get(session.predictionId);
    const sessionAsOf = selection.view === "retrospective" ? session.targetEndDate : asOfDate;
    const sessionView = resolveAsOfLabelView(session, sessionAsOf, true, sessionEvaluation);
    return {
      predictionDate: session.predictionDate,
      predictionId: session.predictionId,
      forecast: session.forecastStatus === "VALID" ? session.predictedVolAnnualized : null,
      actual: sessionView.status === "revealed" ? sessionView.actual : null,
      status: session.evaluationStatus === "PENDING_LABEL" ? "PENDING_LABEL" : sessionView.status === "revealed" ? "EVALUABLE" : sessionView.status,
    };
  });
  const portfolioReady = selection.split === "test" && selectedPortfolioRow(snapshot, row.predictionDate, selection.modelName) !== undefined;
  const noForecastWarning = !validForecast ? '<p class="error-inline">ไม่มีค่าพยากรณ์ที่ใช้แสดงได้ตามสถานะใน source row</p>' : "";
  return `
    <section class="session-card" aria-labelledby="session-title">
      <div class="session-head"><div><h2 id="session-title">ไล่ดู Forecast รายวัน</h2><p>ดูค่าที่บันทึกไว้ ระบบไม่สร้าง Forecast หรือ replay ใหม่</p></div><span class="readonly-pill">${icon("lock", 14)} ดูอย่างเดียว</span></div>
      <div class="session-step-row" role="group" aria-label="Recorded forecast timeline">
          <button class="session-step-button" type="button" data-action="previous" aria-label="วันก่อนหน้า" ${index === 0 ? "disabled" : ""}>${icon("arrowLeft")}<span>วันก่อนหน้า</span></button>
          <div class="session-date" aria-live="polite"><span>วันทำนาย (XNYS)</span><strong data-session-current-date>${escapeHtml(row.predictionDate)}</strong><small data-session-position>วันที่ ${index + 1} จาก ${available.length}</small><small class="session-step-context">${escapeHtml(selection.ticker)} · ${modelId(selection.modelName)} · ${selection.view === "as-of" ? `ข้อมูลถึง ${escapeHtml(asOfDate)}` : "ย้อนหลัง"}</small></div>
          <button class="session-step-button" type="button" data-action="next" aria-label="วันถัดไป" ${index >= available.length - 1 ? "disabled" : ""}><span>วันถัดไป</span>${icon("arrowRight")}</button>
      </div>
      <details class="session-settings" id="session-settings" data-persist-open><summary>ตัวเลือกเพิ่มเติม: ${escapeHtml(selection.ticker)}, โมเดล ${modelId(selection.modelName)} และวันที่ข้อมูลครบถึง</summary><div class="session-settings-panel"><div class="session-filters"><label class="field-label">สินทรัพย์<select data-field="ticker">${tickerOptions}</select></label><label class="field-label">โมเดล<select data-field="model">${modelOptions}</select></label></div><div class="session-asof-row"><label class="field-label" for="session-asof-select">วันที่ระบบจำลองว่าข้อมูลครบถึง<select id="session-asof-select" data-field="session-as-of" aria-describedby="session-asof-note">${asOfDates.map((date) => `<option value="${escapeHtml(date)}" ${date === asOfDate ? "selected" : ""}>${escapeHtml(date)}</option>`).join("")}</select></label><button class="button button-secondary maturity-reveal-button" type="button" data-action="toggle-session-view" aria-pressed="${selection.view === "retrospective"}">${selection.view === "retrospective" ? "ดูตามวันที่เลือก" : "ดูย้อนหลัง"}</button></div><p id="session-asof-note" class="asof-caveat">วันที่นี้ใช้จำลองว่าข้อมูลครบถึงวันใด ไม่ยืนยันว่าข้อมูลตลาดพร้อมใช้จริงและไม่เปลี่ยนสถานะต้นทาง</p></div></details>
      <div class="session-evidence-grid"><div class="session-main-evidence">
        <div class="session-status-row"><span class="status-chip ${statusClass}" ${pending ? `title="${pendingTooltip}" aria-label="${pendingTooltip}"` : ""}>${escapeHtml(statusLabel)}</span><span class="status-chip status-outline">Forecast ${forecastStatusThai(row.forecastStatus)}</span><span class="session-horizon">ช่วงเป้าหมาย ${escapeHtml(row.targetStartDatePrediction)} → ${escapeHtml(row.targetEndDatePrediction)}</span></div>
        <div class="asof-overlay ${overlayClass}" role="status" aria-live="polite"><strong>${escapeHtml(maturityHeading)}</strong><span>${escapeHtml(overlayMessage[labelView.status])}</span></div>
        <div class="session-values"><div class="session-value-card"><span>Forecast RV5</span><strong>${validForecast ? format(row.predictedVolAnnualized) : "—"}</strong><small>Annualized volatility จาก forecast_audit.csv</small></div><div class="session-value-card${revealed ? "" : " muted-value"}"><span>Actual RV5</span><strong>${revealed ? format(labelView.actual) : "—"}</strong><small>${actualLabel}</small></div><div class="session-value-card${revealed ? "" : " muted-value"}"><span>Absolute error</span><strong>${revealed ? format(labelView.absoluteError) : "—"}</strong><small>${errorLabel}</small></div></div>
        ${pending ? '<p class="pending-note"><span>i</span> ต้นทางยังไม่ให้คะแนน ณ วันตัดข้อมูล จึงไม่แสดงค่าจริงหรือความคลาดเคลื่อน แม้เลือกวันหลังจากนั้น</p>' : ""}${noForecastWarning}
        <section class="session-chart-panel" aria-labelledby="session-chart-heading"><div class="session-chart-heading"><div><h3 id="session-chart-heading">Forecast และ Actual ของ session ที่บันทึกไว้</h3><p>Actual จะแสดงเมื่อ target ครบและ source เป็น Evaluable จุดที่เลือกในกราฟตรงกับวันด้านบน</p></div><span class="pill pill-neutral">${available.length.toLocaleString()} วัน</span></div><div class="session-timeline"><label for="session-index">เลือกวันจาก ${available.length.toLocaleString()} วันทำการ</label><div class="session-date-controls"><button class="session-boundary-button" type="button" data-action="first" ${index === 0 ? "disabled" : ""}>วันแรก</button><select id="session-date-select" data-field="session-date" aria-label="เลือกวันทำนายที่บันทึกไว้">${available.map((session, itemIndex) => `<option value="${escapeHtml(session.predictionDate)}" ${itemIndex === index ? "selected" : ""}>${escapeHtml(session.predictionDate)} (${itemIndex + 1}/${available.length})</option>`).join("")}</select><button class="session-boundary-button" type="button" data-action="last" ${index >= available.length - 1 ? "disabled" : ""}>วันล่าสุด</button></div><input id="session-index" class="session-timeline-slider" type="range" min="0" max="${available.length - 1}" step="1" value="${index}" data-field="session-index" aria-label="เลื่อนไปยังวันพยากรณ์ที่บันทึกไว้" aria-valuetext="${escapeHtml(row.predictionDate)}, วันที่ ${index + 1} จาก ${available.length}" /><div class="session-timeline-meta"><span>เริ่ม ${escapeHtml(available[0].predictionDate)}</span><span>สิ้นสุด ${escapeHtml(available[available.length - 1].predictionDate)}</span></div></div><div class="session-play-row"><button class="button button-secondary session-play-button" type="button" data-action="toggle-session-play" aria-pressed="${state.sessionPlaying}" ${available.length < 2 ? "disabled" : ""}>${state.sessionPlaying ? "หยุดเล่น" : "เล่นวันต่อเนื่อง"}</button><label class="field-label session-speed-control">ความเร็ว<select data-field="session-speed"><option value="1600" ${state.sessionSpeedMs === 1600 ? "selected" : ""}>ช้า (1.6 วินาที)</option><option value="900" ${state.sessionSpeedMs === 900 ? "selected" : ""}>ปกติ (0.9 วินาที)</option><option value="450" ${state.sessionSpeedMs === 450 ? "selected" : ""}>เร็ว (0.45 วินาที)</option></select></label><span class="session-play-note">${state.sessionPlaying ? "กำลังเล่น forecast ที่บันทึกไว้ ไม่รันโมเดล" : "เล่นเฉพาะข้อมูลที่บันทึกไว้ ไม่รันโมเดล"}</span></div>${renderSessionChart(chartPoints, row.predictionDate, state.unit)}</section>
      </div><aside class="session-inspector" aria-label="รายละเอียดของ session ที่เลือก"><section class="same-date-comparison"><div class="section-card-heading"><div><h3>เทียบ forecast ทั้ง 4 โมเดล: ${escapeHtml(row.predictionDate)}, ${selection.ticker}</h3></div><span class="pill pill-neutral">${comparisonRows.length}/4 source rows</span></div><p>ค่าทั้งหมดผูกกับวันและสินทรัพย์เดียวกัน สถานะ source ของแต่ละโมเดลยังคงเดิม</p><div class="table-scroll"><table class="data-table"><caption class="visually-hidden">B0 to B3 recorded forecasts for ${selection.ticker} on ${row.predictionDate}</caption><thead><tr><th scope="col">Model</th><th scope="col">Forecast RV5</th><th scope="col">Actual หลังครบช่วง</th><th scope="col">Absolute error</th><th scope="col">Source status</th><th scope="col">Record</th></tr></thead><tbody>${comparisonTableRows.join("")}</tbody></table></div></section>
      <details class="session-source-details" id="session-source-details" data-persist-open><summary>เปิด Source record และหลักฐานของแถวที่เลือก</summary><div class="session-source-grid"><span>Prediction ID</span><code>${escapeHtml(row.predictionId)}</code><span>Prediction date</span><strong>${escapeHtml(row.predictionDate)} · XNYS</strong><span>Target window</span><strong>${escapeHtml(row.targetStartDate)} → ${escapeHtml(row.targetEndDate)}</strong><span>Forecast / label / evaluation</span><strong>${escapeHtml(row.forecastStatus)} · ${escapeHtml(row.labelStatus)} · ${escapeHtml(row.evaluationStatus)}</strong><span>Source files</span><strong>forecast_audit.csv${evaluation ? " · evaluation.csv" : ""}</strong><span>Evaluation ID</span><code>${escapeHtml(snapshot.manifest.evaluationId)}</code><span>Replay ID</span><code>${escapeHtml(snapshot.manifest.replayId)}</code></div><small>As-of eligibility is an instructional overlay. Snapshot status and the official evaluation remain unchanged.</small></details>
      <div class="session-footer"><span>Prediction ID <code>${escapeHtml(row.predictionId)}</code></span><span>${escapeHtml(tickerLabel[selection.ticker])} · ${modelId(selection.modelName)}</span></div>
      <div class="session-actions"><span>เปลี่ยนเฉพาะการเลือก observation ที่บันทึกไว้</span><button class="button button-secondary" type="button" data-action="open-portfolio" ${portfolioReady ? "" : "disabled"}>ใช้วันและโมเดลนี้ใน Portfolio →</button></div>${!portfolioReady ? '<p class="chart-note">ไม่มี portfolio row สถานะ OK สำหรับ ' + escapeHtml(row.predictionDate) + ' · ' + modelId(selection.modelName) + ' จึงยังเปิด what-if วันนี้ไม่ได้</p>' : ""}</aside></div>
    </section>`;
}

function stopSessionPlayback(state: ViewState): void {
  if (state.sessionTimer !== null) window.clearInterval(state.sessionTimer);
  state.sessionTimer = null;
  state.sessionPlaying = false;
}

function setSessionIndex(root: HTMLElement, state: ViewState, index: number, historyMode: "push" | "replace" = "push"): void {
  stopSessionPlayback(state);
  if (state.snapshot.status !== "ready" || !state.selection) return;
  const available = selectionSessions(state.snapshot, state.selection);
  const nextIndex = Math.max(0, Math.min(index, available.length - 1));
  const row = available[nextIndex];
  if (!row) return;
  publishSelection(root, state, { ...state.selection, predictionDate: row.predictionDate, asOfDate: row.predictionDate }, historyMode);
}

function portfolioDateSequence(state: ViewState): string[] {
  if (state.snapshot.status !== "ready" || !state.selection || state.routePath !== "/portfolio") return [];
  return portfolioRiskSourceDates(state.snapshot.portfolioRisk, state.selection.modelName);
}

function setPortfolioDateIndex(root: HTMLElement, state: ViewState, index: number, historyMode: "push" | "replace" = "push"): void {
  if (state.snapshot.status !== "ready" || !state.selection || state.routePath !== "/portfolio") return;
  const dates = portfolioDateSequence(state);
  const selectedIndex = Math.max(0, Math.min(index, dates.length - 1));
  const date = dates[selectedIndex];
  if (!date) return;
  stopSessionPlayback(state);
  publishSelection(root, state, { ...state.selection, predictionDate: date, asOfDate: date }, historyMode);
}

function playbackDateSequence(state: ViewState): string[] {
  if (state.snapshot.status !== "ready" || !state.selection) return [];
  if (state.routePath === "/forecasts") return selectionSessions(state.snapshot, state.selection).map((row) => row.predictionDate);
  if (state.routePath === "/portfolio") return portfolioDateSequence(state);
  return [];
}

function toggleSessionPlayback(root: HTMLElement, state: ViewState): void {
  if (state.sessionPlaying) {
    stopSessionPlayback(state);
    render(root, state);
    return;
  }
  if (state.snapshot.status !== "ready" || !state.selection || !["/forecasts", "/portfolio"].includes(state.routePath)) return;
  const availableDates = playbackDateSequence(state);
  if (availableDates.length < 2) return;
  const currentIndex = availableDates.indexOf(state.selection.predictionDate);
  if (currentIndex < 0) return;
  if (currentIndex >= availableDates.length - 1) {
    const firstDate = availableDates[0];
    if (!firstDate) return;
    publishSelection(root, state, { ...state.selection, predictionDate: firstDate, asOfDate: firstDate }, "replace");
  }
  state.sessionPlaying = true;
  state.sessionTimer = window.setInterval(() => {
    if (!root.isConnected || document.hidden || !["/forecasts", "/portfolio"].includes(state.routePath) || state.snapshot.status !== "ready" || !state.selection || state.selectionError) {
      stopSessionPlayback(state);
      render(root, state);
      return;
    }
    const currentDates = playbackDateSequence(state);
    const index = currentDates.indexOf(state.selection.predictionDate);
    if (index < 0 || index >= currentDates.length - 1) {
      stopSessionPlayback(state);
      render(root, state);
      return;
    }
    const next = currentDates[index + 1];
    if (!next) {
      stopSessionPlayback(state);
      render(root, state);
      return;
    }
    if (index + 1 >= currentDates.length - 1) stopSessionPlayback(state);
    publishSelection(root, state, { ...state.selection, predictionDate: next, asOfDate: next }, "replace");
  }, state.sessionSpeedMs);
  render(root, state);
}

function descriptiveRangePanel(state: ViewState, snapshot: Extract<SnapshotState, { status: "ready" }>): string {
  const commonDates = commonRangeDates(snapshot);
  const firstDate = commonDates[0] ?? "";
  const lastDate = commonDates[commonDates.length - 1] ?? "";
  const last20Start = commonDates[Math.max(0, commonDates.length - 20)] ?? firstDate;
  const startDate = state.rangePreset === "all-test" ? firstDate : state.rangePreset === "last20" ? last20Start : state.rangeFrom || firstDate;
  const endDate = state.rangePreset === "all-test" ? lastDate : state.rangePreset === "last20" ? lastDate : state.rangeTo || lastDate;
  const result = calculateDescriptiveRangeMetrics(snapshot.sessions, snapshot.evaluations, startDate, endDate, state.rangeTicker);
  const rangeTickerOptions = metricTickerNames.map((ticker) => `<option value="${ticker}" ${ticker === state.rangeTicker ? "selected" : ""}>${ticker === "MACRO" ? "ภาพรวม ETF" : ticker}</option>`).join("");
  const presetOptions = [
    ["all-test", "Test ทั้งหมด"], ["last20", "20 วันล่าสุดที่มีข้อมูล"], ["custom", "กำหนดช่วงเอง"],
  ].map(([value, label]) => `<option value="${value}" ${state.rangePreset === value ? "selected" : ""}>${label}</option>`).join("");
  let resultContent: string;
  if (result.status === "insufficient") {
    resultContent = emptyState("ข้อมูลยังไม่พอสำหรับช่วงนี้", `${result.reason} · เลือกช่วงที่มี วันข้อมูลร่วมของ B0–B3 ครบก่อน`);
  } else {
    const values = result.scores.map((score) => state.rangeMetric === "mae" ? score.mae : score.rmse).filter((value): value is number => value !== null);
    const maxValue = Math.max(...values, Number.EPSILON);
    const bars = result.scores.map((score, index) => {
      const value = state.rangeMetric === "mae" ? score.mae : score.rmse;
      if (value === null) return "";
      const y = 13 + index * 39;
      const barWidth = Math.max(2, 510 * value / maxValue);
      return `<g><text class="chart-model-label" x="0" y="${y + 18}">${modelId(score.modelName)}</text><rect x="54" y="${y + 3}" width="${barWidth}" height="19" rx="5" fill="${modelColors[score.modelName]}"><title>${modelId(score.modelName)} ${metricName(state.rangeMetric)} ${formatVol(value, state.unit)} · N=${score.n}</title></rect><text class="chart-value-label" x="${Math.min(565, 64 + barWidth)}" y="${y + 18}">${formatVol(value, state.unit)}</text></g>`;
    }).join("");
    const b3 = result.scores.find((score) => score.modelName === "ONLINE_SGD");
    const tableRows = result.scores.map((score) => {
      const delta = score.modelName === "ONLINE_SGD" || score.mae === null || b3?.mae === null || b3?.mae === undefined ? null : score.mae - b3.mae;
      const relative = delta === null || score.mae === null || score.mae === 0 ? null : delta / score.mae * 100;
      return `<tr><th scope="row">${modelId(score.modelName)}</th><td>${formatVol(score.mae, state.unit)}</td><td>${formatVol(score.rmse, state.unit)}</td><td>${score.n.toLocaleString()}</td><td>${delta === null ? "—" : formatVol(delta, state.unit)}</td><td>${relative === null ? "—" : `${relative.toFixed(2)}%`}</td></tr>`;
    }).join("");
    const tickerN = state.rangeTicker === "MACRO"
      ? ["SPY", "IEF", "GLD"].map((ticker) => `${ticker} ${result.nByTicker[ticker as Ticker] ?? 0}`).join(" · ")
      : `${state.rangeTicker} ${result.nByTicker[state.rangeTicker] ?? 0}`;
    resultContent = `${result.smallSample ? '<p class="range-warning"><strong>ตัวอย่างมีขนาดเล็ก</strong> ใช้อ่านแนวโน้มในช่วงที่เลือกเท่านั้น Test เต็ม</p>' : ""}<div class="range-summary-strip"><span>จำนวนคู่ที่ใช้ร่วมกัน <strong>${result.n.toLocaleString()}</strong></span><span>แยกตาม ETF <strong>${tickerN}</strong></span></div><div class="chart-scroll"><svg class="metric-bar-chart range-metric-chart" role="img" aria-label="Exploratory ${metricName(state.rangeMetric)} by model from ${startDate} to ${endDate}" viewBox="0 0 660 180" preserveAspectRatio="xMinYMin meet">${bars}</svg></div><div class="table-scroll"><table class="data-table"><caption class="visually-hidden">Descriptive paired metrics for selected Test range</caption><thead><tr><th scope="col">Model</th><th scope="col">MAE</th><th scope="col">RMSE</th><th scope="col">N</th><th scope="col">ΔMAE vs B3</th><th scope="col">Relative Δ</th></tr></thead><tbody>${tableRows}</tbody></table></div>`;
  }
  return `<section class="analysis-card descriptive-range-card"><div class="section-card-heading"><div><h3>ทดลองเลือกช่วงวันที่</h3><p>คำนวณ MAE/RMSE จาก paired anchors ที่ครบกำหนดของ B0–B3 โดยใช้วันเดียวกัน</p></div><span class="pill pill-neutral">ใช้ชุดข้อมูลร่วมกัน</span></div><div class="range-filter-grid"><label class="field-label">ช่วงข้อมูล<select data-field="range-preset">${presetOptions}</select></label><label class="field-label">ETF / aggregate<select data-field="range-ticker">${rangeTickerOptions}</select></label><label class="field-label">Metric<select data-field="range-metric"><option value="mae" ${state.rangeMetric === "mae" ? "selected" : ""}>MAE</option><option value="rmse" ${state.rangeMetric === "rmse" ? "selected" : ""}>RMSE</option></select></label><label class="field-label">ตั้งแต่วันที่<input type="date" data-field="range-from" min="${escapeHtml(firstDate)}" max="${escapeHtml(lastDate)}" value="${escapeHtml(startDate)}" ${state.rangePreset !== "custom" ? "disabled" : ""}></label><label class="field-label">ถึงวันที่<input type="date" data-field="range-to" min="${escapeHtml(firstDate)}" max="${escapeHtml(lastDate)}" value="${escapeHtml(endDate)}" ${state.rangePreset !== "custom" ? "disabled" : ""}></label></div><div class="range-result-heading"><strong>${escapeHtml(startDate || "—")} → ${escapeHtml(endDate || "—")}</strong><span>Exploratory subset · descriptive only</span></div>${resultContent}${sourceFooter("forecast_audit.csv + evaluation.csv", "Test · selected date range", `${state.rangeTicker} · ${startDate} → ${endDate}`, result.n, `annualized volatility (${state.unit}) · common paired anchors`, snapshot.manifest.evaluationId)}<p class="range-limitation">เป็นค่าสรุปเชิงพรรณนาของช่วงที่เลือกเท่านั้น · ไม่ใช่ H2/H3 test ใหม่ · p-values, CIs และ Official Test ด้านบนไม่เปลี่ยนตามตัวกรองนี้ · <a href="${escapeHtml(routeHash("/research", state))}">ดูผล H1–H3 ที่ตรึงไว้</a></p></section>`;
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
    ? `<div class="table-scroll"><table class="data-table"><caption class="visually-hidden">Paired B3 comparison results for ${state.modelTicker}</caption><thead><tr><th scope="col">Comparison</th><th scope="col">Baseline → B3</th><th scope="col">ΔMAE</th><th scope="col">Relative improvement</th><th scope="col">วันข้อมูลร่วม</th></tr></thead><tbody>${pairRows.map((row) => `<tr><th scope="row"><span class="status-chip status-outline">${row.comparisonId}</span></th><td>${modelId(row.baselineModel)} → B3</td><td title="Baseline MAE minus B3 MAE">${formatVol(row.deltaMaeBaselineMinusOnline, state.unit)}</td><td>${row.relativeImprovementPct.toFixed(2)}%</td><td>${row.pairedN.toLocaleString()}</td></tr>`).join("")}</tbody></table></div>${sourceFooter("pair_comparisons.csv", "Test · paired", `${state.modelTicker} · per comparison`, pairRows[0]?.pairedN ?? 0, `annualized decimal (${state.unit}) · paired N per row`, snapshot.manifest.evaluationId)}`
    : emptyState("ไม่มี paired comparison สำหรับตัวเลือกนี้", "แสดงเฉพาะ comparison ที่อยู่ใน frozen source.");
  return `<div class="page-stack">
    <section class="analysis-card analysis-card-primary"><div class="section-card-heading"><div><h2 class="analysis-title">คะแนน Test ของ B0–B3</h2><p>เทียบทุกโมเดลจากวันเดียวกัน จำนวนวันข้อมูลร่วมแสดงเป็น N</p></div><span class="readonly-pill">${icon("lock", 14)} ผลที่บันทึกไว้</span></div><div class="inline-controls"><label class="field-label">สินทรัพย์หรือภาพรวม<select data-field="model-ticker">${metricTickerNames.map((ticker) => `<option value="${ticker}" ${state.modelTicker === ticker ? "selected" : ""}>${ticker === "MACRO" ? "ภาพรวม ETF (MACRO)" : ticker}</option>`).join("")}</select></label><label class="field-label">Metric<select data-field="metric"><option value="mae" ${state.metric === "mae" ? "selected" : ""}>MAE</option><option value="rmse" ${state.metric === "rmse" ? "selected" : ""}>RMSE</option></select></label></div>${metricChart(metricRows, state.metric, state.unit, `Stored Test ${state.modelTicker} ${metricName(state.metric)} by model`)}<div class="model-definition-grid">${modelNames.map((model) => `<article class="model-definition" style="--model-color:${modelColors[model]}"><span class="model-chip">${modelId(model)}</span><strong>${escapeHtml(modelLabel(model))}</strong><small>${model === "ONLINE_SGD" ? "B3 · online model" : `${modelId(model)} · comparator`}</small></article>`).join("")}</div><div class="comparison-note"><strong>วิธีเทียบ</strong><span>เปรียบเทียบจากวันข้อมูลเดียวกัน ส่วน MACRO ใช้ค่ารวมที่บันทึกไว้</span></div>${sourceFooter("model_metrics.csv", "Test", `${state.modelTicker} · B0–B3`, metricRows[0]?.pairedN ?? 0, `annualized decimal (${state.unit}) · common paired dates`, snapshot.manifest.evaluationId)}</section>
    <details class="analysis-disclosure" id="models-range-analysis" data-persist-open><summary>ดูผลเมื่อเลือกช่วงวันที่</summary>${descriptiveRangePanel(state, snapshot)}</details>
    <section class="analysis-card"><div class="section-card-heading"><div><h3>B3 เทียบกับ baseline · Official Test</h3></div><span class="pill pill-neutral">ΔMAE เป็นบวก = B3 มี error ต่ำกว่า</span></div>${pairTable}</section>
    <section class="limitation-card"><span class="limitation-mark">i</span><p>ผลนี้อธิบาย frozen Test sample เท่านั้น ไม่ยืนยันความเหนือกว่าในอนาคต และไม่ใช่ผล Validation หรือผลคาดการณ์สด</p></section>
  </div>`;
}

function portfolioPage(state: ViewState): string {
  const snapshot = state.snapshot;
  if (snapshot.status === "loading") return loadingState();
  if (snapshot.status !== "ready") return snapshot.status === "error" ? errorState(snapshot.message) : emptyState("ยังโหลดข้อมูล Portfolio ไม่ได้", "ต้องตรวจไฟล์ portfolio_risk.csv และ covariance ที่บันทึกไว้ให้ครบก่อน");
  const selection = state.selection;
  if (!selection) return selectionUnavailable(state);
  const row = recordedPortfolioRow(snapshot, selection.predictionDate, selection.modelName);
  if (!row) return selectionUnavailable({ ...state, selectionError: `ไม่มี recorded portfolio row สำหรับ ${selection.predictionDate} · ${modelId(selection.modelName)}` });
  const availableDates = portfolioRiskSourceDates(snapshot.portfolioRisk, selection.modelName);
  const availableModels = modelNames.filter((model) => recordedPortfolioRow(snapshot, selection.predictionDate, model) !== undefined);
  return `${selectionContextSummary(state)}${renderFinancialDecisionLab({
    rows: snapshot.portfolioRisk,
    selectedRow: row,
    selection,
    decision: state.financialDecision,
    availableDates,
    availableModels,
    sessionPlaying: state.sessionPlaying,
    sessionSpeedMs: state.sessionSpeedMs,
    modelMetrics: snapshot.modelMetrics,
    coverage: snapshot.coverage,
    unit: state.unit,
    budgetDraft: state.riskBudgetDraft,
    budgetError: state.riskBudgetError,
    evaluationId: snapshot.manifest.evaluationId,
    strictCutoff: snapshot.manifest.strictCutoff,
    pointInTimeSourceAvailabilityVerified: snapshot.manifest.pointInTimeSourceAvailabilityVerified,
  })}${sourceFooter("portfolio_risk.csv", "Test", `${row.predictionDate} · ${modelId(row.modelName)} · ${state.financialDecision.activeScenario}`, 1, `annualized volatility (${state.unit})`, snapshot.manifest.evaluationId)}`;
}

function rollingMaeChart(rows: RollingMae20Row[], state: ViewState): string {
  const selection = state.selection;
  if (!selection) return emptyState("ไม่มี session ที่เลือก", "เลือก recorded Test session ก่อนเปิด Drift");
  if (rows.length === 0) return emptyState("ไม่พบ rolling window ตามตัวกรอง", "เลือก model, asset หรือช่วงวันที่ที่มีข้อมูลใน source");
  const values = [...rows].sort((left, right) => left.windowEnd.localeCompare(right.windowEnd));
  const maxValue = Math.max(...values.map((row) => row.mae), Number.EPSILON);
  const points = values.map((row, index) => `${44 + index * (760 / Math.max(values.length - 1, 1))},${182 - row.mae / maxValue * 145}`).join(" ");
  const circles = values.map((row, index) => `<circle cx="${44 + index * (760 / Math.max(values.length - 1, 1))}" cy="${182 - row.mae / maxValue * 145}" r="2.2" fill="${modelColors[row.modelName]}"><title>${row.windowEnd} · ${modelId(row.modelName)} MAE ${formatVol(row.mae, state.unit)} · N=${row.evaluableCount}/${row.expectedAnchorCount} · fixed ${row.windowSessionCount} XNYS sessions</title></circle>`).join("");
  const tableRows = values.map((row) => `<tr><th scope="row">${escapeHtml(row.windowEnd)}</th><td>${modelId(row.modelName)}</td><td>${formatVol(row.mae, state.unit)}</td><td>${row.evaluableCount.toLocaleString()}</td><td>${row.expectedAnchorCount.toLocaleString()}</td><td>${row.windowSessionCount}</td></tr>`);
  return `<div class="chart-scroll"><svg class="trend-chart" role="img" aria-label="Rolling MAE20 for ${selection.ticker} ${modelId(selection.modelName)}" viewBox="0 0 840 218"><line x1="44" y1="182" x2="804" y2="182" class="chart-axis"/><line x1="44" y1="37" x2="44" y2="182" class="chart-axis"/><polyline points="${points}" fill="none" stroke="${modelColors[selection.modelName]}" stroke-width="2"/>${circles}<text x="44" y="206" class="chart-date-label">${escapeHtml(values[0].windowEnd)}</text><text x="804" y="206" text-anchor="end" class="chart-date-label">${escapeHtml(values[values.length - 1].windowEnd)}</text><text x="5" y="42" class="chart-date-label">${formatVol(maxValue, state.unit, 2)}</text></svg></div><div class="chart-legend"><span><i style="--legend-color:${modelColors[selection.modelName]}"></i>${modelId(selection.modelName)} · source rolling MAE20</span><span>${values.length.toLocaleString()} fixed windows</span></div>${chartDataTable(`Rolling MAE20 values for ${selection.ticker} ${modelId(selection.modelName)}`, ["Window end", "Model", "MAE", "Evaluable N", "Expected anchors", "Window sessions"], tableRows)}`;
}

function adwinTimelineChart(rows: DriftTimelineRow[], ticker: Ticker, unit: DisplayUnit, selectedPredictionId: string): string {
  if (rows.length === 0) return emptyState("ไม่มี ADWIN row ตามตัวกรอง", "เลือกช่วงวันที่ที่อยู่ใน verified B3 Test timeline");
  const values = [...rows].sort((left, right) => left.predictionDate.localeCompare(right.predictionDate));
  const maxValue = Math.max(...values.map((row) => row.absoluteErrorAdwin), Number.EPSILON);
  const points = values.map((row, index) => `${44 + index * (760 / Math.max(values.length - 1, 1))},${182 - row.absoluteErrorAdwin / maxValue * 145}`).join(" ");
  const circles = values.map((row, index) => {
    const selected = row.predictionId === selectedPredictionId;
    return `<circle class="adwin-observation${selected ? " selected" : ""}" tabindex="0" role="button" aria-label="เลือก ${row.predictionDate} ${ticker} B3 observation, absolute error ${formatVol(row.absoluteErrorAdwin, unit)}, drift ${row.driftDetected ? "detected" : "not detected"}" aria-pressed="${selected}" data-action="select-drift-observation" data-prediction-id="${escapeHtml(row.predictionId)}" cx="${44 + index * (760 / Math.max(values.length - 1, 1))}" cy="${182 - row.absoluteErrorAdwin / maxValue * 145}" r="${selected ? 5.2 : row.driftDetected ? 4 : 2.7}" fill="${row.driftDetected ? "#b54545" : "#496b88"}"><title>${row.predictionDate} · ${ticker} · B3 error ${formatVol(row.absoluteErrorAdwin, unit)} · drift_detected=${row.driftDetected} · alert_record_present=${row.alertRecordPresent}</title></circle>`;
  }).join("");
  const alerts = values.filter((row) => row.driftDetected || row.alertRecordPresent).length;
  const tableRows = values.map((row) => `<tr${row.predictionId === selectedPredictionId ? ' class="selected-observation-row"' : ""}><th scope="row"><button class="table-link" type="button" data-action="select-drift-observation" data-prediction-id="${escapeHtml(row.predictionId)}" aria-pressed="${row.predictionId === selectedPredictionId}">${escapeHtml(row.predictionDate)}</button></th><td>${formatVol(row.absoluteErrorAdwin, unit)}</td><td>${row.driftDetected ? "Yes" : "No"}</td><td>${row.alertRecordPresent ? "Yes" : "No"}</td></tr>`);
  return `<div class="chart-scroll"><svg class="trend-chart" role="img" aria-label="Recorded B3 ADWIN error timeline for ${ticker}, ${alerts} recorded alerts" viewBox="0 0 840 218"><line x1="44" y1="182" x2="804" y2="182" class="chart-axis"/><line x1="44" y1="37" x2="44" y2="182" class="chart-axis"/><polyline points="${points}" fill="none" stroke="#496b88" stroke-width="1.8"/>${circles}<text x="44" y="206" class="chart-date-label">${escapeHtml(values[0].predictionDate)}</text><text x="804" y="206" text-anchor="end" class="chart-date-label">${escapeHtml(values[values.length - 1].predictionDate)}</text><text x="5" y="42" class="chart-date-label">${formatVol(maxValue, unit, 2)}</text></svg></div><div class="chart-legend"><span><i style="--legend-color:#496b88"></i>Recorded absolute_error_adwin</span><span>${alerts} source-recorded alerts</span><span>เลือกจุดหรือวันที่เพื่อเปิดรายละเอียด</span></div>${chartDataTable(`Recorded B3 ADWIN error values for ${ticker}`, ["Prediction date", "Absolute error", "พบ drift", "มี alert ในข้อมูลต้นทาง"], tableRows)}`;
}

function driftPage(state: ViewState): string {
  const snapshot = state.snapshot;
  if (snapshot.status === "loading") return loadingState();
  if (snapshot.status !== "ready") return snapshot.status === "error" ? errorState(snapshot.message) : emptyState("ยังโหลดข้อมูล Drift ไม่ได้", "ไฟล์ rolling_mae20.csv และ drift_error_timeline.csv ต้องผ่านการตรวจสอบก่อน");
  const selection = state.selection;
  if (!selection) return selectionUnavailable(state);
  const rolling = snapshot.rollingMae20.filter((row) => row.split === "test" && row.ticker === selection.ticker && row.modelName === selection.modelName && (!state.driftFrom || row.windowEnd >= state.driftFrom) && (!state.driftTo || row.windowEnd <= state.driftTo));
  const supportsAdwin = selection.modelName === "ONLINE_SGD";
  const timeline = supportsAdwin ? snapshot.driftTimeline.filter((row) => row.ticker === selection.ticker && (!state.driftFrom || row.predictionDate >= state.driftFrom) && (!state.driftTo || row.predictionDate <= state.driftTo)) : [];
  const alertCount = timeline.filter((row) => row.driftDetected || row.alertRecordPresent).length;
  const selectedObservation = timeline.find((row) => row.predictionDate === selection.predictionDate && row.ticker === selection.ticker);
  const alertSummary = !supportsAdwin ? "ไม่พร้อม · ADWIN มีข้อมูลเฉพาะ B3" : timeline.length === 0 ? "ไม่พบข้อมูล ADWIN ในช่วงนี้" : `พบ ${alertCount} alert ในรายการที่เลือก`;
  const flowSteps = [
    ["01", "ทำนายและบันทึก", "บันทึก forecast ณ เวลา t"],
    ["02", "label ครบกำหนด", "รอ target ครบ 5 sessions"],
    ["03", "ประเมินผล", "คำนวณ error เมื่อ evaluable"],
    ["04", "Monitor ด้วย ADWIN", "ตรวจ error ที่ป้อนเข้า monitor"],
    ["05", "อัปเดต B3", "อัปเดตตาม learning policy"],
    ["06", "บันทึก checkpoint", "บันทึกสถานะเพื่อ resume"],
  ];
  const conceptualFlow = '<section class="conceptual-flow-card" aria-label="ลำดับการทำงานเชิงแนวคิด"><div><h2>Forecast → label ครบกำหนด → ประเมินผล → monitor → update → checkpoint</h2><p>ลำดับนี้อธิบาย online learning · จุดและสถานะด้านล่างอ่านจากข้อมูลที่บันทึกไว้</p></div><ol class="conceptual-flow">' +
    flowSteps.map(([step, title, detail]) => "<li><span>" + step + "</span><strong>" + title + "</strong><small>" + detail + "</small></li>").join("") +
    '</ol><p class="flow-evidence-limit">snapshot นี้มี rolling MAE และ ADWIN observation แต่ไม่มีบันทึก update/checkpoint รายเหตุการณ์ จึงยืนยันขั้น 05–06 ในแต่ละวันไม่ได้</p></section>';
  const filters = `<div class="forecast-filters"><label class="field-label">สินทรัพย์<select data-field="ticker">${tickerNames.map((ticker) => `<option value="${ticker}" ${ticker === selection.ticker ? "selected" : ""}>${ticker}</option>`).join("")}</select></label><label class="field-label">โมเดล<select data-field="model">${modelNames.map((model) => `<option value="${model}" ${model === selection.modelName ? "selected" : ""}>${modelId(model)} · ${escapeHtml(modelLabel(model))}</option>`).join("")}</select></label></div><details class="filter-disclosure" id="drift-advanced-filters" data-persist-open><summary>ตัวกรองเพิ่มเติม <span>วันที่และ observation</span></summary><div class="forecast-filter-advanced"><label class="field-label">ตั้งแต่วันที่<input type="date" data-field="drift-from" value="${escapeHtml(state.driftFrom)}"></label><label class="field-label">ถึงวันที่<input type="date" data-field="drift-to" value="${escapeHtml(state.driftTo)}"></label><label class="field-label">วันที่ของ B3<select data-field="drift-observation">${timeline.map((row) => `<option value="${escapeHtml(row.predictionId)}" ${row.predictionDate === selection.predictionDate ? "selected" : ""}>${escapeHtml(row.predictionDate)}</option>`).join("")}</select><small>เลือกวันที่เพื่อเปิดข้อมูล session เดียวกัน</small></label></div></details>`;
  const inspector = selectedObservation ? `<section class="drift-inspector" aria-label="รายละเอียด ADWIN observation"><div class="drift-inspector-heading"><div><h3>${escapeHtml(selectedObservation.predictionDate)} · ${selectedObservation.ticker}</h3><p>ข้อมูลจากแถวที่เลือกใน drift_error_timeline.csv</p></div><span class="pill ${selectedObservation.driftDetected || selectedObservation.alertRecordPresent ? "pill-pending" : "pill-neutral"}">${selectedObservation.driftDetected || selectedObservation.alertRecordPresent ? "มี alert บันทึกไว้" : "ไม่มี alert ในข้อมูลต้นทาง"}</span></div><div class="drift-inspector-grid"><div><small>Absolute error · จาก evaluation</small><strong>${formatVol(selectedObservation.absoluteErrorEvaluation, state.unit)}</strong></div><div><small>Absolute error · ที่ ADWIN ใช้</small><strong>${formatVol(selectedObservation.absoluteErrorAdwin, state.unit)}</strong></div><div><small>พบ drift</small><strong>${selectedObservation.driftDetected ? "พบ" : "ไม่พบ"}</strong></div><div><small>มี alert ในข้อมูลต้นทาง</small><strong>${selectedObservation.alertRecordPresent ? "มี" : "ไม่มี"}</strong></div><div><small>ADWIN delta</small><strong>${selectedObservation.adwinDelta}</strong></div><div><small>ADWIN width</small><strong>${selectedObservation.adwinWidth.toLocaleString()}</strong></div><div><small>ค่าประมาณ ADWIN</small><strong>${formatVol(selectedObservation.adwinEstimation, state.unit)}</strong></div></div><div class="drift-source-ids"><span>Prediction ID <code>${escapeHtml(selectedObservation.predictionId)}</code></span><span>Evaluation ID <code>${escapeHtml(snapshot.manifest.evaluationId)}</code></span><span>Replay ID <code>${escapeHtml(snapshot.manifest.replayId)}</code></span></div><p class="drift-history-limitation">snapshot ไม่มีบันทึกการอัปเดตโมเดลหรือ checkpoint รายเหตุการณ์ จึงยืนยันไม่ได้ว่าจุดนี้ทำให้โมเดลอัปเดตหรือเกิด drift นอกเหนือจาก flag ที่บันทึกไว้</p></section>` : emptyState(supportsAdwin ? "ไม่พบข้อมูล ADWIN ของ session นี้" : "ADWIN ใช้ได้เฉพาะกับ B3 · ONLINE_SGD", supportsAdwin ? `ไม่พบแถวต้นทางของ ${selection.ticker} · ${selection.predictionDate} ในช่วงที่เลือก` : "เลือกโมเดล B3 เพื่อดู timeline ที่ Stage 06 บันทึกไว้");
  return `<div class="page-stack">${selectionContextSummary(state)}<section class="analysis-card analysis-card-primary drift-workbench">
    <div class="section-card-heading"><div><h2 class="analysis-title">ข้อมูลจาก ADWIN</h2><p>ADWIN ตรวจการเปลี่ยนแปลงของความคลาดเคลื่อนที่บันทึกไว้ หน้านี้ไม่สร้างสัญญาณใหม่</p></div><span class="pill pill-neutral">${alertSummary}</span></div>
    ${filters}<div class="drift-panels"><section class="drift-panel"><div class="section-card-heading"><div><h3>Rolling MAE20</h3><p>แต่ละจุดมาจาก rolling_mae20.csv แสดง N และ coverage ที่บันทึกไว้</p></div></div>${rollingMaeChart(rolling, state)}${sourceFooter("rolling_mae20.csv", "Test", `${selection.ticker} · ${modelId(selection.modelName)}`, rolling.length, `annualized decimal · 20 XNYS sessions`, snapshot.manifest.evaluationId)}</section>
    <section class="drift-panel"><div class="section-card-heading"><div><h3>แนวโน้ม Error</h3><p>แสดง error และ flag จาก Stage 06 โดยไม่สร้าง alert เพิ่มในหน้าเว็บ</p></div></div><div class="drift-adwin-layout"><div>${adwinTimelineChart(timeline, selection.ticker, state.unit, selectedObservation?.predictionId ?? "")}</div>${inspector}</div>${sourceFooter("drift_error_timeline.csv", "Test · B3", selection.ticker, timeline.length, `absolute error (${state.unit})`, snapshot.manifest.evaluationId)}<div class="session-actions"><span>ดูข้อมูลต้นทางวันเดียวกันใน Replay</span><button class="button button-secondary" type="button" data-route="/forecasts">เปิด Replay →</button></div></section></div>
  </section>${conceptualFlow}<section class="limitation-card"><span class="limitation-mark">i</span><p>handoff snapshot ไม่มี event-level update/checkpoint history จุดที่เลือกจึงบอกได้เฉพาะ observation และ flag ที่บันทึกไว้</p></section></div>`;
}

function scatterChart(rows: H1ScatterRow[], ticker: Ticker): string {
  if (rows.length === 0) return emptyState("ไม่พบข้อมูล H1 ในชุด Train", `ไม่มีข้อมูลที่ตรวจสอบแล้วสำหรับ ${ticker}`);
  const xValues = rows.map((row) => row.rv5);
  const yValues = rows.map((row) => row.targetRealizedVol5d);
  const xMin = Math.min(...xValues), xMax = Math.max(...xValues), yMin = Math.min(...yValues), yMax = Math.max(...yValues);
  const x = (value: number) => 42 + (value - xMin) / Math.max(xMax - xMin, Number.EPSILON) * 690;
  const y = (value: number) => 190 - (value - yMin) / Math.max(yMax - yMin, Number.EPSILON) * 154;
  const circles = rows.map((row) => `<circle cx="${x(row.rv5)}" cy="${y(row.targetRealizedVol5d)}" r="2.2" fill="#2e62a5" fill-opacity="0.48"><title>วันทำนาย ${row.date} · ${ticker} · ชุด Train · RV5 ย้อนหลัง ${row.rv5.toFixed(4)} · ความผันผวนจริง 5 วันถัดไป ${row.targetRealizedVol5d.toFixed(4)} · วันสิ้นสุดช่วง ${row.targetEndDate}</title></circle>`).join("");
  const tableRows = rows.map((row) => `<tr><th scope="row">${escapeHtml(row.date)}</th><td>${row.rv5.toFixed(6)}</td><td>${row.targetRealizedVol5d.toFixed(6)}</td><td>${escapeHtml(row.targetEndDate)}</td></tr>`);
  return `<div class="chart-scroll"><svg class="scatter-chart" role="img" aria-label="กราฟกระจาย H1 ชุด Train ของ ${ticker}" viewBox="0 0 770 236"><line x1="42" y1="190" x2="742" y2="190" class="chart-axis"/><line x1="42" y1="36" x2="42" y2="190" class="chart-axis"/>${circles}<text x="390" y="222" text-anchor="middle" class="chart-date-label">RV5 ย้อนหลัง · หน่วยทศนิยมรายปี</text><text x="10" y="40" class="chart-date-label">ความผันผวนจริง 5 วันถัดไป</text><text x="42" y="207" class="chart-date-label">${xMin.toFixed(2)}</text><text x="742" y="207" text-anchor="end" class="chart-date-label">${xMax.toFixed(2)}</text><text x="735" y="43" text-anchor="end" class="chart-date-label">${rows.length.toLocaleString()} จุดใน Train</text></svg></div>${chartDataTable(`ค่า RV5 ย้อนหลังและ Forward RV5 ในชุด Train สำหรับ ${ticker}`, ["วันทำนาย", "RV5 ย้อนหลัง", "Forward RV5", "วันสิ้นสุดช่วงจริง"], tableRows)}`;
}

function researchPage(state: ViewState): string {
  const snapshot = state.snapshot;
  if (snapshot.status === "loading") return loadingState();
  if (snapshot.status !== "ready") return snapshot.status === "error" ? errorState(snapshot.message) : emptyState("ยังโหลดผลการวิจัยไม่ได้", "ตาราง H1–H3 และข้อมูลประกอบต้องผ่านการตรวจสอบก่อนจึงจะแสดงได้");
  const scatterRows = snapshot.h1Scatter.filter((row) => row.ticker === state.researchTicker);
  const h1Rows = snapshot.h1Results.filter((row) => row.ticker === state.researchTicker);
  const sensitivity = snapshot.h1Sensitivity.filter((row) => row.ticker === state.researchTicker).sort((left, right) => left.hacMaxlags - right.hacMaxlags);
  const macroHypotheses = snapshot.hypothesisResults.filter((row) => row.hypothesisId === "H2" || row.hypothesisId === "H3");
  const bootstrapRows = snapshot.bootstrapDiagnostics;
  const highVol = snapshot.highVolatilityMetrics.filter((row) => row.split === "test" && row.ticker === state.researchTicker).sort((left, right) => modelNames.indexOf(left.modelName) - modelNames.indexOf(right.modelName));
  const h1Result = h1Rows[0];
  const h1Method = hypothesisMethodThai("H1", `OLS + Newey-West HAC maxlags=${h1Result?.hacLag ?? 5}; one-sided normal tail; Holm across SPY/IEF/GLD`);
  const h1Table = h1Result
    ? `<div class="table-scroll"><table class="data-table"><caption class="visually-hidden">ผลหลัก H1 จากชุด Train สำหรับ ${state.researchTicker}</caption><thead><tr><th scope="col">ชุดข้อมูล</th><th scope="col">จำนวนจุด (N)</th><th scope="col">เบตา (β)</th><th scope="col">ช่วงความเชื่อมั่น 95%</th><th scope="col">HAC ย้อนหลัง (วัน)</th><th scope="col">ค่า p หลังปรับ Holm</th><th scope="col">ข้อสรุป</th></tr></thead><tbody><tr><th scope="row">Train</th><td>${h1Result.n.toLocaleString()}</td><td>${h1Result.beta.toFixed(6)}</td><td>[${h1Result.ci95.map((value) => value.toFixed(6)).join(", ")}]</td><td>${h1Result.hacLag}</td><td>${h1Result.pHolm.toExponential(3)}</td><td>${escapeHtml(hypothesisDecisionThai(h1Result.decision))}</td></tr></tbody></table></div><p class="research-interpretation"><strong>อ่านผล:</strong> ${escapeHtml(summarizeH1EvidenceThai(h1Result))}</p><p class="chart-note"><strong>วิธีคำนวณ:</strong> ${escapeHtml(h1Method)}</p>`
    : emptyState("ไม่มีผลหลัก H1 สำหรับสินทรัพย์นี้", "ไม่พบแถวที่ผ่านการตรวจสอบใน H1_results.csv");
  const h2h3Cards = macroHypotheses.length
    ? `<div class="research-hypothesis-list">${macroHypotheses.map((row) => renderHypothesisResultCard(row, state.unit)).join("")}</div>`
    : emptyState("ไม่มีผล H2/H3", "ไม่พบผลทดสอบ Test ที่ผ่านการตรวจสอบใน snapshot นี้");
  const bootstrapTable = `<div class="table-scroll"><table class="data-table"><caption class="visually-hidden">ผลตรวจความไวของ bootstrap จากข้อมูลต้นทาง</caption><thead><tr><th scope="col">สมมติฐาน</th><th scope="col">ความยาวช่วง (วัน)</th><th scope="col">จำนวนรอบสุ่ม</th><th scope="col">ค่าคลาดเคลื่อนมาตรฐาน (SE)</th><th scope="col">ช่วงความเชื่อมั่น 95%</th><th scope="col">ค่า p ก่อนปรับ</th><th scope="col">จำนวนคู่ข้อมูลแยกตาม ETF</th></tr></thead><tbody>${bootstrapRows.map((row) => `<tr><th scope="row">${row.hypothesisId} · ตรวจความไว</th><td>${row.blockLength}</td><td>${row.replicates.toLocaleString()}</td><td>${formatVol(row.standardError, state.unit)}</td><td>[${row.ci95.map((value) => formatVol(value, state.unit)).join(", ")}]</td><td>${row.pRaw.toExponential(3)}</td><td>${escapeHtml(Object.entries(row.nByTicker).map(([ticker, n]) => `${ticker} ${n}`).join(" · "))}</td></tr>`).join("")}</tbody></table></div>`;
  const highVolTable = `<div class="table-scroll"><table class="data-table"><caption class="visually-hidden">ผล Test ในวันที่ผันผวนสูงของ ${state.researchTicker} ใช้เกณฑ์ p80 จาก Train</caption><thead><tr><th scope="col">โมเดล</th><th scope="col">เกณฑ์ความผันผวนสูงจาก Train (p80)</th><th scope="col">จำนวนวันที่เข้าเกณฑ์</th><th scope="col">จำนวนวันที่คำนวณร่วมได้</th><th scope="col">MAE</th><th scope="col">RMSE</th></tr></thead><tbody>${highVol.map((row) => `<tr><th scope="row">${modelId(row.modelName)}</th><td>${formatVol(row.trainThreshold, state.unit)}</td><td>${row.highVolAnchorCount}</td><td>${row.highVolCommonEvaluableN}</td><td>${row.highVolCommonEvaluableN === 0 ? "ข้อมูลไม่เพียงพอ (N=0)" : formatVol(row.mae, state.unit)}</td><td>${row.highVolCommonEvaluableN === 0 ? "—" : formatVol(row.rmse, state.unit)}</td></tr>`).join("")}</tbody></table></div><p class="chart-note">เกณฑ์ความผันผวนสูงคำนวณและตรึงไว้จากชุด Train หากชุด Test ไม่มีข้อมูลที่ใช้ได้ จะไม่รายงาน MAE หรือ RMSE</p>`;
  const units = state.unit === "percent" ? "เปอร์เซ็นต์ความผันผวนรายปี" : "ทศนิยมความผันผวนรายปี";
  return `<div class="page-stack"><section class="analysis-card"><div class="section-card-heading"><div><h2 class="analysis-title">RV5 บอกความผันผวนใน 5 วันถัดไปได้หรือไม่?</h2><p>ตรวจว่าค่า RV5 ย้อนหลังสัมพันธ์กับความผันผวนจริงใน 5 วันถัดไปหรือไม่ โดยใช้ข้อมูล Train</p></div></div><label class="field-label">เลือก ETF<select data-field="research-ticker">${tickerNames.map((ticker) => `<option value="${ticker}" ${ticker === state.researchTicker ? "selected" : ""}>${ticker}</option>`).join("")}</select></label>${scatterChart(scatterRows, state.researchTicker)}${researchSourceFooter("H1_scatter_data.csv", "Train", state.researchTicker, scatterRows.length, "ทศนิยมรายปี", snapshot.manifest.evaluationId)}${h1Table}${researchSourceFooter("H1_results.csv", "Train · ผลหลัก HAC 5 วัน", state.researchTicker, h1Result?.n ?? 0, "ค่าสัมประสิทธิ์เบตา", snapshot.manifest.evaluationId)}<details class="research-progressive-details" data-persist-open><summary>ดูผลเมื่อเปลี่ยนจำนวนวันย้อนหลังของ HAC (5, 10, 20 วัน)</summary><div class="table-scroll"><table class="data-table"><caption class="visually-hidden">ผลตรวจความไวของจำนวนวันย้อนหลังสำหรับ H1 ชุด Train</caption><thead><tr><th scope="col">จำนวนวันย้อนหลังของ HAC</th><th scope="col">จำนวนจุด (N)</th><th scope="col">เบตา (β)</th><th scope="col">ช่วงความเชื่อมั่น 95%</th><th scope="col">ค่า p ก่อนปรับ</th></tr></thead><tbody>${sensitivity.map((row) => `<tr><th scope="row">${row.hacMaxlags}${row.hacMaxlags === 5 ? " · ผลหลัก" : " · ตรวจความไว"}</th><td>${row.n.toLocaleString()}</td><td>${row.beta.toFixed(6)}</td><td>[${row.ci95.map((value) => value.toFixed(6)).join(", ")}]</td><td>${row.pRaw.toExponential(3)}</td></tr>`).join("")}</tbody></table></div>${researchSourceFooter("H1_sensitivity.csv", "Train", `${state.researchTicker} · HAC 5/10/20 วัน`, sensitivity.length, "ค่าสถิติจากแหล่งข้อมูล", snapshot.manifest.evaluationId)}</details></section>
    <section class="analysis-card"><div class="section-card-heading"><div><h3>เปรียบเทียบความคลาดเคลื่อนของโมเดล</h3><p>เทียบ MAE ของ B3 กับ baseline บนวันที่มีข้อมูลครบเป็นคู่ในชุด Test</p></div></div>${h2h3Cards}${researchSourceFooter("hypothesis_results.csv", "Test", "H2/H3 · รวม ETF", macroHypotheses.length, units, snapshot.manifest.evaluationId)}<details class="research-progressive-details" data-persist-open><summary>ดูผลตรวจความไวของการสุ่มข้อมูล (Bootstrap)</summary><p class="chart-note">ใช้ดูว่าผลเปลี่ยนหรือไม่เมื่อปรับจำนวนวันต่อบล็อก · เป็นข้อมูลประกอบผลหลัก</p>${bootstrapTable}${researchSourceFooter("bootstrap_diagnostics.csv", "Test · ตรวจความไว", "H2/H3 · บล็อก 5 และ 20 วัน", bootstrapRows.length, units, snapshot.manifest.evaluationId)}</details></section>
    <section class="analysis-card"><div class="section-card-heading"><div><h3>${state.researchTicker} · ใช้เกณฑ์ p80 จากชุด Train</h3><p>เกณฑ์ p80 มาจาก Train และตรึงไว้ หาก Test ไม่มีข้อมูล ระบบไม่แสดง MAE หรือ RMSE</p></div></div>${highVolTable}${researchSourceFooter("high_volatility_metrics.csv", "Test", `${state.researchTicker} · B0–B3`, highVol.length, units, snapshot.manifest.evaluationId)}</section><section class="limitation-card"><span class="limitation-mark">i</span><p>ผล H1–H3 มาจาก snapshot ชุดเดียว ค่า p ช่วงความเชื่อมั่น และข้อสรุปคำนวณไว้แล้ว<br />H1 ใช้ Train ส่วน H2/H3 ใช้ Test หน้านี้ไม่คำนวณสถิติใหม่และผลไม่รับรองอนาคต</p></section></div>`;
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
  const legends = [...selectedModels.map((model) => `<span><i style="--legend-color:${modelColors[model]}"></i>${modelId(model)} forecast</span>`), `<span><i style="--legend-color:#34455e"></i>Actual (ครบกำหนด)</span>`].join("");
  const tableRows = rows.map((row) => {
    const actual = forecastActual(row, state.snapshot as Extract<SnapshotState, { status: "ready" }>).actual;
    const forecast = row.forecastStatus === "VALID" ? row.predictedVolAnnualized : null;
    const pendingTooltip = row.evaluationStatus === "PENDING_LABEL" ? "ยังไม่ให้คะแนน เพราะช่วงเป้าหมายยังไม่ครบภายในวันตัดข้อมูล" : "";
    return `<tr><th scope="row">${escapeHtml(row.predictionDate)}</th><td>${escapeHtml(row.ticker)}</td><td>${modelId(row.modelName)}</td><td>${formatVol(forecast, state.unit)}</td><td title="${pendingTooltip}">${formatVol(actual, state.unit)}</td><td title="${pendingTooltip}">${pendingTooltip ? `<span title="${pendingTooltip}" aria-label="${pendingTooltip}">รอข้อมูลครบ</span>` : row.evaluationStatus === "EVALUABLE" ? "ประเมินได้" : escapeHtml(row.evaluationStatus)}</td></tr>`;
  });
  return `<div class="chart-scroll"><svg class="forecast-chart" viewBox="0 0 880 246" role="img" aria-label="Forecast and mature actual RV5 by recorded prediction date"><line x1="58" y1="210" x2="848" y2="210" class="chart-axis"/><line x1="58" y1="38" x2="58" y2="210" class="chart-axis"/><line x1="58" y1="124" x2="848" y2="124" class="chart-gridline"/><text x="5" y="42" class="chart-date-label">${formatVol(maxValue, state.unit, 2)}</text><text x="58" y="231" class="chart-date-label">${escapeHtml(dates[0])}</text><text x="848" y="231" text-anchor="end" class="chart-date-label">${escapeHtml(dates[dates.length - 1])}</text>${series}<polyline points="${actualLine}" fill="none" stroke="#34455e" stroke-width="1.8" stroke-dasharray="5 4"/>${actualCircles}</svg></div><div class="chart-legend">${legends}</div>${actualPoints.length === 0 ? '<p class="pending-note"><span>i</span> บันทึก Forecast แล้ว แต่ Actual ของแถวที่เลือกยังไม่ครบช่วงข้อมูล</p>' : ""}${chartDataTable(`Filtered forecast chart values for ${state.forecastTicker} in ${state.forecastSplit}`, ["Prediction date", "Ticker", "Model", "Forecast", "Actual (evaluable only)", "Label status"], tableRows)}`;
}

function forecastExplorerPage(state: ViewState): string {
  const snapshot = state.snapshot;
  if (snapshot.status === "loading") return loadingState();
  if (snapshot.status === "missing") return emptyState("ยังไม่มี Forecast ที่บันทึก", "ถ้าไฟล์ snapshot ไม่ครบ ระบบจะไม่สร้างข้อมูลขึ้นมาแทน");
  if (snapshot.status === "error") return errorState(snapshot.message);
  const filter: ForecastFilter = {
    split: state.forecastSplit, ticker: state.forecastTicker, models: state.forecastModels,
    status: state.forecastStatus, from: state.forecastFrom, to: state.forecastTo,
  };
  const rows = filterForecastRows(snapshot.forecasts, filter);
  const tableRows = rows.slice(0, 100).map((row) => {
    const { actual, error } = forecastActual(row, snapshot);
    const forecast = row.forecastStatus === "VALID" ? row.predictedVolAnnualized : null;
    const status = row.evaluationStatus === "PENDING_LABEL" ? "รอข้อมูลครบ" : row.evaluationStatus === "EVALUABLE" ? "ประเมินได้" : row.evaluationStatus;
    const pendingTooltip = row.evaluationStatus === "PENDING_LABEL" ? "ยังไม่ให้คะแนน เพราะช่วงเป้าหมายยังไม่ครบภายในวันตัดข้อมูล" : "";
    const replayAction = row.split === "test"
      ? `<button class="table-link" type="button" data-action="open-session" data-prediction-id="${escapeHtml(row.predictionId)}">${escapeHtml(row.predictionId.slice(0, 12))}…</button>`
      : `<span title="Replay Lab supports Test sessions">Validation · explorer only</span>`;
    return `<tr><td>${escapeHtml(row.predictionDate)}</td><td>${escapeHtml(row.ticker)}</td><td><span class="model-chip" style="--model-color:${modelColors[row.modelName]}">${modelId(row.modelName)}</span></td><td>${formatVol(forecast, state.unit)}</td><td title="${pendingTooltip}">${formatVol(actual, state.unit)}</td><td title="${pendingTooltip}">${formatVol(error, state.unit)}</td><td><span class="status-chip ${row.evaluationStatus === "PENDING_LABEL" ? "status-pending" : row.evaluationStatus === "EVALUABLE" ? "status-evaluable" : "status-neutral"}" ${pendingTooltip ? `title="${pendingTooltip}" aria-label="${pendingTooltip}"` : ""}>${escapeHtml(status)}</span></td><td>${escapeHtml(row.forecastStatus)}</td><td title="${escapeHtml(row.predictionId)}">${replayAction}</td><td>${escapeHtml(row.targetEndDate)}</td></tr>`;
  }).join("");
  const modelOptions = modelNames.map((model) => `<option value="${model}" ${state.forecastModels.includes(model) ? "selected" : ""}>${modelId(model)} · ${escapeHtml(modelLabel(model))}</option>`).join("");
  const selectedModelsLabel = state.forecastModels.map(modelId).join(", ") || "ยังไม่ได้เลือก";
  return `<div class="page-stack forecasts-page">
    ${sessionCard(state)}
      <section class="analysis-card analysis-card-primary"><div class="section-card-heading"><div><h2 class="analysis-title">สำรวจ Forecast ที่บันทึก</h2><p>ดูข้อมูลที่บันทึกและส่งออกผลพร้อมตัวกรองปัจจุบัน</p></div><div class="forecast-export-actions"><span class="readonly-pill">${icon("lock", 14)} ตัดข้อมูล ${snapshot.manifest.strictCutoff}</span><button class="button button-secondary export-button" type="button" data-action="export-forecasts-csv" ${rows.length === 0 ? "disabled" : ""}>ส่งออก CSV</button><button class="button button-secondary export-button" type="button" data-action="export-forecasts-metadata" ${rows.length === 0 ? "disabled" : ""}>ส่งออก metadata</button></div></div>
      <div class="forecast-filters"><label class="field-label">ชุดข้อมูล<select data-field="forecast-split"><option value="test" ${state.forecastSplit === "test" ? "selected" : ""}>Test</option><option value="validation" ${state.forecastSplit === "validation" ? "selected" : ""}>Validation</option></select></label><label class="field-label">สินทรัพย์<select data-field="forecast-ticker">${tickerNames.map((ticker) => `<option value="${ticker}" ${state.forecastTicker === ticker ? "selected" : ""}>${ticker}</option>`).join("")}</select></label><label class="field-label">โมเดลที่ต้องการเทียบ<select data-field="forecast-models" multiple size="4" aria-describedby="model-filter-help">${modelOptions}</select><small id="model-filter-help">เลือกหลายโมเดลด้วย Ctrl หรือ Command</small></label></div><details class="filter-disclosure" id="forecast-advanced-filters" data-persist-open><summary>ตัวกรองเพิ่มเติม <span>สถานะและช่วงวันที่</span></summary><div class="forecast-filter-advanced"><label class="field-label">สถานะผลประเมิน<select data-field="forecast-status"><option value="all" ${state.forecastStatus === "all" ? "selected" : ""}>ทั้งหมด</option><option value="mature" ${state.forecastStatus === "mature" ? "selected" : ""}>ประเมินได้</option><option value="pending" ${state.forecastStatus === "pending" ? "selected" : ""}>รอ target ครบ</option><option value="invalid" ${state.forecastStatus === "invalid" ? "selected" : ""}>ผิดรูปแบบหรือขาดหาย</option></select></label><label class="field-label">ตั้งแต่วันที่<input type="date" data-field="forecast-from" value="${escapeHtml(state.forecastFrom)}"></label><label class="field-label">ถึงวันที่<input type="date" data-field="forecast-to" value="${escapeHtml(state.forecastTo)}"></label></div></details>
      <div class="chart-heading-row"><div><h3>${state.forecastSplit} · ${state.forecastTicker}</h3><p>ช่วงเป้าหมาย t+1 ถึง t+5 วันซื้อขาย · ความผันผวนรายปี</p></div><span class="result-count">${rows.length.toLocaleString()} รายการ · ${selectedModelsLabel}</span></div>${forecastExplorerChart(rows, state)}${sourceFooter("forecast_audit.csv + evaluation.csv", state.forecastSplit, `${state.forecastTicker} · ${selectedModelsLabel}`, rows.length, `annualized decimal (${state.unit})`, snapshot.manifest.evaluationId)}</section>
    <section class="analysis-card"><div class="section-card-heading"><div><h3>ข้อมูลรายแถว</h3><p>แสดง ${Math.min(rows.length, 100).toLocaleString()} จาก ${rows.length.toLocaleString()} แถวแรก เรียงตามวันและโมเดล</p></div><span class="pill pill-neutral">คงคอลัมน์จากต้นทาง</span></div>${rows.length === 0 ? emptyState("ไม่พบแถวตามตัวกรอง", "ลองปรับตัวกรองด้านบน") : `<details class="analysis-disclosure" id="forecast-observation-rows" data-persist-open><summary>ดูข้อมูลรายแถว</summary><div class="table-scroll"><table class="data-table forecast-data-table"><caption class="visually-hidden">Filtered recorded forecasts for ${state.forecastTicker} in ${state.forecastSplit}</caption><thead><tr><th scope="col">วันที่พยากรณ์</th><th scope="col">สินทรัพย์</th><th scope="col">โมเดล</th><th scope="col">Forecast</th><th scope="col">ค่าจริง</th><th scope="col">ความคลาดเคลื่อน</th><th scope="col">ผลประเมิน</th><th scope="col">สถานะ Forecast</th><th scope="col">ID พยากรณ์</th><th scope="col">วันสิ้นสุดช่วง</th></tr></thead><tbody>${tableRows}</tbody></table></div></details>`}${sourceFooter("forecast_audit.csv + evaluation.csv", state.forecastSplit, `${state.forecastTicker} · ${selectedModelsLabel}`, rows.length, `annualized decimal (${state.unit})`, snapshot.manifest.evaluationId)}</section>
  </div>`;
}

function provenancePage(state: ViewState): string {
  const snapshot = state.snapshot;
  if (snapshot.status === "loading") return loadingState();
  if (snapshot.status !== "ready") return emptyState("ยังไม่มี provenance ที่ผ่านการตรวจ", "ซ่อน Source IDs และ checksums จนกว่า adapter จะยืนยัน snapshot ได้");
  const { manifest } = snapshot;
  const files = Object.entries(manifest.files).map(([, file]) => `<div class="source-file-row"><div class="file-type-mark">CSV</div><div class="source-file-details"><strong>${escapeHtml(file.path)}</strong><small>${file.rowCount.toLocaleString()} source rows, ${file.headers.length} columns</small></div><code>${escapeHtml(file.sha256)}</code>${copyValueButton(file.sha256, `${file.path} SHA-256`)}</div>`).join("");
  const selection = state.selection;
  const replayHref = escapeHtml(routeHash("/forecasts", state));
  const portfolioHref = escapeHtml(routeHash("/portfolio", state));
  return `<div class="page-stack">
    <section class="provenance-summary-card"><div class="provenance-summary-top"><div><h2>ผลชุดไหน และควรอ่านอย่างไร</h2></div><span class="verified-badge">${icon("check", 13)} ตรวจชุดข้อมูลแล้ว</span></div><p>ตรวจ snapshot ที่บันทึกไว้นี้ด้วย SHA-256, รหัสชุดข้อมูล และโครงสร้างไฟล์ก่อนแสดงผล</p><div class="provenance-pills"><span class="pill pill-neutral">ตัดข้อมูลถึง ${escapeHtml(manifest.strictCutoff)}</span><span class="pill pill-pending">รายงานยังรออนุมัติ</span></div><p class="provenance-plain-note">ค่า hash ยืนยันว่าไฟล์ตรงกับ snapshot ที่บันทึกไว้ แต่ยืนยันไม่ได้ว่าข้อมูลตลาดพร้อมใช้ ณ วันจำลอง</p><div class="provenance-action-row"><a class="button button-secondary" href="${replayHref}">เปิด Replay ของ session นี้ →</a><a class="button button-secondary" href="${portfolioHref}">เปิด Portfolio ของ session นี้ →</a></div><small class="provenance-selection-note">${selection ? `${escapeHtml(selection.predictionDate)}, ${modelId(selection.modelName)}, ${escapeHtml(selection.ticker)}, ${selection.view === "as-of" ? `ตามข้อมูล ณ ${escapeHtml(selection.asOfDate ?? selection.predictionDate)}` : "ย้อนหลัง"}` : "ยังไม่ได้เลือก session"}</small></section>
    <details class="technical-details-card" id="provenance-run-details" data-persist-open><summary>Run ID, commit และ checksum ของ handoff</summary><div class="technical-details-body"><div class="identity-pair"><span>Evaluation ID</span><code>${escapeHtml(manifest.evaluationId)}</code>${copyValueButton(manifest.evaluationId, "Evaluation ID")}</div><div class="identity-pair"><span>Replay ID</span><code>${escapeHtml(manifest.replayId)}</code>${copyValueButton(manifest.replayId, "Replay ID")}</div><div class="identity-pair"><span>คลัง source</span><a href="https://github.com/${escapeHtml(manifest.sourceRepository)}" target="_blank" rel="noopener noreferrer">${escapeHtml(manifest.sourceRepository)}</a></div><div class="identity-pair"><span>commit ของ handoff</span><a href="https://github.com/${escapeHtml(manifest.sourceRepository)}/commit/${escapeHtml(manifest.sourceHandoffCommit)}" target="_blank" rel="noopener noreferrer"><code>${escapeHtml(manifest.sourceHandoffCommit)}</code></a>${copyValueButton(manifest.sourceHandoffCommit, "handoff commit")}</div><div class="identity-pair"><span>commit ตั้งต้น</span><code>${escapeHtml(manifest.baselineGitCommit)}</code>${copyValueButton(manifest.baselineGitCommit, "baseline commit")}</div><div class="identity-pair"><span>Handoff ZIP SHA-256</span><code>${escapeHtml(manifest.sourceZipSha256)}</code>${copyValueButton(manifest.sourceZipSha256, "ZIP SHA-256")}</div><div class="identity-pair"><span>สถานะอนุมัติรายงาน</span><strong>รออนุมัติ</strong></div></div></details>
    <details class="source-file-card technical-details-card" id="provenance-files" data-persist-open><summary>ไฟล์และ SHA-256 ที่ใช้โดย dashboard · ${Object.keys(manifest.files).length} ไฟล์</summary><div class="technical-details-body"><div class="source-file-list">${files}</div><p class="source-footnote">Build ใช้ manifest และ handoff ID ตรวจสอบชุดข้อมูล · hash ของไฟล์ export อยู่ใน metadata แยกจาก source CSV</p></div></details>
  </div>`;
}

function guidePage(state: ViewState): string {
  const tasks = [
    { title: "ดูผลพยากรณ์รายวัน", route: "/forecasts", description: "เลือกวัน Test แล้วดูค่าพยากรณ์และผลจริง เมื่อประเมินได้", steps: "เลือกวัน → ดูผล → เทียบ B0–B3" },
    { title: "เปรียบเทียบโมเดล", route: "/models", description: "ดูความคลาดเคลื่อนของ B0–B3 และลองเลือกช่วงย่อย", steps: "เทียบวันเดียวกัน → แยกผล Test เต็มจากช่วงทดลอง" },
    { title: "ทดลองน้ำหนักพอร์ต", route: "/portfolio", description: "ปรับสัดส่วนสินทรัพย์ แล้วดูผลต่อความเสี่ยงพอร์ต", steps: "รวมน้ำหนักให้ครบ 100% → เทียบส่วนต่าง → ตั้งงบความเสี่ยง" },
    { title: "อ่านหลักฐานวิจัย", route: "/research", description: "ดูผล H1–H3 พร้อมวิธีทดสอบและข้อจำกัด", steps: "อ่านผล → ตรวจวิธีทดสอบ → ดูข้อจำกัดของข้อมูล" },
  ];
  const definitions: Array<[string, string, string]> = [
    ["RV5 และความผันผวนรายปี", "ความผันผวนจริงใน 5 วันซื้อขายถัดไป แสดงเป็นทศนิยมหรือเปอร์เซ็นต์รายปี", "/forecasts"],
    ["รอผลประเมิน", "มี Forecast แล้ว แต่ช่วงเป้าหมาย 5 วันยังไม่ครบ ณ วันตัดข้อมูล จึงยังไม่แสดงค่าจริงหรือความคลาดเคลื่อน", "/forecasts"],
    ["B0–B3: โมเดล", "B0–B1 คือโมเดลพื้นฐาน ส่วน B2–B3 คือโมเดล SGD ที่ปรับตามข้อมูล ใช้ค่าที่บันทึกจาก Stage 06", "/models"],
    ["Train / Validation / Test", "Train ใช้ฝึกโมเดล Validation ใช้เลือกการตั้งค่า ส่วน Test ใช้ประเมินผล อย่านำ Test ไปปรับโมเดล", "/models"],
    ["ข้อมูลรั่วไหล", "ข้อมูลอนาคตอาจปะปนในชุดฝึกหรือการเลือกโมเดล ทำให้ผลทดสอบดูดีเกินจริง หน้านี้แสดงเฉพาะขอบเขตที่ตรวจสอบได้", "/research"],
    ["ADWIN", "วิธีตรวจว่าความคลาดเคลื่อนเปลี่ยนไปหรือไม่ หน้านี้แสดงเฉพาะผลที่บันทึกไว้", "/drift"],
    ["MAE / RMSE", "MAE คือค่าเฉลี่ยของความคลาดเคลื่อน ส่วน RMSE ให้น้ำหนักกับค่าที่สูงกว่า ทั้งคู่แสดงความผันผวนรายปี", "/models"],
    ["ความเสี่ยงพอร์ตรายปี", "คำนวณจาก √(wᵀΣw) ด้วยน้ำหนักและค่าความแปรปรวนร่วมของสินทรัพย์ ไม่ใช่ผลตอบแทนหรือการคาดการณ์ราคา", "/portfolio"],
    ["MACRO", "ค่าเฉลี่ยรวม ETF ที่บันทึกจาก Stage 06 หน้านี้ไม่คำนวณค่าใหม่", "/models"],
    ["ผลย้อนหลัง", "ข้อมูลจาก snapshot ที่บันทึกไว้ ไม่ใช่ข้อมูลสด และไม่ยืนยันว่าเข้าถึงข้อมูลตลาดได้จริง ณ วันจำลอง", "/provenance"],
  ];
  return `<div class="page-stack"><section class="guide-intro"><h2>เริ่มจากสิ่งที่อยากตรวจ</h2><p>ทุกหน้าใช้ผลที่บันทึกไว้ ไม่ฝึกโมเดล ไม่รัน replay หรือทดสอบสถิติซ้ำ</p></section><section class="guide-task-section"><div class="section-card-heading"><div><h2>4 งานที่พบบ่อย</h2></div></div><div class="guide-task-grid">${tasks.map((task) => `<article class="guide-task-card"><h3>${task.title}</h3><p>${task.description}</p><small>${task.steps}</small><a class="button button-secondary" href="${escapeHtml(routeHash(task.route, state))}">เปิด ${task.route === "/forecasts" ? "Replay" : task.route === "/portfolio" ? "Portfolio" : task.route === "/models" ? "Models" : "Research"} →</a></article>`).join("")}</div><div class="guide-related-links"><a class="button button-secondary" href="${escapeHtml(routeHash("/drift", state))}">ดู Drift / ADWIN →</a><a class="button button-secondary" href="${escapeHtml(routeHash("/provenance", state))}">ตรวจที่มาและวันตัดข้อมูล →</a></div></section><section class="guide-glossary-section"><div class="section-card-heading"><div><h2>คำศัพท์ที่ใช้ในหน้า dashboard</h2></div></div><div class="glossary-grid">${definitions.map(([term, definition, path], index) => `<details class="glossary-card" id="guide-term-${index + 1}" data-persist-open><summary><h3>${term}</h3></summary><p>${definition}</p><a class="guide-term-link" href="${escapeHtml(routeHash(path, state))}">ดูใน ${path.slice(1)} →</a></details>`).join("")}</div></section><div class="limitation-card"><span class="limitation-mark">!</span><p>ผล Test อธิบายเฉพาะข้อมูลที่บันทึกไว้ ไม่ยืนยันแหล่งข้อมูล ณ วันจำลอง ไม่รับรองผลในอนาคต และไม่ใช่คำแนะนำซื้อขาย</p></div></div>`;
}

function pageContent(state: ViewState): string {
  if (state.selectionError && ["/forecasts", "/portfolio", "/drift"].includes(state.routePath)) return selectionUnavailable(state);
  if (state.routePath === "/overview") return overviewPage(state);
  if (state.routePath === "/forecasts") return forecastExplorerPage(state);
  if (state.routePath === "/provenance") return provenancePage(state);
  if (state.routePath === "/guide") return guidePage(state);
  if (state.routePath === "/models") return modelsPage(state);
  if (state.routePath === "/portfolio") return portfolioPage(state);
  if (state.routePath === "/drift") return driftPage(state);
  return researchPage(state);
}

function shell(state: ViewState): string {
  const route = routes.find((item) => item.path === state.routePath) ?? routes[0];
  const sidebarLinks = routes.map((item) => navLink(item, item.path === state.routePath, "", state.selection)).join("");
  const mobilePrimary = routes.slice(0, 3).map((item) => navLink(item, item.path === state.routePath, "", state.selection)).join("");
  const secondaryRoutes = routes.slice(3);
  const mobileDrawer = state.mobileMenuOpen ? `<div class="mobile-nav-overlay" data-action="close-menu"><nav class="mobile-drawer" aria-label="เมนูทั้งหมด"><div class="drawer-heading"><strong>ไปยังหน้า</strong><button class="icon-button" type="button" data-action="close-menu" aria-label="ปิดเมนู">×</button></div>${sidebarLinks}</nav></div>` : "";
  const morePanel = state.moreOpen ? `<div class="mobile-more-panel" aria-label="หน้าเพิ่มเติม">${secondaryRoutes.map((item) => navLink(item, item.path === state.routePath, "", state.selection)).join("")}</div>` : "";
  return `<div class="app-frame${state.presentationMode ? " presentation-mode" : ""}" data-route-path="${escapeHtml(state.routePath)}">
    <aside class="sidebar" aria-label="เมนูหลัก"><div class="brand-lockup"><div class="brand-mark">A</div><div><strong>Adaptive Risk Lab</strong><span>DEDS · RESEARCH WORKBENCH</span></div></div><div class="sidebar-section-label">หน้าต่างๆ</div><nav class="sidebar-nav">${sidebarLinks}</nav><div class="sidebar-bottom"><div class="sidebar-status-mark">${icon("lock", 16)}<span>ชุดข้อมูลอ่านอย่างเดียว</span></div><div class="sidebar-caption">ใช้ผลที่บันทึกไว้สำหรับทบทวน<br />ไม่มีการเรียก ML pipeline</div><span class="version-label">D1–D9 · REVIEW LAB</span></div></aside>
    <div class="app-main"><header class="mobile-topbar"><a class="mobile-brand" href="${escapeHtml(routeHash("/overview", state))}"><span class="brand-mark small">A</span><strong>Adaptive Risk Lab</strong></a><button class="icon-button mobile-menu-button" type="button" aria-label="เปิดเมนู" aria-expanded="${state.mobileMenuOpen}" data-action="toggle-menu">${icon("menu")}</button></header>${mobileDrawer}<main class="workspace"><div class="page-heading-row"><div><h1>${escapeHtml(route.thai)}</h1><p>${escapeHtml(route.description)}</p></div><div class="page-tools"><label class="unit-control"><span>หน่วย</span><select aria-label="Display units" data-field="unit"><option value="decimal" ${state.unit === "decimal" ? "selected" : ""}>Decimal</option><option value="percent" ${state.unit === "percent" ? "selected" : ""}>Percent</option></select></label><button class="presentation-toggle${state.presentationMode ? " active" : ""}" type="button" data-action="toggle-presentation" aria-pressed="${state.presentationMode}">${state.presentationMode ? "ออกจากโหมดนำเสนอ" : "โหมดนำเสนอ"}</button></div></div>${state.snapshot.status !== "ready" || ["/overview", "/provenance"].includes(state.routePath) ? snapshotBanner(state.snapshot) : ""}${state.snapshot.status === "missing" ? errorState(state.snapshot.message, "ยังไม่มีไฟล์ snapshot ที่ตรวจสอบแล้ว") : state.snapshot.status === "error" ? errorState(state.snapshot.message) : ""}<div class="page-content">${state.selectionError && !["/forecasts", "/portfolio", "/drift"].includes(state.routePath) ? selectionUnavailable(state) : ""}${pageContent(state)}</div></main><nav class="mobile-bottom-nav" aria-label="Navigation">${mobilePrimary}<button class="nav-link mobile-more-link${state.moreOpen ? " active" : ""}" type="button" aria-expanded="${state.moreOpen}" data-action="toggle-more">${icon("menu", 19)}<span>เพิ่มเติม</span></button></nav>${morePanel}${guidedTourPanel(state)}</div>
  </div>`;
}

function focusSelector(element: HTMLElement): string | null {
  if (element.id) return `#${element.id.replace(/([^a-zA-Z0-9_-])/g, "\\$1")}`;
  const attributes = ["data-action", "data-field", "data-route", "data-scenario", "data-index", "data-tab", "data-preset"];
  const parts = attributes.flatMap((attribute) => {
    const value = element.getAttribute(attribute);
    return value === null ? [] : [`[${attribute}="${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"]`];
  });
  return parts.length > 0 ? `${element.tagName.toLowerCase()}${parts.join("")}` : null;
}

function restoreScrollPosition(left: number, top: number): void {
  const documentElement = document.documentElement;
  const previousBehavior = documentElement.style.scrollBehavior;
  documentElement.style.scrollBehavior = "auto";
  window.scrollTo(left, top);
  documentElement.style.scrollBehavior = previousBehavior;
}

function render(root: HTMLElement, state: ViewState, focusFallback: HTMLElement | null = null): void {
  const currentRoute = root.querySelector<HTMLElement>(".app-frame")?.dataset.routePath;
  const routeChanged = currentRoute !== undefined && currentRoute !== state.routePath;
  const active = document.activeElement instanceof HTMLElement && root.contains(document.activeElement)
    ? document.activeElement
    : focusFallback && root.contains(focusFallback)
      ? focusFallback
      : null;
  const activeSelector = active ? focusSelector(active) : null;
  let selectionStart: number | null = null;
  let selectionEnd: number | null = null;
  if (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement) {
    try {
      selectionStart = active.selectionStart;
      selectionEnd = active.selectionEnd;
    } catch {
      selectionStart = null;
      selectionEnd = null;
    }
  }
  const scrollLeft = routeChanged ? 0 : window.scrollX;
  const scrollTop = routeChanged ? 0 : window.scrollY;
  const expandedDetails = routeChanged
    ? []
    : Array.from(root.querySelectorAll<HTMLDetailsElement>("details[data-persist-open][open]"))
      .map((details) => details.id)
      .filter(Boolean);
  root.innerHTML = shell(state);
  const route = routes.find((item) => item.path === state.routePath);
  document.title = `${route?.label ?? "Overview"} · Adaptive Portfolio Risk Lab`;
  restoreScrollPosition(scrollLeft, scrollTop);
  for (const id of expandedDetails) {
    const details = root.querySelector<HTMLDetailsElement>(`details[id="${id}"][data-persist-open]`);
    if (details) details.open = true;
  }
  if (!routeChanged) {
    window.requestAnimationFrame(() => {
      if (activeSelector) {
        const replacement = root.querySelector<HTMLElement>(activeSelector);
        replacement?.focus({ preventScroll: true });
        if ((replacement instanceof HTMLInputElement || replacement instanceof HTMLTextAreaElement) && selectionStart !== null && selectionEnd !== null) {
          try {
            replacement.setSelectionRange(selectionStart, selectionEnd);
          } catch {
            // Number and range inputs do not expose a text selection range.
          }
        }
      }
      restoreScrollPosition(scrollLeft, scrollTop);
    });
  }
}

async function reload(root: HTMLElement, state: ViewState): Promise<void> {
  state.snapshot = { status: "loading" };
  state.attempt += 1;
  render(root, state);
  state.snapshot = await loadSnapshot();
  applyLocationSelection(state, window.location.hash);
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
    selection: null,
    selectionError: "",
    mobileMenuOpen: false,
    moreOpen: false,
    sessionSpeedMs: 900,
    sessionPlaying: false,
    sessionTimer: null,
    unit: "percent",
    metric: "mae",
    modelTicker: "MACRO",
    rangeTicker: "MACRO",
    rangeMetric: "mae",
    rangePreset: "all-test",
    rangeFrom: "",
    rangeTo: "",
    forecastTicker: "SPY",
    forecastSplit: "test",
    forecastModels: ["ONLINE_SGD"],
    forecastStatus: "all",
    forecastFrom: "",
    forecastTo: "",
    financialDecision: createDefaultFinancialScenarioState(),
    riskBudgetDraft: "",
    riskBudgetError: "",
    driftFrom: "",
    driftTo: "",
    researchTicker: "SPY",
    guidedActive: false,
    guidedStep: 0,
    tourRecord: null,
    presentationMode: false,
    attempt: 0,
  };

  const updateRoute = () => {
    stopSessionPlayback(state);
    applyLocationSelection(state, window.location.hash);
    state.mobileMenuOpen = false;
    state.moreOpen = false;
    if (state.guidedActive) {
      const expectedRoute = tourStops[state.guidedStep]?.route;
      if (expectedRoute && state.routePath !== expectedRoute) {
        state.guidedActive = false;
        state.tourRecord = null;
      }
    }
    render(root, state);
  };
  window.addEventListener("hashchange", updateRoute);
  window.addEventListener("popstate", updateRoute);
  const pausePlayback = () => {
    if (!state.sessionPlaying) return;
    stopSessionPlayback(state);
    render(root, state);
  };
  document.addEventListener("visibilitychange", () => { if (document.hidden) pausePlayback(); });
  window.addEventListener("blur", pausePlayback);
  const motionPreference = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  motionPreference?.addEventListener?.("change", (event) => { if (event.matches) pausePlayback(); });
  window.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (state.guidedActive) exitGuidedTour(root, state);
    else if (state.presentationMode) { state.presentationMode = false; render(root, state); }
  });
  root.addEventListener("keydown", (event) => {
    if (!(event instanceof KeyboardEvent) || !["Enter", " "].includes(event.key)) return;
    const target = event.target instanceof Element ? event.target : null;
    const observation = target?.closest<SVGElement>(".adwin-observation[data-action]");
    if (!observation) return;
    event.preventDefault();
    observation.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
  root.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const button = target?.closest<HTMLElement>("[data-action], [data-route]");
    if (!button) return;
    const route = button.dataset.route;
    if (route) { navigateRoute(state, route); return; }
    switch (button.dataset.action) {
      case "start-guided-tour": {
        state.guidedActive = true;
        state.tourRecord = state.snapshot.status === "ready" ? findTourRecord(state.snapshot) : null;
        setGuidedStep(root, state, 0);
        break;
      }
      case "guided-next":
        if (state.guidedStep >= tourStops.length - 1) exitGuidedTour(root, state);
        else setGuidedStep(root, state, state.guidedStep + 1);
        break;
      case "guided-previous": setGuidedStep(root, state, state.guidedStep - 1); break;
      case "exit-guided-tour": exitGuidedTour(root, state); break;
      case "toggle-presentation": state.presentationMode = !state.presentationMode; render(root, state); break;
      case "select-drift-observation": {
        const predictionId = button.dataset.predictionId;
        const observation = state.snapshot.status === "ready" ? state.snapshot.driftTimeline.find((row) => row.predictionId === predictionId) : undefined;
        if (observation && state.snapshot.status === "ready") {
          const selection: ExperimentSelection = {
            evaluationId: state.snapshot.manifest.evaluationId,
            replayId: state.snapshot.manifest.replayId,
            split: "test",
            predictionDate: observation.predictionDate,
            modelName: "ONLINE_SGD",
            ticker: observation.ticker,
            asOfDate: observation.predictionDate,
            view: "as-of",
          };
          publishSelection(root, state, selection);
          window.setTimeout(() => root.querySelector<HTMLElement>(".drift-inspector")?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" }), 0);
        }
        break;
      }
      case "reset-selection": {
        const fallback = state.snapshot.status === "ready" ? routeFallbackSelection(state.snapshot, state.routePath) : null;
        if (fallback) publishSelection(root, state, fallback, "replace");
        else window.location.hash = "#/overview";
        break;
      }
      case "toggle-menu": state.mobileMenuOpen = !state.mobileMenuOpen; render(root, state); break;
      case "close-menu": if (target === button || button.classList.contains("mobile-nav-overlay")) { state.mobileMenuOpen = false; render(root, state); } break;
      case "toggle-more": state.moreOpen = !state.moreOpen; render(root, state); break;
      case "previous":
      case "next":
      case "reset":
      case "first":
      case "last": {
        if (state.snapshot.status !== "ready" || !state.selection) break;
        const sessions = selectionSessions(state.snapshot, state.selection);
        const currentIndex = sessions.findIndex((session) => session.predictionDate === state.selection?.predictionDate);
        const nextIndex = button.dataset.action === "previous" ? currentIndex - 1
          : button.dataset.action === "next" ? currentIndex + 1
            : button.dataset.action === "last" ? sessions.length - 1 : 0;
        setSessionIndex(root, state, nextIndex);
        break;
      }
      case "toggle-session-view": {
        if (state.selection) publishSelection(root, state, { ...state.selection, view: state.selection.view === "as-of" ? "retrospective" : "as-of" });
        break;
      }
      case "toggle-session-play": toggleSessionPlayback(root, state); break;
      case "portfolio-date-step": {
        const selection = state.selection;
        if (!selection) break;
        const dates = portfolioDateSequence(state);
        const currentIndex = dates.indexOf(selection.predictionDate);
        const step = button.dataset.direction === "previous" ? -1 : 1;
        setPortfolioDateIndex(root, state, currentIndex + step);
        break;
      }
      case "open-portfolio": {
        if (state.snapshot.status === "ready" && state.selection && selectedPortfolioRow(state.snapshot, state.selection.predictionDate, state.selection.modelName)) {
          navigateRoute(state, "/portfolio");
        }
        break;
      }
      case "portfolio-tab": {
        const tab = button.dataset.tab;
        if (tab === "risk" || tab === "drivers" || tab === "scenarios") {
          state.financialDecision.activeTab = tab;
          publishFinancialDecision(root, state);
        }
        break;
      }
      case "portfolio-active-scenario": {
        const scenario = button.dataset.scenario;
        if (scenario === "A" || scenario === "B") {
          state.financialDecision.activeScenario = scenario;
          publishFinancialDecision(root, state);
        }
        break;
      }
      case "portfolio-weight-preset": {
        const scenario = button.dataset.scenario;
        const preset = button.dataset.preset;
        if ((scenario === "A" || scenario === "B") && ["default", "example", "equal"].includes(preset ?? "")) {
          const key = scenario === "A" ? "scenarioA" : "scenarioB";
          state.financialDecision[key] = preset === "example" ? [0.6, 0.2, 0.2] : preset === "equal" ? [1 / 3, 1 / 3, 1 / 3] : [0.5, 0.3, 0.2];
          publishFinancialDecision(root, state);
        }
        break;
      }
      case "portfolio-clear-budget":
        state.financialDecision.budgetAnnualizedDecimal = null;
        state.riskBudgetDraft = "";
        state.riskBudgetError = "";
        publishFinancialDecision(root, state);
        break;
      case "open-session": {
        const predictionId = button.dataset.predictionId;
        if (state.snapshot.status === "ready" && predictionId) {
          const row = state.snapshot.sessions.find((session) => session.predictionId === predictionId);
          if (row) {
            stopSessionPlayback(state);
            publishSelection(root, state, {
              evaluationId: state.snapshot.manifest.evaluationId,
              replayId: state.snapshot.manifest.replayId,
              split: row.split,
              predictionDate: row.predictionDate,
              modelName: row.modelName,
              ticker: row.ticker,
              asOfDate: row.predictionDate,
              view: "as-of",
            });
          }
        }
        break;
      }
      case "retry": void reload(root, state); break;
      case "copy-id": {
        if (state.snapshot.status === "ready") void navigator.clipboard?.writeText(`Evaluation ID: ${state.snapshot.manifest.evaluationId}\nReplay ID: ${state.snapshot.manifest.replayId}`);
        break;
      }
      case "copy-source-value": {
        const value = button.dataset.copyValue;
        const label = button.dataset.copyLabel ?? "ค่า";
        const status = button.querySelector<HTMLElement>("[data-copy-status]");
        if (!value || !navigator.clipboard) {
          if (status) status.textContent = "คัดลอกไม่ได้";
          break;
        }
        void navigator.clipboard.writeText(value).then(() => {
          if (status) status.textContent = "คัดลอกแล้ว";
          button.setAttribute("aria-label", `คัดลอก ${label} แล้ว`);
          window.setTimeout(() => {
            if (status) status.textContent = "คัดลอก";
            button.setAttribute("aria-label", `คัดลอก ${label}`);
          }, 1600);
        }).catch(() => { if (status) status.textContent = "คัดลอกไม่ได้"; });
        break;
      }
      case "export-forecasts-csv": exportForecastCsv(state); break;
      case "export-forecasts-metadata": void exportForecastMetadata(state); break;
    }
  });
  root.addEventListener("change", (event) => {
    const target = event.target;
    if (target instanceof HTMLSelectElement) {
      if (target.dataset.field === "scenario-remainder") {
        const scenario = target.dataset.scenario;
        if ((scenario === "A" || scenario === "B") && tickerNames.includes(target.value as Ticker)) {
          state.financialDecision = setScenarioRemainderAsset(state.financialDecision, scenario, target.value as ScenarioRemainderAsset);
          publishFinancialDecision(root, state);
        }
        return;
      }
      if (target.dataset.field === "ticker" && tickerNames.includes(target.value as Ticker) && state.selection) {
        stopSessionPlayback(state);
        publishSelection(root, state, { ...state.selection, ticker: target.value as Ticker });
        return;
      }
      if (target.dataset.field === "model" && modelNames.includes(target.value as ModelName) && state.selection) {
        stopSessionPlayback(state);
        publishSelection(root, state, { ...state.selection, modelName: target.value as ModelName });
        return;
      }
      if (target.dataset.field === "session-date") {
        const sessions = state.snapshot.status === "ready" && state.selection ? selectionSessions(state.snapshot, state.selection) : [];
        const selectedIndex = sessions.findIndex((session) => session.predictionDate === target.value);
        if (selectedIndex >= 0) { setSessionIndex(root, state, selectedIndex); return; }
      }
      if (target.dataset.field === "session-as-of" && state.selection) {
        publishSelection(root, state, { ...state.selection, asOfDate: target.value });
        return;
      }
      if (target.dataset.field === "session-speed" && [450, 900, 1600].includes(Number(target.value))) {
        const resumePlayback = state.sessionPlaying;
        if (resumePlayback) stopSessionPlayback(state);
        state.sessionSpeedMs = Number(target.value);
        if (resumePlayback) {
          toggleSessionPlayback(root, state);
          return;
        }
      }
      if (target.dataset.field === "unit" && ["decimal", "percent"].includes(target.value)) state.unit = target.value as DisplayUnit;
      if (target.dataset.field === "metric" && ["mae", "rmse"].includes(target.value)) state.metric = target.value as MetricName;
      if (target.dataset.field === "range-metric" && ["mae", "rmse"].includes(target.value)) state.rangeMetric = target.value as MetricName;
      if (target.dataset.field === "range-ticker" && metricTickerNames.includes(target.value as Ticker | "MACRO")) state.rangeTicker = target.value as Ticker | "MACRO";
      if (target.dataset.field === "range-preset" && ["all-test", "last20", "custom"].includes(target.value)) {
        state.rangePreset = target.value as ViewState["rangePreset"];
        if (state.rangePreset !== "all-test" && state.snapshot.status === "ready") {
          const dates = commonRangeDates(state.snapshot);
          if (state.rangePreset === "last20") {
            if (dates.length === 0) state.rangePreset = "all-test";
            state.rangeFrom = dates[Math.max(0, dates.length - 20)] ?? "";
            state.rangeTo = dates[dates.length - 1] ?? "";
          } else {
            if (!state.rangeFrom) state.rangeFrom = dates[0] ?? "";
            if (!state.rangeTo) state.rangeTo = dates[dates.length - 1] ?? "";
          }
        } else {
          state.rangeFrom = "";
          state.rangeTo = "";
        }
        publishRangeSelection(root, state);
        return;
      }
      if (target.dataset.field === "model-ticker" && metricTickerNames.includes(target.value as Ticker | "MACRO")) state.modelTicker = target.value as Ticker | "MACRO";
      if (target.dataset.field === "coverage-ticker" && tickerNames.includes(target.value as Ticker)) state.forecastTicker = target.value as Ticker;
      if (target.dataset.field === "forecast-ticker" && tickerNames.includes(target.value as Ticker)) state.forecastTicker = target.value as Ticker;
      if (target.dataset.field === "forecast-split" && ["test", "validation"].includes(target.value)) state.forecastSplit = target.value as "test" | "validation";
      if (target.dataset.field === "forecast-status" && ["all", "mature", "pending", "invalid"].includes(target.value)) state.forecastStatus = target.value as ForecastFilter["status"];
      if (target.dataset.field === "forecast-models") state.forecastModels = Array.from(target.selectedOptions).map((option) => option.value).filter((model): model is ModelName => modelNames.includes(model as ModelName));
      if (target.dataset.field === "portfolio-date" && state.selection) {
        stopSessionPlayback(state);
        publishSelection(root, state, { ...state.selection, predictionDate: target.value, asOfDate: target.value });
        return;
      }
      if (target.dataset.field === "portfolio-model" && modelNames.includes(target.value as ModelName) && state.selection) {
        stopSessionPlayback(state);
        publishSelection(root, state, { ...state.selection, modelName: target.value as ModelName });
        return;
      }
      if (target.dataset.field === "drift-observation" && state.snapshot.status === "ready") {
        const selected = state.snapshot.driftTimeline.find((row) => row.predictionId === target.value && (!state.driftFrom || row.predictionDate >= state.driftFrom) && (!state.driftTo || row.predictionDate <= state.driftTo));
        if (selected && state.selection) {
          publishSelection(root, state, {
            ...state.selection,
            split: "test",
            predictionDate: selected.predictionDate,
            modelName: "ONLINE_SGD",
            ticker: selected.ticker,
            asOfDate: selected.predictionDate,
            view: "as-of",
          });
          window.setTimeout(() => root.querySelector<HTMLElement>(".drift-inspector")?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" }), 0);
          return;
        }
      }
      if (target.dataset.field === "research-ticker" && tickerNames.includes(target.value as Ticker)) state.researchTicker = target.value as Ticker;
    }
    if (target instanceof HTMLInputElement) {
      if (target.dataset.field === "session-index") {
        setSessionIndex(root, state, Number(target.value));
        return;
      }
      if (target.dataset.field === "forecast-from") state.forecastFrom = target.value;
      if (target.dataset.field === "forecast-to") state.forecastTo = target.value;
      if (target.dataset.field === "range-from" || target.dataset.field === "range-to") {
        if (target.dataset.field === "range-from") state.rangeFrom = target.value;
        else state.rangeTo = target.value;
        if (state.rangeFrom && state.rangeTo && state.rangeFrom > state.rangeTo) render(root, state);
        else publishRangeSelection(root, state);
        return;
      }
      if (target.dataset.field === "drift-from") state.driftFrom = target.value;
      if (target.dataset.field === "drift-to") state.driftTo = target.value;
      if (target.dataset.field === "scenario-weight" || target.dataset.field === "scenario-weight-slider") {
        const result = applyScenarioWeightInput(root, state, target);
        if (result) {
          if (result.valid) publishFinancialDecision(root, state, target);
          else render(root, state, target);
          return;
        }
      }
      if (target.dataset.field === "risk-budget") {
        state.riskBudgetDraft = target.value;
        const raw = target.value.trim();
        if (raw === "") {
          state.financialDecision.budgetAnnualizedDecimal = null;
          state.riskBudgetError = "";
          publishFinancialDecision(root, state, target);
          return;
        }
        const percentValue = Number(raw);
        if (!Number.isFinite(percentValue) || percentValue < 0) {
          state.riskBudgetError = "กรอกเปอร์เซ็นต์รายปีเป็นตัวเลขที่ไม่ติดลบ หรือเว้นว่าง";
          render(root, state, target);
          return;
        }
        state.financialDecision.budgetAnnualizedDecimal = percentValue / 100;
        state.riskBudgetError = "";
        publishFinancialDecision(root, state, target);
        return;
      }
    }
    render(root, state);
  });
  root.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;
    if (target.dataset.field === "session-index") {
      const available = state.snapshot.status === "ready" && state.selection ? selectionSessions(state.snapshot, state.selection) : [];
      if (available.length === 0) return;
      stopSessionPlayback(state);
      const index = Math.max(0, Math.min(Number(target.value), available.length - 1));
      const selected = available[index];
      if (!selected) return;
      const currentDate = root.querySelector<HTMLElement>("[data-session-current-date]");
      const position = root.querySelector<HTMLElement>("[data-session-position]");
      const dateSelect = root.querySelector<HTMLSelectElement>('[data-field="session-date"]');
      const asOfSelect = root.querySelector<HTMLSelectElement>('[data-field="session-as-of"]');
      if (currentDate) currentDate.textContent = selected.predictionDate;
      if (position) position.textContent = `วันที่ ${index + 1} จาก ${available.length}`;
      if (dateSelect) dateSelect.value = selected.predictionDate;
      if (asOfSelect) asOfSelect.value = selected.predictionDate;
      target.setAttribute("aria-valuetext", `${selected.predictionDate} · วันที่ ${index + 1} จาก ${available.length}`);
      return;
    }
    if (target.dataset.field === "risk-budget") {
      state.riskBudgetDraft = target.value;
      return;
    }
    if (target.dataset.field !== "scenario-weight" && target.dataset.field !== "scenario-weight-slider") return;
    applyScenarioWeightInput(root, state, target);
  });
  if (!window.location.hash) window.location.hash = "/overview";
  render(root, state);
  void loadSnapshot().then((snapshot) => {
    state.snapshot = snapshot;
    applyLocationSelection(state, window.location.hash);
    if (state.guidedActive) state.tourRecord = snapshot.status === "ready" ? findTourRecord(snapshot) : null;
    render(root, state);
  });
}
