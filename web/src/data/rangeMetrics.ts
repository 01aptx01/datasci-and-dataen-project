import type { EvaluationRow, ForecastAuditRow, ModelName, Ticker } from "./schemas.js";

export const rangeModelOrder: ModelName[] = ["CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD"];
const rangeTickers: Ticker[] = ["SPY", "IEF", "GLD"];

export interface DescriptiveModelScore {
  modelName: ModelName;
  mae: number | null;
  rmse: number | null;
  n: number;
}

export interface DescriptiveRangeMetrics {
  status: "ready" | "insufficient";
  ticker: Ticker | "MACRO";
  startDate: string;
  endDate: string;
  scores: DescriptiveModelScore[];
  n: number;
  nByTicker: Partial<Record<Ticker, number>>;
  smallSample: boolean;
  reason: string;
}

interface PairedError { absolute: number; squared: number }

function pairedEvaluation(row: ForecastAuditRow, evaluation: EvaluationRow | undefined): PairedError | undefined {
  if (!evaluation || evaluation.predictionId !== row.predictionId || evaluation.predictionDate !== row.predictionDate || evaluation.ticker !== row.ticker || evaluation.modelName !== row.modelName || evaluation.targetEndDate !== row.targetEndDate) return undefined;
  const residual = evaluation.predictedVolAnnualized - evaluation.targetRealizedVol5d;
  const absolute = Math.abs(residual);
  if (!Number.isFinite(absolute) || !Number.isFinite(residual * residual)) return undefined;
  return { absolute, squared: residual * residual };
}

function emptyResult(ticker: Ticker | "MACRO", startDate: string, endDate: string, reason: string, nByTicker: Partial<Record<Ticker, number>> = {}): DescriptiveRangeMetrics {
  return {
    status: "insufficient", ticker, startDate, endDate,
    scores: rangeModelOrder.map((modelName) => ({ modelName, mae: null, rmse: null, n: 0 })),
    n: 0, nByTicker, smallSample: false, reason,
  };
}

export function calculateDescriptiveRangeMetrics(
  rows: ForecastAuditRow[],
  evaluations: Map<string, EvaluationRow>,
  startDate: string,
  endDate: string,
  ticker: Ticker | "MACRO",
): DescriptiveRangeMetrics {
  if (!startDate || !endDate || startDate > endDate) return emptyResult(ticker, startDate, endDate, "เลือกช่วงวันที่ให้ถูกต้องก่อนคำนวณ");

  const scopedRows = rows.filter((row) => row.split === "test" && row.predictionDate >= startDate && row.predictionDate <= endDate && row.isCommonPanel && row.evaluationStatus === "EVALUABLE" && row.forecastStatus === "VALID");
  const anchors = new Map<string, Map<ModelName, ForecastAuditRow>>();
  const duplicateKeys = new Set<string>();
  for (const row of scopedRows) {
    const key = `${row.ticker}\u0000${row.predictionDate}`;
    const modelRows = anchors.get(key) ?? new Map<ModelName, ForecastAuditRow>();
    if (modelRows.has(row.modelName)) duplicateKeys.add(key);
    else modelRows.set(row.modelName, row);
    anchors.set(key, modelRows);
  }

  const errorsByTicker = new Map<Ticker, Map<ModelName, PairedError[]>>();
  for (const asset of rangeTickers) {
    const byModel = new Map<ModelName, PairedError[]>();
    for (const modelName of rangeModelOrder) byModel.set(modelName, []);
    errorsByTicker.set(asset, byModel);
  }
  for (const [key, modelRows] of anchors) {
    if (duplicateKeys.has(key)) continue;
    if (!rangeModelOrder.every((modelName) => modelRows.has(modelName))) continue;
    const rowsForAnchor = rangeModelOrder.map((modelName) => modelRows.get(modelName)!);
    const pairs = rowsForAnchor.map((row) => pairedEvaluation(row, evaluations.get(row.predictionId)));
    if (pairs.some((pair) => pair === undefined)) continue;
    const asset = rowsForAnchor[0].ticker;
    const byModel = errorsByTicker.get(asset)!;
    rangeModelOrder.forEach((modelName, index) => byModel.get(modelName)!.push(pairs[index]!));
  }

  const nByTicker = Object.fromEntries(rangeTickers.map((asset) => [asset, errorsByTicker.get(asset)!.get("ONLINE_SGD")!.length])) as Record<Ticker, number>;
  const selectedTickers = ticker === "MACRO" ? rangeTickers : [ticker];
  if (selectedTickers.some((asset) => nByTicker[asset] === 0)) {
    return emptyResult(ticker, startDate, endDate, ticker === "MACRO" ? "MACRO ต้องมี common paired rows ครบทั้ง SPY, IEF และ GLD ในช่วงนี้" : `ไม่มี common paired rows ที่ประเมินได้สำหรับ ${ticker} ในช่วงนี้`, nByTicker);
  }

  const scores = rangeModelOrder.map((modelName) => {
    const perTicker = selectedTickers.map((asset) => {
      const errors = errorsByTicker.get(asset)!.get(modelName)!;
      const mae = errors.reduce((sum, item) => sum + item.absolute, 0) / errors.length;
      const rmse = Math.sqrt(errors.reduce((sum, item) => sum + item.squared, 0) / errors.length);
      return { mae, rmse, n: errors.length };
    });
    const mae = perTicker.reduce((sum, item) => sum + item.mae, 0) / perTicker.length;
    const rmse = Math.sqrt(perTicker.reduce((sum, item) => sum + item.rmse * item.rmse, 0) / perTicker.length);
    return { modelName, mae, rmse, n: perTicker.reduce((sum, item) => sum + item.n, 0) };
  });
  const n = selectedTickers.reduce((sum, asset) => sum + nByTicker[asset], 0);
  return {
    status: "ready", ticker, startDate, endDate, scores, n, nByTicker,
    smallSample: selectedTickers.some((asset) => nByTicker[asset] < 20),
    reason: ticker === "MACRO" ? "MACRO MAE คือค่าเฉลี่ย MAE ราย ETF; RMSE คือรากที่สองของค่าเฉลี่ย RMSE² ราย ETF" : "คำนวณจาก common paired rows ของทั้ง 4 โมเดลใน ETF ที่เลือก",
  };
}
