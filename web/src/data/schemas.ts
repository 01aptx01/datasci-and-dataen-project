export interface SnapshotPolicy {
  schemaVersion: "1.0.0" | "1.1.0" | "1.2.0";
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
    modelMetrics: string;
    pairComparisons: string;
    coverage: string;
    portfolioRisk: string;
    rollingMae20: string;
    driftErrorTimeline?: string;
    h1ScatterData: string;
    h1Results: string;
    h1Sensitivity: string;
    hypothesisResults: string;
    bootstrapDiagnostics: string;
    highVolatilityMetrics: string;
    b4Comparisons?: string;
    referenceB0B3Metrics?: string;
  };
  memberSha256: Record<string, string>;
  expectedHeaders: {
    forecastAudit: string[];
    evaluation: string[];
    modelMetrics: string[];
    pairComparisons: string[];
    coverage: string[];
    portfolioRisk: string[];
    rollingMae20: string[];
    driftErrorTimeline?: string[];
    h1ScatterData: string[];
    h1Results: string[];
    h1Sensitivity: string[];
    hypothesisResults: string[];
    bootstrapDiagnostics: string[];
    highVolatilityMetrics: string[];
    b4Comparisons?: string[];
    referenceB0B3Metrics?: string[];
  };
  expectedCounts: {
    forecastAuditRows: number;
    evaluationRows: number;
    testForecastRows: number;
    testEvaluableRows: number;
    testPendingRows: number;
    modelMetricsRows: number;
    pairComparisonsRows: number;
    coverageRows: number;
    portfolioRiskRows: number;
    rollingMae20Rows: number;
    driftErrorTimelineRows?: number;
    driftAlertRows?: number;
    h1ScatterDataRows: number;
    h1ResultsRows: number;
    h1SensitivityRows: number;
    hypothesisResultsRows: number;
    bootstrapDiagnosticsRows: number;
    highVolatilityMetricsRows: number;
    b4ComparisonsRows?: number;
    referenceB0B3MetricsRows?: number;
  };
  publicOutputs: {
    forecastAudit: string;
    evaluation: string;
    modelMetrics: string;
    pairComparisons: string;
    coverage: string;
    portfolioRisk: string;
    rollingMae20: string;
    driftErrorTimeline?: string;
    h1ScatterData: string;
    h1Results: string;
    h1Sensitivity: string;
    hypothesisResults: string;
    bootstrapDiagnostics: string;
    highVolatilityMetrics: string;
    b4Comparisons?: string;
    referenceB0B3Metrics?: string;
  };
}

export interface SnapshotFileArtifact {
  path: string;
  sha256: string;
  bytes: number;
  rowCount: number;
  headers: string[];
}

export interface SnapshotManifest {
  schemaVersion: SnapshotPolicy["schemaVersion"];
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
  files: Record<string, SnapshotFileArtifact>;
}

export type ModelName = "CONSTANT_BASELINE" | "ROLLING_20D_BASELINE" | "STATIC_SGD" | "ONLINE_SGD" | "HAR_X_OLS";
import { minimumEigenvalueSymmetric3 } from "./portfolio.js";

export type Ticker = "SPY" | "IEF" | "GLD";

export interface ForecastAuditRow {
  predictionDate: string;
  ticker: Ticker;
  split: "test" | "validation";
  modelName: ModelName;
  isLabelMature: boolean;
  isCommonPanel: boolean;
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

export interface ModelMetricRow {
  split: "test";
  ticker: Ticker | "MACRO";
  modelName: ModelName;
  pairedN: number;
  expectedEligibleAnchorCount: number;
  mae: number;
  rmse: number;
  comparisonPanel: string;
}

export interface B4ComparisonRow {
  comparisonId: "B4_VS_B2" | "B4_VS_B3" | "B4_VS_B1";
  b4Model: "HAR_X_OLS";
  comparatorModel: ModelName;
  split: "test";
  ticker: Ticker | "MACRO";
  pairedN: number;
  expectedEligibleAnchorCount: number;
  pairedCoverage: number;
  b4Mae: number;
  comparatorMae: number;
  deltaMaeComparatorMinusB4: number;
  relativeImprovementPct: number;
  b4Rmse: number | null;
  comparatorRmse: number | null;
  commonAllFiveN: number;
  commonB0B3N: number;
  evaluationScope: string;
}

export interface PairComparisonRow {
  comparisonId: "B0" | "B1" | "B2" | "H2" | "H3";
  baselineModel: ModelName;
  onlineModel: "ONLINE_SGD";
  ticker: Ticker | "MACRO";
  pairedN: number;
  baselineMae: number;
  onlineMae: number;
  deltaMaeBaselineMinusOnline: number;
  relativeImprovementPct: number;
  baselineRmse: number | null;
  onlineRmse: number | null;
  commonAllFourN: number;
  pairingPolicy: string;
}

export interface CoverageRow {
  split: "test" | "validation";
  ticker: Ticker;
  modelName: ModelName;
  expectedEligiblePredictionAnchors: number;
  forecastSuccessCount: number;
  invalidForecastCount: number;
  missingForecastCount: number;
  matureTargetCount: number;
  pendingLabelCount: number;
  invalidOrMissingTargetCount: number;
  matureEvaluableCount: number;
  commonPanelCount: number;
  forecastCoverage: number;
  evaluationCoverage: number;
}

export interface PortfolioRiskRow {
  split: "test" | "validation";
  predictionDate: string;
  modelName: ModelName;
  replayRunId: string;
  inputSnapshotId: string;
  forecastVols: [number, number, number];
  forecastStatuses: ["VALID" | "INVALID" | "MISSING", "VALID" | "INVALID" | "MISSING", "VALID" | "INVALID" | "MISSING"];
  correlations: { spyIef: number | null; spyGld: number | null; iefGld: number | null };
  correlationReady: boolean;
  correlationRunId: string;
  sourceWeights: [number, number, number];
  portfolioVol: number | null;
  status: string;
  missingInputs: string[];
  covariance: number[][] | null;
}

export interface RollingMae20Row {
  split: "test" | "validation";
  ticker: Ticker;
  modelName: ModelName;
  windowStart: string;
  windowEnd: string;
  windowSessionCount: number;
  expectedAnchorCount: number;
  evaluableCount: number;
  coverage: number;
  mae: number;
  rmse: number;
}

export interface DriftTimelineRow {
  predictionId: string;
  predictionDate: string;
  ticker: Ticker;
  absoluteErrorEvaluation: number;
  absoluteErrorAdwin: number;
  driftDetected: boolean;
  adwinDelta: number;
  adwinWidth: number;
  adwinEstimation: number;
  alertRecordPresent: boolean;
}

export interface H1ScatterRow {
  date: string;
  ticker: Ticker;
  split: "train";
  targetEndDate: string;
  rv5: number;
  targetRealizedVol5d: number;
}

export interface H1ResultRow {
  ticker: Ticker;
  n: number;
  expectedN: number;
  trainStartDate: string;
  trainEndDate: string;
  beta: number;
  intercept: number;
  hacSe: number;
  testStatistic: number;
  pRaw: number;
  pHolm: number;
  ci95: [number, number];
  hacLag: number;
  decision: string;
  interpretation: string;
}

export interface H1SensitivityRow {
  ticker: Ticker;
  hacMaxlags: number;
  n: number;
  beta: number;
  intercept: number;
  hacSe: number;
  testStatistic: number;
  pRaw: number;
  ci95: [number, number];
  status: string;
}

export interface HypothesisResultRow {
  hypothesisId: "H1" | "H2" | "H3";
  tickerOrMacro: Ticker | "MACRO";
  datasetSplit: "train" | "test";
  nExpected: number;
  nPaired: number;
  pairedNByTicker: Record<string, number>;
  alpha: number;
  method: string;
  testStatistic: number;
  effectSize: number;
  rawPValue: number;
  adjustedPValue: number;
  confidenceInterval95: [number, number];
  decision: string;
  interpretation: string;
  statisticalStatus: string;
}

export interface BootstrapDiagnosticRow {
  hypothesisId: "H2" | "H3";
  blockLength: number;
  replicates: number;
  seed: number;
  status: string;
  observedDelta: number;
  standardError: number;
  ci95: [number, number];
  pRaw: number;
  nByTicker: Record<string, number>;
  invalidReplicates: number;
}

export interface HighVolatilityMetricRow {
  split: "test" | "validation";
  ticker: Ticker;
  modelName: ModelName;
  trainThreshold: number;
  thresholdTrainN: number;
  highVolAnchorCount: number;
  highVolCommonEvaluableN: number;
  mae: number | null;
  rmse: number | null;
  evaluationCoverage: number | null;
  subsetPolicy: string;
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
  const expectedHeaders = value.expectedHeaders;
  if (value.schemaVersion !== "1.0.0" && value.schemaVersion !== "1.1.0" && value.schemaVersion !== "1.2.0") {
    throw new Error("Snapshot policy schemaVersion must be 1.0.0, 1.1.0, or 1.2.0");
  }
  const schemaVersion = value.schemaVersion;
  const isCurrentSchema = schemaVersion === "1.2.0";
  const driftFields = [members.driftErrorTimeline, expectedHeaders.driftErrorTimeline, counts.driftErrorTimelineRows, value.publicOutputs.driftErrorTimeline];
  const driftMemberHashes = Object.keys(value.memberSha256).filter((name) => name.toLowerCase().includes("drift_error_timeline.csv"));
  const driftKeyExists = [members, expectedHeaders, counts, value.publicOutputs]
    .some((section) => Object.keys(section).some((key) => key.toLowerCase().includes("drift")));
  const driftPathExists = [members, value.publicOutputs]
    .some((section) => Object.values(section).some((entry) => typeof entry === "string" && entry.toLowerCase().includes("drift_error_timeline.csv")));
  if (isCurrentSchema && (driftFields.some((field) => field !== undefined) || counts.driftAlertRows !== undefined || driftMemberHashes.length > 0 || driftKeyExists || driftPathExists)) {
    throw new Error("Snapshot policy schema 1.2.0 must not define the retired B3 drift error timeline");
  }
  if (!isCurrentSchema && (driftFields.some((field) => field === undefined) || driftMemberHashes.length !== 1 || driftMemberHashes[0] !== members.driftErrorTimeline)) {
    throw new Error("Snapshot policy schema 1.0.0/1.1.0 requires the archived B3 drift error timeline fields");
  }
  if (identity.reportApproval !== "PENDING") throw new Error("reportApproval must remain PENDING");
  const hashEntries = Object.fromEntries(Object.entries(value.memberSha256).map(([name, hash]) => {
    if (typeof hash !== "string" || !/^[a-f0-9]{64}$/i.test(hash)) throw new Error(`Invalid source member hash for ${name}`);
    return [name, hash.toLowerCase()];
  }));
  return {
    schemaVersion,
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
      baselineGitCommit: typeof identity.baselineGitCommit === "string" ? identity.baselineGitCommit : "unverified",
      strictCutoff: stringField(identity, "strictCutoff"),
      reportApproval: "PENDING",
    },
    members: {
      sourceIdentity: stringField(members, "sourceIdentity"),
      executionManifest: stringField(members, "executionManifest"),
      stage05Manifest: stringField(members, "stage05Manifest"),
      forecastAudit: stringField(members, "forecastAudit"),
      evaluation: stringField(members, "evaluation"),
      modelMetrics: stringField(members, "modelMetrics"),
      pairComparisons: stringField(members, "pairComparisons"),
      coverage: stringField(members, "coverage"),
      portfolioRisk: stringField(members, "portfolioRisk"),
      rollingMae20: stringField(members, "rollingMae20"),
      ...(members.driftErrorTimeline !== undefined ? { driftErrorTimeline: stringField(members, "driftErrorTimeline") } : {}),
      h1ScatterData: stringField(members, "h1ScatterData"),
      h1Results: stringField(members, "h1Results"),
      h1Sensitivity: stringField(members, "h1Sensitivity"),
      hypothesisResults: stringField(members, "hypothesisResults"),
      bootstrapDiagnostics: stringField(members, "bootstrapDiagnostics"),
      highVolatilityMetrics: stringField(members, "highVolatilityMetrics"),
      ...(members.b4Comparisons !== undefined ? { b4Comparisons: stringField(members, "b4Comparisons") } : {}),
      ...(members.referenceB0B3Metrics !== undefined ? { referenceB0B3Metrics: stringField(members, "referenceB0B3Metrics") } : {}),
    },
    memberSha256: hashEntries,
    expectedHeaders: {
      forecastAudit: stringArray(expectedHeaders.forecastAudit, "forecastAudit headers"),
      evaluation: stringArray(expectedHeaders.evaluation, "evaluation headers"),
      modelMetrics: stringArray(expectedHeaders.modelMetrics, "modelMetrics headers"),
      pairComparisons: stringArray(expectedHeaders.pairComparisons, "pairComparisons headers"),
      coverage: stringArray(expectedHeaders.coverage, "coverage headers"),
      portfolioRisk: stringArray(expectedHeaders.portfolioRisk, "portfolioRisk headers"),
      rollingMae20: stringArray(expectedHeaders.rollingMae20, "rollingMae20 headers"),
      ...(expectedHeaders.driftErrorTimeline !== undefined ? { driftErrorTimeline: stringArray(expectedHeaders.driftErrorTimeline, "driftErrorTimeline headers") } : {}),
      h1ScatterData: stringArray(expectedHeaders.h1ScatterData, "h1ScatterData headers"),
      h1Results: stringArray(expectedHeaders.h1Results, "h1Results headers"),
      h1Sensitivity: stringArray(expectedHeaders.h1Sensitivity, "h1Sensitivity headers"),
      hypothesisResults: stringArray(expectedHeaders.hypothesisResults, "hypothesisResults headers"),
      bootstrapDiagnostics: stringArray(expectedHeaders.bootstrapDiagnostics, "bootstrapDiagnostics headers"),
      highVolatilityMetrics: stringArray(expectedHeaders.highVolatilityMetrics, "highVolatilityMetrics headers"),
      ...(expectedHeaders.b4Comparisons ? { b4Comparisons: stringArray(expectedHeaders.b4Comparisons, "b4Comparisons headers") } : {}),
      ...(expectedHeaders.referenceB0B3Metrics ? { referenceB0B3Metrics: stringArray(expectedHeaders.referenceB0B3Metrics, "referenceB0B3Metrics headers") } : {}),
    },
    expectedCounts: {
      forecastAuditRows: numberField(counts, "forecastAuditRows"),
      evaluationRows: numberField(counts, "evaluationRows"),
      testForecastRows: numberField(counts, "testForecastRows"),
      testEvaluableRows: numberField(counts, "testEvaluableRows"),
      testPendingRows: numberField(counts, "testPendingRows"),
      modelMetricsRows: numberField(counts, "modelMetricsRows"),
      pairComparisonsRows: numberField(counts, "pairComparisonsRows"),
      coverageRows: numberField(counts, "coverageRows"),
      portfolioRiskRows: numberField(counts, "portfolioRiskRows"),
      rollingMae20Rows: numberField(counts, "rollingMae20Rows"),
      ...(counts.driftErrorTimelineRows !== undefined ? { driftErrorTimelineRows: numberField(counts, "driftErrorTimelineRows") } : {}),
      ...(counts.driftAlertRows !== undefined ? { driftAlertRows: numberField(counts, "driftAlertRows") } : {}),
      h1ScatterDataRows: numberField(counts, "h1ScatterDataRows"),
      h1ResultsRows: numberField(counts, "h1ResultsRows"),
      h1SensitivityRows: numberField(counts, "h1SensitivityRows"),
      hypothesisResultsRows: numberField(counts, "hypothesisResultsRows"),
      bootstrapDiagnosticsRows: numberField(counts, "bootstrapDiagnosticsRows"),
      highVolatilityMetricsRows: numberField(counts, "highVolatilityMetricsRows"),
      ...(counts.b4ComparisonsRows !== undefined ? { b4ComparisonsRows: numberField(counts, "b4ComparisonsRows") } : {}),
      ...(counts.referenceB0B3MetricsRows !== undefined ? { referenceB0B3MetricsRows: numberField(counts, "referenceB0B3MetricsRows") } : {}),
    },
    publicOutputs: {
      forecastAudit: stringField(value.publicOutputs, "forecastAudit"),
      evaluation: stringField(value.publicOutputs, "evaluation"),
      modelMetrics: stringField(value.publicOutputs, "modelMetrics"),
      pairComparisons: stringField(value.publicOutputs, "pairComparisons"),
      coverage: stringField(value.publicOutputs, "coverage"),
      portfolioRisk: stringField(value.publicOutputs, "portfolioRisk"),
      rollingMae20: stringField(value.publicOutputs, "rollingMae20"),
      ...(value.publicOutputs.driftErrorTimeline !== undefined ? { driftErrorTimeline: stringField(value.publicOutputs, "driftErrorTimeline") } : {}),
      h1ScatterData: stringField(value.publicOutputs, "h1ScatterData"),
      h1Results: stringField(value.publicOutputs, "h1Results"),
      h1Sensitivity: stringField(value.publicOutputs, "h1Sensitivity"),
      hypothesisResults: stringField(value.publicOutputs, "hypothesisResults"),
      bootstrapDiagnostics: stringField(value.publicOutputs, "bootstrapDiagnostics"),
      highVolatilityMetrics: stringField(value.publicOutputs, "highVolatilityMetrics"),
      ...(value.publicOutputs.b4Comparisons !== undefined ? { b4Comparisons: stringField(value.publicOutputs, "b4Comparisons") } : {}),
      ...(value.publicOutputs.referenceB0B3Metrics !== undefined ? { referenceB0B3Metrics: stringField(value.publicOutputs, "referenceB0B3Metrics") } : {}),
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
  if (manifest.schemaVersion !== policy.schemaVersion) {
    throw new Error("schemaVersion does not match the pinned handoff policy");
  }
  equal("sourceRepository", policy.source.repository);
  equal("sourceHandoffCommit", policy.source.handoffCommit);
  equal("sourceMainCommitAtStart", policy.source.mainCommitAtStart);
  equal("sourceZipName", policy.source.zipName);
  equal("sourceZipSha256", policy.source.zipSha256);
  equal("evaluationId", policy.identity.evaluationId);
  equal("replayId", policy.identity.replayId);
  if ((manifest.baselineGitCommit ?? "unverified") !== policy.identity.baselineGitCommit) {
    throw new Error("baselineGitCommit does not match the pinned handoff policy");
  }
  equal("sourceVerificationStatus", "SOURCE VERIFIED");
  equal("stage05Status", "COMPLETED");
  equal("stage06Status", "COMPLETED");
  equal("reportApproval", "PENDING");
  equal("mode", "SIMULATED HISTORICAL REPLAY");
  equal("pointInTimeSourceAvailabilityVerified", false);
  equal("strictCutoff", policy.identity.strictCutoff);

  const counts = manifest.expectedCounts as Record<string, unknown>;
  const hasDriftTimeline = policy.schemaVersion !== "1.2.0";
  const hasLegacyDriftFields = counts.driftErrorTimelineRows !== undefined || counts.driftAlertRows !== undefined;
  if (hasDriftTimeline && counts.driftErrorTimelineRows === undefined) {
    throw new Error("expectedCounts.driftErrorTimelineRows is required for archived snapshot schemas");
  }
  if (!hasDriftTimeline && hasLegacyDriftFields) {
    throw new Error("schema 1.2.0 expectedCounts must not include retired B3 drift fields");
  }
  const expectedCounts = {
    forecastAuditRows: numberField(counts, "forecastAuditRows"),
    evaluationRows: numberField(counts, "evaluationRows"),
    testForecastRows: numberField(counts, "testForecastRows"),
    testEvaluableRows: numberField(counts, "testEvaluableRows"),
    testPendingRows: numberField(counts, "testPendingRows"),
    modelMetricsRows: numberField(counts, "modelMetricsRows"),
    pairComparisonsRows: numberField(counts, "pairComparisonsRows"),
    coverageRows: numberField(counts, "coverageRows"),
    portfolioRiskRows: numberField(counts, "portfolioRiskRows"),
    rollingMae20Rows: numberField(counts, "rollingMae20Rows"),
    ...(hasDriftTimeline ? { driftErrorTimelineRows: numberField(counts, "driftErrorTimelineRows") } : {}),
    ...(counts.driftAlertRows !== undefined ? { driftAlertRows: numberField(counts, "driftAlertRows") } : {}),
    h1ScatterDataRows: numberField(counts, "h1ScatterDataRows"),
    h1ResultsRows: numberField(counts, "h1ResultsRows"),
    h1SensitivityRows: numberField(counts, "h1SensitivityRows"),
    hypothesisResultsRows: numberField(counts, "hypothesisResultsRows"),
    bootstrapDiagnosticsRows: numberField(counts, "bootstrapDiagnosticsRows"),
    highVolatilityMetricsRows: numberField(counts, "highVolatilityMetricsRows"),
    ...(counts.b4ComparisonsRows !== undefined ? { b4ComparisonsRows: numberField(counts, "b4ComparisonsRows") } : {}),
    ...(counts.referenceB0B3MetricsRows !== undefined ? { referenceB0B3MetricsRows: numberField(counts, "referenceB0B3MetricsRows") } : {}),
    recordedTestDates: numberField(counts, "recordedTestDates"),
  };
  const policyCountKeys = ["forecastAuditRows", "evaluationRows", "testForecastRows", "testEvaluableRows", "testPendingRows", "modelMetricsRows", "pairComparisonsRows", "coverageRows", "portfolioRiskRows", "rollingMae20Rows", "h1ScatterDataRows", "h1ResultsRows", "h1SensitivityRows", "hypothesisResultsRows", "bootstrapDiagnosticsRows", "highVolatilityMetricsRows"] as const;
  for (const key of policyCountKeys) {
    if (expectedCounts[key] !== policy.expectedCounts[key]) throw new Error(`expectedCounts.${key} does not match the pinned handoff policy`);
  }
  if (hasDriftTimeline && expectedCounts.driftErrorTimelineRows !== policy.expectedCounts.driftErrorTimelineRows) {
    throw new Error("expectedCounts.driftErrorTimelineRows does not match the pinned handoff policy");
  }
  const files = manifest.files as Record<string, unknown>;
  const artifactCountKey: Partial<Record<keyof SnapshotPolicy["publicOutputs"], keyof typeof expectedCounts>> = {
    forecastAudit: "forecastAuditRows",
    evaluation: "evaluationRows",
    modelMetrics: "modelMetricsRows",
    pairComparisons: "pairComparisonsRows",
    coverage: "coverageRows",
    portfolioRisk: "portfolioRiskRows",
    rollingMae20: "rollingMae20Rows",
    driftErrorTimeline: "driftErrorTimelineRows",
    h1ScatterData: "h1ScatterDataRows",
    h1Results: "h1ResultsRows",
    h1Sensitivity: "h1SensitivityRows",
    hypothesisResults: "hypothesisResultsRows",
    bootstrapDiagnostics: "bootstrapDiagnosticsRows",
    highVolatilityMetrics: "highVolatilityMetricsRows",
    b4Comparisons: "b4ComparisonsRows",
    referenceB0B3Metrics: "referenceB0B3MetricsRows",
  };
  const parsedFiles = {} as SnapshotManifest["files"];
  const outputKeys = Object.keys(policy.publicOutputs) as (keyof SnapshotPolicy["publicOutputs"])[];
  if (Object.keys(files).length !== outputKeys.length) throw new Error("Snapshot manifest includes an unexpected file list");
  for (const key of outputKeys) {
    const artifact = parseArtifact(files[key], key);
    const expectedPath = policy.publicOutputs[key];
    const memberKey = policy.members[key];
    const expectedHeaders = policy.expectedHeaders[key];
    if (!expectedPath || !memberKey || !expectedHeaders) throw new Error(`Snapshot policy is missing definition for ${key}`);
    if (artifact.path !== expectedPath) throw new Error(`Snapshot manifest uses an unapproved output path for ${key}`);
    if (artifact.sha256 !== policy.memberSha256[memberKey]) throw new Error(`Snapshot manifest ${key} hash differs from the pinned source hash`);
    const countKey = artifactCountKey[key];
    if (!countKey || artifact.rowCount !== expectedCounts[countKey]) throw new Error(`Snapshot manifest ${key} row count does not match the pinned source`);
    if (!sameArray(artifact.headers, expectedHeaders)) throw new Error(`Snapshot manifest ${key} headers do not match the pinned source schema`);
    parsedFiles[key] = artifact;
  }

  return {
    schemaVersion: policy.schemaVersion,
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
    files: parsedFiles,
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

function parseSignedFiniteOrNull(value: string, field: string): number | null {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`${field} must be blank or a finite number`);
  return parsed;
}

function parseFinite(value: string, field: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`${field} must be a finite nonnegative number`);
  return parsed;
}

function parseSignedFinite(value: string, field: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`${field} must be a finite number`);
  return parsed;
}

function parseCount(value: string, field: string): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) throw new Error(`${field} must be a nonnegative integer`);
  return parsed;
}

function parseModelName(value: string, field: string): ModelName {
  return oneOf(value, ["CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD", "HAR_X_OLS"], field);
}

function parseTickerOrMacro(value: string, field: string): Ticker | "MACRO" {
  return oneOf(value, ["SPY", "IEF", "GLD", "MACRO"], field);
}

function parseCoverageRate(value: string, field: string): number {
  const parsed = parseFinite(value, field);
  if (parsed > 1) throw new Error(`${field} must be between 0 and 1`);
  return parsed;
}

export function parseModelMetricRow(record: Record<string, string>): ModelMetricRow {
  if (record.split !== "test") throw new Error("model_metrics.csv is Test-only");
  const row: ModelMetricRow = {
    split: "test",
    ticker: parseTickerOrMacro(record.ticker, "ticker"),
    modelName: parseModelName(record.model_name, "model_name"),
    pairedN: parseCount(record.paired_n, "paired_n"),
    expectedEligibleAnchorCount: parseCount(record.expected_eligible_anchor_count, "expected_eligible_anchor_count"),
    mae: parseFinite(record.mae, "mae"),
    rmse: parseFinite(record.rmse, "rmse"),
    comparisonPanel: stringField(record, "comparison_panel"),
  };
  if (row.pairedN === 0 || row.expectedEligibleAnchorCount === 0 || row.pairedN > row.expectedEligibleAnchorCount) {
    throw new Error("model metric counts are inconsistent");
  }
  return row;
}

export function parsePairComparisonRow(record: Record<string, string>): PairComparisonRow {
  const comparisonId = oneOf(record.comparison_id, ["B0", "B1", "B2", "H2", "H3"], "comparison_id");
  const expectedBaseline: Record<PairComparisonRow["comparisonId"], ModelName> = {
    B0: "CONSTANT_BASELINE",
    B1: "ROLLING_20D_BASELINE",
    B2: "STATIC_SGD",
    H2: "STATIC_SGD",
    H3: "ROLLING_20D_BASELINE",
  };
  const baselineModel = parseModelName(record.baseline_model, "baseline_model");
  const onlineModel = parseModelName(record.online_model, "online_model");
  if (baselineModel !== expectedBaseline[comparisonId] || onlineModel !== "ONLINE_SGD") throw new Error("pair comparison model identity is inconsistent");
  const row: PairComparisonRow = {
    comparisonId,
    baselineModel,
    onlineModel,
    ticker: parseTickerOrMacro(record.ticker, "ticker"),
    pairedN: parseCount(record.paired_n, "paired_n"),
    baselineMae: parseFinite(record.baseline_mae, "baseline_mae"),
    onlineMae: parseFinite(record.online_mae, "online_mae"),
    deltaMaeBaselineMinusOnline: parseSignedFinite(record.delta_mae_baseline_minus_online, "delta_mae_baseline_minus_online"),
    relativeImprovementPct: parseSignedFinite(record.relative_improvement_pct, "relative_improvement_pct"),
    baselineRmse: parseFiniteOrNull(record.baseline_rmse, "baseline_rmse"),
    onlineRmse: parseFiniteOrNull(record.online_rmse, "online_rmse"),
    commonAllFourN: parseCount(record.common_all_four_n, "common_all_four_n"),
    pairingPolicy: stringField(record, "pairing_policy"),
  };
  if (row.pairedN === 0 || row.commonAllFourN > row.pairedN) throw new Error("pair comparison counts are inconsistent");
  if ((row.ticker === "MACRO") !== (row.baselineRmse === null && row.onlineRmse === null)) throw new Error("Macro RMSE must remain blank while ETF RMSE must be present");
  return row;
}

export function parseCoverageRow(record: Record<string, string>): CoverageRow {
  const row: CoverageRow = {
    split: oneOf(record.split, ["test", "validation"], "split"),
    ticker: oneOf(record.ticker, ["SPY", "IEF", "GLD"], "ticker"),
    modelName: parseModelName(record.model_name, "model_name"),
    expectedEligiblePredictionAnchors: parseCount(record.expected_eligible_prediction_anchors, "expected_eligible_prediction_anchors"),
    forecastSuccessCount: parseCount(record.forecast_success_count, "forecast_success_count"),
    invalidForecastCount: parseCount(record.invalid_forecast_count, "invalid_forecast_count"),
    missingForecastCount: parseCount(record.missing_forecast_count, "missing_forecast_count"),
    matureTargetCount: parseCount(record.mature_target_count, "mature_target_count"),
    pendingLabelCount: parseCount(record.pending_label_count, "pending_label_count"),
    invalidOrMissingTargetCount: parseCount(record.invalid_or_missing_target_count, "invalid_or_missing_target_count"),
    matureEvaluableCount: parseCount(record.mature_evaluable_count, "mature_evaluable_count"),
    commonPanelCount: parseCount(record.common_panel_count, "common_panel_count"),
    forecastCoverage: parseCoverageRate(record.forecast_coverage, "forecast_coverage"),
    evaluationCoverage: parseCoverageRate(record.evaluation_coverage, "evaluation_coverage"),
  };
  const forecastCount = row.forecastSuccessCount + row.invalidForecastCount + row.missingForecastCount;
  const targetCount = row.matureTargetCount + row.pendingLabelCount + row.invalidOrMissingTargetCount;
  if (forecastCount !== row.expectedEligiblePredictionAnchors || targetCount !== row.expectedEligiblePredictionAnchors || row.matureEvaluableCount > row.matureTargetCount || row.commonPanelCount > row.matureEvaluableCount) {
    throw new Error("coverage counts do not reconcile with the eligible anchor denominator");
  }
  return row;
}

function parseJsonValue(value: string, field: string): unknown {
  try { return JSON.parse(value) as unknown; } catch { throw new Error(`${field} must contain valid JSON`); }
}

function parseNumberTuple(value: string, field: string): [number, number] {
  const parsed = parseJsonValue(value, field);
  if (!Array.isArray(parsed) || parsed.length !== 2 || parsed.some((item) => typeof item !== "number" || !Number.isFinite(item))) throw new Error(`${field} must contain two finite numbers`);
  const tuple = parsed as [number, number];
  if (tuple[0] > tuple[1]) throw new Error(`${field} bounds are reversed`);
  return tuple;
}

function parseTickerCounts(value: string, field: string): Record<string, number> {
  const parsed = parseJsonValue(value, field);
  if (!isRecord(parsed)) throw new Error(`${field} must contain a JSON object`);
  const result: Record<string, number> = {};
  for (const [ticker, count] of Object.entries(parsed)) {
    if (!(["SPY", "IEF", "GLD"] as string[]).includes(ticker) || typeof count !== "number" || !Number.isInteger(count) || count < 0) throw new Error(`${field} contains an invalid ticker count`);
    result[ticker] = count;
  }
  return result;
}

function parseBoolean(value: string, field: string): boolean {
  if (value === "True" || value.toLowerCase() === "true") return true;
  if (value === "False" || value.toLowerCase() === "false") return false;
  throw new Error(`${field} must be a source boolean`);
}

export function parsePortfolioRiskRow(record: Record<string, string>): PortfolioRiskRow {
  const matrixValue = record.covariance_matrix.trim() ? parseJsonValue(record.covariance_matrix, "covariance_matrix") : null;
  let covariance: number[][] | null = null;
  if (matrixValue !== null) {
    if (!Array.isArray(matrixValue) || matrixValue.length !== 3 || matrixValue.some((row) => !Array.isArray(row) || row.length !== 3 || row.some((value) => typeof value !== "number" || !Number.isFinite(value)))) throw new Error("covariance_matrix must be a 3 by 3 finite matrix");
    covariance = matrixValue as number[][];
    for (let row = 0; row < 3; row += 1) for (let column = row + 1; column < 3; column += 1) {
      if (Math.abs(covariance[row][column] - covariance[column][row]) > 1e-10) throw new Error("covariance_matrix must be symmetric");
    }
  }
  const missing = parseJsonValue(record.missing_inputs, "missing_inputs");
  if (!Array.isArray(missing) || missing.some((item) => typeof item !== "string")) throw new Error("missing_inputs must contain a JSON string array");
  const correlations = {
    spyIef: parseSignedFiniteOrNull(record.corr_spy_ief_20d, "corr_spy_ief_20d"),
    spyGld: parseSignedFiniteOrNull(record.corr_spy_gld_20d, "corr_spy_gld_20d"),
    iefGld: parseSignedFiniteOrNull(record.corr_ief_gld_20d, "corr_ief_gld_20d"),
  };
  const correlationReady = parseBoolean(record.is_corr_ready, "is_corr_ready");
  if (correlationReady) {
    const values = [correlations.spyIef, correlations.spyGld, correlations.iefGld];
    if (values.some((value) => value === null)) throw new Error("Ready 20-session correlation values must all be present");
    if (values.some((value) => value! < -1 || value! > 1)) throw new Error("20-session correlation values must be in [-1, 1]");
    const matrix = [
      [1, correlations.spyIef!, correlations.spyGld!],
      [correlations.spyIef!, 1, correlations.iefGld!],
      [correlations.spyGld!, correlations.iefGld!, 1],
    ];
    if (minimumEigenvalueSymmetric3(matrix) < -1e-10) throw new Error("20-session correlation matrix must be positive semidefinite");
  }
  const row: PortfolioRiskRow = {
    split: oneOf(record.split, ["test", "validation"], "split"),
    predictionDate: dateString(record.prediction_date, "prediction_date"),
    modelName: parseModelName(record.model_name, "model_name"),
    replayRunId: stringField(record, "replay_run_id"),
    inputSnapshotId: hashField({ id: record.input_snapshot_id }, "id"),
    forecastVols: [parseFiniteOrNull(record.spy_forecast_vol_annualized, "spy_forecast_vol_annualized"), parseFiniteOrNull(record.ief_forecast_vol_annualized, "ief_forecast_vol_annualized"), parseFiniteOrNull(record.gld_forecast_vol_annualized, "gld_forecast_vol_annualized")] as [number, number, number],
    forecastStatuses: [oneOf(record.spy_forecast_status, ["VALID", "INVALID", "MISSING"], "spy_forecast_status"), oneOf(record.ief_forecast_status, ["VALID", "INVALID", "MISSING"], "ief_forecast_status"), oneOf(record.gld_forecast_status, ["VALID", "INVALID", "MISSING"], "gld_forecast_status")],
    correlations,
    correlationReady,
    correlationRunId: record.correlation_run_id.trim(),
    sourceWeights: [parseFinite(record.weight_spy, "weight_spy"), parseFinite(record.weight_ief, "weight_ief"), parseFinite(record.weight_gld, "weight_gld")],
    portfolioVol: parseFiniteOrNull(record.portfolio_vol_annualized, "portfolio_vol_annualized"),
    status: stringField(record, "portfolio_status"),
    missingInputs: missing as string[],
    covariance,
  };
  for (let index = 0; index < 3; index += 1) {
    if ((row.forecastStatuses[index] === "VALID") !== (row.forecastVols[index] !== null)) throw new Error("Forecast status and value do not agree");
  }
  if (Math.abs(row.sourceWeights.reduce((sum, weight) => sum + weight, 0) - 1) > 1e-8) throw new Error("Stored portfolio weights must sum to 1");
  if (row.status === "OK" && (row.covariance === null || row.portfolioVol === null || row.missingInputs.length > 0 || row.forecastStatuses.some((status) => status !== "VALID") || !row.correlationReady)) throw new Error("An OK portfolio row must have complete covariance, forecast inputs, and ready correlations");
  return row;
}

export function parseRollingMae20Row(record: Record<string, string>): RollingMae20Row {
  const windowSessionCount = parseCount(record.window_session_count, "window_session_count");
  const expectedAnchorCount = parseCount(record.expected_anchor_count, "expected_anchor_count");
  const evaluableCount = parseCount(record.evaluable_count, "evaluable_count");
  const coverage = parseCoverageRate(record.coverage, "coverage");
  if (windowSessionCount !== 20 || expectedAnchorCount <= 0 || evaluableCount <= 0 || evaluableCount > expectedAnchorCount || Math.abs(coverage - evaluableCount / expectedAnchorCount) > 1e-10) throw new Error("rolling MAE20 counts or coverage are inconsistent");
  return {
    split: oneOf(record.split, ["test", "validation"], "split"), ticker: oneOf(record.ticker, ["SPY", "IEF", "GLD"], "ticker"),
    modelName: parseModelName(record.model_name, "model_name"), windowStart: dateString(record.window_start, "window_start"), windowEnd: dateString(record.window_end, "window_end"),
    windowSessionCount, expectedAnchorCount, evaluableCount, coverage,
    mae: parseFinite(record.mae, "mae"), rmse: parseFinite(record.rmse, "rmse"),
  };
}

export function parseDriftTimelineRow(record: Record<string, string>): DriftTimelineRow {
  return {
    predictionId: stringField(record, "prediction_id"), predictionDate: dateString(record.prediction_date, "prediction_date"),
    ticker: oneOf(record.ticker, ["SPY", "IEF", "GLD"], "ticker"), absoluteErrorEvaluation: parseFinite(record.absolute_error_evaluation, "absolute_error_evaluation"),
    absoluteErrorAdwin: parseFinite(record.absolute_error_adwin, "absolute_error_adwin"), driftDetected: parseBoolean(record.drift_detected, "drift_detected"),
    adwinDelta: parseCoverageRate(record.adwin_delta, "adwin_delta"), adwinWidth: parseCount(record.adwin_width, "adwin_width"),
    adwinEstimation: parseFinite(record.adwin_estimation, "adwin_estimation"), alertRecordPresent: parseBoolean(record.alert_record_present, "alert_record_present"),
  };
}

export function parseH1ScatterRow(record: Record<string, string>): H1ScatterRow {
  const split = oneOf(record.split, ["train", "validation", "test"], "split");
  if (split !== "train") throw new Error("H1 scatter is Train-only");
  return { date: dateString(record.date, "date"), ticker: oneOf(record.ticker, ["SPY", "IEF", "GLD"], "ticker"), split, targetEndDate: dateString(record.target_end_date, "target_end_date"), rv5: parseFinite(record.rv_5d, "rv_5d"), targetRealizedVol5d: parseFinite(record.target_realized_vol_5d, "target_realized_vol_5d") };
}

export function parseH1ResultRow(record: Record<string, string>): H1ResultRow {
  const row: H1ResultRow = {
    ticker: oneOf(record.ticker, ["SPY", "IEF", "GLD"], "ticker"), n: parseCount(record.n, "n"), expectedN: parseCount(record.expected_n, "expected_n"),
    trainStartDate: dateString(record.train_start_date, "train_start_date"), trainEndDate: dateString(record.train_end_date, "train_end_date"),
    beta: parseSignedFinite(record.beta, "beta"), intercept: parseSignedFinite(record.intercept, "intercept"), hacSe: parseFinite(record.hac_se, "hac_se"), testStatistic: parseSignedFinite(record.test_statistic, "test_statistic"),
    pRaw: parseCoverageRate(record.p_raw_one_sided, "p_raw_one_sided"), pHolm: parseCoverageRate(record.p_holm, "p_holm"), ci95: [parseSignedFinite(record.ci95_lower, "ci95_lower"), parseSignedFinite(record.ci95_upper, "ci95_upper")],
    hacLag: parseCount(record.hac_lag, "hac_lag"), decision: stringField(record, "decision"), interpretation: stringField(record, "effect_size_interpretation"),
  };
  if (row.n === 0 || row.n !== row.expectedN || row.hacLag !== 5 || row.ci95[0] > row.ci95[1]) throw new Error("H1 primary result counts, HAC lag, or interval are inconsistent");
  return row;
}

export function parseH1SensitivityRow(record: Record<string, string>): H1SensitivityRow {
  const row: H1SensitivityRow = {
    ticker: oneOf(record.ticker, ["SPY", "IEF", "GLD"], "ticker"), hacMaxlags: parseCount(record.hac_maxlags, "hac_maxlags"), n: parseCount(record.n, "n"),
    beta: parseSignedFinite(record.beta, "beta"), intercept: parseSignedFinite(record.intercept, "intercept"), hacSe: parseFinite(record.hac_se, "hac_se"), testStatistic: parseSignedFinite(record.test_statistic, "test_statistic"),
    pRaw: parseCoverageRate(record.p_raw_one_sided, "p_raw_one_sided"), ci95: [parseSignedFinite(record.ci95_lower, "ci95_lower"), parseSignedFinite(record.ci95_upper, "ci95_upper")], status: stringField(record, "status"),
  };
  if (![5, 10, 20].includes(row.hacMaxlags) || row.n === 0 || row.ci95[0] > row.ci95[1] || row.status !== "computed") throw new Error("H1 sensitivity row is inconsistent");
  return row;
}

export function parseHypothesisResultRow(record: Record<string, string>): HypothesisResultRow {
  const hypothesisId = oneOf(record.hypothesis_id, ["H1", "H2", "H3"], "hypothesis_id");
  const datasetSplit = oneOf(record.dataset_split, ["train", "test"], "dataset_split");
  const tickerOrMacro = parseTickerOrMacro(record.ticker_or_macro, "ticker_or_macro");
  const pairedNByTicker = parseTickerCounts(record.paired_n_by_ticker, "paired_n_by_ticker");
  const row: HypothesisResultRow = {
    hypothesisId, tickerOrMacro, datasetSplit, nExpected: parseCount(record.n_expected, "n_expected"), nPaired: parseCount(record.n_paired, "n_paired"), pairedNByTicker,
    alpha: parseCoverageRate(record.alpha, "alpha"), method: stringField(record, "method"), testStatistic: parseSignedFinite(record.test_statistic, "test_statistic"), effectSize: parseSignedFinite(record.effect_size, "effect_size"),
    rawPValue: parseCoverageRate(record.raw_p_value, "raw_p_value"), adjustedPValue: parseCoverageRate(record.adjusted_p_value, "adjusted_p_value"), confidenceInterval95: parseNumberTuple(record.confidence_interval_95, "confidence_interval_95"),
    decision: stringField(record, "decision"), interpretation: stringField(record, "effect_size_interpretation"), statisticalStatus: record.statistical_status,
  };
  if (hypothesisId === "H1" ? (datasetSplit !== "train" || tickerOrMacro === "MACRO") : (datasetSplit !== "test" || tickerOrMacro !== "MACRO" || row.nPaired === 0)) throw new Error("Hypothesis split/ticker scope is inconsistent");
  if (Object.keys(pairedNByTicker).length === 0 || Object.values(pairedNByTicker).some((count) => count === 0) || row.nPaired > row.nExpected) throw new Error("Hypothesis paired counts are inconsistent");
  return row;
}

export function parseBootstrapDiagnosticRow(record: Record<string, string>): BootstrapDiagnosticRow {
  const hypothesisId = oneOf(record.hypothesis_id, ["H2", "H3"], "hypothesis_id");
  const row: BootstrapDiagnosticRow = {
    hypothesisId, blockLength: parseCount(record.block_length_xnys_sessions, "block_length_xnys_sessions"), replicates: parseCount(record.replicates, "replicates"), seed: parseCount(record.seed, "seed"), status: stringField(record, "status"),
    observedDelta: parseSignedFinite(record.observed_delta, "observed_delta"), standardError: parseFinite(record.bootstrap_standard_error, "bootstrap_standard_error"), ci95: [parseSignedFinite(record.ci95_lower, "ci95_lower"), parseSignedFinite(record.ci95_upper, "ci95_upper")],
    pRaw: parseCoverageRate(record.p_raw_one_sided, "p_raw_one_sided"), nByTicker: parseTickerCounts(record.n_by_ticker, "n_by_ticker"), invalidReplicates: parseCount(record.invalid_replicates, "invalid_replicates"),
  };
  if (![5, 20].includes(row.blockLength) || row.replicates <= 0 || row.status !== "COMPUTED" || row.invalidReplicates > row.replicates || row.ci95[0] > row.ci95[1]) throw new Error("Bootstrap diagnostics are inconsistent");
  return row;
}

export function parseHighVolatilityMetricRow(record: Record<string, string>): HighVolatilityMetricRow {
  const row: HighVolatilityMetricRow = {
    split: oneOf(record.split, ["test", "validation"], "split"), ticker: oneOf(record.ticker, ["SPY", "IEF", "GLD"], "ticker"), modelName: parseModelName(record.model_name, "model_name"),
    trainThreshold: parseFinite(record.train_target_p80_threshold, "train_target_p80_threshold"), thresholdTrainN: parseCount(record.threshold_train_n, "threshold_train_n"), highVolAnchorCount: parseCount(record.high_vol_target_anchor_count, "high_vol_target_anchor_count"),
    highVolCommonEvaluableN: parseCount(record.high_vol_common_evaluable_n, "high_vol_common_evaluable_n"), mae: parseFiniteOrNull(record.mae, "mae"), rmse: parseFiniteOrNull(record.rmse, "rmse"), evaluationCoverage: record.evaluation_coverage.trim() ? parseCoverageRate(record.evaluation_coverage, "evaluation_coverage") : null,
    subsetPolicy: stringField(record, "subset_policy"),
  };
  if (row.thresholdTrainN === 0 || row.highVolCommonEvaluableN > row.highVolAnchorCount || row.highVolCommonEvaluableN > 0 && (row.mae === null || row.rmse === null || row.evaluationCoverage === null) || row.highVolCommonEvaluableN === 0 && (row.mae !== null || row.rmse !== null || row.evaluationCoverage !== null)) throw new Error("High-volatility metrics are inconsistent with subset size");
  return row;
}

export function parseForecastAuditRow(record: Record<string, string>): ForecastAuditRow {
  const row: ForecastAuditRow = {
    predictionDate: dateString(record.prediction_date, "prediction_date"),
    ticker: oneOf(record.ticker, ["SPY", "IEF", "GLD"], "ticker"),
    split: oneOf(record.split, ["test", "validation"], "split"),
    modelName: oneOf(record.model_name, ["CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD", "HAR_X_OLS"], "model_name"),
    isLabelMature: parseBoolean(record.is_label_mature, "is_label_mature"),
    isCommonPanel: parseBoolean(record.is_common_panel, "is_common_panel"),
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
  if (row.isCommonPanel && (row.evaluationStatus !== "EVALUABLE" || row.forecastStatus !== "VALID")) throw new Error(`Common-panel forecast ${row.predictionId} must be valid and evaluable`);
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
    modelName: oneOf(record.model_name, ["CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD", "HAR_X_OLS"], "model_name"),
    targetStartDate: dateString(record.target_start_date, "target_start_date"),
    targetEndDate: dateString(record.target_end_date, "target_end_date"),
    predictedVolAnnualized: parseFinite(record.predicted_vol_annualized, "predicted_vol_annualized"),
    targetRealizedVol5d: parseFinite(record.target_realized_vol_5d, "target_realized_vol_5d"),
    absoluteError: parseFinite(record.absolute_error, "absolute_error"),
  };
}

export function modelId(model: ModelName): "B0" | "B1" | "B2" | "B3" | "B4" {
  const ids: Record<ModelName, "B0" | "B1" | "B2" | "B3" | "B4"> = {
    CONSTANT_BASELINE: "B0",
    ROLLING_20D_BASELINE: "B1",
    STATIC_SGD: "B2",
    ONLINE_SGD: "B3",
    HAR_X_OLS: "B4",
  };
  return ids[model];
}

export function modelLabel(model: ModelName): string {
  const labels: Record<ModelName, string> = {
    CONSTANT_BASELINE: "Constant baseline",
    ROLLING_20D_BASELINE: "Rolling 20D baseline",
    STATIC_SGD: "Static SGD",
    ONLINE_SGD: "Online SGD",
    HAR_X_OLS: "HAR-X (OLS)",
  };
  return labels[model];
}

export function parseB4ComparisonRow(record: Record<string, string>): B4ComparisonRow {
  const comparisonId = oneOf(record.comparison_id, ["B4_VS_B2", "B4_VS_B3", "B4_VS_B1"], "comparison_id");
  const b4Model = oneOf(record.b4_model, ["HAR_X_OLS"], "b4_model");
  const comparatorModel = parseModelName(record.comparator_model, "comparator_model");
  const expectedComparator: Record<B4ComparisonRow["comparisonId"], ModelName> = {
    B4_VS_B2: "STATIC_SGD",
    B4_VS_B3: "ONLINE_SGD",
    B4_VS_B1: "ROLLING_20D_BASELINE",
  };
  if (comparatorModel !== expectedComparator[comparisonId]) throw new Error("B4 comparison identity does not match comparator model");
  if (record.split !== "test") throw new Error("B4 comparisons are Test-only");
  if (record.direction_definition !== "comparator_mae_minus_b4_mae (positive means HAR_X_OLS lower error)") throw new Error("B4 comparison direction is inconsistent");
  if (record.evaluation_scope !== "retrospective_test_non_hypothesis") throw new Error("B4 comparison scope is inconsistent");
  const ticker = parseTickerOrMacro(record.ticker, "ticker");
  const row: B4ComparisonRow = {
    comparisonId,
    b4Model,
    comparatorModel,
    split: "test",
    ticker,
    pairedN: parseCount(record.paired_n, "paired_n"),
    expectedEligibleAnchorCount: parseCount(record.expected_eligible_anchor_count, "expected_eligible_anchor_count"),
    pairedCoverage: parseCoverageRate(record.paired_coverage, "paired_coverage"),
    b4Mae: parseFinite(record.b4_mae, "b4_mae"),
    comparatorMae: parseFinite(record.comparator_mae, "comparator_mae"),
    deltaMaeComparatorMinusB4: parseSignedFinite(record.delta_mae_comparator_minus_b4, "delta_mae_comparator_minus_b4"),
    relativeImprovementPct: parseSignedFinite(record.relative_improvement_pct, "relative_improvement_pct"),
    b4Rmse: ticker === "MACRO" ? null : parseFinite(record.b4_rmse, "b4_rmse"),
    comparatorRmse: ticker === "MACRO" ? null : parseFinite(record.comparator_rmse, "comparator_rmse"),
    commonAllFiveN: parseCount(record.common_all_five_n, "common_all_five_n"),
    commonB0B3N: parseCount(record.common_b0_b3_n, "common_b0_b3_n"),
    evaluationScope: record.evaluation_scope,
  };
  if (row.pairedN === 0 || row.expectedEligibleAnchorCount === 0 || row.pairedN > row.expectedEligibleAnchorCount) throw new Error("B4 comparison counts are inconsistent");
  if (Math.abs(row.pairedCoverage - row.pairedN / row.expectedEligibleAnchorCount) > 1e-12) throw new Error("B4 comparison coverage does not match paired counts");
  if (Math.abs(row.deltaMaeComparatorMinusB4 - (row.comparatorMae - row.b4Mae)) > 1e-12) throw new Error("B4 comparison DeltaMAE does not match model MAEs");
  if (row.comparatorMae === 0) throw new Error("B4 comparison relative improvement is undefined when comparator MAE is zero");
  const expectedRelativeImprovement = (row.deltaMaeComparatorMinusB4 / row.comparatorMae) * 100;
  if (Math.abs(row.relativeImprovementPct - expectedRelativeImprovement) > 1e-9) throw new Error("B4 comparison relative improvement does not match model MAEs");
  if ((ticker === "MACRO") !== (row.b4Rmse === null && row.comparatorRmse === null)) throw new Error("Macro B4 RMSE must remain blank while ETF RMSE must be present");
  const expectedPairingPolicy = ticker === "MACRO"
    ? "equal ETF weight over per-ETF paired anchors"
    : "same prediction_date/ticker/split with mature target and both forecasts valid";
  if (record.pairing_policy !== expectedPairingPolicy) throw new Error("B4 comparison pairing policy is inconsistent");
  return row;
}
