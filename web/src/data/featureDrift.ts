import { assertExactHeaders, parseCsv } from "./csv.js";
import { sha256 } from "./loadSnapshot.js";

export const FEATURE_DRIFT_METRIC_HEADERS = [
  "diagnostic_id", "evaluation_id", "replay_id", "source_feature_run_id", "feature_set_version", "split", "as_of_date", "ticker", "feature_name",
  "reference_start", "reference_end", "reference_n", "current_start", "current_end", "current_n", "window_size", "wasserstein_raw", "train_iqr",
  "wasserstein_normalized", "psi", "median_ref", "median_current", "p95_ref", "p95_current", "out_of_train_range_rate", "wasserstein_threshold",
  "psi_threshold", "status", "status_reason",
];
export const FEATURE_DRIFT_HISTOGRAM_HEADERS = [
  "diagnostic_id", "as_of_date", "ticker", "feature_name", "window_size", "bin_index", "lower_edge", "upper_edge", "reference_count", "current_count",
  "reference_pct", "current_pct", "bin_definition_id", "effective_bin_count",
];
export const FEATURE_DRIFT_REFERENCE_HEADERS = [
  "diagnostic_id", "ticker", "feature_name", "reference_start", "reference_end", "reference_n", "q01", "q05", "q25", "median", "q75", "q95", "q99",
  "train_iqr", "effective_bin_count", "bin_definition_id", "reference_hash", "bin_status",
];
export const FEATURE_DRIFT_CALIBRATION_HEADERS = [
  "diagnostic_id", "ticker", "feature_name", "window_size", "calibration_start", "calibration_end", "valid_window_count", "threshold_percentile",
  "threshold_method", "wasserstein_threshold", "psi_threshold", "calibration_status",
];

export type DriftStatus = "DRIFT_SIGNAL" | "NO_SIGNAL" | "INSUFFICIENT_DATA" | "UNCOMPUTABLE_SCALE" | "CALIBRATION_LIMITATION";
export type DriftMetricName = "wasserstein_normalized" | "psi";
export type DriftWindowSize = 60 | 120;
export type DriftTicker = "SPY" | "IEF" | "GLD";

export interface FeatureDriftMetric {
  diagnosticId: string;
  evaluationId: string;
  replayId: string;
  sourceFeatureRunId: string;
  featureSetVersion: string;
  asOfDate: string;
  ticker: DriftTicker;
  featureName: string;
  referenceStart: string;
  referenceEnd: string;
  referenceN: number;
  currentStart: string;
  currentEnd: string;
  currentN: number;
  windowSize: DriftWindowSize;
  wassersteinRaw: number | null;
  trainIqr: number;
  wassersteinNormalized: number | null;
  psi: number | null;
  medianReference: number | null;
  medianCurrent: number | null;
  p95Reference: number | null;
  p95Current: number | null;
  outOfTrainRangeRate: number | null;
  wassersteinThreshold: number | null;
  psiThreshold: number | null;
  status: DriftStatus;
  statusReason: string;
}

export interface FeatureDriftHistogramBin {
  index: number;
  lowerEdge: number;
  upperEdge: number;
  referenceCount: number;
  currentCount: number;
  referencePct: number;
  currentPct: number;
  binDefinitionId: string;
  effectiveBinCount: number;
}

export interface FeatureDriftReferenceSummary {
  ticker: DriftTicker;
  featureName: string;
  referenceStart: string;
  referenceEnd: string;
  referenceN: number;
  q01: number;
  q05: number;
  q25: number;
  median: number;
  q75: number;
  q95: number;
  q99: number;
  trainIqr: number;
  effectiveBinCount: number;
  binDefinitionId: string;
  referenceHash: string;
  binStatus: string;
}

export interface FeatureDriftCalibration {
  ticker: DriftTicker;
  featureName: string;
  windowSize: DriftWindowSize;
  calibrationStart: string;
  calibrationEnd: string;
  validWindowCount: number;
  thresholdPercentile: number;
  thresholdMethod: string;
  wassersteinThreshold: number | null;
  psiThreshold: number | null;
  calibrationStatus: string;
}

export interface FeatureDriftManifest {
  diagnosticId: string;
  schemaVersion: string;
  status: string;
  evaluationId: string;
  replayId: string;
  strictCutoff: string;
  featureSetVersion: string;
  source: {
    featureRunId: string;
    featureParquetSha256: string;
    targetRunId: string;
    targetParquetSha256: string;
    pointInTimeSourceAvailabilityVerified: boolean;
  };
  configuration: {
    core_features: string[];
    tickers: DriftTicker[];
    windows: { sizes: DriftWindowSize[]; primary: DriftWindowSize };
    splits: { train: [string, string]; validation: [string, string]; test: [string, string] };
  };
  coverage: { testMetricRows: number; testHistogramRows: number; validationCalibrationRows: number };
  files: Record<string, { path: string; bytes: number; rows: number | null; sha256: string }>;
}

export interface FeatureDriftIdentity {
  evaluationId: string;
  replayId: string;
  strictCutoff: string;
}

export type FeatureDriftState =
  | { status: "loading" }
  | { status: "missing"; message: string; localSummary?: LocalFeatureDriftSummary }
  | { status: "error"; message: string }
  | {
      status: "ready";
      manifest: FeatureDriftManifest;
      metrics: FeatureDriftMetric[];
      histogramsByScope: Map<string, FeatureDriftHistogramBin[]>;
      referenceSummary: FeatureDriftReferenceSummary[];
      calibrations: FeatureDriftCalibration[];
    };

export interface LocalFeatureDriftSummary {
  sourceRunIds: string[]; sourceSha256: string; referenceStart: string; referenceEnd: string;
  rows: { ticker: string; feature: string; w1: number; psi: number; date: string; windowStart: string }[];
}

export class FeatureDriftLoadError extends Error {
  constructor(message: string, readonly kind: "missing" | "integrity" | "network") {
    super(message);
    this.name = "FeatureDriftLoadError";
  }
}

const DATA_FILES = [
  "feature_drift_metrics.csv",
  "feature_drift_histograms.csv",
  "feature_drift_reference_summary.csv",
  "feature_drift_calibration.csv",
] as const;
const MANIFEST_FILE = "feature_drift_manifest.json";
const CHECKSUM_FILE = "CHECKSUMS.sha256";
const ALL_DATA_FILES = [...DATA_FILES, "feature_drift_summary.md"] as const;
const PINNED_TICKERS: DriftTicker[] = ["SPY", "IEF", "GLD"];
const PINNED_FEATURES = ["ret_1d_t", "ret_lag_1d", "ret_lag_2d", "ret_trailing_5d", "ret_trailing_20d", "rv_5d", "rv_20d", "rv_60d"];
const allowedStatuses = new Set<DriftStatus>(["DRIFT_SIGNAL", "NO_SIGNAL", "INSUFFICIENT_DATA", "UNCOMPUTABLE_SCALE", "CALIBRATION_LIMITATION"]);

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new FeatureDriftLoadError(`${label} must be an object.`, "integrity");
  return value as Record<string, unknown>;
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) throw new FeatureDriftLoadError(`${label} is invalid.`, "integrity");
  return value;
}

function requireInteger(value: unknown, label: string): number {
  if (!Number.isInteger(value) || Number(value) < 0) throw new FeatureDriftLoadError(`${label} is invalid.`, "integrity");
  return Number(value);
}

function requireDate(value: string, label: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || Number.isNaN(Date.parse(`${value}T00:00:00Z`)) || new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) !== value) throw new FeatureDriftLoadError(`${label} is not an ISO date.`, "integrity");
  return value;
}

async function validateManifest(value: unknown, expected: FeatureDriftIdentity): Promise<FeatureDriftManifest> {
  const manifest = requireRecord(value, "Feature Drift manifest");
  const source = requireRecord(manifest.source, "Feature Drift source identity");
  const config = requireRecord(manifest.configuration, "Feature Drift configuration");
  const windows = requireRecord(config.windows, "Feature Drift window configuration");
  const splits = requireRecord(config.splits, "Feature Drift split configuration");
  const coverage = requireRecord(manifest.coverage, "Feature Drift coverage");
  const files = requireRecord(manifest.files, "Feature Drift file manifest");
  if (manifest.schemaVersion !== "1.0.0" || manifest.status !== "COMPLETED") throw new FeatureDriftLoadError("Feature Drift schema is unsupported or the diagnostic is incomplete.", "integrity");
  for (const [key, value] of Object.entries({ evaluationId: expected.evaluationId, replayId: expected.replayId, strictCutoff: expected.strictCutoff })) {
    if (manifest[key] !== value) throw new FeatureDriftLoadError(`Feature Drift ${key} does not match the frozen Stage 06 snapshot.`, "integrity");
  }
  const diagnosticId = requireString(manifest.diagnosticId, "Feature Drift diagnostic ID");
  if (!/^[a-f0-9]{64}$/.test(diagnosticId)) throw new FeatureDriftLoadError("Feature Drift diagnostic ID is malformed.", "integrity");
  const canonical = requireString(manifest.diagnosticIdentityCanonical, "Feature Drift canonical identity");
  if (await sha256(new TextEncoder().encode(canonical)) !== diagnosticId) throw new FeatureDriftLoadError("Feature Drift diagnostic ID does not match its canonical identity.", "integrity");
  const canonicalIdentity = requireRecord(JSON.parse(canonical), "Feature Drift canonical identity");
  const canonicalSource = requireRecord(canonicalIdentity.source_identity, "Feature Drift canonical source identity");
  if (canonicalSource.evaluation_id !== expected.evaluationId || canonicalSource.replay_id !== expected.replayId || canonicalSource.strict_cutoff !== expected.strictCutoff) {
    throw new FeatureDriftLoadError("Feature Drift canonical identity does not match the frozen Stage 06 snapshot.", "integrity");
  }
  const tickerValues = config.tickers;
  const featureValues = config.core_features;
  const windowValues = windows.sizes;
  if (!Array.isArray(tickerValues) || tickerValues.length !== PINNED_TICKERS.length || tickerValues.some((item, index) => item !== PINNED_TICKERS[index])) {
    throw new FeatureDriftLoadError("Feature Drift ticker scope is not the pinned ETF set.", "integrity");
  }
  if (!Array.isArray(featureValues) || featureValues.length !== PINNED_FEATURES.length || featureValues.some((item, index) => item !== PINNED_FEATURES[index])) {
    throw new FeatureDriftLoadError("Feature Drift feature scope is not the pinned Core 8 set.", "integrity");
  }
  if (!Array.isArray(windowValues) || windowValues.length !== 2 || windowValues[0] !== 60 || windowValues[1] !== 120 || windows.primary !== 60) {
    throw new FeatureDriftLoadError("Feature Drift windows do not match the 60/120-session contract.", "integrity");
  }
  const sourceFeatureRunId = requireString(source.featureRunId, "Feature Drift feature run ID");
  const featureParquetSha256 = requireString(source.featureParquetSha256, "Feature Drift feature source SHA-256");
  if (!/^[a-f0-9]{64}$/.test(featureParquetSha256)) throw new FeatureDriftLoadError("Feature Drift feature source SHA-256 is malformed.", "integrity");
  const sourceTargetRunId = requireString(source.targetRunId, "Feature Drift target run ID");
  const targetParquetSha256 = requireString(source.targetParquetSha256, "Feature Drift target source SHA-256");
  if (!/^[a-f0-9]{64}$/.test(targetParquetSha256)) throw new FeatureDriftLoadError("Feature Drift target source SHA-256 is malformed.", "integrity");
  const featureSetVersion = requireString(manifest.featureSetVersion, "Feature Drift feature set version");
  if (featureSetVersion !== "2.0.0" || config.feature_set_version !== featureSetVersion || config.evaluation_id !== expected.evaluationId || config.replay_id !== expected.replayId || config.strict_cutoff !== expected.strictCutoff) {
    throw new FeatureDriftLoadError("Feature Drift configuration does not match the frozen source contract.", "integrity");
  }
  if (canonicalSource.feature_run_id !== sourceFeatureRunId || canonicalSource.target_run_id !== sourceTargetRunId
    || canonicalSource.feature_set_version !== featureSetVersion || canonicalSource.feature_parquet_sha256 !== featureParquetSha256
    || canonicalSource.target_parquet_sha256 !== targetParquetSha256) {
    throw new FeatureDriftLoadError("Feature Drift canonical source identity does not match its manifest.", "integrity");
  }
  if (typeof source.pointInTimeSourceAvailabilityVerified !== "boolean") throw new FeatureDriftLoadError("Feature Drift point-in-time availability status is invalid.", "integrity");
  const splitRange = (value: unknown, label: string): [string, string] => {
    if (!Array.isArray(value) || value.length !== 2 || value.some((item) => typeof item !== "string")) throw new FeatureDriftLoadError(`${label} range is invalid.`, "integrity");
    const start = requireDate(value[0], `${label} start`);
    const end = requireDate(value[1], `${label} end`);
    if (start > end) throw new FeatureDriftLoadError(`${label} range is reversed.`, "integrity");
    return [start, end];
  };
  const train = splitRange(splits.train, "Train");
  const validation = splitRange(splits.validation, "Validation");
  const test = splitRange(splits.test, "Test");
  if (test[1] !== expected.strictCutoff) throw new FeatureDriftLoadError("Feature Drift Test range does not end at the pinned cutoff.", "integrity");
  const typedFiles: FeatureDriftManifest["files"] = {};
  for (const name of ALL_DATA_FILES) {
    const item = requireRecord(files[name], `Feature Drift file entry ${name}`);
    if (item.path !== name || !/^[a-f0-9]{64}$/.test(String(item.sha256))) throw new FeatureDriftLoadError(`Feature Drift file entry ${name} is invalid.`, "integrity");
    typedFiles[name] = {
      path: name,
      bytes: requireInteger(item.bytes, `${name} byte count`),
      rows: item.rows === null ? null : requireInteger(item.rows, `${name} row count`),
      sha256: String(item.sha256),
    };
  }
  if (Object.keys(files).length !== ALL_DATA_FILES.length) throw new FeatureDriftLoadError("Feature Drift manifest contains an unexpected file entry.", "integrity");
  if (DATA_FILES.some((name) => typedFiles[name]?.rows === null || typedFiles[name]?.rows === undefined)) throw new FeatureDriftLoadError("Feature Drift CSV row counts are missing from the manifest.", "integrity");
  const typedCoverage = {
    testMetricRows: requireInteger(coverage.testMetricRows, "Test metric row count"),
    testHistogramRows: requireInteger(coverage.testHistogramRows, "Test histogram row count"),
    validationCalibrationRows: requireInteger(coverage.validationCalibrationRows, "Validation calibration row count"),
  };
  return {
    diagnosticId,
    schemaVersion: "1.0.0",
    status: "COMPLETED",
    evaluationId: expected.evaluationId,
    replayId: expected.replayId,
    strictCutoff: expected.strictCutoff,
    featureSetVersion,
    source: {
      featureRunId: sourceFeatureRunId,
      featureParquetSha256,
      targetRunId: sourceTargetRunId,
      targetParquetSha256,
      pointInTimeSourceAvailabilityVerified: source.pointInTimeSourceAvailabilityVerified,
    },
    configuration: {
      core_features: featureValues as string[],
      tickers: tickerValues as DriftTicker[],
      windows: { sizes: windowValues as DriftWindowSize[], primary: 60 },
      splits: { train, validation, test },
    },
    coverage: typedCoverage,
    files: typedFiles,
  };
}

function parseChecksums(text: string, manifest: FeatureDriftManifest): Map<string, string> {
  const checksums = new Map<string, string>();
  for (const line of text.trimEnd().split(/\r?\n/)) {
    const match = /^([a-f0-9]{64})  ([A-Za-z0-9_.-]+)$/.exec(line);
    if (!match || checksums.has(match[2]!)) throw new FeatureDriftLoadError("Feature Drift checksum list is invalid.", "integrity");
    checksums.set(match[2]!, match[1]!);
  }
  const expectedNames = [...ALL_DATA_FILES, MANIFEST_FILE].sort();
  if (checksums.size !== expectedNames.length || expectedNames.some((name) => !checksums.has(name))) {
    throw new FeatureDriftLoadError("Feature Drift checksum list differs from the published package allowlist.", "integrity");
  }
  for (const name of ALL_DATA_FILES) {
    if (checksums.get(name) !== manifest.files[name]!.sha256) throw new FeatureDriftLoadError(`Feature Drift ${name} checksum differs from its manifest entry.`, "integrity");
  }
  return checksums;
}

function finite(record: Record<string, string>, key: string, label: string): number {
  const value = Number(record[key]);
  if (record[key] === "" || !Number.isFinite(value)) throw new FeatureDriftLoadError(`${label} has an invalid ${key}.`, "integrity");
  return value;
}

function nullableFinite(record: Record<string, string>, key: string, label: string): number | null {
  return record[key] === "" ? null : finite(record, key, label);
}

function integer(record: Record<string, string>, key: string, label: string): number {
  const value = finite(record, key, label);
  if (!Number.isInteger(value) || value < 0) throw new FeatureDriftLoadError(`${label} has an invalid ${key}.`, "integrity");
  return value;
}

function sameNullableNumber(left: number | null, right: number | null): boolean {
  return left === right || (left !== null && right !== null && Math.abs(left - right) <= 1e-12);
}

function ticker(value: string, label: string): DriftTicker {
  if (value !== "SPY" && value !== "IEF" && value !== "GLD") throw new FeatureDriftLoadError(`${label} has an unsupported ticker.`, "integrity");
  return value;
}

function windowSize(record: Record<string, string>, label: string): DriftWindowSize {
  const value = integer(record, "window_size", label);
  if (value !== 60 && value !== 120) throw new FeatureDriftLoadError(`${label} has an unsupported window size.`, "integrity");
  return value;
}

export function featureDriftScopeKey(date: string, symbol: DriftTicker, feature: string, window: DriftWindowSize): string {
  return `${date}|${symbol}|${feature}|${window}`;
}

function parseMetricRows(text: string, manifest: FeatureDriftManifest): FeatureDriftMetric[] {
  const table = parseCsv(text);
  assertExactHeaders(table.headers, FEATURE_DRIFT_METRIC_HEADERS, DATA_FILES[0]);
  const rows: FeatureDriftMetric[] = [];
  const seen = new Set<string>();
  const tickers = new Set(manifest.configuration.tickers);
  const features = new Set(manifest.configuration.core_features);
  for (const [index, record] of table.records.entries()) {
    const label = `Feature Drift metric row ${index + 2}`;
    const status = record.status as DriftStatus;
    if (!allowedStatuses.has(status)) throw new FeatureDriftLoadError(`${label} has an unsupported status.`, "integrity");
    const rowTicker = ticker(record.ticker!, label);
    const rowFeature = record.feature_name!;
    const rowWindow = windowSize(record, label);
    const asOfDate = requireDate(record.as_of_date!, `${label} as-of date`);
    if (record.diagnostic_id !== manifest.diagnosticId || record.evaluation_id !== manifest.evaluationId || record.replay_id !== manifest.replayId
      || record.source_feature_run_id !== manifest.source.featureRunId || record.feature_set_version !== manifest.featureSetVersion || record.split !== "test") {
      throw new FeatureDriftLoadError(`${label} does not match the Feature Drift manifest identity.`, "integrity");
    }
    if (!tickers.has(rowTicker) || !features.has(rowFeature) || !manifest.configuration.windows.sizes.includes(rowWindow)) throw new FeatureDriftLoadError(`${label} is outside the pinned diagnostic scope.`, "integrity");
    if (asOfDate > manifest.strictCutoff || asOfDate < manifest.configuration.splits.test[0] || record.current_end !== asOfDate) throw new FeatureDriftLoadError(`${label} is outside the Test cutoff or window end.`, "integrity");
    const key = featureDriftScopeKey(asOfDate, rowTicker, rowFeature, rowWindow);
    if (seen.has(key)) throw new FeatureDriftLoadError(`${label} duplicates an existing metric scope.`, "integrity");
    seen.add(key);
    rows.push({
      diagnosticId: manifest.diagnosticId,
      evaluationId: manifest.evaluationId,
      replayId: manifest.replayId,
      sourceFeatureRunId: manifest.source.featureRunId,
      featureSetVersion: manifest.featureSetVersion,
      asOfDate,
      ticker: rowTicker,
      featureName: rowFeature,
      referenceStart: requireDate(record.reference_start!, `${label} reference start`),
      referenceEnd: requireDate(record.reference_end!, `${label} reference end`),
      referenceN: integer(record, "reference_n", label),
      currentStart: requireDate(record.current_start!, `${label} window start`),
      currentEnd: requireDate(record.current_end!, `${label} window end`),
      currentN: integer(record, "current_n", label),
      windowSize: rowWindow,
      wassersteinRaw: nullableFinite(record, "wasserstein_raw", label),
      trainIqr: finite(record, "train_iqr", label),
      wassersteinNormalized: nullableFinite(record, "wasserstein_normalized", label),
      psi: nullableFinite(record, "psi", label),
      medianReference: nullableFinite(record, "median_ref", label),
      medianCurrent: nullableFinite(record, "median_current", label),
      p95Reference: nullableFinite(record, "p95_ref", label),
      p95Current: nullableFinite(record, "p95_current", label),
      outOfTrainRangeRate: nullableFinite(record, "out_of_train_range_rate", label),
      wassersteinThreshold: nullableFinite(record, "wasserstein_threshold", label),
      psiThreshold: nullableFinite(record, "psi_threshold", label),
      status,
      statusReason: record.status_reason!,
    });
    const parsed = rows[rows.length - 1]!;
    if (status === "DRIFT_SIGNAL" && (parsed.wassersteinNormalized === null || parsed.wassersteinThreshold === null || parsed.wassersteinNormalized <= parsed.wassersteinThreshold)) {
      throw new FeatureDriftLoadError(`${label} reports a W1 signal that does not exceed its Validation threshold.`, "integrity");
    }
    if (status === "NO_SIGNAL" && (parsed.wassersteinNormalized === null || parsed.wassersteinThreshold === null || parsed.wassersteinNormalized > parsed.wassersteinThreshold)) {
      throw new FeatureDriftLoadError(`${label} reports no signal without a W1 value at or below its Validation threshold.`, "integrity");
    }
  }
  if (rows.length !== manifest.coverage.testMetricRows) throw new FeatureDriftLoadError("Feature Drift metric row count does not match the manifest.", "integrity");
  if (rows.length !== manifest.files[DATA_FILES[0]]!.rows) throw new FeatureDriftLoadError("Feature Drift metric file count does not match the manifest.", "integrity");
  return rows;
}

function parseReferenceRows(text: string, manifest: FeatureDriftManifest): FeatureDriftReferenceSummary[] {
  const table = parseCsv(text);
  assertExactHeaders(table.headers, FEATURE_DRIFT_REFERENCE_HEADERS, DATA_FILES[2]);
  const rows: FeatureDriftReferenceSummary[] = [];
  const seen = new Set<string>();
  for (const [index, record] of table.records.entries()) {
    const label = `Feature Drift reference row ${index + 2}`;
    const rowTicker = ticker(record.ticker!, label);
    const rowFeature = record.feature_name!;
    const values = ["q01", "q05", "q25", "median", "q75", "q95", "q99"].map((key) => finite(record, key, label));
    if (!manifest.configuration.core_features.includes(rowFeature) || record.diagnostic_id !== manifest.diagnosticId) throw new FeatureDriftLoadError(`${label} is outside the pinned reference scope.`, "integrity");
    if (values.some((value, position) => position > 0 && value < values[position - 1]!)) throw new FeatureDriftLoadError(`${label} quantiles are not monotonic.`, "integrity");
    const key = `${rowTicker}|${rowFeature}`;
    if (seen.has(key)) throw new FeatureDriftLoadError(`${label} duplicates an existing reference.`, "integrity");
    seen.add(key);
    rows.push({
      ticker: rowTicker,
      featureName: rowFeature,
      referenceStart: requireDate(record.reference_start!, `${label} start`),
      referenceEnd: requireDate(record.reference_end!, `${label} end`),
      referenceN: integer(record, "reference_n", label),
      q01: values[0]!, q05: values[1]!, q25: values[2]!, median: values[3]!, q75: values[4]!, q95: values[5]!, q99: values[6]!,
      trainIqr: finite(record, "train_iqr", label),
      effectiveBinCount: integer(record, "effective_bin_count", label),
      binDefinitionId: requireString(record.bin_definition_id, `${label} bin definition ID`),
      referenceHash: requireString(record.reference_hash, `${label} reference hash`),
      binStatus: requireString(record.bin_status, `${label} bin status`),
    });
  }
  if (rows.length !== manifest.configuration.tickers.length * manifest.configuration.core_features.length) throw new FeatureDriftLoadError("Feature Drift reference row count does not match the pinned scope.", "integrity");
  if (rows.length !== manifest.files[DATA_FILES[2]]!.rows) throw new FeatureDriftLoadError("Feature Drift reference row count does not match the manifest file entry.", "integrity");
  return rows;
}

function parseCalibrationRows(text: string, manifest: FeatureDriftManifest): FeatureDriftCalibration[] {
  const table = parseCsv(text);
  assertExactHeaders(table.headers, FEATURE_DRIFT_CALIBRATION_HEADERS, DATA_FILES[3]);
  const rows: FeatureDriftCalibration[] = [];
  const seen = new Set<string>();
  for (const [index, record] of table.records.entries()) {
    const label = `Feature Drift calibration row ${index + 2}`;
    const rowTicker = ticker(record.ticker!, label);
    const rowFeature = record.feature_name!;
    const rowWindow = windowSize(record, label);
    if (!manifest.configuration.core_features.includes(rowFeature) || !manifest.configuration.windows.sizes.includes(rowWindow) || record.diagnostic_id !== manifest.diagnosticId) {
      throw new FeatureDriftLoadError(`${label} is outside the pinned calibration scope.`, "integrity");
    }
    const key = `${rowTicker}|${rowFeature}|${rowWindow}`;
    if (seen.has(key)) throw new FeatureDriftLoadError(`${label} duplicates an existing calibration row.`, "integrity");
    seen.add(key);
    const calibrationStart = requireDate(record.calibration_start!, `${label} start`);
    const calibrationEnd = requireDate(record.calibration_end!, `${label} end`);
    const validWindowCount = integer(record, "valid_window_count", label);
    const thresholdPercentile = finite(record, "threshold_percentile", label);
    const thresholdMethod = requireString(record.threshold_method, `${label} method`);
    const wassersteinThreshold = nullableFinite(record, "wasserstein_threshold", label);
    const psiThreshold = nullableFinite(record, "psi_threshold", label);
    const calibrationStatus = requireString(record.calibration_status, `${label} status`);
    if (calibrationStart !== manifest.configuration.splits.validation[0] || calibrationEnd !== manifest.configuration.splits.validation[1]
      || thresholdPercentile !== 95 || thresholdMethod !== "empirical_linear_quantile_validation_only") {
      throw new FeatureDriftLoadError(`${label} does not match Validation-only calibration settings.`, "integrity");
    }
    if (!["CALIBRATED", "UNCOMPUTABLE_SCALE", "CALIBRATION_LIMITATION", "W1_CALIBRATED_PSI_UNAVAILABLE"].includes(calibrationStatus)) {
      throw new FeatureDriftLoadError(`${label} has an unsupported calibration status.`, "integrity");
    }
    if (calibrationStatus === "CALIBRATED" && (validWindowCount < 100 || wassersteinThreshold === null || psiThreshold === null)) {
      throw new FeatureDriftLoadError(`${label} is marked calibrated without enough windows and both thresholds.`, "integrity");
    }
    rows.push({
      ticker: rowTicker,
      featureName: rowFeature,
      windowSize: rowWindow,
      calibrationStart,
      calibrationEnd,
      validWindowCount,
      thresholdPercentile,
      thresholdMethod,
      wassersteinThreshold,
      psiThreshold,
      calibrationStatus,
    });
  }
  if (rows.length !== manifest.coverage.validationCalibrationRows) throw new FeatureDriftLoadError("Feature Drift calibration row count does not match the manifest.", "integrity");
  if (rows.length !== manifest.files[DATA_FILES[3]]!.rows) throw new FeatureDriftLoadError("Feature Drift calibration row count does not match the manifest file entry.", "integrity");
  return rows;
}

function parseHistogramRows(text: string, manifest: FeatureDriftManifest, metrics: FeatureDriftMetric[], references: FeatureDriftReferenceSummary[]): Map<string, FeatureDriftHistogramBin[]> {
  const table = parseCsv(text);
  assertExactHeaders(table.headers, FEATURE_DRIFT_HISTOGRAM_HEADERS, DATA_FILES[1]);
  if (table.records.length !== manifest.coverage.testHistogramRows) throw new FeatureDriftLoadError("Feature Drift histogram row count does not match the manifest.", "integrity");
  if (table.records.length !== manifest.files[DATA_FILES[1]]!.rows) throw new FeatureDriftLoadError("Feature Drift histogram row count does not match the manifest file entry.", "integrity");
  const metricByKey = new Map(metrics.map((row) => [featureDriftScopeKey(row.asOfDate, row.ticker, row.featureName, row.windowSize), row]));
  const definitionByReference = new Map(references.map((row) => [`${row.ticker}|${row.featureName}`, row.binDefinitionId]));
  const groups = new Map<string, FeatureDriftHistogramBin[]>();
  for (const [index, record] of table.records.entries()) {
    const label = `Feature Drift histogram row ${index + 2}`;
    const rowTicker = ticker(record.ticker!, label);
    const rowFeature = record.feature_name!;
    const asOfDate = requireDate(record.as_of_date!, `${label} as-of date`);
    const rowWindow = windowSize(record, label);
    const key = featureDriftScopeKey(asOfDate, rowTicker, rowFeature, rowWindow);
    const metric = metricByKey.get(key);
    const binDefinitionId = requireString(record.bin_definition_id, `${label} bin definition ID`);
    if (!metric || record.diagnostic_id !== manifest.diagnosticId || !manifest.configuration.core_features.includes(rowFeature)
      || asOfDate > manifest.strictCutoff || definitionByReference.get(`${rowTicker}|${rowFeature}`) !== binDefinitionId) {
      throw new FeatureDriftLoadError(`${label} does not reconcile to a metric/reference row.`, "integrity");
    }
    const binIndex = integer(record, "bin_index", label);
    const effectiveBinCount = integer(record, "effective_bin_count", label);
    const edge = (value: string): number => value === "-inf" ? Number.NEGATIVE_INFINITY : value === "+inf" ? Number.POSITIVE_INFINITY : Number(value);
    const lowerEdge = edge(record.lower_edge!);
    const upperEdge = edge(record.upper_edge!);
    const referencePct = finite(record, "reference_pct", label);
    const currentPct = finite(record, "current_pct", label);
    if (Number.isNaN(lowerEdge) || Number.isNaN(upperEdge) || lowerEdge >= upperEdge || referencePct < 0 || currentPct < 0 || effectiveBinCount < 1 || binIndex >= effectiveBinCount) {
      throw new FeatureDriftLoadError(`${label} has invalid bin edges or proportions.`, "integrity");
    }
    const bins = groups.get(key) ?? [];
    if (bins[binIndex]) throw new FeatureDriftLoadError(`${label} duplicates a histogram bin.`, "integrity");
    bins[binIndex] = {
      index: binIndex,
      lowerEdge,
      upperEdge,
      referenceCount: integer(record, "reference_count", label),
      currentCount: integer(record, "current_count", label),
      referencePct,
      currentPct,
      binDefinitionId,
      effectiveBinCount,
    };
    groups.set(key, bins);
  }
  for (const [key, bins] of groups) {
    const metric = metricByKey.get(key)!;
    if (bins.length !== bins[0]!.effectiveBinCount || bins.some((bin, index) => !bin || bin.index !== index || bin.effectiveBinCount !== bins.length)) {
      throw new FeatureDriftLoadError("Feature Drift histogram bins are incomplete or unordered.", "integrity");
    }
    const referenceCount = bins.reduce((sum, bin) => sum + bin.referenceCount, 0);
    const currentCount = bins.reduce((sum, bin) => sum + bin.currentCount, 0);
    const referencePct = bins.reduce((sum, bin) => sum + bin.referencePct, 0);
    const currentPct = bins.reduce((sum, bin) => sum + bin.currentPct, 0);
    if (referenceCount !== metric.referenceN || currentCount !== metric.currentN || Math.abs(referencePct - 1) > 1e-6 || Math.abs(currentPct - 1) > 1e-6) {
      throw new FeatureDriftLoadError("Feature Drift histogram totals do not reconcile to their metric row.", "integrity");
    }
  }
  for (const [key, metric] of metricByKey) {
    if ((metric.status === "DRIFT_SIGNAL" || metric.status === "NO_SIGNAL") && !groups.has(key)) throw new FeatureDriftLoadError("A computable Feature Drift metric is missing its histogram.", "integrity");
  }
  return groups;
}

export async function loadFeatureDrift(
  expected: FeatureDriftIdentity,
  fetcher: typeof fetch = fetch,
  baseHref: string = typeof document === "undefined" ? "http://localhost/" : document.baseURI,
): Promise<FeatureDriftState> {
  const assetUrl = (relative: string) => new URL(relative, baseHref).toString();
  let manifestResponse: Response;
  try {
    manifestResponse = await fetcher(assetUrl(`feature-drift/current/${MANIFEST_FILE}`));
  } catch {
    return { status: "missing", message: "ยังไม่มีผลตรวจ Feature Drift ใน build นี้" };
  }
  if (manifestResponse.status === 404) {
    try {
      const response = await fetcher(assetUrl("feature-drift/local-summary.json"));
      if (response.ok) {
        const summary = await response.json() as LocalFeatureDriftSummary;
        if (Array.isArray(summary.rows) && summary.rows.length && Array.isArray(summary.sourceRunIds)) {
          return { status: "missing", message: "ผลตรวจจากฟีเจอร์ในเครื่อง", localSummary: summary };
        }
      }
    } catch { /* The optional local summary is unavailable. */ }
    return { status: "missing", message: "ยังไม่มีผลตรวจ Feature Drift ที่ตรวจสอบกับ Stage 06 ชุดนี้" };
  }
  if (!manifestResponse.ok) return { status: "error", message: `โหลด Feature Drift manifest ไม่สำเร็จ (HTTP ${manifestResponse.status})` };
  try {
    const manifestBytes = new Uint8Array(await manifestResponse.arrayBuffer());
    let manifestJson: unknown;
    try {
      manifestJson = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(manifestBytes));
    } catch {
      throw new FeatureDriftLoadError("Feature Drift manifest is not valid UTF-8 JSON.", "integrity");
    }
    const manifest = await validateManifest(manifestJson, expected);
    const names = [...DATA_FILES, CHECKSUM_FILE] as const;
    const responses = await Promise.all(names.map((name) => fetcher(assetUrl(`feature-drift/current/${name}`))));
    if (responses.some((response) => response.status === 404)) throw new FeatureDriftLoadError("A required Feature Drift sidecar file is missing.", "missing");
    if (responses.some((response) => !response.ok)) throw new FeatureDriftLoadError("A Feature Drift sidecar file could not be loaded.", "network");
    const bytes = await Promise.all(responses.map((response) => response.arrayBuffer().then((buffer) => new Uint8Array(buffer))));
    const checksums = parseChecksums(new TextDecoder("utf-8", { fatal: true }).decode(bytes[4]!), manifest);
    const payloadByName = new Map<string, Uint8Array>([[MANIFEST_FILE, manifestBytes], ...DATA_FILES.map((name, index) => [name, bytes[index]!] as [string, Uint8Array])]);
    for (const [name, payload] of payloadByName) {
      const expectedHash = name === MANIFEST_FILE ? checksums.get(MANIFEST_FILE) : checksums.get(name);
      if (!expectedHash || await sha256(payload) !== expectedHash) throw new FeatureDriftLoadError(`Feature Drift SHA-256 mismatch for ${name}.`, "integrity");
      if (name !== MANIFEST_FILE && payload.byteLength !== manifest.files[name]!.bytes) throw new FeatureDriftLoadError(`Feature Drift byte count does not match for ${name}.`, "integrity");
    }
    const decoder = new TextDecoder("utf-8", { fatal: true });
    const content = new Map(DATA_FILES.map((name, index) => [name, decoder.decode(bytes[index]!)]));
    const metrics = parseMetricRows(content.get(DATA_FILES[0])!, manifest);
    const references = parseReferenceRows(content.get(DATA_FILES[2])!, manifest);
    const calibrations = parseCalibrationRows(content.get(DATA_FILES[3])!, manifest);
    const histogramsByScope = parseHistogramRows(content.get(DATA_FILES[1])!, manifest, metrics, references);
    const calibrationByKey = new Map(calibrations.map((row) => [`${row.ticker}|${row.featureName}|${row.windowSize}`, row]));
    for (const row of metrics) {
      const calibration = calibrationByKey.get(`${row.ticker}|${row.featureName}|${row.windowSize}`);
      if (!calibration || !sameNullableNumber(calibration.wassersteinThreshold, row.wassersteinThreshold) || !sameNullableNumber(calibration.psiThreshold, row.psiThreshold)) {
        throw new FeatureDriftLoadError("Feature Drift metric thresholds do not match Validation calibration.", "integrity");
      }
    }
    return { status: "ready", manifest, metrics, histogramsByScope, referenceSummary: references, calibrations };
  } catch (error) {
    if (error instanceof FeatureDriftLoadError && error.kind === "missing") return { status: "missing", message: error.message };
    return { status: "error", message: error instanceof Error ? error.message : "Feature Drift schema validation failed." };
  }
}
