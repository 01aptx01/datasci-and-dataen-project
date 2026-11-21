import { modelId, modelLabel, type CoverageRow, type ModelMetricRow, type ModelName, type PortfolioRiskRow, type Ticker } from "../data/schemas.js";
import { computePortfolioRiskContributions, computePortfolioVolatility, type PortfolioWeights } from "../data/portfolio.js";
import { buildPortfolioRiskTimeline, compareScenarioRisks, findPriorComparableRisk, riskBudgetStatus, splitRiskTimelineSegments, summarizeRiskBudget, validateScenarioWeights, type FinancialDecisionTab, type FinancialScenarioState, type PortfolioRiskTimelinePoint } from "../data/decisionLab.js";
import type { ExperimentSelection } from "../data/selection.js";

type DisplayUnit = "decimal" | "percent";

export interface FinancialDecisionLabInput {
  rows: PortfolioRiskRow[];
  selectedRow: PortfolioRiskRow;
  selection: ExperimentSelection;
  decision: FinancialScenarioState;
  availableDates: string[];
  availableModels: ModelName[];
  modelMetrics: ModelMetricRow[];
  coverage: CoverageRow[];
  unit: DisplayUnit;
  budgetDraft: string;
  budgetError: string;
  evaluationId: string;
  strictCutoff: string;
  pointInTimeSourceAvailabilityVerified: boolean;
}

const assets: Ticker[] = ["SPY", "IEF", "GLD"];
const tabLabels: Record<FinancialDecisionTab, string> = { risk: "Risk Center", drivers: "Risk Drivers", scenarios: "Scenario Lab" };

function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] ?? character);
}

function formatRisk(value: number | null | undefined, unit: DisplayUnit, digits = 4): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return unit === "percent" ? `${(value * 100).toFixed(2)}%` : value.toFixed(digits);
}

function formatRiskDelta(value: number | null | undefined, unit: DisplayUnit): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return unit === "percent" ? `${(value * 100).toFixed(2)} pp` : value.toFixed(4);
}

function percent(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined || !Number.isFinite(value) ? "—" : `${(value * 100).toFixed(digits)}%`;
}

function formatWeight(value: number): string {
  return Number.isFinite(value) ? `${Math.round(value * 100)}%` : "—";
}

function safeRisk(row: PortfolioRiskRow, weights: PortfolioWeights): number | null {
  if (row.status !== "OK" || row.covariance === null || !row.correlationReady || row.missingInputs.length > 0) return null;
  try { return computePortfolioVolatility(row.covariance, weights); }
  catch { return null; }
}

function activeWeights(state: FinancialScenarioState): PortfolioWeights {
  return state.activeScenario === "A" ? state.scenarioA : state.scenarioB;
}

function actionTab(tab: FinancialDecisionTab, selected: FinancialDecisionTab): string {
  return `<button class="decision-tab" type="button" role="tab" id="portfolio-tab-${tab}" aria-selected="${tab === selected}" aria-controls="portfolio-panel" data-action="portfolio-tab" data-tab="${tab}">${tabLabels[tab]}</button>`;
}

function contributionBar(value: number | null, maxAbs: number, label: string): string {
  if (value === null || !Number.isFinite(value)) return "";
  const width = Math.max(1, Math.min(48, Math.abs(value) / (maxAbs || 1) * 48));
  const left = value < 0 ? 50 - width : 50;
  return `<span class="decision-contribution-track" aria-hidden="true"><span class="decision-contribution-zero"></span><span class="decision-contribution-fill ${value < 0 ? "negative" : "positive"}" style="left:${left}%;width:${width}%"></span></span><span class="visually-hidden">${escapeHtml(label)} ${value < 0 ? "negative" : "positive"}</span>`;
}

function selectionControls(input: FinancialDecisionLabInput): string {
  return `<section class="analysis-card decision-selection-card"><div class="section-card-heading"><div><span class="section-overline">D8 SHARED SELECTION · D9 USES ALL THREE ASSETS</span><h2 class="analysis-title">Financial Decision Lab</h2><p>เลือกวันและโมเดลจาก Test ที่บันทึกไว้ ความเสี่ยงพอร์ตใช้ SPY, IEF และ GLD ร่วมกัน; ticker ใน Replay เป็นเพียงบริบท</p></div><span class="readonly-pill">Frozen Test</span></div><div class="inline-controls"><label class="field-label">Recorded Test date<select data-field="portfolio-date">${input.availableDates.map((date) => `<option value="${escapeHtml(date)}" ${date === input.selection.predictionDate ? "selected" : ""}>${escapeHtml(date)}</option>`).join("")}</select></label><label class="field-label">Model<select data-field="portfolio-model">${input.availableModels.map((model) => `<option value="${model}" ${model === input.selection.modelName ? "selected" : ""}>${modelId(model)} · ${escapeHtml(modelLabel(model))}</option>`).join("")}</select></label></div><div class="decision-context-line"><span>Shared ticker context</span><strong>${input.selection.ticker}</strong><span>·</span><span>Portfolio inputs</span><strong>SPY + IEF + GLD</strong><span>·</span><span>View</span><strong>${input.selection.view === "as-of" ? `As-of ${escapeHtml(input.selection.asOfDate ?? input.selection.predictionDate)}` : "Retrospective"}</strong><button class="button button-secondary" type="button" data-action="toggle-session-view">${input.selection.view === "as-of" ? "ดูย้อนหลังเต็มช่วง" : "กลับไปดูตาม as-of"}</button></div></section>`;
}

function timelineChart(points: PortfolioRiskTimelinePoint[], selectedDate: string, weights: PortfolioWeights, evaluationId: string, budget: number | null, unit: DisplayUnit): string {
  const valid = points.filter((point) => point.risk !== null);
  if (valid.length === 0) return `<div class="decision-chart-empty" role="status">ช่วงที่เลือกไม่มีแถว covariance ที่ใช้คำนวณได้</div>`;
  const low = Math.min(0, ...valid.map((point) => point.risk!));
  const high = Math.max(...valid.map((point) => point.risk!), budget ?? 0);
  const spread = high - low || Math.max(high, 0.01);
  const left = 50, right = 750, top = 28, bottom = 176;
  const x = (index: number) => left + index * (right - left) / Math.max(points.length - 1, 1);
  const y = (risk: number) => bottom - (risk - low) / spread * (bottom - top);
  const segments = splitRiskTimelineSegments(points).map((segment) => {
    const coords = segment.map((point) => `${x(points.indexOf(point)).toFixed(1)},${y(point.risk!).toFixed(1)}`).join(" ");
    return `<polyline class="decision-risk-line" points="${coords}" />`;
  }).join("");
  const dots = valid.map((point) => `<circle class="decision-risk-dot${point.date === selectedDate ? " selected" : ""}" cx="${x(points.indexOf(point)).toFixed(1)}" cy="${y(point.risk!).toFixed(1)}" r="${point.date === selectedDate ? 4 : 2.3}"><title>${escapeHtml(point.date)} · ${modelId(point.row.modelName)} · ${formatRisk(point.risk, unit)} annualized · approx 5-session equivalent (sqrt-of-time) ${formatRisk(point.risk! * Math.sqrt(5 / 252), unit)} · weights SPY/IEF/GLD ${weights.map(formatWeight).join("/")} · ${escapeHtml(point.row.status)} · Eval ${escapeHtml(evaluationId)} · replay ${escapeHtml(point.row.replayRunId)} · snapshot ${escapeHtml(point.row.inputSnapshotId)}</title></circle>`).join("");
  const budgetLine = budget !== null && budget >= low && budget <= high
    ? `<line class="decision-budget-line" x1="${left}" y1="${y(budget)}" x2="${right}" y2="${y(budget)}"/><text class="decision-budget-label" x="${right}" y="${Math.max(top + 10, y(budget) - 5)}" text-anchor="end">User budget ${percent(budget)}</text>`
    : "";
  return `<div class="chart-scroll"><svg class="decision-risk-chart" role="img" aria-label="Portfolio annualized risk over recorded Test dates for ${escapeHtml(modelId(points[0].row.modelName))}" viewBox="0 0 800 220" preserveAspectRatio="xMinYMin meet"><line x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}" class="chart-axis"/><line x1="${left}" y1="${top}" x2="${left}" y2="${bottom}" class="chart-axis"/><text x="${left}" y="${top - 5}" class="chart-date-label">${formatRisk(high, unit, 2)}</text><text x="${left}" y="${bottom + 18}" class="chart-date-label">${escapeHtml(points[0].date)}</text><text x="${right}" y="${bottom + 18}" text-anchor="end" class="chart-date-label">${escapeHtml(points[points.length - 1].date)}</text>${budgetLine}${segments}${dots}</svg></div><div class="chart-legend"><span><i class="decision-legend-risk"></i>Recorded covariance · recalculated for selected weights</span><span><i class="decision-legend-budget"></i>User budget</span><span>${valid.length.toLocaleString()} usable / ${points.length.toLocaleString()} source dates</span></div>`;
}

function timelineTable(points: PortfolioRiskTimelinePoint[], unit: DisplayUnit): string {
  if (points.length === 0) return "";
  const rows = points.map((point) => `<tr><th scope="row">${escapeHtml(point.date)}</th><td>${formatRisk(point.risk, unit)}</td><td>${escapeHtml(point.status)}</td><td>${point.missingInputs.length ? escapeHtml(point.missingInputs.join("; ")) : "—"}</td></tr>`).join("");
  return `<details class="chart-data-details"><summary>ดูข้อมูล Risk Center เป็นตาราง · ${points.length.toLocaleString()} วันที่</summary><div class="table-scroll"><table class="data-table"><caption class="visually-hidden">Recorded portfolio risk by Test date</caption><thead><tr><th scope="col">Date</th><th scope="col">Annualized portfolio risk</th><th scope="col">Source status</th><th scope="col">Unavailable inputs</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
}

function scenarioTimelineChart(pointsA: PortfolioRiskTimelinePoint[], pointsB: PortfolioRiskTimelinePoint[], selectedDate: string, weightsA: PortfolioWeights, weightsB: PortfolioWeights, evaluationId: string, budget: number | null, unit: DisplayUnit): string {
  const validA = pointsA.filter((point) => point.risk !== null);
  const validB = pointsB.filter((point) => point.risk !== null);
  const allValid = [...validA, ...validB];
  if (allValid.length === 0) return `<div class="decision-chart-empty" role="status">ช่วงที่เลือกไม่มีแถว covariance ที่ใช้คำนวณได้</div>`;
  const low = Math.min(0, ...allValid.map((point) => point.risk!));
  const high = Math.max(...allValid.map((point) => point.risk!), budget ?? 0);
  const spread = high - low || Math.max(high, 0.01);
  const left = 50, right = 750, top = 28, bottom = 176;
  const x = (index: number) => left + index * (right - left) / Math.max(pointsA.length - 1, 1);
  const y = (risk: number) => bottom - (risk - low) / spread * (bottom - top);
  const line = (points: PortfolioRiskTimelinePoint[], scenario: "a" | "b") => splitRiskTimelineSegments(points).map((segment) => {
    const coords = segment.map((point) => `${x(points.indexOf(point)).toFixed(1)},${y(point.risk!).toFixed(1)}`).join(" ");
    return `<polyline class="decision-risk-line scenario-${scenario}" points="${coords}" />`;
  }).join("");
  const dots = (points: PortfolioRiskTimelinePoint[], weights: PortfolioWeights, scenario: "a" | "b") => points
    .filter((point) => point.risk !== null)
    .map((point) => `<circle class="decision-risk-dot scenario-${scenario}${point.date === selectedDate ? " selected" : ""}" cx="${x(points.indexOf(point)).toFixed(1)}" cy="${y(point.risk!).toFixed(1)}" r="${point.date === selectedDate ? 4 : 2.3}"><title>Scenario ${scenario.toUpperCase()} · ${escapeHtml(point.date)} · ${modelId(point.row.modelName)} · ${formatRisk(point.risk, unit)} annualized · approx 5-session equivalent (sqrt-of-time) ${formatRisk(point.risk! * Math.sqrt(5 / 252), unit)} · weights SPY/IEF/GLD ${weights.map(formatWeight).join("/")} · ${escapeHtml(point.row.status)} · Eval ${escapeHtml(evaluationId)} · replay ${escapeHtml(point.row.replayRunId)} · snapshot ${escapeHtml(point.row.inputSnapshotId)}</title></circle>`).join("");
  const budgetLine = budget !== null && budget >= low && budget <= high
    ? `<line class="decision-budget-line" x1="${left}" y1="${y(budget)}" x2="${right}" y2="${y(budget)}"/><text class="decision-budget-label" x="${right}" y="${Math.max(top + 10, y(budget) - 5)}" text-anchor="end">User budget ${percent(budget)}</text>`
    : "";
  const summary = (name: string, points: PortfolioRiskTimelinePoint[]) => {
    const budgetSummary = summarizeRiskBudget(points, budget);
    return `${name} · ${budget === null ? `${budgetSummary.evaluableCount.toLocaleString()} usable dates` : `${budgetSummary.evaluableCount.toLocaleString()} usable · ${budgetSummary.aboveCount.toLocaleString()} above budget`}`;
  };
  return `<div class="chart-scroll"><svg class="decision-risk-chart" role="img" aria-label="Scenario A and B annualized portfolio risk over the same recorded Test dates for ${escapeHtml(modelId(pointsA[0]!.row.modelName))}" viewBox="0 0 800 220" preserveAspectRatio="xMinYMin meet"><line x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}" class="chart-axis"/><line x1="${left}" y1="${top}" x2="${left}" y2="${bottom}" class="chart-axis"/><text x="${left}" y="${top - 5}" class="chart-date-label">${formatRisk(high, unit, 2)}</text><text x="${left}" y="${bottom + 18}" class="chart-date-label">${escapeHtml(pointsA[0]!.date)}</text><text x="${right}" y="${bottom + 18}" text-anchor="end" class="chart-date-label">${escapeHtml(pointsA[pointsA.length - 1]!.date)}</text>${budgetLine}${line(pointsA, "a")}${line(pointsB, "b")}${dots(pointsA, weightsA, "a")}${dots(pointsB, weightsB, "b")}</svg></div><div class="chart-legend"><span><i class="decision-legend-risk scenario-a"></i>${summary("Scenario A", pointsA)}</span><span><i class="decision-legend-risk scenario-b"></i>${summary("Scenario B", pointsB)}</span>${budget !== null ? `<span><i class="decision-legend-budget"></i>User budget</span>` : ""}<span>${pointsA.length.toLocaleString()} source dates · fixed weights on each date's stored covariance</span></div>`;
}

function scenarioTimelineTable(pointsA: PortfolioRiskTimelinePoint[], pointsB: PortfolioRiskTimelinePoint[], unit: DisplayUnit): string {
  if (pointsA.length === 0) return "";
  const rows = pointsA.map((point, index) => {
    const pointB = pointsB[index];
    return `<tr><th scope="row">${escapeHtml(point.date)}</th><td>${formatRisk(point.risk, unit)}</td><td>${formatRisk(pointB?.risk, unit)}</td><td>${escapeHtml(point.status)}</td><td>${point.missingInputs.length ? escapeHtml(point.missingInputs.join("; ")) : "—"}</td></tr>`;
  }).join("");
  return `<details class="chart-data-details"><summary>ดูเส้น Scenario A/B เป็นตาราง · ${pointsA.length.toLocaleString()} วันที่</summary><div class="table-scroll"><table class="data-table"><caption class="visually-hidden">Recorded annualized portfolio risk for fixed Scenario A and B weights</caption><thead><tr><th scope="col">Date</th><th scope="col">Scenario A risk</th><th scope="col">Scenario B risk</th><th scope="col">Source status</th><th scope="col">Unavailable inputs</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
}

function statusLabel(status: ReturnType<typeof riskBudgetStatus>): string {
  return ({ below: "ต่ำกว่าขีดที่ตั้ง", at: "เท่ากับขีดที่ตั้ง", above: "สูงกว่าขีดที่ตั้ง", unavailable: "ข้อมูลใช้ไม่ได้", unset: "ยังไม่ได้ตั้งขีด" })[status];
}

function riskCenter(input: FinancialDecisionLabInput, activeRisk: number | null, timeline: PortfolioRiskTimelinePoint[], defaultRisk: number | null): string {
  const currentPoint = timeline.find((point) => point.date === input.selection.predictionDate);
  const prior = findPriorComparableRisk(timeline, input.selection.predictionDate);
  const priorChange = prior && currentPoint ? compareScenarioRisks(prior.point.risk, currentPoint.risk) : null;
  const defaultChange = compareScenarioRisks(defaultRisk, activeRisk);
  const budget = input.decision.budgetAnnualizedDecimal;
  const budgetStatus = riskBudgetStatus(activeRisk, budget);
  const budgetSummary = summarizeRiskBudget(timeline, budget);
  let highestContribution = "—";
  if (activeRisk !== null && input.selectedRow.covariance) {
    const result = computePortfolioRiskContributions(input.selectedRow.covariance, activeWeights(input.decision));
    if (result.absoluteContributions) {
      const highestIndex = result.absoluteContributions.reduce((best, value, index, values) => value > values[best] ? index : best, 0);
      const value = result.absoluteContributions[highestIndex];
      if (value > 0) highestContribution = `${assets[highestIndex]} · ${formatRisk(value, input.unit)}`;
    }
  }
  const priorDelta = priorChange?.differenceAnnualizedDecimal;
  const previousText = prior && priorDelta !== null && priorDelta !== undefined
    ? `${prior.point.date} · ${prior.sessionsBack} แถวก่อนหน้า · ${priorDelta > 0 ? "+" : ""}${formatRiskDelta(priorDelta, input.unit)}`
    : prior ? `${prior.point.date} · ค่าปัจจุบันใช้คำนวณไม่ได้` : "ไม่มีแถวก่อนหน้าที่คำนวณได้ในช่วงนี้";
  const defaultText = defaultChange.differenceAnnualizedDecimal === null ? "—" : `${defaultChange.differenceAnnualizedDecimal > 0 ? "+" : ""}${formatRiskDelta(defaultChange.differenceAnnualizedDecimal, input.unit)}`;
  const budgetValue = budget === null ? "ยังไม่ได้ตั้ง" : `${percent(budget)} · ${statusLabel(budgetStatus)}`;
  const budgetSummaryText = budget === null
    ? "ตั้ง budget เพื่อดูจำนวนวันที่สูงกว่าขีด"
    : `${budgetSummary.aboveCount}/${budgetSummary.evaluableCount} usable dates สูงกว่าขีด · เป็นจำนวนครั้ง ไม่ใช่ความน่าจะเป็น`;
  const futureLabel = input.selection.view === "as-of" ? `As-of view · ตัดวันที่หลัง ${escapeHtml(input.selection.asOfDate ?? input.selection.predictionDate)} ออก` : "Retrospective · แสดงประวัติ Test ที่บันทึกไว้ทั้งหมด";
  const weightValidation = validateScenarioWeights(activeWeights(input.decision));
  return `<section class="analysis-card decision-main-card" role="tabpanel" id="portfolio-panel" aria-labelledby="portfolio-tab-risk"><div class="section-card-heading"><div><span class="section-overline">RISK CENTER · HISTORICAL SOURCE CALCULATION</span><h2 class="analysis-title">ความเสี่ยงของ Scenario ${input.decision.activeScenario}</h2><p>ใช้ covariance ตามวันที่และโมเดลที่เลือก คำนวณใหม่ด้วยน้ำหนัก Scenario ${input.decision.activeScenario}; ไม่มีการ fit model</p></div><span class="readonly-pill">${input.decision.activeScenario === "A" ? "Scenario A" : "Scenario B"}</span></div><div class="decision-active-picker" role="group" aria-label="เลือก scenario สำหรับ Risk Center"><button class="decision-scenario-choice${input.decision.activeScenario === "A" ? " active" : ""}" type="button" data-action="portfolio-active-scenario" data-scenario="A" aria-pressed="${input.decision.activeScenario === "A"}">Scenario A · ${input.decision.scenarioA.map(formatWeight).join(" / ")}</button><button class="decision-scenario-choice${input.decision.activeScenario === "B" ? " active" : ""}" type="button" data-action="portfolio-active-scenario" data-scenario="B" aria-pressed="${input.decision.activeScenario === "B"}">Scenario B · ${input.decision.scenarioB.map(formatWeight).join(" / ")}</button></div>${weightValidation.status === "invalid" ? `<div class="decision-warning" role="alert">${escapeHtml(weightValidation.message)} · ผล risk ยังไม่แสดงจนกว่าน้ำหนักรวมจะครบ 100%</div>` : `<div class="decision-kpi-grid"><article><span>Active portfolio risk</span><strong>${formatRisk(activeRisk, input.unit)}</strong><small>${assets.map((asset, index) => `${asset} ${formatWeight(activeWeights(input.decision)[index])}`).join(" · ")}</small></article><article><span>เปลี่ยนจาก prior usable date</span><strong>${priorChange?.differenceAnnualizedDecimal === null || !priorChange ? "—" : `${priorChange.differenceAnnualizedDecimal > 0 ? "+" : ""}${formatRiskDelta(priorChange.differenceAnnualizedDecimal, input.unit)}`}</strong><small>${escapeHtml(previousText)}</small></article><article><span>เปลี่ยนจาก 50/30/20 ในวันเดียวกัน</span><strong>${defaultText}</strong><small>วัน ${escapeHtml(input.selection.predictionDate)} · ${modelId(input.selection.modelName)}</small></article><article><span>Positive risk contribution สูงสุด</span><strong>${escapeHtml(highestContribution)}</strong><small>Signed RC จาก covariance ของแถวที่เลือก</small></article><article class="decision-budget-kpi"><span>User-entered annualized risk budget</span><strong>${escapeHtml(budgetValue)}</strong><small>${budgetSummaryText}</small></article></div>`}<div class="decision-budget-input"><label class="field-label" for="risk-budget-input">ตั้งขีดความเสี่ยงรายปี (%)<input id="risk-budget-input" type="number" min="0" step="0.1" inputmode="decimal" data-field="risk-budget" value="${escapeHtml(input.budgetDraft)}" placeholder="เว้นว่างไว้หากยังไม่ตั้ง" aria-describedby="risk-budget-help" /></label><small id="risk-budget-help">ไม่มีค่าเริ่มต้นหรือเพดานที่ระบบกำหนด · กรอกเป็นเปอร์เซ็นต์รายปี เช่น 9 หมายถึง 9%</small><button class="button button-secondary" type="button" data-action="portfolio-clear-budget">ล้างขีด</button>${input.budgetError ? `<p class="field-help weight-error" role="alert">${escapeHtml(input.budgetError)}</p>` : ""}</div><div class="decision-chart-heading"><div><strong>Portfolio risk timeline</strong><span>${futureLabel} · Each point forecasts Forward RV5 for the next five XNYS sessions.</span></div><span>Model ${modelId(input.selection.modelName)} · ${timeline.length.toLocaleString()} source rows</span></div>${timelineChart(timeline, input.selection.predictionDate, activeWeights(input.decision), input.evaluationId, budget, input.unit)}${timelineTable(timeline, input.unit)}<div class="decision-explain"><strong>Explain this value</strong><p>Annualized portfolio risk = √(wᵀΣw). Timeline ใช้ covariance ของแต่ละวันจากโมเดลเดียวกันและใช้น้ำหนักปัจจุบันทุกวัน แสดงเฉพาะวันจริงที่มีใน source; จุดที่ input ใช้ไม่ได้จะเป็นช่องว่างและตัดเส้น</p></div></section>`;
}

function riskDrivers(input: FinancialDecisionLabInput, activeRisk: number | null): string {
  const weights = activeWeights(input.decision);
  const contributions = activeRisk === null || input.selectedRow.covariance === null
    ? null
    : computePortfolioRiskContributions(input.selectedRow.covariance, weights);
  const maxAbsolute = Math.max(0, ...(contributions?.absoluteContributions ?? []).map(Math.abs));
  const maxRelative = Math.max(0, ...(contributions?.relativeContributions ?? []).map(Math.abs));
  const contributionRows = assets.map((asset, index) => {
    const absolute = contributions?.absoluteContributions?.[index] ?? null;
    const relative = contributions?.relativeContributions?.[index] ?? null;
    return `<tr><th scope="row">${asset}</th><td>${formatWeight(weights[index])}</td><td>${formatRisk(input.selectedRow.forecastVols[index], input.unit)}</td><td><span>${formatRisk(absolute, input.unit)}</span>${contributionBar(absolute, maxAbsolute, `${asset} absolute contribution`)}</td><td><span>${percent(relative)}</span>${contributionBar(relative, maxRelative, `${asset} relative contribution`)}</td></tr>`;
  }).join("");
  const correlationPairs: Record<string, number | null> = {
    "SPY|IEF": input.selectedRow.correlations.spyIef,
    "IEF|SPY": input.selectedRow.correlations.spyIef,
    "SPY|GLD": input.selectedRow.correlations.spyGld,
    "GLD|SPY": input.selectedRow.correlations.spyGld,
    "IEF|GLD": input.selectedRow.correlations.iefGld,
    "GLD|IEF": input.selectedRow.correlations.iefGld,
  };
  const matrixRows = assets.map((rowAsset) => `<tr><th scope="row">${rowAsset}</th>${assets.map((columnAsset) => {
    const value = rowAsset === columnAsset ? (input.selectedRow.correlationReady ? 1 : null) : correlationPairs[`${rowAsset}|${columnAsset}`];
    const color = value === null || value === undefined ? "transparent" : value >= 0 ? `rgba(46,98,165,${Math.abs(value) * 0.2 + 0.06})` : `rgba(163,79,70,${Math.abs(value) * 0.2 + 0.06})`;
    return `<td style="background:${color}">${value === null || value === undefined ? "—" : value.toFixed(3)}</td>`;
  }).join("")}</tr>`).join("");
  const readyText = input.selectedRow.correlationReady ? "Correlation window ready" : "Correlation unavailable";
  return `<section class="analysis-card decision-main-card" role="tabpanel" id="portfolio-panel" aria-labelledby="portfolio-tab-drivers"><div class="section-card-heading"><div><span class="section-overline">RISK DRIVERS · SIGNED CONTRIBUTIONS</span><h2 class="analysis-title">อะไรผลักความเสี่ยงพอร์ต?</h2><p>Contribution แสดงเครื่องหมายตาม covariance จึงมีค่าติดลบได้เมื่อสินทรัพย์ช่วยหักล้างความเสี่ยงร่วมกัน</p></div><span class="readonly-pill">Scenario ${input.decision.activeScenario}</span></div><div class="decision-subsection-heading"><strong>Signed risk contributions</strong><span>${formatRisk(activeRisk, input.unit)} total · row ${escapeHtml(input.selection.predictionDate)}</span></div><div class="table-scroll"><table class="data-table decision-driver-table"><caption class="visually-hidden">Risk contribution by asset for the active portfolio weights</caption><thead><tr><th scope="col">Asset</th><th scope="col">Weight</th><th scope="col">Forecast volatility</th><th scope="col">Absolute RC · signed</th><th scope="col">Relative RC · signed</th></tr></thead><tbody>${contributionRows}</tbody><tfoot><tr><th scope="row">Sum</th><td>100%</td><td>—</td><td>${formatRisk(contributions?.absoluteContributions?.reduce((sum, value) => sum + value, 0) ?? null, input.unit)}</td><td>${percent(contributions?.relativeContributions?.reduce((sum, value) => sum + value, 0) ?? null)}</td></tr></tfoot></table></div><div class="decision-explain"><strong>สูตรที่ใช้</strong><p>RCᵢ = wᵢ(Σw)ᵢ / σₚ และ RRCᵢ = RCᵢ / σₚ · เมื่อ σₚ &gt; 0 ผลรวม RC เท่ากับ σₚ และผลรวม RRC เท่ากับ 100% · หาก σₚ = 0 contribution จะไม่กำหนด</p></div><div class="decision-subsection-heading"><strong>Stored 20-session correlations</strong><span>${readyText} · run ${escapeHtml(input.selectedRow.correlationRunId || "—")}</span></div><div class="table-scroll"><table class="data-table decision-correlation-matrix"><caption class="visually-hidden">Correlation heatmap from stored source correlations for the selected date and model</caption><thead><tr><th scope="col">Asset</th>${assets.map((asset) => `<th scope="col">${asset}</th>`).join("")}</tr></thead><tbody>${matrixRows}</tbody></table></div><p class="decision-note">Heatmap นี้ใช้ค่าที่บันทึกใน <code>corr_*_20d</code> โดยตรง ไม่ได้อนุมาน correlation จาก covariance ที่แสดงด้านอื่น · ค่านี้เป็น historical proxies ไม่ใช่ correlation forecasts · Forecast input และ correlation เป็นแถวเดียวกันใน portfolio_risk.csv</p></section>`;
}

function scenarioEditor(name: "A" | "B", weights: PortfolioWeights, active: boolean): string {
  const result = validateScenarioWeights(weights);
  const total = weights.reduce((sum, value) => sum + (Number.isFinite(value) ? value : 0), 0);
  const controls = assets.map((asset, index) => {
    const value = Number.isFinite(weights[index]) ? escapeHtml(String(weights[index] * 100)) : "";
    return `<div class="scenario-weight-control"><label class="field-label scenario-weight-field" for="scenario-${name}-${asset}">${asset} weight (%)<input id="scenario-${name}-${asset}" type="number" min="0" max="100" step="1" inputmode="decimal" data-field="scenario-weight" data-scenario="${name}" data-index="${index}" value="${value}" /></label><input class="scenario-weight-slider" id="scenario-${name}-${asset}-slider" type="range" min="0" max="100" step="1" aria-label="${asset} weight slider (%)" data-field="scenario-weight-slider" data-scenario="${name}" data-index="${index}" value="${value || "0"}" /></div>`;
  }).join("");
  return `<article class="scenario-editor${active ? " active" : ""}"><div class="scenario-editor-heading"><div><span class="section-overline">SCENARIO ${name}</span><strong>${name === "A" ? "ชุดน้ำหนัก A" : "ชุดน้ำหนัก B"}</strong><small>${weights.map((weight, index) => `${assets[index]} ${formatWeight(weight)}`).join(" · ")}</small></div><button class="button ${active ? "button-primary" : "button-secondary"}" type="button" data-action="portfolio-active-scenario" data-scenario="${name}" aria-pressed="${active}">${active ? "กำลังใช้ใน Risk Center" : "ใช้ใน Risk Center"}</button></div><div class="scenario-weight-grid">${controls}</div><p class="field-help${result.status === "invalid" ? " weight-error" : ""}" role="${result.status === "invalid" ? "alert" : "status"}" aria-live="polite" data-scenario-total="${name}">รวม ${(total * 100).toFixed(2)}%${result.status === "invalid" ? ` · ${escapeHtml(result.message)}` : " · น้ำหนักครบ 100%"}</p><div class="portfolio-preset-row"><span>ตัวอย่าง</span><button class="portfolio-preset-button" type="button" data-action="portfolio-weight-preset" data-scenario="${name}" data-preset="default">50/30/20</button><button class="portfolio-preset-button" type="button" data-action="portfolio-weight-preset" data-scenario="${name}" data-preset="example">60/20/20</button><button class="portfolio-reset-button" type="button" data-action="portfolio-weight-preset" data-scenario="${name}" data-preset="equal">Equal weight</button></div></article>`;
}

function scenarioLab(input: FinancialDecisionLabInput, riskA: number | null, riskB: number | null, timelineA: PortfolioRiskTimelinePoint[], timelineB: PortfolioRiskTimelinePoint[]): string {
  const comparison = compareScenarioRisks(riskA, riskB);
  const delta = comparison.differenceAnnualizedDecimal;
  const defaultA = input.decision.scenarioA;
  const defaultB = input.decision.scenarioB;
  const deltaText = delta === null ? "—" : `${delta > 0 ? "+" : ""}${formatRiskDelta(delta, input.unit)}${comparison.relativeDifferencePercent === null ? " · relative change undefined from zero baseline" : ` · ${comparison.relativeDifferencePercent > 0 ? "+" : ""}${comparison.relativeDifferencePercent.toFixed(2)}% vs A`}`;
  const rows = [
    `<tr><th scope="row">Portfolio risk</th><td>${formatRisk(riskA, input.unit)}</td><td>${formatRisk(riskB, input.unit)}</td></tr>`,
    `<tr><th scope="row">Difference · B − A</th><td colspan="2">${deltaText}</td></tr>`,
  ].join("");
  const validA = validateScenarioWeights(defaultA).status === "valid";
  const validB = validateScenarioWeights(defaultB).status === "valid";
  return `<section class="analysis-card decision-main-card" role="tabpanel" id="portfolio-panel" aria-labelledby="portfolio-tab-scenarios"><div class="section-card-heading"><div><span class="section-overline">SCENARIO LAB · SAME DATE · SAME MODEL · SAME COVARIANCE</span><h2 class="analysis-title">เปรียบเทียบ A กับ B</h2><p>ทั้งสองชุดเริ่มจาก 50/30/20 และปรับได้เอง ไม่มี allocation ที่ระบบแนะนำ</p></div><span class="readonly-pill">Local what-if</span></div><div class="scenario-editor-grid">${scenarioEditor("A", defaultA, input.decision.activeScenario === "A")}${scenarioEditor("B", defaultB, input.decision.activeScenario === "B")}</div>${!validA || !validB ? `<div class="decision-warning" role="alert">ผลเปรียบเทียบยังไม่แสดงจนกว่าน้ำหนัก Scenario A และ B จะรวมได้ 100%</div>` : `<div class="table-scroll"><table class="data-table scenario-compare-table"><caption class="visually-hidden">Portfolio risk comparison for two user-defined allocations</caption><thead><tr><th scope="col">Measure</th><th scope="col">Scenario A</th><th scope="col">Scenario B</th></tr></thead><tbody>${rows}</tbody></table><div class="decision-chart-heading"><div><strong>Historical risk · fixed Scenario A/B weights</strong><span>${input.selection.view === "as-of" ? `As-of view through ${escapeHtml(input.selection.asOfDate ?? input.selection.predictionDate)}` : "Retrospective · all recorded Test dates"} · Each point forecasts Forward RV5 for the next five XNYS sessions.</span></div><span>${modelId(input.selection.modelName)} · same source rows</span></div>${scenarioTimelineChart(timelineA, timelineB, input.selection.predictionDate, defaultA, defaultB, input.evaluationId, input.decision.budgetAnnualizedDecimal, input.unit)}${scenarioTimelineTable(timelineA, timelineB, input.unit)}</div>`}<p class="decision-note">ใช้น้ำหนักแต่ละชุดกับ covariance matrix เดียวกันของ ${escapeHtml(input.selection.predictionDate)} · ${modelId(input.selection.modelName)} · เปลี่ยนสัดส่วนเท่านั้น ไม่มีการ optimize หรือสร้าง forecast เพิ่ม</p></section>`;
}

function trustAndMethods(input: FinancialDecisionLabInput): string {
  const metrics = input.modelMetrics.find((row) => row.modelName === input.selection.modelName && row.ticker === "MACRO");
  const coverage = assets.map((asset) => input.coverage.find((row) => row.modelName === input.selection.modelName && row.ticker === asset));
  const coverageItems = assets.map((asset, index) => {
    const row = coverage[index];
    return `<li><strong>${asset}</strong> · forecast coverage ${row ? percent(row.forecastCoverage) : "—"} · mature/evaluable ${row?.matureEvaluableCount.toLocaleString() ?? "—"}/${row?.expectedEligiblePredictionAnchors.toLocaleString() ?? "—"}</li>`;
  }).join("");
  return `<details class="decision-trust-details"><summary>Trust &amp; Methods · source, formula and limitations</summary><div class="decision-trust-grid"><div><h3>Calculation and source row</h3><p>Σ = diag(σ) R diag(σ) จาก forecasts และ corr_*_20d ที่ตรวจแล้ว · portfolio risk = √(wᵀΣw). เปลี่ยนได้เฉพาะน้ำหนักและ risk budget ที่ผู้ใช้กรอก</p><dl><dt>Selected date · model</dt><dd>${escapeHtml(input.selectedRow.predictionDate)} · ${modelId(input.selectedRow.modelName)}</dd><dt>Replay run</dt><dd><code>${escapeHtml(input.selectedRow.replayRunId)}</code></dd><dt>Input snapshot</dt><dd><code>${escapeHtml(input.selectedRow.inputSnapshotId)}</code></dd><dt>Correlation run</dt><dd><code>${escapeHtml(input.selectedRow.correlationRunId || "—")}</code></dd><dt>Source allocation</dt><dd>${input.selectedRow.sourceWeights.map((weight, index) => `${assets[index]} ${Math.round(weight * 100)}%`).join(" · ")}</dd></dl></div><div><h3>Model and coverage context</h3><p>${metrics ? `${modelId(metrics.modelName)} · MACRO Test MAE ${formatRisk(metrics.mae, input.unit)} · RMSE ${formatRisk(metrics.rmse, input.unit)} · paired N ${metrics.pairedN.toLocaleString()}/${metrics.expectedEligibleAnchorCount.toLocaleString()}` : "ไม่มี MACRO model metric ที่ตรงกับโมเดลนี้"}</p><ul class="decision-coverage-list">${coverageItems}</ul><small>Coverage และ error เป็นหลักฐานบริบทของ forecast ในชุด Test; ไม่ใช่ช่วงความเชื่อมั่นหรือความแม่นยำที่รับประกันของ portfolio risk</small></div><div><h3>ข้อจำกัด</h3><p>${input.selectedRow.split.toUpperCase()} historical replay ที่ตรวจแล้ว · source เป็น simulated historical replay. Snapshot ระบุ point-in-time source availability verified: <strong>${input.pointInTimeSourceAvailabilityVerified ? "Yes" : "No"}</strong> · strict cutoff ${escapeHtml(input.strictCutoff)}. ไม่แสดงผลตอบแทน, P&amp;L, VaR, expected return หรือ allocation ที่เหมาะสม; ค่านี้ไม่ใช่คำแนะนำการลงทุน.</p><p>Risk budget เป็นขีดที่ผู้ใช้กำหนดเอง จำนวนวันเหนือขีดคือ count ใน source rows ที่ประเมินได้ ไม่ใช่ probability.</p></div><div><h3>เปิดหลักฐานที่เกี่ยวข้อง</h3><p><button class="link-button" type="button" data-route="/models">Models</button> <button class="link-button" type="button" data-route="/research">Research</button> <button class="link-button" type="button" data-route="/provenance">Provenance</button> <button class="link-button" type="button" data-route="/forecasts">Replay session เดียวกัน</button></p><p>Evaluation <code>${escapeHtml(input.evaluationId)}</code></p></div></div></details>`;
}

export function renderFinancialDecisionLab(input: FinancialDecisionLabInput): string {
  const active = activeWeights(input.decision);
  const activeValidation = validateScenarioWeights(active);
  const timeline = activeValidation.status === "valid"
    ? buildPortfolioRiskTimeline(input.rows, input.selection.modelName, active, {
      view: input.selection.view,
      asOfDate: input.selection.asOfDate ?? input.selection.predictionDate,
      rangeStart: input.selection.rangeStart,
      rangeEnd: input.selection.rangeEnd,
    })
    : [];
  const activeRisk = safeRisk(input.selectedRow, active);
  const defaultRisk = safeRisk(input.selectedRow, [0.5, 0.3, 0.2]);
  const riskA = safeRisk(input.selectedRow, input.decision.scenarioA);
  const riskB = safeRisk(input.selectedRow, input.decision.scenarioB);
  const validA = validateScenarioWeights(input.decision.scenarioA).status === "valid";
  const validB = validateScenarioWeights(input.decision.scenarioB).status === "valid";
  const timelineA = validA ? buildPortfolioRiskTimeline(input.rows, input.selection.modelName, input.decision.scenarioA, {
    view: input.selection.view,
    asOfDate: input.selection.asOfDate ?? input.selection.predictionDate,
    rangeStart: input.selection.rangeStart,
    rangeEnd: input.selection.rangeEnd,
  }) : [];
  const timelineB = validB ? buildPortfolioRiskTimeline(input.rows, input.selection.modelName, input.decision.scenarioB, {
    view: input.selection.view,
    asOfDate: input.selection.asOfDate ?? input.selection.predictionDate,
    rangeStart: input.selection.rangeStart,
    rangeEnd: input.selection.rangeEnd,
  }) : [];
  const activeContent = input.decision.activeTab === "risk" ? riskCenter(input, activeRisk, timeline, defaultRisk)
    : input.decision.activeTab === "drivers" ? riskDrivers(input, activeRisk)
      : scenarioLab(input, riskA, riskB, timelineA, timelineB);
  return `<div class="decision-lab-stack">${selectionControls(input)}<div class="decision-tabs" role="tablist" aria-label="Financial Decision Lab sections">${actionTab("risk", input.decision.activeTab)}${actionTab("drivers", input.decision.activeTab)}${actionTab("scenarios", input.decision.activeTab)}</div>${activeContent}${trustAndMethods(input)}<section class="limitation-card"><span class="limitation-mark">i</span><p>Historical source calculation for education and review. It is not a live portfolio estimate, a forecast of returns, or an investment recommendation.</p></section></div>`;
}
