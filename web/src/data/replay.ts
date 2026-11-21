import type { EvaluationRow, ForecastAuditRow, ModelName, Ticker } from "./schemas.js";

export type AsOfLabelView =
  | { status: "source-pending"; actual: null; absoluteError: null }
  | { status: "source-not-evaluable"; actual: null; absoluteError: null }
  | { status: "awaiting-target-end"; actual: null; absoluteError: null }
  | { status: "eligible-reveal-required"; actual: null; absoluteError: null }
  | { status: "missing-evaluation"; actual: null; absoluteError: null }
  | { status: "revealed"; actual: number; absoluteError: number };

/**
 * Teaching overlay only: source Pending remains hidden forever, and actual/error
 * are revealed only for the exact verified evaluation row after target maturity.
 */
export function resolveAsOfLabelView(
  row: ForecastAuditRow,
  asOfDate: string,
  reveal: boolean,
  evaluation: EvaluationRow | undefined,
): AsOfLabelView {
  if (row.labelStatus === "PENDING" || row.evaluationStatus === "PENDING_LABEL") {
    return { status: "source-pending", actual: null, absoluteError: null };
  }
  if (row.evaluationStatus !== "EVALUABLE") {
    return { status: "source-not-evaluable", actual: null, absoluteError: null };
  }
  if (row.targetEndDate > asOfDate) {
    return { status: "awaiting-target-end", actual: null, absoluteError: null };
  }
  if (!evaluation || evaluation.predictionId !== row.predictionId || evaluation.predictionDate !== row.predictionDate || evaluation.ticker !== row.ticker || evaluation.modelName !== row.modelName || evaluation.targetEndDate !== row.targetEndDate) {
    return { status: "missing-evaluation", actual: null, absoluteError: null };
  }
  if (!reveal) return { status: "eligible-reveal-required", actual: null, absoluteError: null };
  return { status: "revealed", actual: evaluation.targetRealizedVol5d, absoluteError: evaluation.absoluteError };
}

export function selectSameDateForecasts(rows: ForecastAuditRow[], ticker: Ticker, predictionDate: string): ForecastAuditRow[] {
  const modelOrder: ModelName[] = ["CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD"];
  return rows
    .filter((row) => row.split === "test" && row.ticker === ticker && row.predictionDate === predictionDate)
    .sort((left, right) => modelOrder.indexOf(left.modelName) - modelOrder.indexOf(right.modelName));
}
