import { computePortfolioVolatility, type PortfolioWeights } from "./portfolio.js";
import { parseHashRoute } from "./selection.js";
import type { ModelName, PortfolioRiskRow } from "./schemas.js";

export type FinancialDecisionTab = "risk" | "drivers" | "scenarios";
export type ActiveScenario = "A" | "B";
export type ScenarioAsset = "SPY" | "IEF" | "GLD";
export type ScenarioRemainderAsset = ScenarioAsset;

export interface FinancialScenarioState {
  scenarioA: PortfolioWeights;
  scenarioB: PortfolioWeights;
  remainderAssetA: ScenarioRemainderAsset;
  remainderAssetB: ScenarioRemainderAsset;
  activeScenario: ActiveScenario;
  budgetAnnualizedDecimal: number | null;
  activeTab: FinancialDecisionTab;
}

export type ScenarioWeightsValidation =
  | { status: "valid"; weights: PortfolioWeights }
  | { status: "invalid"; message: string };

export interface PortfolioRiskTimelinePoint {
  date: string;
  risk: number | null;
  status: string;
  missingInputs: string[];
  row: PortfolioRiskRow;
}

const scenarioKeys = ["scenarioA", "scenarioB", "scenarioRemainderA", "scenarioRemainderB", "activeScenario", "riskBudget", "portfolioTab"] as const;
const weightTolerance = 1e-8;
const defaultWeights: PortfolioWeights = [0.5, 0.3, 0.2];
const scenarioAssets: ScenarioAsset[] = ["SPY", "IEF", "GLD"];
const remainderAssets: ScenarioRemainderAsset[] = ["SPY", "IEF", "GLD"];

export function createDefaultFinancialScenarioState(): FinancialScenarioState {
  return {
    scenarioA: [...defaultWeights],
    scenarioB: [...defaultWeights],
    remainderAssetA: "GLD",
    remainderAssetB: "GLD",
    activeScenario: "A",
    budgetAnnualizedDecimal: null,
    activeTab: "risk",
  };
}

export function updateScenarioRemainderWeight(
  weights: PortfolioWeights,
  remainderAsset: ScenarioRemainderAsset,
  editedAsset: ScenarioAsset,
  weightDecimal: number,
): PortfolioWeights {
  const remainderIndex = scenarioAssets.indexOf(remainderAsset);
  const editedIndex = scenarioAssets.indexOf(editedAsset);
  if (editedIndex === remainderIndex) throw new Error("Cannot edit the selected remainder asset");
  const updated = [...weights] as PortfolioWeights;
  updated[editedIndex] = weightDecimal;
  updated[remainderIndex] = 1 - updated.reduce((sum, weight, index) => index === remainderIndex ? sum : sum + weight, 0);
  return updated;
}

export function setScenarioRemainderAsset(
  state: FinancialScenarioState,
  scenario: ActiveScenario,
  asset: ScenarioRemainderAsset,
): FinancialScenarioState {
  return scenario === "A"
    ? { ...state, remainderAssetA: asset }
    : { ...state, remainderAssetB: asset };
}

export function validateScenarioWeights(value: unknown): ScenarioWeightsValidation {
  if (!Array.isArray(value) || value.length !== 3 || value.some((weight) => typeof weight !== "number" || !Number.isFinite(weight))) {
    return { status: "invalid", message: "น้ำหนักต้องมีตัวเลขจำกัดสามค่า" };
  }
  const weights = value as PortfolioWeights;
  if (weights.some((weight) => weight < 0 || weight > 1)) return { status: "invalid", message: "น้ำหนักแต่ละสินทรัพย์ต้องอยู่ระหว่าง 0 ถึง 1" };
  if (Math.abs(weights.reduce((sum, weight) => sum + weight, 0) - 1) > weightTolerance) {
    return { status: "invalid", message: "น้ำหนักรวมต้องเท่ากับ 100%" };
  }
  return { status: "valid", weights: [...weights] };
}

export interface ScenarioRiskComparison {
  differenceAnnualizedDecimal: number | null;
  differencePercentagePoints: number | null;
  relativeDifferencePercent: number | null;
}

export function compareScenarioRisks(riskA: number | null, riskB: number | null): ScenarioRiskComparison {
  if (![riskA, riskB].every((value) => typeof value === "number" && Number.isFinite(value) && value >= 0)) {
    return { differenceAnnualizedDecimal: null, differencePercentagePoints: null, relativeDifferencePercent: null };
  }
  const differenceAnnualizedDecimal = riskB! - riskA!;
  return {
    differenceAnnualizedDecimal,
    differencePercentagePoints: differenceAnnualizedDecimal * 100,
    relativeDifferencePercent: riskA! === 0 ? null : differenceAnnualizedDecimal / riskA! * 100,
  };
}

export interface RiskTimelineOptions {
  view: "as-of" | "retrospective";
  asOfDate?: string;
  rangeStart?: string;
  rangeEnd?: string;
}

export function buildPortfolioRiskTimeline(
  rows: PortfolioRiskRow[],
  modelName: ModelName,
  weights: PortfolioWeights,
  options: RiskTimelineOptions,
): PortfolioRiskTimelinePoint[] {
  const validation = validateScenarioWeights(weights);
  if (validation.status === "invalid") throw new Error(validation.message);
  return rows
    .filter((row) => row.split === "test" && row.modelName === modelName)
    .filter((row) => options.view !== "as-of" || !options.asOfDate || row.predictionDate <= options.asOfDate)
    .filter((row) => !options.rangeStart || row.predictionDate >= options.rangeStart)
    .filter((row) => !options.rangeEnd || row.predictionDate <= options.rangeEnd)
    .sort((left, right) => left.predictionDate.localeCompare(right.predictionDate))
    .map((row) => {
      let risk: number | null = null;
      if (row.status === "OK" && row.covariance !== null && row.correlationReady && row.missingInputs.length === 0) {
        try {
          risk = computePortfolioVolatility(row.covariance, validation.weights);
        } catch {
          risk = null;
        }
      }
      return { date: row.predictionDate, risk, status: row.status, missingInputs: [...row.missingInputs], row };
    });
}

export function splitRiskTimelineSegments(points: PortfolioRiskTimelinePoint[]): PortfolioRiskTimelinePoint[][] {
  const segments: PortfolioRiskTimelinePoint[][] = [];
  let current: PortfolioRiskTimelinePoint[] = [];
  for (const point of points) {
    if (point.risk === null) {
      if (current.length > 0) segments.push(current);
      current = [];
      continue;
    }
    current.push(point);
  }
  if (current.length > 0) segments.push(current);
  return segments;
}

export function findPriorComparableRisk(
  points: PortfolioRiskTimelinePoint[],
  date: string,
): { point: PortfolioRiskTimelinePoint; sessionsBack: number } | null {
  const currentIndex = points.findIndex((point) => point.date === date);
  if (currentIndex < 0) return null;
  for (let index = currentIndex - 1; index >= 0; index -= 1) {
    const point = points[index];
    if (point?.risk !== null && point !== undefined) return { point, sessionsBack: currentIndex - index };
  }
  return null;
}

export type RiskBudgetStatus = "below" | "at" | "above" | "unavailable" | "unset";

export function riskBudgetStatus(risk: number | null, budget: number | null): RiskBudgetStatus {
  if (risk === null || !Number.isFinite(risk) || risk < 0) return "unavailable";
  if (budget === null) return "unset";
  if (!Number.isFinite(budget) || budget < 0) return "unavailable";
  return risk < budget ? "below" : risk > budget ? "above" : "at";
}

export function summarizeRiskBudget(points: Array<{ date: string; risk: number | null }>, budget: number | null): {
  evaluableCount: number;
  aboveCount: number;
  aboveDates: string[];
} {
  const evaluable = points.filter((point) => point.risk !== null && Number.isFinite(point.risk) && point.risk >= 0);
  const aboveDates = budget === null || !Number.isFinite(budget) || budget < 0
    ? []
    : evaluable.filter((point) => point.risk! > budget).map((point) => point.date);
  return { evaluableCount: evaluable.length, aboveCount: aboveDates.length, aboveDates };
}

export type FinancialDecisionParseResult =
  | { status: "absent" }
  | { status: "invalid"; message: string }
  | { status: "valid"; state: FinancialScenarioState };

function parseWeightParam(value: string | null, name: string): ScenarioWeightsValidation {
  if (value === null) return { status: "invalid", message: `ลิงก์ขาดค่า ${name}` };
  const parts = value.split(",");
  if (parts.length !== 3 || parts.some((part) => !/^-?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(part))) {
    return { status: "invalid", message: `${name} ต้องเป็นตัวเลขสามค่าคั่นด้วย comma` };
  }
  return validateScenarioWeights(parts.map(Number));
}

export function parseFinancialDecisionParams(params: URLSearchParams): FinancialDecisionParseResult {
  const present = scenarioKeys.filter((key) => params.has(key));
  if (present.length === 0) return { status: "absent" };
  const duplicate = scenarioKeys.find((key) => params.getAll(key).length > 1);
  if (duplicate) return { status: "invalid", message: `URL มีค่า ${duplicate} ซ้ำกัน` };

  const scenarioA = parseWeightParam(params.get("scenarioA"), "scenarioA");
  if (scenarioA.status === "invalid") return scenarioA;
  const scenarioB = parseWeightParam(params.get("scenarioB"), "scenarioB");
  if (scenarioB.status === "invalid") return scenarioB;
  const remainderAssetA = params.get("scenarioRemainderA") ?? "GLD";
  const remainderAssetB = params.get("scenarioRemainderB") ?? "GLD";
  if (!remainderAssets.includes(remainderAssetA as ScenarioRemainderAsset)) return { status: "invalid", message: "scenarioRemainderA ไม่รองรับ" };
  if (!remainderAssets.includes(remainderAssetB as ScenarioRemainderAsset)) return { status: "invalid", message: "scenarioRemainderB ไม่รองรับ" };
  const activeScenario = params.get("activeScenario");
  if (activeScenario !== "A" && activeScenario !== "B") return { status: "invalid", message: "activeScenario ต้องเป็น A หรือ B" };
  const activeTab = params.get("portfolioTab");
  if (activeTab !== "risk" && activeTab !== "drivers" && activeTab !== "scenarios") return { status: "invalid", message: "portfolioTab ไม่รองรับ" };

  const rawBudget = params.get("riskBudget");
  let budgetAnnualizedDecimal: number | null = null;
  if (rawBudget !== null) {
    if (!/^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(rawBudget)) return { status: "invalid", message: "riskBudget ต้องเป็นค่าร้อยละรายปีที่ไม่ติดลบ" };
    budgetAnnualizedDecimal = Number(rawBudget);
    if (!Number.isFinite(budgetAnnualizedDecimal) || budgetAnnualizedDecimal < 0) return { status: "invalid", message: "riskBudget ต้องเป็นค่าร้อยละรายปีที่ไม่ติดลบ" };
  }

  return {
    status: "valid",
    state: {
      scenarioA: scenarioA.weights,
      scenarioB: scenarioB.weights,
      remainderAssetA: remainderAssetA as ScenarioRemainderAsset,
      remainderAssetB: remainderAssetB as ScenarioRemainderAsset,
      activeScenario,
      budgetAnnualizedDecimal,
      activeTab,
    },
  };
}

export function serializeFinancialDecisionHash(selectionHash: string, state: FinancialScenarioState): string {
  const scenarioA = validateScenarioWeights(state.scenarioA);
  const scenarioB = validateScenarioWeights(state.scenarioB);
  if (scenarioA.status === "invalid" || scenarioB.status === "invalid") throw new Error("Cannot serialize invalid scenario weights");
  if (!remainderAssets.includes(state.remainderAssetA) || !remainderAssets.includes(state.remainderAssetB)) throw new Error("Cannot serialize invalid scenario remainder asset");
  if (state.activeScenario !== "A" && state.activeScenario !== "B") throw new Error("Cannot serialize invalid active scenario");
  if (!["risk", "drivers", "scenarios"].includes(state.activeTab)) throw new Error("Cannot serialize invalid portfolio tab");
  if (state.budgetAnnualizedDecimal !== null && (!Number.isFinite(state.budgetAnnualizedDecimal) || state.budgetAnnualizedDecimal < 0)) throw new Error("Cannot serialize invalid risk budget");

  const route = parseHashRoute(selectionHash);
  const params = new URLSearchParams(route.params);
  for (const key of scenarioKeys) params.delete(key);
  params.set("scenarioA", scenarioA.weights.join(","));
  params.set("scenarioB", scenarioB.weights.join(","));
  params.set("scenarioRemainderA", state.remainderAssetA);
  params.set("scenarioRemainderB", state.remainderAssetB);
  params.set("activeScenario", state.activeScenario);
  params.set("portfolioTab", state.activeTab);
  if (state.budgetAnnualizedDecimal !== null) params.set("riskBudget", String(state.budgetAnnualizedDecimal));
  return `#${route.path}?${params.toString()}`;
}
