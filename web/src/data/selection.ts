import type { ForecastAuditRow, ModelName, PortfolioRiskRow, Ticker } from "./schemas.js";

export type ExperimentSplit = "validation" | "test";
export type ExperimentView = "as-of" | "retrospective";
export type SelectionRangePreset = "all-test" | "last20" | "custom";

export interface ExperimentSelection {
  evaluationId: string;
  replayId: string;
  split: ExperimentSplit;
  predictionDate: string;
  modelName: ModelName;
  ticker: Ticker;
  asOfDate?: string;
  rangeStart?: string;
  rangeEnd?: string;
  rangePreset?: SelectionRangePreset;
  view: ExperimentView;
}

export interface SelectionSource {
  evaluationId: string;
  replayId: string;
  forecasts: ForecastAuditRow[];
  portfolioRisk: PortfolioRiskRow[];
}

export interface ParsedHashRoute {
  path: string;
  params: URLSearchParams;
}

export type SelectionParseResult =
  | { status: "absent" }
  | { status: "invalid"; message: string }
  | { status: "valid"; selection: ExperimentSelection };

export type SelectionValidationResult =
  | { status: "valid"; selection: ExperimentSelection; forecast: ForecastAuditRow }
  | { status: "invalid"; message: string };

const models: ModelName[] = ["CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD"];
const tickers: Ticker[] = ["SPY", "IEF", "GLD"];
const selectionKeys = ["evaluationId", "replayId", "split", "date", "model", "ticker", "asOf", "rangeStart", "rangeEnd", "rangePreset", "view"];
const allowedAuxiliaryKeys = ["mode", "scope", "dateStart", "dateEnd"];

export function parseHashRoute(hash: string): ParsedHashRoute {
  const value = hash.startsWith("#") ? hash.slice(1) : hash;
  const queryIndex = value.indexOf("?");
  const path = queryIndex < 0 ? value : value.slice(0, queryIndex);
  const query = queryIndex < 0 ? "" : value.slice(queryIndex + 1);
  return { path: path || "/overview", params: new URLSearchParams(query) };
}

export function serializeSelectionHash(path: string, selection: ExperimentSelection): string {
  const params = new URLSearchParams();
  params.set("evaluationId", selection.evaluationId);
  params.set("replayId", selection.replayId);
  params.set("split", selection.split);
  params.set("date", selection.predictionDate);
  params.set("model", selection.modelName);
  params.set("ticker", selection.ticker);
  if (selection.asOfDate) params.set("asOf", selection.asOfDate);
  if (selection.rangeStart) params.set("rangeStart", selection.rangeStart);
  if (selection.rangeEnd) params.set("rangeEnd", selection.rangeEnd);
  if (selection.rangePreset) params.set("rangePreset", selection.rangePreset);
  params.set("view", selection.view);
  return `#${path}?${params.toString()}`;
}

export function parseExperimentSelection(params: URLSearchParams): SelectionParseResult {
  const keys = [...params.keys()];
  const unsupported = keys.find((key) => !selectionKeys.includes(key) && !allowedAuxiliaryKeys.includes(key));
  if (unsupported) return { status: "invalid", message: `ไม่รองรับ URL parameter: ${unsupported}` };
  if (!selectionKeys.some((key) => params.has(key))) return { status: "absent" };

  const duplicate = selectionKeys.find((key) => params.getAll(key).length > 1);
  if (duplicate) return { status: "invalid", message: `URL มีค่า ${duplicate} ซ้ำกัน` };

  const evaluationId = params.get("evaluationId");
  const replayId = params.get("replayId");
  const split = params.get("split");
  const predictionDate = params.get("date");
  const modelName = params.get("model");
  const ticker = params.get("ticker");
  const view = params.get("view");
  const rawRangePreset = params.get("rangePreset");
  if (!evaluationId || !replayId || !split || !predictionDate || !modelName || !ticker || !view) {
    return { status: "invalid", message: "ลิงก์เลือก session ไม่ครบ ต้องมี Eval/Replay ID, split, date, model, ticker และ view" };
  }
  if (split !== "test" && split !== "validation") return { status: "invalid", message: "split ในลิงก์ต้องเป็น test หรือ validation" };
  if (!models.includes(modelName as ModelName)) return { status: "invalid", message: `ไม่รู้จัก model: ${modelName}` };
  if (!tickers.includes(ticker as Ticker)) return { status: "invalid", message: `ไม่รู้จัก ticker: ${ticker}` };
  if (view !== "as-of" && view !== "retrospective") return { status: "invalid", message: `ไม่รู้จัก view: ${view}` };
  if (rawRangePreset !== null && rawRangePreset !== "all-test" && rawRangePreset !== "last20" && rawRangePreset !== "custom") {
    return { status: "invalid", message: `ไม่รู้จัก range preset: ${rawRangePreset}` };
  }
  const rangePreset: SelectionRangePreset | undefined = rawRangePreset === null ? undefined : rawRangePreset;

  const asOfDate = params.get("asOf") ?? undefined;
  const rangeStart = params.get("rangeStart") ?? params.get("dateStart") ?? undefined;
  const rangeEnd = params.get("rangeEnd") ?? params.get("dateEnd") ?? undefined;
  return {
    status: "valid",
    selection: {
      evaluationId,
      replayId,
      split,
      predictionDate,
      modelName: modelName as ModelName,
      ticker: ticker as Ticker,
      ...(asOfDate ? { asOfDate } : {}),
      ...(rangeStart ? { rangeStart } : {}),
      ...(rangeEnd ? { rangeEnd } : {}),
      ...(rangePreset ? { rangePreset } : {}),
      view,
    },
  };
}

export function isIsoCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00.000Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function validateExperimentSelection(
  selection: ExperimentSelection,
  source: SelectionSource,
  requirePortfolioRow = false,
): SelectionValidationResult {
  if (selection.evaluationId !== source.evaluationId) return { status: "invalid", message: "Evaluation ID ไม่ตรงกับ snapshot ที่ตรวจแล้ว" };
  if (selection.replayId !== source.replayId) return { status: "invalid", message: "Replay ID ไม่ตรงกับ snapshot ที่ตรวจแล้ว" };
  if (selection.split !== "test" && selection.split !== "validation") return { status: "invalid", message: "split ในลิงก์ไม่รองรับ" };
  if (!isIsoCalendarDate(selection.predictionDate)) return { status: "invalid", message: "วันที่ prediction ในลิงก์ไม่ใช่วันที่ YYYY-MM-DD ที่ถูกต้อง" };
  if (!models.includes(selection.modelName) || !tickers.includes(selection.ticker)) return { status: "invalid", message: "model หรือตัวสินทรัพย์ในลิงก์ไม่รองรับ" };
  if (selection.view !== "as-of" && selection.view !== "retrospective") return { status: "invalid", message: "รูปแบบการดูผลในลิงก์ไม่รองรับ" };
  if (selection.asOfDate && (!isIsoCalendarDate(selection.asOfDate) || selection.asOfDate < selection.predictionDate)) {
    return { status: "invalid", message: "As-of date ต้องเป็นวันที่ถูกต้องและไม่ก่อน prediction date" };
  }
  if (selection.rangeStart && !isIsoCalendarDate(selection.rangeStart)) return { status: "invalid", message: "rangeStart ไม่ใช่วันที่ YYYY-MM-DD ที่ถูกต้อง" };
  if (selection.rangeEnd && !isIsoCalendarDate(selection.rangeEnd)) return { status: "invalid", message: "rangeEnd ไม่ใช่วันที่ YYYY-MM-DD ที่ถูกต้อง" };
  if (selection.rangeStart && selection.rangeEnd && selection.rangeStart > selection.rangeEnd) {
    return { status: "invalid", message: "rangeStart ต้องไม่อยู่หลัง rangeEnd" };
  }
  if (selection.rangePreset === "all-test" && (selection.rangeStart || selection.rangeEnd)) {
    return { status: "invalid", message: "All Test ไม่ควรมีขอบเขตวันที่กำหนดเอง" };
  }
  if (selection.rangePreset === "last20" && (!selection.rangeStart || !selection.rangeEnd)) {
    return { status: "invalid", message: "Last 20 ต้องมีวันเริ่มและวันสิ้นสุดในลิงก์" };
  }
  if (selection.rangePreset === "custom" && !selection.rangeStart && !selection.rangeEnd) {
    return { status: "invalid", message: "Custom range ต้องมีวันเริ่มหรือวันสิ้นสุดอย่างน้อยหนึ่งค่า" };
  }

  const forecast = source.forecasts.find((row) =>
    row.split === selection.split && row.predictionDate === selection.predictionDate &&
    row.ticker === selection.ticker && row.modelName === selection.modelName,
  );
  if (!forecast) {
    return {
      status: "invalid",
      message: `ไม่มี recorded forecast สำหรับ ${selection.ticker} · ${selection.modelName} · ${selection.split} · ${selection.predictionDate}`,
    };
  }
  if (selection.asOfDate && !source.forecasts.some((row) =>
    row.split === selection.split && row.ticker === selection.ticker && row.predictionDate === selection.asOfDate,
  )) {
    return { status: "invalid", message: `ไม่มี XNYS session ${selection.asOfDate} ในชุด ${selection.ticker} ที่เลือก` };
  }

  if (requirePortfolioRow) {
    const portfolio = source.portfolioRisk.find((row) =>
      row.split === selection.split && row.predictionDate === selection.predictionDate && row.modelName === selection.modelName &&
      row.status === "OK" && row.covariance !== null && row.portfolioVol !== null && row.missingInputs.length === 0,
    );
    if (!portfolio) {
      return {
        status: "invalid",
        message: `ไม่มี portfolio row สถานะ OK สำหรับ ${selection.predictionDate} · ${selection.modelName}; เลือกวันหรือโมเดลที่มี covariance ครบ`,
      };
    }
  }
  return { status: "valid", selection, forecast };
}

export function defaultExperimentSelection(source: SelectionSource): ExperimentSelection | null {
  const candidates = source.forecasts
    .filter((row) => row.split === "test" && row.ticker === "SPY" && row.modelName === "ONLINE_SGD")
    .sort((left, right) => right.predictionDate.localeCompare(left.predictionDate));
  const selected = candidates.find((forecast) => source.portfolioRisk.some((row) =>
    row.split === "test" && row.predictionDate === forecast.predictionDate && row.modelName === forecast.modelName &&
    row.status === "OK" && row.covariance !== null && row.portfolioVol !== null && row.missingInputs.length === 0,
  ));
  if (!selected) return null;
  return {
    evaluationId: source.evaluationId,
    replayId: source.replayId,
    split: "test",
    predictionDate: selected.predictionDate,
    modelName: selected.modelName,
    ticker: selected.ticker,
    asOfDate: selected.predictionDate,
    view: "as-of",
  };
}
