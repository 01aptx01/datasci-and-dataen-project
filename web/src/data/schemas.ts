export interface SnapshotPolicy {
  source: {
    repository: string;
    handoffCommit: string;
    mainCommitAtStart: string;
    zipName: string;
    zipSha256: string;
  };
  identity: {
    evaluationId: string;
    replayId: string;
    baselineGitCommit: string;
    strictCutoff: string;
    reportApproval: "PENDING";
  };
  members: {
    sourceIdentity: string;
    executionManifest: string;
    stage05Manifest: string;
    forecastAudit: string;
    evaluation: string;
  };
  memberSha256: Record<string, string>;
  expectedHeaders: { forecastAudit: string[]; evaluation: string[] };
  expectedCounts: {
    forecastAuditRows: number;
    evaluationRows: number;
    testForecastRows: number;
    testEvaluableRows: number;
    testPendingRows: number;
  };
  publicOutputs: { forecastAudit: string; evaluation: string };
}

export interface SnapshotFileArtifact {
  path: string;
  sha256: string;
  bytes: number;
  rowCount: number;
  headers: string[];
}

export interface SnapshotManifest {
  schemaVersion: "1.0.0";
  sourceRepository: string;
  sourceHandoffCommit: string;
  sourceMainCommitAtStart: string;
  sourceZipName: string;
  sourceZipSha256: string;
  evaluationId: string;
  replayId: string;
  baselineGitCommit: string;
  sourceVerificationStatus: "SOURCE VERIFIED";
  stage05Status: "COMPLETED";
  stage06Status: "COMPLETED";
  reportApproval: "PENDING";
  mode: "SIMULATED HISTORICAL REPLAY";
  pointInTimeSourceAvailabilityVerified: false;
  strictCutoff: string;
  createdAtUtc: string;
  builtFromCommit: string;
  expectedCounts: SnapshotPolicy["expectedCounts"] & { recordedTestDates: number };
  files: { forecastAudit: SnapshotFileArtifact; evaluation: SnapshotFileArtifact };
}

export type ModelName = "CONSTANT_BASELINE" | "ROLLING_20D_BASELINE" | "STATIC_SGD" | "ONLINE_SGD";
export type Ticker = "SPY" | "IEF" | "GLD";

export interface ForecastAuditRow {
  predictionDate: string;
  ticker: Ticker;
  split: "test" | "validation";
  modelName: ModelName;
  isLabelMature: boolean;
  targetStartDate: string;
  targetEndDate: string;
  predictionId: string;
  targetStartDatePrediction: string;
  targetEndDatePrediction: string;
  predictedVolAnnualized: number | null;
  targetRealizedVol5d: number | null;
  absoluteError: number | null;
  labelStatus: "MATURE" | "PENDING";
  forecastStatus: "VALID" | "INVALID" | "MISSING";
  evaluationStatus: "EVALUABLE" | "PENDING_LABEL" | "INVALID_FORECAST" | "MISSING_FORECAST";
}

export interface EvaluationRow {
  experimentId: string;
  predictionId: string;
  predictionDate: string;
  split: "test";
  ticker: Ticker;
  modelName: ModelName;
  targetStartDate: string;
  targetEndDate: string;
  predictedVolAnnualized: number;
  targetRealizedVol5d: number;
  absoluteError: number;
}

export interface RecordedSession {
  audit: ForecastAuditRow;
  evaluation?: EvaluationRow;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) throw new Error(`${key} must be a nonempty string`);
  return value;
}

function numberField(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) throw new Error(`${key} must be a nonnegative integer`);
  return value;
}

function hashField(record: Record<string, unknown>, key: string): string {
  const value = stringField(record, key);
  if (!/^[a-f0-9]{64}$/i.test(value)) throw new Error(`${key} must be a SHA-256 hex digest`);
  return value.toLowerCase();
}

function stringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || item.length === 0)) throw new Error(`${label} must be an array of nonempty strings`);
  return value as string[];
}

export function parsePolicy(value: unknown): SnapshotPolicy {
  if (!isRecord(value) || !isRecord(value.source) || !isRecord(value.identity) || !isRecord(value.members) || !isRecord(value.memberSha256) || !isRecord(value.expectedHeaders) || !isRecord(value.expectedCounts) || !isRecord(value.publicOutputs)) {
    throw new Error("Snapshot policy has an invalid object structure");
  }
  const source = value.source;
  const identity = value.identity;
  const members = value.members;
  const counts = value.expectedCounts;
  if (identity.reportApproval !== "PENDING") throw new Error("reportApproval must remain PENDING");
  const expectedHeaders = value.expectedHeaders;
  const hashEntries = Object.fromEntries(Object.entries(value.memberSha256).map(([name, hash]) => {
    if (typeof hash !== "string" || !/^[a-f0-9]{64}$/i.test(hash)) throw new Error(`Invalid source member hash for ${name}`);
    return [name, hash.toLowerCase()];
  }));
  return {
    source: {
      repository: stringField(source, "repository"),
      handoffCommit: stringField(source, "handoffCommit"),
      mainCommitAtStart: stringField(source, "mainCommitAtStart"),
      zipName: stringField(source, "zipName"),
      zipSha256: hashField(source, "zipSha256"),
    },
    identity: {
      evaluationId: stringField(identity, "evaluationId"),
      replayId: stringField(identity, "replayId"),
      baselineGitCommit: stringField(identity, "baselineGitCommit"),
      strictCutoff: stringField(identity, "strictCutoff"),
      reportApproval: "PENDING",
    },
    members: {
      sourceIdentity: stringField(members, "sourceIdentity"),
      executionManifest: stringField(members, "executionManifest"),
      stage05Manifest: stringField(members, "stage05Manifest"),
      forecastAudit: stringField(members, "forecastAudit"),
      evaluation: stringField(members, "evaluation"),
    },
    memberSha256: hashEntries,
    expectedHeaders: {
      forecastAudit: stringArray(expectedHeaders.forecastAudit, "forecastAudit headers"),
      evaluation: stringArray(expectedHeaders.evaluation, "evaluation headers"),
    },
    expectedCounts: {
      forecastAuditRows: numberField(counts, "forecastAuditRows"),
      evaluationRows: numberField(counts, "evaluationRows"),
      testForecastRows: numberField(counts, "testForecastRows"),
      testEvaluableRows: numberField(counts, "testEvaluableRows"),
      testPendingRows: numberField(counts, "testPendingRows"),
    },
    publicOutputs: {
      forecastAudit: stringField(value.publicOutputs, "forecastAudit"),
      evaluation: stringField(value.publicOutputs, "evaluation"),
    },
  };
}

function parseArtifact(value: unknown, label: string): SnapshotFileArtifact {
  if (!isRecord(value)) throw new Error(`${label} file metadata is missing`);
  const headers = stringArray(value.headers, `${label} headers`);
  return {
    path: stringField(value, "path"),
    sha256: hashField(value, "sha256"),
    bytes: numberField(value, "bytes"),
    rowCount: numberField(value, "rowCount"),
    headers,
  };
}

export function parseSnapshotManifest(value: unknown, policy: SnapshotPolicy): SnapshotManifest {
  if (!isRecord(value) || !isRecord(value.files) || !isRecord(value.expectedCounts)) throw new Error("Snapshot manifest has an invalid object structure");
  const manifest = value;
  const equal = (field: string, expected: string | boolean): void => {
    if (manifest[field] !== expected) throw new Error(`${field} does not match the pinned handoff policy`);
  };
  equal("schemaVersion", "1.0.0");
  equal("sourceRepository", policy.source.repository);
  equal("sourceHandoffCommit", policy.source.handoffCommit);
  equal("sourceMainCommitAtStart", policy.source.mainCommitAtStart);
  equal("sourceZipName", policy.source.zipName);
  equal("sourceZipSha256", policy.source.zipSha256);
  equal("evaluationId", policy.identity.evaluationId);
  equal("replayId", policy.identity.replayId);
  equal("baselineGitCommit", policy.identity.baselineGitCommit);
  equal("sourceVerificationStatus", "SOURCE VERIFIED");
  equal("stage05Status", "COMPLETED");
  equal("stage06Status", "COMPLETED");
  equal("reportApproval", "PENDING");
  equal("mode", "SIMULATED HISTORICAL REPLAY");
  equal("pointInTimeSourceAvailabilityVerified", false);
  equal("strictCutoff", policy.identity.strictCutoff);

  const counts = manifest.expectedCounts as Record<string, unknown>;
  const expectedCounts = {
    forecastAuditRows: numberField(counts, "forecastAuditRows"),
    evaluationRows: numberField(counts, "evaluationRows"),
    testForecastRows: numberField(counts, "testForecastRows"),
    testEvaluableRows: numberField(counts, "testEvaluableRows"),
    testPendingRows: numberField(counts, "testPendingRows"),
    recordedTestDates: numberField(counts, "recordedTestDates"),
  };
  for (const key of ["forecastAuditRows", "evaluationRows", "testForecastRows", "testEvaluableRows", "testPendingRows"] as const) {
    if (expectedCounts[key] !== policy.expectedCounts[key]) throw new Error(`expectedCounts.${key} does not match the pinned handoff policy`);
  }
  const files = manifest.files as Record<string, unknown>;
  const forecastAudit = parseArtifact(files.forecastAudit, "forecastAudit");
  const evaluation = parseArtifact(files.evaluation, "evaluation");
  if (forecastAudit.path !== policy.publicOutputs.forecastAudit || evaluation.path !== policy.publicOutputs.evaluation) throw new Error("Snapshot manifest uses an unapproved output path");
  if (forecastAudit.sha256 !== policy.memberSha256[policy.members.forecastAudit] || evaluation.sha256 !== policy.memberSha256[policy.members.evaluation]) throw new Error("Snapshot manifest CSV hashes differ from the pinned source hashes");
  if (forecastAudit.rowCount !== expectedCounts.forecastAuditRows || evaluation.rowCount !== expectedCounts.evaluationRows) throw new Error("Snapshot manifest file row counts do not match the pinned source");
  if (!sameArray(forecastAudit.headers, policy.expectedHeaders.forecastAudit) || !sameArray(evaluation.headers, policy.expectedHeaders.evaluation)) throw new Error("Snapshot manifest CSV headers do not match the pinned source schema");

  return {
    schemaVersion: "1.0.0",
    sourceRepository: policy.source.repository,
    sourceHandoffCommit: policy.source.handoffCommit,
    sourceMainCommitAtStart: policy.source.mainCommitAtStart,
    sourceZipName: policy.source.zipName,
    sourceZipSha256: policy.source.zipSha256,
    evaluationId: policy.identity.evaluationId,
    replayId: policy.identity.replayId,
    baselineGitCommit: policy.identity.baselineGitCommit,
    sourceVerificationStatus: "SOURCE VERIFIED",
    stage05Status: "COMPLETED",
    stage06Status: "COMPLETED",
    reportApproval: "PENDING",
    mode: "SIMULATED HISTORICAL REPLAY",
    pointInTimeSourceAvailabilityVerified: false,
    strictCutoff: policy.identity.strictCutoff,
    createdAtUtc: stringField(manifest, "createdAtUtc"),
    builtFromCommit: stringField(manifest, "builtFromCommit"),
    expectedCounts,
    files: { forecastAudit, evaluation },
  };
}

function sameArray(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function oneOf<T extends string>(value: string, values: readonly T[], field: string): T {
  if (!(values as readonly string[]).includes(value)) throw new Error(`${field} contains unsupported value "${value}"`);
  return value as T;
}

function dateString(value: string, field: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || Number.isNaN(Date.parse(`${value}T00:00:00Z`))) throw new Error(`${field} must be a YYYY-MM-DD date`);
  return value;
}

export function parseFiniteOrNull(value: string, field: string): number | null {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`${field} must be blank or a finite nonnegative number`);
  return parsed;
}

function parseFinite(value: string, field: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`${field} must be a finite nonnegative number`);
  return parsed;
}

function parseBoolean(value: string, field: string): boolean {
  if (value === "True" || value.toLowerCase() === "true") return true;
  if (value === "False" || value.toLowerCase() === "false") return false;
  throw new Error(`${field} must be a source boolean`);
}

export function parseForecastAuditRow(record: Record<string, string>): ForecastAuditRow {
  const row: ForecastAuditRow = {
    predictionDate: dateString(record.prediction_date, "prediction_date"),
    ticker: oneOf(record.ticker, ["SPY", "IEF", "GLD"], "ticker"),
    split: oneOf(record.split, ["test", "validation"], "split"),
    modelName: oneOf(record.model_name, ["CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD"], "model_name"),
    isLabelMature: parseBoolean(record.is_label_mature, "is_label_mature"),
    targetStartDate: dateString(record.target_start_date, "target_start_date"),
    targetEndDate: dateString(record.target_end_date, "target_end_date"),
    predictionId: record.prediction_id,
    targetStartDatePrediction: dateString(record.target_start_date_prediction, "target_start_date_prediction"),
    targetEndDatePrediction: dateString(record.target_end_date_prediction, "target_end_date_prediction"),
    predictedVolAnnualized: parseFiniteOrNull(record.predicted_vol_annualized, "predicted_vol_annualized"),
    targetRealizedVol5d: parseFiniteOrNull(record.target_realized_vol_5d, "target_realized_vol_5d"),
    absoluteError: parseFiniteOrNull(record.absolute_error, "absolute_error"),
    labelStatus: oneOf(record.label_status, ["MATURE", "PENDING"], "label_status"),
    forecastStatus: oneOf(record.forecast_status, ["VALID", "INVALID", "MISSING"], "forecast_status"),
    evaluationStatus: oneOf(record.evaluation_status, ["EVALUABLE", "PENDING_LABEL", "INVALID_FORECAST", "MISSING_FORECAST"], "evaluation_status"),
  };
  if (typeof row.predictionId !== "string" || row.predictionId.length === 0) throw new Error("prediction_id must be a nonempty string");
  if (row.forecastStatus === "VALID" && row.predictedVolAnnualized === null) throw new Error("A VALID forecast must contain a finite forecast value");
  assertPendingLabelsHaveNoActual(row);
  return row;
}

export function assertPendingLabelsHaveNoActual(row: ForecastAuditRow): void {
  if (row.labelStatus === "PENDING" || row.evaluationStatus === "PENDING_LABEL") {
    if (row.targetRealizedVol5d !== null || row.absoluteError !== null) throw new Error(`Pending label ${row.predictionId} must not contain actual or error values`);
    if (row.labelStatus !== "PENDING" || row.evaluationStatus !== "PENDING_LABEL" || row.isLabelMature) throw new Error(`Pending label ${row.predictionId} has conflicting source statuses`);
  }
  if (row.evaluationStatus === "EVALUABLE" && (row.labelStatus !== "MATURE" || !row.isLabelMature || row.targetRealizedVol5d === null || row.absoluteError === null)) {
    throw new Error(`Evaluable label ${row.predictionId} is missing mature source values`);
  }
}

export function parseEvaluationRow(record: Record<string, string>): EvaluationRow {
  return {
    experimentId: record.experiment_id,
    predictionId: record.prediction_id,
    predictionDate: dateString(record.prediction_date, "prediction_date"),
    split: oneOf(record.split, ["test"], "split"),
    ticker: oneOf(record.ticker, ["SPY", "IEF", "GLD"], "ticker"),
    modelName: oneOf(record.model_name, ["CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD"], "model_name"),
    targetStartDate: dateString(record.target_start_date, "target_start_date"),
    targetEndDate: dateString(record.target_end_date, "target_end_date"),
    predictedVolAnnualized: parseFinite(record.predicted_vol_annualized, "predicted_vol_annualized"),
    targetRealizedVol5d: parseFinite(record.target_realized_vol_5d, "target_realized_vol_5d"),
    absoluteError: parseFinite(record.absolute_error, "absolute_error"),
  };
}

export function modelId(model: ModelName): "B0" | "B1" | "B2" | "B3" {
  const ids: Record<ModelName, "B0" | "B1" | "B2" | "B3"> = {
    CONSTANT_BASELINE: "B0",
    ROLLING_20D_BASELINE: "B1",
    STATIC_SGD: "B2",
    ONLINE_SGD: "B3",
  };
  return ids[model];
}

export function modelLabel(model: ModelName): string {
  const labels: Record<ModelName, string> = {
    CONSTANT_BASELINE: "Constant baseline",
    ROLLING_20D_BASELINE: "Rolling 20D baseline",
    STATIC_SGD: "Static SGD",
    ONLINE_SGD: "Online SGD",
  };
  return labels[model];
}
