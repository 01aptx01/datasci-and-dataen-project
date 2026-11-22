import { assertExactHeaders, parseCsv } from "./csv.js";
import { sha256 } from "./loadSnapshot.js";
import type { Ticker } from "./schemas.js";

export const POLICY_SCHEMA_VERSION = "1.2.0";
export const POLICY_VERSION = "1.0.0";

export const POLICY_EXPECTED_HEADERS = {
  policyForecasts: [
    "policy_prediction_id", "experiment_id", "policy_version", "prediction_date", "split", "ticker",
    "role", "model_id", "model_name", "champion_version_id", "model_state_sha256",
    "target_start_date", "target_end_date", "predicted_vol_annualized", "is_promoted_snapshot",
  ],
  policyEvaluations: [
    "policy_prediction_id", "experiment_id", "policy_version", "prediction_date", "evaluation_date", "split", "ticker",
    "role", "model_id", "model_name", "champion_version_id", "model_state_sha256",
    "target_start_date", "target_end_date", "predicted_vol_annualized", "target_realized_vol_5d",
    "absolute_error", "squared_error",
  ],
  policyDetectorStream: [
    "policy_prediction_id", "experiment_id", "policy_version", "ticker", "prediction_date", "evaluation_date",
    "feed_order_in_session", "champion_version_id", "champion_model_id", "champion_state_sha256",
    "absolute_error", "adwin_delta", "adwin_width", "adwin_estimation", "drift_detected",
    "drift_direction", "triggered_decision", "cooldown_remaining_before", "decision_event_id",
  ],
  policyDecisionEvents: [
    "event_id", "experiment_id", "policy_version", "ticker", "decision_date", "effective_from_date",
    "trigger_prediction_id", "trigger_prediction_date", "trigger_absolute_error", "drift_direction",
    "champion_version_id_before", "champion_model_id_before", "champion_state_sha256_before",
    "challenger_model_id", "challenger_state_sha256", "window_size", "minimum_pairs", "valid_pair_count",
    "champion_window_mae", "challenger_window_mae", "delta_mae_champion_minus_challenger",
    "relative_improvement", "min_relative_improvement", "cooldown_active", "cooldown_remaining_before",
    "decision_outcome", "decision_reason", "switched", "champion_version_id_after", "champion_model_id_after",
    "champion_state_sha256_after", "rollback_target_version_id", "rollback_target_model_id",
    "rollback_target_state_sha256",
  ],
  policyChampionTimeline: [
    "timeline_event_id", "experiment_id", "policy_version", "ticker", "event_type", "decision_event_id",
    "decision_date", "effective_from_date", "from_champion_version_id", "from_model_id", "from_state_sha256",
    "to_champion_version_id", "to_model_id", "to_state_sha256",
    "rollback_target_version_id", "rollback_target_model_id", "rollback_target_state_sha256", "reason",
  ],
  policyFailures: [
    "failure_id", "experiment_id", "policy_version", "session_date", "ticker", "role", "model_id",
    "champion_version_id", "stage", "reason", "raw_value",
  ],
  policyModelMetrics: [
    "split", "ticker", "system_id", "model_name", "paired_n", "expected_eligible_anchor_count",
    "paired_coverage", "mae", "rmse", "comparison_panel", "evaluation_scope",
  ],
  policyComparisons: [
    "comparison_id", "policy_system", "comparator_system", "comparator_model", "split", "ticker",
    "paired_n", "expected_eligible_anchor_count", "paired_coverage", "policy_mae", "comparator_mae",
    "delta_mae_comparator_minus_policy", "relative_improvement_pct", "policy_rmse", "comparator_rmse",
    "direction_definition", "pairing_policy", "evaluation_scope", "status",
  ],
  policyOperationsSummary: [
    "ticker", "initial_champion_model_id", "final_champion_model_id", "final_champion_version_id",
    "detector_observations", "alert_count", "decision_count", "promotion_count", "retained_count",
    "insufficient_pairs_count", "invalid_decision_count", "cooldown_suppressed_count",
    "b3_to_b3_promotion_count", "served_invalid_forecast_count", "shadow_invalid_forecast_count",
    "median_eval_to_alert_latency_sessions", "median_decision_to_effective_latency_sessions",
  ],
  policyCoverageSummary: [
    "ticker", "expected_eligible_prediction_anchors", "served_forecast_count", "shadow_forecast_count",
    "served_invalid_count", "shadow_invalid_count", "served_mature_evaluable_count",
    "shadow_mature_evaluable_count", "served_pending_count", "matched_all_systems_n",
    "served_forecast_coverage", "served_evaluation_coverage",
  ],
} as const;

export type PolicyFileKey = keyof typeof POLICY_EXPECTED_HEADERS;
export type PolicyRole = "SERVED_CHAMPION" | "SHADOW_B3";
export type PolicyModelId = "B0" | "B1" | "B2" | "B3";
export type PolicyDriftDirection = "error_increase" | "error_decrease" | "shift_neutral" | "no_signal";
export type PolicyDecisionOutcome = "promoted" | "retained" | "insufficient_pairs" | "invalid" | "cooldown_suppressed";
export type PolicyTimelineEventType = "INITIAL_CHAMPION_CUTOVER" | "PROMOTED_SNAPSHOT_ACTIVE_NEXT_SESSION";

export interface PolicyFileArtifact {
  path: string;
  sha256: string;
  bytes: number;
  rowCount: number;
  headers: string[];
}

export interface PolicySnapshotManifest {
  schemaVersion: "1.2.0";
  policyVersion: "1.0.0";
  policyEvaluationVersion: string;
  policyEvaluationId: string;
  policyReplayExperimentId: string;
  policyConfigFingerprint: string;
  replayConfigVersion: string;
  checkpointVersion: string;
  sourceBundleName: string;
  sourceZipSha256: string | null;
  sourceVerificationStatus: string;
  mode: "SIMULATED HISTORICAL REPLAY";
  exploratoryOnly: true;
  h1H3ConfirmatoryUnchanged: true;
  pointInTimeSourceAvailabilityVerified: false;
  championChallengerPolicy: Record<string, unknown>;
  initialChampion: Record<Ticker, "B0" | "B1" | "B2">;
  initialChampionSummary: Record<string, unknown>;
  replayWindow: Record<string, unknown>;
  limitations: string[];
  createdAtUtc: string;
  builtFromCommit: string;
  expectedCounts: {
    policyForecastRows: number;
    policyEvaluationRows: number;
    policyDetectorStreamRows: number;
    policyDecisionEventRows: number;
    policyChampionTimelineRows: number;
    policyFailureRows: number;
    policyModelMetricsRows: number;
    policyComparisonsRows: number;
    policyOperationsSummaryRows: number;
    policyCoverageSummaryRows: number;
    policyAlertCount: number;
    policyDecisionCount: number;
    policyPromotionCount: number;
  };
  reconciliationSha256: string;
  files: Record<PolicyFileKey, PolicyFileArtifact>;
}

export interface PolicyForecastRow {
  policyPredictionId: string;
  experimentId: string;
  policyVersion: string;
  predictionDate: string;
  split: string;
  ticker: Ticker;
  role: PolicyRole;
  modelId: PolicyModelId;
  modelName: string;
  championVersionId: string;
  modelStateSha256: string;
  targetStartDate: string;
  targetEndDate: string;
  predictedVolAnnualized: number;
  isPromotedSnapshot: boolean;
}

export interface PolicyEvaluationRow {
  policyPredictionId: string;
  experimentId: string;
  policyVersion: string;
  predictionDate: string;
  evaluationDate: string;
  split: string;
  ticker: Ticker;
  role: PolicyRole;
  modelId: PolicyModelId;
  modelName: string;
  championVersionId: string;
  modelStateSha256: string;
  targetStartDate: string;
  targetEndDate: string;
  predictedVolAnnualized: number;
  targetRealizedVol5d: number;
  absoluteError: number;
  squaredError: number;
}

export interface PolicyDetectorRow {
  policyPredictionId: string;
  experimentId: string;
  policyVersion: string;
  ticker: Ticker;
  predictionDate: string;
  evaluationDate: string;
  feedOrderInSession: number;
  championVersionId: string;
  championModelId: PolicyModelId;
  championStateSha256: string;
  absoluteError: number;
  adwinDelta: number;
  adwinWidth: number;
  adwinEstimation: number;
  driftDetected: boolean;
  driftDirection: PolicyDriftDirection;
  triggeredDecision: boolean;
  cooldownRemainingBefore: number;
  decisionEventId: string;
}

export interface PolicyDecisionEventRow {
  eventId: string;
  experimentId: string;
  policyVersion: string;
  ticker: Ticker;
  decisionDate: string;
  effectiveFromDate: string | null;
  triggerPredictionId: string;
  triggerPredictionDate: string;
  triggerAbsoluteError: number;
  driftDirection: PolicyDriftDirection;
  championVersionIdBefore: string;
  championModelIdBefore: PolicyModelId;
  championStateSha256Before: string;
  challengerModelId: string;
  challengerStateSha256: string;
  windowSize: number;
  minimumPairs: number;
  validPairCount: number;
  championWindowMae: number | null;
  challengerWindowMae: number | null;
  deltaMaeChampionMinusChallenger: number | null;
  relativeImprovement: number | null;
  minRelativeImprovement: number;
  cooldownActive: boolean;
  cooldownRemainingBefore: number;
  decisionOutcome: PolicyDecisionOutcome;
  decisionReason: string;
  switched: boolean;
  championVersionIdAfter: string;
  championModelIdAfter: PolicyModelId;
  championStateSha256After: string;
  rollbackTargetVersionId: string;
  rollbackTargetModelId: string;
  rollbackTargetStateSha256: string;
}

export interface PolicyTimelineRow {
  timelineEventId: string;
  experimentId: string;
  policyVersion: string;
  ticker: Ticker;
  eventType: PolicyTimelineEventType;
  decisionEventId: string;
  decisionDate: string;
  effectiveFromDate: string;
  fromChampionVersionId: string;
  fromModelId: string;
  fromStateSha256: string;
  toChampionVersionId: string;
  toModelId: PolicyModelId;
  toStateSha256: string;
  rollbackTargetVersionId: string;
  rollbackTargetModelId: string;
  rollbackTargetStateSha256: string;
  reason: string;
}

export interface PolicyFailureRow {
  failureId: string;
  experimentId: string;
  policyVersion: string;
  sessionDate: string;
  ticker: Ticker;
  role: PolicyRole;
  modelId: PolicyModelId;
  championVersionId: string;
  stage: string;
  reason: string;
  rawValue: string;
}

export interface PolicyModelMetricRow {
  split: string;
  ticker: Ticker | "MACRO";
  systemId: string;
  modelName: string;
  pairedN: number;
  expectedEligibleAnchorCount: number;
  pairedCoverage: number | null;
  mae: number | null;
  rmse: number | null;
  comparisonPanel: string;
  evaluationScope: string;
}

export interface PolicyComparisonRow {
  comparisonId: string;
  policySystem: string;
  comparatorSystem: string;
  comparatorModel: string;
  split: string;
  ticker: Ticker | "MACRO";
  pairedN: number;
  expectedEligibleAnchorCount: number;
  pairedCoverage: number | null;
  policyMae: number | null;
  comparatorMae: number | null;
  deltaMaeComparatorMinusPolicy: number | null;
  relativeImprovementPct: number | null;
  policyRmse: number | null;
  comparatorRmse: number | null;
  directionDefinition: string;
  pairingPolicy: string;
  evaluationScope: string;
  status: string;
}

export interface PolicyOperationsRow {
  ticker: Ticker | "MACRO";
  initialChampionModelId: string;
  finalChampionModelId: string;
  finalChampionVersionId: string;
  detectorObservations: number;
  alertCount: number;
  decisionCount: number;
  promotionCount: number;
  retainedCount: number;
  insufficientPairsCount: number;
  invalidDecisionCount: number;
  cooldownSuppressedCount: number;
  b3ToB3PromotionCount: number;
  servedInvalidForecastCount: number;
  shadowInvalidForecastCount: number;
  medianEvalToAlertLatencySessions: number | null;
  medianDecisionToEffectiveLatencySessions: number | null;
}

export interface PolicyCoverageRow {
  ticker: Ticker;
  expectedEligiblePredictionAnchors: number;
  servedForecastCount: number;
  shadowForecastCount: number;
  servedInvalidCount: number;
  shadowInvalidCount: number;
  servedMatureEvaluableCount: number;
  shadowMatureEvaluableCount: number;
  servedPendingCount: number;
  matchedAllSystemsN: number;
  servedForecastCoverage: number | null;
  servedEvaluationCoverage: number | null;
}

export interface PolicySnapshotReady {
  status: "ready";
  manifest: PolicySnapshotManifest;
  reconciliation: Record<string, unknown>;
  forecasts: PolicyForecastRow[];
  evaluations: PolicyEvaluationRow[];
  detectorStream: PolicyDetectorRow[];
  decisionEvents: PolicyDecisionEventRow[];
  championTimeline: PolicyTimelineRow[];
  failures: PolicyFailureRow[];
  modelMetrics: PolicyModelMetricRow[];
  comparisons: PolicyComparisonRow[];
  operationsSummary: PolicyOperationsRow[];
  coverageSummary: PolicyCoverageRow[];
}

export type PolicySnapshotState =
  | { status: "loading" }
  | { status: "missing"; message: string }
  | { status: "error"; message: string }
  | PolicySnapshotReady;

export interface PolicyDaySelection {
  ticker: Ticker;
  date: string;
  availableDates: string[];
  initialChampion: "B0" | "B1" | "B2";
  activeTimelineEntry: PolicyTimelineRow | null;
  pendingPromotionDecision: PolicyDecisionEventRow | null;
  servedForecast: PolicyForecastRow | null;
  shadowForecast: PolicyForecastRow | null;
  servedEvaluation: PolicyEvaluationRow | null;
  shadowEvaluation: PolicyEvaluationRow | null;
  servedFailure: PolicyFailureRow | null;
  shadowFailure: PolicyFailureRow | null;
  servedPendingLabel: boolean;
  detectorRowsOnDate: PolicyDetectorRow[];
  decisionsOnDate: PolicyDecisionEventRow[];
  tickerEvents: PolicyDecisionEventRow[];
  tickerTimeline: PolicyTimelineRow[];
  tickerOperations: PolicyOperationsRow | null;
  tickerCoverage: PolicyCoverageRow | null;
  tickerMetrics: PolicyModelMetricRow[];
  tickerComparisons: PolicyComparisonRow[];
  macroMetrics: PolicyModelMetricRow[];
  macroComparisons: PolicyComparisonRow[];
}

export class PolicySnapshotLoadError extends Error {
  constructor(message: string, readonly kind: "missing" | "integrity" | "network") {
    super(message);
    this.name = "PolicySnapshotLoadError";
  }
}

const TICKERS = new Set<Ticker>(["SPY", "IEF", "GLD"]);
const MODELS = new Set<PolicyModelId>(["B0", "B1", "B2", "B3"]);
const INITIAL_MODELS = new Set<"B0" | "B1" | "B2">(["B0", "B1", "B2"]);
const ROLES = new Set<PolicyRole>(["SERVED_CHAMPION", "SHADOW_B3"]);
const DIRECTIONS = new Set<PolicyDriftDirection>(["error_increase", "error_decrease", "shift_neutral", "no_signal"]);
const OUTCOMES = new Set<PolicyDecisionOutcome>(["promoted", "retained", "insufficient_pairs", "invalid", "cooldown_suppressed"]);
const FILE_KEYS = Object.keys(POLICY_EXPECTED_HEADERS) as PolicyFileKey[];
const COUNT_KEY_BY_FILE: Record<PolicyFileKey, keyof PolicySnapshotManifest["expectedCounts"]> = {
  policyForecasts: "policyForecastRows",
  policyEvaluations: "policyEvaluationRows",
  policyDetectorStream: "policyDetectorStreamRows",
  policyDecisionEvents: "policyDecisionEventRows",
  policyChampionTimeline: "policyChampionTimelineRows",
  policyFailures: "policyFailureRows",
  policyModelMetrics: "policyModelMetricsRows",
  policyComparisons: "policyComparisonsRows",
  policyOperationsSummary: "policyOperationsSummaryRows",
  policyCoverageSummary: "policyCoverageSummaryRows",
};

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new PolicySnapshotLoadError(`${label} must be an object.`, "integrity");
  }
  return value as Record<string, unknown>;
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new PolicySnapshotLoadError(`${label} must be a non-empty string.`, "integrity");
  }
  return value;
}

function requireHash(value: unknown, label: string): string {
  const text = requireString(value, label).toLowerCase();
  if (!/^[a-f0-9]{64}$/.test(text)) {
    throw new PolicySnapshotLoadError(`${label} must be a 64-char SHA-256 hex digest.`, "integrity");
  }
  return text;
}

function requireNonNegInt(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new PolicySnapshotLoadError(`${label} must be a non-negative integer.`, "integrity");
  }
  return value;
}

function parseDate(value: string, label: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || Number.isNaN(Date.parse(`${value}T00:00:00Z`)) || new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) !== value) {
    throw new PolicySnapshotLoadError(`${label} is not a valid ISO date: ${value}`, "integrity");
  }
  return value;
}

function parseBool(value: string, label: string): boolean {
  const lowered = value.trim().toLowerCase();
  if (lowered === "true") return true;
  if (lowered === "false") return false;
  throw new PolicySnapshotLoadError(`${label} is not a boolean: ${value}`, "integrity");
}

function parseFinite(value: string, label: string): number {
  const num = Number(value);
  if (!value.trim() || !Number.isFinite(num)) {
    throw new PolicySnapshotLoadError(`${label} is not a finite number: ${value}`, "integrity");
  }
  return num;
}

function parseNullableFinite(value: string, label: string): number | null {
  if (!value.trim()) return null;
  return parseFinite(value, label);
}

function parseIntString(value: string, label: string): number {
  if (!/^-?\d+$/.test(value.trim())) {
    throw new PolicySnapshotLoadError(`${label} is not an integer: ${value}`, "integrity");
  }
  return Number.parseInt(value.trim(), 10);
}

function parseTicker(value: string, label: string): Ticker {
  if (!TICKERS.has(value as Ticker)) throw new PolicySnapshotLoadError(`${label} has unsupported ticker: ${value}`, "integrity");
  return value as Ticker;
}

function parseTickerOrMacro(value: string, label: string): Ticker | "MACRO" {
  if (value === "MACRO") return "MACRO";
  return parseTicker(value, label);
}

function parseModelId(value: string, label: string): PolicyModelId {
  if (!MODELS.has(value as PolicyModelId)) throw new PolicySnapshotLoadError(`${label} has unsupported model_id: ${value}`, "integrity");
  return value as PolicyModelId;
}

function parseRole(value: string, label: string): PolicyRole {
  if (!ROLES.has(value as PolicyRole)) throw new PolicySnapshotLoadError(`${label} has unsupported role: ${value}`, "integrity");
  return value as PolicyRole;
}

function parseDirection(value: string, label: string): PolicyDriftDirection {
  if (!DIRECTIONS.has(value as PolicyDriftDirection)) throw new PolicySnapshotLoadError(`${label} has unsupported drift_direction: ${value}`, "integrity");
  return value as PolicyDriftDirection;
}

function parseOutcome(value: string, label: string): PolicyDecisionOutcome {
  if (!OUTCOMES.has(value as PolicyDecisionOutcome)) throw new PolicySnapshotLoadError(`${label} has unsupported decision_outcome: ${value}`, "integrity");
  return value as PolicyDecisionOutcome;
}

function sameStringArray(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function validateManifest(raw: unknown, expectedEvalId: string): PolicySnapshotManifest {
  const m = requireRecord(raw, "Policy snapshot manifest");
  if (m.schemaVersion !== POLICY_SCHEMA_VERSION) {
    throw new PolicySnapshotLoadError(`Unsupported policy snapshot schemaVersion: ${String(m.schemaVersion)}`, "integrity");
  }
  if (m.policyVersion !== POLICY_VERSION) {
    throw new PolicySnapshotLoadError(`Unsupported policyVersion: ${String(m.policyVersion)}`, "integrity");
  }
  const policyEvaluationId = requireString(m.policyEvaluationId, "policyEvaluationId");
  if (policyEvaluationId !== expectedEvalId) {
    throw new PolicySnapshotLoadError("Policy manifest evaluation ID disagrees with ACTIVE.json", "integrity");
  }
  if (m.mode !== "SIMULATED HISTORICAL REPLAY") {
    throw new PolicySnapshotLoadError("Policy manifest mode must be SIMULATED HISTORICAL REPLAY", "integrity");
  }
  if (m.exploratoryOnly !== true || m.h1H3ConfirmatoryUnchanged !== true || m.pointInTimeSourceAvailabilityVerified !== false) {
    throw new PolicySnapshotLoadError("Policy manifest governance flags violate exploratory/PIT contract", "integrity");
  }
  const initialRaw = requireRecord(m.initialChampion, "initialChampion");
  const initialChampion = {} as Record<Ticker, "B0" | "B1" | "B2">;
  for (const ticker of ["SPY", "IEF", "GLD"] as const) {
    const model = requireString(initialRaw[ticker], `initialChampion.${ticker}`);
    if (!INITIAL_MODELS.has(model as "B0" | "B1" | "B2")) {
      throw new PolicySnapshotLoadError(`Initial champion for ${ticker} must be B0/B1/B2, got ${model}`, "integrity");
    }
    initialChampion[ticker] = model as "B0" | "B1" | "B2";
  }
  if (Object.keys(initialRaw).length !== 3) {
    throw new PolicySnapshotLoadError("initialChampion must contain exactly SPY, IEF, GLD", "integrity");
  }
  const countsRaw = requireRecord(m.expectedCounts, "expectedCounts");
  const expectedCounts: PolicySnapshotManifest["expectedCounts"] = {
    policyForecastRows: requireNonNegInt(countsRaw.policyForecastRows, "policyForecastRows"),
    policyEvaluationRows: requireNonNegInt(countsRaw.policyEvaluationRows, "policyEvaluationRows"),
    policyDetectorStreamRows: requireNonNegInt(countsRaw.policyDetectorStreamRows, "policyDetectorStreamRows"),
    policyDecisionEventRows: requireNonNegInt(countsRaw.policyDecisionEventRows, "policyDecisionEventRows"),
    policyChampionTimelineRows: requireNonNegInt(countsRaw.policyChampionTimelineRows, "policyChampionTimelineRows"),
    policyFailureRows: requireNonNegInt(countsRaw.policyFailureRows, "policyFailureRows"),
    policyModelMetricsRows: requireNonNegInt(countsRaw.policyModelMetricsRows, "policyModelMetricsRows"),
    policyComparisonsRows: requireNonNegInt(countsRaw.policyComparisonsRows, "policyComparisonsRows"),
    policyOperationsSummaryRows: requireNonNegInt(countsRaw.policyOperationsSummaryRows, "policyOperationsSummaryRows"),
    policyCoverageSummaryRows: requireNonNegInt(countsRaw.policyCoverageSummaryRows, "policyCoverageSummaryRows"),
    policyAlertCount: requireNonNegInt(countsRaw.policyAlertCount, "policyAlertCount"),
    policyDecisionCount: requireNonNegInt(countsRaw.policyDecisionCount, "policyDecisionCount"),
    policyPromotionCount: requireNonNegInt(countsRaw.policyPromotionCount, "policyPromotionCount"),
  };
  const filesRaw = requireRecord(m.files, "files");
  if (Object.keys(filesRaw).length !== FILE_KEYS.length) {
    throw new PolicySnapshotLoadError("Policy snapshot manifest file list does not match contract", "integrity");
  }
  const files = {} as Record<PolicyFileKey, PolicyFileArtifact>;
  for (const key of FILE_KEYS) {
    const entry = requireRecord(filesRaw[key], `files.${key}`);
    const headers = entry.headers;
    if (!Array.isArray(headers) || !sameStringArray(headers as string[], POLICY_EXPECTED_HEADERS[key])) {
      throw new PolicySnapshotLoadError(`Policy manifest headers mismatch for ${key}`, "integrity");
    }
    const rowCount = requireNonNegInt(entry.rowCount, `files.${key}.rowCount`);
    if (rowCount !== expectedCounts[COUNT_KEY_BY_FILE[key]]) {
      throw new PolicySnapshotLoadError(`Policy manifest rowCount disagrees with expectedCounts for ${key}`, "integrity");
    }
    files[key] = {
      path: requireString(entry.path, `files.${key}.path`),
      sha256: requireHash(entry.sha256, `files.${key}.sha256`),
      bytes: requireNonNegInt(entry.bytes, `files.${key}.bytes`),
      rowCount,
      headers: headers as string[],
    };
  }
  const limitations = Array.isArray(m.limitations) && m.limitations.every((item) => typeof item === "string")
    ? (m.limitations as string[])
    : [];
  return {
    schemaVersion: POLICY_SCHEMA_VERSION,
    policyVersion: POLICY_VERSION,
    policyEvaluationVersion: requireString(m.policyEvaluationVersion, "policyEvaluationVersion"),
    policyEvaluationId,
    policyReplayExperimentId: requireString(m.policyReplayExperimentId, "policyReplayExperimentId"),
    policyConfigFingerprint: requireHash(m.policyConfigFingerprint, "policyConfigFingerprint"),
    replayConfigVersion: requireString(m.replayConfigVersion, "replayConfigVersion"),
    checkpointVersion: requireString(m.checkpointVersion, "checkpointVersion"),
    sourceBundleName: requireString(m.sourceBundleName, "sourceBundleName"),
    sourceZipSha256: m.sourceZipSha256 === null || m.sourceZipSha256 === undefined ? null : requireHash(m.sourceZipSha256, "sourceZipSha256"),
    sourceVerificationStatus: requireString(m.sourceVerificationStatus, "sourceVerificationStatus"),
    mode: "SIMULATED HISTORICAL REPLAY",
    exploratoryOnly: true,
    h1H3ConfirmatoryUnchanged: true,
    pointInTimeSourceAvailabilityVerified: false,
    championChallengerPolicy: requireRecord(m.championChallengerPolicy, "championChallengerPolicy"),
    initialChampion,
    initialChampionSummary: typeof m.initialChampionSummary === "object" && m.initialChampionSummary !== null && !Array.isArray(m.initialChampionSummary)
      ? (m.initialChampionSummary as Record<string, unknown>)
      : {},
    replayWindow: typeof m.replayWindow === "object" && m.replayWindow !== null && !Array.isArray(m.replayWindow)
      ? (m.replayWindow as Record<string, unknown>)
      : {},
    limitations,
    createdAtUtc: typeof m.createdAtUtc === "string" ? m.createdAtUtc : "unknown",
    builtFromCommit: typeof m.builtFromCommit === "string" ? m.builtFromCommit : "unknown",
    expectedCounts,
    reconciliationSha256: requireHash(m.reconciliationSha256, "reconciliationSha256"),
    files,
  };
}

function parseTable(text: string, key: PolicyFileKey, expectedRowCount: number): Record<string, string>[] {
  const parsed = parseCsv(text);
  assertExactHeaders(parsed.headers, [...POLICY_EXPECTED_HEADERS[key]], key);
  if (parsed.records.length !== expectedRowCount) {
    throw new PolicySnapshotLoadError(`${key} row count (${parsed.records.length}) does not match manifest (${expectedRowCount}).`, "integrity");
  }
  return parsed.records;
}

function parseAndReconcilePolicyTables(
  manifest: PolicySnapshotManifest,
  reconciliation: Record<string, unknown>,
  texts: Record<PolicyFileKey, string>,
): PolicySnapshotReady {
  const forecastRaw = parseTable(texts.policyForecasts, "policyForecasts", manifest.expectedCounts.policyForecastRows);
  const evalRaw = parseTable(texts.policyEvaluations, "policyEvaluations", manifest.expectedCounts.policyEvaluationRows);
  const detectorRaw = parseTable(texts.policyDetectorStream, "policyDetectorStream", manifest.expectedCounts.policyDetectorStreamRows);
  const decisionRaw = parseTable(texts.policyDecisionEvents, "policyDecisionEvents", manifest.expectedCounts.policyDecisionEventRows);
  const timelineRaw = parseTable(texts.policyChampionTimeline, "policyChampionTimeline", manifest.expectedCounts.policyChampionTimelineRows);
  const failureRaw = parseTable(texts.policyFailures, "policyFailures", manifest.expectedCounts.policyFailureRows);
  const metricRaw = parseTable(texts.policyModelMetrics, "policyModelMetrics", manifest.expectedCounts.policyModelMetricsRows);
  const comparisonRaw = parseTable(texts.policyComparisons, "policyComparisons", manifest.expectedCounts.policyComparisonsRows);
  const opsRaw = parseTable(texts.policyOperationsSummary, "policyOperationsSummary", manifest.expectedCounts.policyOperationsSummaryRows);
  const covRaw = parseTable(texts.policyCoverageSummary, "policyCoverageSummary", manifest.expectedCounts.policyCoverageSummaryRows);

  const forecastsById = new Map<string, PolicyForecastRow>();
  const forecasts: PolicyForecastRow[] = forecastRaw.map((row, idx) => {
    const id = requireString(row.policy_prediction_id, `policyForecasts[${idx}].policy_prediction_id`);
    if (forecastsById.has(id)) throw new PolicySnapshotLoadError(`Duplicate policy_prediction_id in policy_forecasts.csv: ${id}`, "integrity");
    const predictionDate = parseDate(row.prediction_date!, `policyForecasts[${idx}].prediction_date`);
    const targetStartDate = parseDate(row.target_start_date!, `policyForecasts[${idx}].target_start_date`);
    const targetEndDate = parseDate(row.target_end_date!, `policyForecasts[${idx}].target_end_date`);
    if (!(predictionDate <= targetStartDate && targetStartDate <= targetEndDate)) {
      throw new PolicySnapshotLoadError(`Invalid target date ordering in policy_forecasts.csv row ${idx + 2}`, "integrity");
    }
    const predicted = parseFinite(row.predicted_vol_annualized!, `policyForecasts[${idx}].predicted_vol_annualized`);
    if (predicted < 0) throw new PolicySnapshotLoadError(`Negative forecast in policy_forecasts.csv row ${idx + 2}`, "integrity");
    const parsed: PolicyForecastRow = {
      policyPredictionId: id,
      experimentId: row.experiment_id!,
      policyVersion: row.policy_version!,
      predictionDate,
      split: row.split!,
      ticker: parseTicker(row.ticker!, `policyForecasts[${idx}].ticker`),
      role: parseRole(row.role!, `policyForecasts[${idx}].role`),
      modelId: parseModelId(row.model_id!, `policyForecasts[${idx}].model_id`),
      modelName: row.model_name!,
      championVersionId: row.champion_version_id!,
      modelStateSha256: row.model_state_sha256!,
      targetStartDate,
      targetEndDate,
      predictedVolAnnualized: predicted,
      isPromotedSnapshot: parseBool(row.is_promoted_snapshot!, `policyForecasts[${idx}].is_promoted_snapshot`),
    };
    forecastsById.set(id, parsed);
    return parsed;
  });

  const evalsById = new Map<string, PolicyEvaluationRow>();
  const evaluations: PolicyEvaluationRow[] = evalRaw.map((row, idx) => {
    const id = requireString(row.policy_prediction_id, `policyEvaluations[${idx}].policy_prediction_id`);
    if (evalsById.has(id)) throw new PolicySnapshotLoadError(`Duplicate policy_prediction_id in policy_evaluations.csv: ${id}`, "integrity");
    const fc = forecastsById.get(id);
    const ticker = parseTicker(row.ticker!, `policyEvaluations[${idx}].ticker`);
    const role = parseRole(row.role!, `policyEvaluations[${idx}].role`);
    const predictionDate = parseDate(row.prediction_date!, `policyEvaluations[${idx}].prediction_date`);
    const evaluationDate = parseDate(row.evaluation_date!, `policyEvaluations[${idx}].evaluation_date`);
    const targetStartDate = parseDate(row.target_start_date!, `policyEvaluations[${idx}].target_start_date`);
    const targetEndDate = parseDate(row.target_end_date!, `policyEvaluations[${idx}].target_end_date`);
    if (!fc || fc.ticker !== ticker || fc.role !== role || fc.predictionDate !== predictionDate || fc.championVersionId !== row.champion_version_id) {
      throw new PolicySnapshotLoadError(`policy_evaluations.csv row ${idx + 2} does not match policy_forecasts.csv`, "integrity");
    }
    if (!(predictionDate <= targetEndDate && targetEndDate <= evaluationDate)) {
      throw new PolicySnapshotLoadError(`Invalid maturity date ordering in policy_evaluations.csv row ${idx + 2}`, "integrity");
    }
    const target = parseFinite(row.target_realized_vol_5d!, `policyEvaluations[${idx}].target_realized_vol_5d`);
    if (target < 0) throw new PolicySnapshotLoadError(`Negative realized target in policy_evaluations.csv row ${idx + 2}`, "integrity");
    const parsed: PolicyEvaluationRow = {
      policyPredictionId: id,
      experimentId: row.experiment_id!,
      policyVersion: row.policy_version!,
      predictionDate,
      evaluationDate,
      split: row.split!,
      ticker,
      role,
      modelId: parseModelId(row.model_id!, `policyEvaluations[${idx}].model_id`),
      modelName: row.model_name!,
      championVersionId: row.champion_version_id!,
      modelStateSha256: row.model_state_sha256!,
      targetStartDate,
      targetEndDate,
      predictedVolAnnualized: parseFinite(row.predicted_vol_annualized!, `policyEvaluations[${idx}].predicted_vol_annualized`),
      targetRealizedVol5d: target,
      absoluteError: parseFinite(row.absolute_error!, `policyEvaluations[${idx}].absolute_error`),
      squaredError: parseFinite(row.squared_error!, `policyEvaluations[${idx}].squared_error`),
    };
    evalsById.set(id, parsed);
    return parsed;
  });

  const streamIds = new Set<string>();
  const triggeredByKey = new Map<string, PolicyDetectorRow>();
  let alertCount = 0;
  const detectorStream: PolicyDetectorRow[] = detectorRaw.map((row, idx) => {
    const id = requireString(row.policy_prediction_id, `policyDetectorStream[${idx}].policy_prediction_id`);
    if (streamIds.has(id)) throw new PolicySnapshotLoadError(`Duplicate policy_prediction_id in policy_detector_stream.csv: ${id}`, "integrity");
    streamIds.add(id);
    const ev = evalsById.get(id);
    const ticker = parseTicker(row.ticker!, `policyDetectorStream[${idx}].ticker`);
    const predictionDate = parseDate(row.prediction_date!, `policyDetectorStream[${idx}].prediction_date`);
    const evaluationDate = parseDate(row.evaluation_date!, `policyDetectorStream[${idx}].evaluation_date`);
    const absError = parseFinite(row.absolute_error!, `policyDetectorStream[${idx}].absolute_error`);
    if (!ev || ev.role !== "SERVED_CHAMPION" || ev.ticker !== ticker || ev.predictionDate !== predictionDate || ev.evaluationDate !== evaluationDate || ev.championVersionId !== row.champion_version_id) {
      throw new PolicySnapshotLoadError(`policy_detector_stream.csv row ${idx + 2} does not match a served evaluation`, "integrity");
    }
    if (Math.abs(absError - ev.absoluteError) > 1e-12) {
      throw new PolicySnapshotLoadError(`policy_detector_stream.csv absolute_error disagrees with evaluation on row ${idx + 2}`, "integrity");
    }
    const driftDetected = parseBool(row.drift_detected!, `policyDetectorStream[${idx}].drift_detected`);
    const triggeredDecision = parseBool(row.triggered_decision!, `policyDetectorStream[${idx}].triggered_decision`);
    if (triggeredDecision && !driftDetected) {
      throw new PolicySnapshotLoadError(`Forged triggered_decision without drift_detected on row ${idx + 2}`, "integrity");
    }
    const adwinDelta = parseFinite(row.adwin_delta!, `policyDetectorStream[${idx}].adwin_delta`);
    const adwinWidth = parseIntString(row.adwin_width!, `policyDetectorStream[${idx}].adwin_width`);
    if (adwinDelta <= 0 || adwinWidth <= 0) {
      throw new PolicySnapshotLoadError(`Invalid ADWIN parameters on detector row ${idx + 2}`, "integrity");
    }
    const parsed: PolicyDetectorRow = {
      policyPredictionId: id,
      experimentId: row.experiment_id!,
      policyVersion: row.policy_version!,
      ticker,
      predictionDate,
      evaluationDate,
      feedOrderInSession: parseIntString(row.feed_order_in_session!, `policyDetectorStream[${idx}].feed_order_in_session`),
      championVersionId: row.champion_version_id!,
      championModelId: parseModelId(row.champion_model_id!, `policyDetectorStream[${idx}].champion_model_id`),
      championStateSha256: row.champion_state_sha256!,
      absoluteError: absError,
      adwinDelta,
      adwinWidth,
      adwinEstimation: parseFinite(row.adwin_estimation!, `policyDetectorStream[${idx}].adwin_estimation`),
      driftDetected,
      driftDirection: parseDirection(row.drift_direction!, `policyDetectorStream[${idx}].drift_direction`),
      triggeredDecision,
      cooldownRemainingBefore: parseIntString(row.cooldown_remaining_before!, `policyDetectorStream[${idx}].cooldown_remaining_before`),
      decisionEventId: row.decision_event_id!.trim(),
    };
    if (driftDetected) alertCount += 1;
    if (triggeredDecision) triggeredByKey.set(`${id}|${ticker}|${evaluationDate}`, parsed);
    return parsed;
  });

  const decisionsById = new Map<string, PolicyDecisionEventRow>();
  const promotedById = new Map<string, PolicyDecisionEventRow>();
  const decisionEvents: PolicyDecisionEventRow[] = decisionRaw.map((row, idx) => {
    const eventId = requireString(row.event_id, `policyDecisionEvents[${idx}].event_id`);
    if (decisionsById.has(eventId)) throw new PolicySnapshotLoadError(`Duplicate event_id in policy_decision_events.csv: ${eventId}`, "integrity");
    const ticker = parseTicker(row.ticker!, `policyDecisionEvents[${idx}].ticker`);
    const decisionDate = parseDate(row.decision_date!, `policyDecisionEvents[${idx}].decision_date`);
    const triggerPredictionId = requireString(row.trigger_prediction_id, `policyDecisionEvents[${idx}].trigger_prediction_id`);
    if (!triggeredByKey.has(`${triggerPredictionId}|${ticker}|${decisionDate}`)) {
      throw new PolicySnapshotLoadError(`Forged or ungrounded decision event ${eventId}: no matching ADWIN trigger`, "integrity");
    }
    const outcome = parseOutcome(row.decision_outcome!, `policyDecisionEvents[${idx}].decision_outcome`);
    const switched = parseBool(row.switched!, `policyDecisionEvents[${idx}].switched`);
    const effectiveRaw = row.effective_from_date!.trim();
    const effectiveFromDate = effectiveRaw ? parseDate(effectiveRaw, `policyDecisionEvents[${idx}].effective_from_date`) : null;
    const minimumPairs = parseIntString(row.minimum_pairs!, `policyDecisionEvents[${idx}].minimum_pairs`);
    const validPairCount = parseIntString(row.valid_pair_count!, `policyDecisionEvents[${idx}].valid_pair_count`);
    const minRel = parseFinite(row.min_relative_improvement!, `policyDecisionEvents[${idx}].min_relative_improvement`);
    const relImp = parseNullableFinite(row.relative_improvement!, `policyDecisionEvents[${idx}].relative_improvement`);
    const cooldownActive = parseBool(row.cooldown_active!, `policyDecisionEvents[${idx}].cooldown_active`);
    const cooldownBefore = parseIntString(row.cooldown_remaining_before!, `policyDecisionEvents[${idx}].cooldown_remaining_before`);
    const modelBefore = parseModelId(row.champion_model_id_before!, `policyDecisionEvents[${idx}].champion_model_id_before`);
    const modelAfter = parseModelId(row.champion_model_id_after!, `policyDecisionEvents[${idx}].champion_model_id_after`);

    if (outcome === "promoted") {
      if (!switched || modelAfter !== "B3") {
        throw new PolicySnapshotLoadError(`Promoted event ${eventId} must switch to a B3 snapshot`, "integrity");
      }
      if (!effectiveFromDate || effectiveFromDate <= decisionDate) {
        throw new PolicySnapshotLoadError(`Promoted event ${eventId} violates effective_from_date > decision_date`, "integrity");
      }
      if (validPairCount < minimumPairs || relImp === null || relImp < minRel) {
        throw new PolicySnapshotLoadError(`Promoted event ${eventId} violates pair count or improvement threshold`, "integrity");
      }
      if (row.rollback_target_version_id !== row.champion_version_id_before || row.rollback_target_state_sha256 !== row.champion_state_sha256_before) {
        throw new PolicySnapshotLoadError(`Promoted event ${eventId} rollback target disagrees with prior champion`, "integrity");
      }
    } else {
      if (switched || effectiveFromDate !== null) {
        throw new PolicySnapshotLoadError(`Non-promoted event ${eventId} must not switch or set effective_from_date`, "integrity");
      }
      if (row.champion_version_id_after !== row.champion_version_id_before || modelAfter !== modelBefore) {
        throw new PolicySnapshotLoadError(`Non-promoted event ${eventId} mutated champion identity`, "integrity");
      }
      if (outcome === "insufficient_pairs" && validPairCount >= minimumPairs) {
        throw new PolicySnapshotLoadError(`insufficient_pairs event ${eventId} has valid_pair_count >= minimum_pairs`, "integrity");
      }
      if (outcome === "cooldown_suppressed" && (!cooldownActive || cooldownBefore <= 0)) {
        throw new PolicySnapshotLoadError(`cooldown_suppressed event ${eventId} lacks active cooldown`, "integrity");
      }
    }

    const parsed: PolicyDecisionEventRow = {
      eventId,
      experimentId: row.experiment_id!,
      policyVersion: row.policy_version!,
      ticker,
      decisionDate,
      effectiveFromDate,
      triggerPredictionId,
      triggerPredictionDate: parseDate(row.trigger_prediction_date!, `policyDecisionEvents[${idx}].trigger_prediction_date`),
      triggerAbsoluteError: parseFinite(row.trigger_absolute_error!, `policyDecisionEvents[${idx}].trigger_absolute_error`),
      driftDirection: parseDirection(row.drift_direction!, `policyDecisionEvents[${idx}].drift_direction`),
      championVersionIdBefore: row.champion_version_id_before!,
      championModelIdBefore: modelBefore,
      championStateSha256Before: row.champion_state_sha256_before!,
      challengerModelId: row.challenger_model_id!,
      challengerStateSha256: row.challenger_state_sha256!,
      windowSize: parseIntString(row.window_size!, `policyDecisionEvents[${idx}].window_size`),
      minimumPairs,
      validPairCount,
      championWindowMae: parseNullableFinite(row.champion_window_mae!, `policyDecisionEvents[${idx}].champion_window_mae`),
      challengerWindowMae: parseNullableFinite(row.challenger_window_mae!, `policyDecisionEvents[${idx}].challenger_window_mae`),
      deltaMaeChampionMinusChallenger: parseNullableFinite(row.delta_mae_champion_minus_challenger!, `policyDecisionEvents[${idx}].delta_mae_champion_minus_challenger`),
      relativeImprovement: relImp,
      minRelativeImprovement: minRel,
      cooldownActive,
      cooldownRemainingBefore: cooldownBefore,
      decisionOutcome: outcome,
      decisionReason: row.decision_reason!,
      switched,
      championVersionIdAfter: row.champion_version_id_after!,
      championModelIdAfter: modelAfter,
      championStateSha256After: row.champion_state_sha256_after!,
      rollbackTargetVersionId: row.rollback_target_version_id!,
      rollbackTargetModelId: row.rollback_target_model_id!,
      rollbackTargetStateSha256: row.rollback_target_state_sha256!,
    };
    decisionsById.set(eventId, parsed);
    if (outcome === "promoted") promotedById.set(eventId, parsed);
    return parsed;
  });

  if (decisionsById.size !== triggeredByKey.size) {
    throw new PolicySnapshotLoadError(`Decision event count (${decisionsById.size}) disagrees with triggered ADWIN alerts (${triggeredByKey.size})`, "integrity");
  }

  const timelineIds = new Set<string>();
  const initTickers = new Set<Ticker>();
  const timelinePromoIds = new Set<string>();
  const championTimeline: PolicyTimelineRow[] = timelineRaw.map((row, idx) => {
    const id = requireString(row.timeline_event_id, `policyChampionTimeline[${idx}].timeline_event_id`);
    if (timelineIds.has(id)) throw new PolicySnapshotLoadError(`Duplicate timeline_event_id in policy_champion_timeline.csv: ${id}`, "integrity");
    timelineIds.add(id);
    const ticker = parseTicker(row.ticker!, `policyChampionTimeline[${idx}].ticker`);
    const eventType = row.event_type as PolicyTimelineEventType;
    const toModelId = parseModelId(row.to_model_id!, `policyChampionTimeline[${idx}].to_model_id`);
    const decisionDate = parseDate(row.decision_date!, `policyChampionTimeline[${idx}].decision_date`);
    const effectiveFromDate = parseDate(row.effective_from_date!, `policyChampionTimeline[${idx}].effective_from_date`);
    if (eventType === "INITIAL_CHAMPION_CUTOVER") {
      if (initTickers.has(ticker) || toModelId !== manifest.initialChampion[ticker]) {
        throw new PolicySnapshotLoadError(`Invalid INITIAL_CHAMPION_CUTOVER timeline entry for ${ticker}`, "integrity");
      }
      initTickers.add(ticker);
    } else if (eventType === "PROMOTED_SNAPSHOT_ACTIVE_NEXT_SESSION") {
      const dec = promotedById.get(row.decision_event_id!);
      if (!dec || timelinePromoIds.has(row.decision_event_id!)) {
        throw new PolicySnapshotLoadError(`Timeline promotion ${id} lacks a unique matching promoted decision`, "integrity");
      }
      if (effectiveFromDate <= decisionDate || effectiveFromDate !== dec.effectiveFromDate || row.to_champion_version_id !== dec.championVersionIdAfter || toModelId !== "B3") {
        throw new PolicySnapshotLoadError(`Timeline promotion ${id} disagrees with decision ${dec.eventId}`, "integrity");
      }
      timelinePromoIds.add(dec.eventId);
    } else {
      throw new PolicySnapshotLoadError(`Unsupported timeline event_type: ${String(row.event_type)}`, "integrity");
    }
    return {
      timelineEventId: id,
      experimentId: row.experiment_id!,
      policyVersion: row.policy_version!,
      ticker,
      eventType,
      decisionEventId: row.decision_event_id!,
      decisionDate,
      effectiveFromDate,
      fromChampionVersionId: row.from_champion_version_id!,
      fromModelId: row.from_model_id!,
      fromStateSha256: row.from_state_sha256!,
      toChampionVersionId: row.to_champion_version_id!,
      toModelId,
      toStateSha256: row.to_state_sha256!,
      rollbackTargetVersionId: row.rollback_target_version_id!,
      rollbackTargetModelId: row.rollback_target_model_id!,
      rollbackTargetStateSha256: row.rollback_target_state_sha256!,
      reason: row.reason!,
    };
  });

  if (initTickers.size !== 3 || timelinePromoIds.size !== promotedById.size) {
    throw new PolicySnapshotLoadError("Champion timeline does not reconcile 1:1 with initial champions and promotions", "integrity");
  }
  if (
    alertCount !== manifest.expectedCounts.policyAlertCount
    || decisionsById.size !== manifest.expectedCounts.policyDecisionCount
    || promotedById.size !== manifest.expectedCounts.policyPromotionCount
    || Number(reconciliation.total_alerts) !== alertCount
    || Number(reconciliation.total_decisions) !== decisionsById.size
    || Number(reconciliation.total_promotions) !== promotedById.size
  ) {
    throw new PolicySnapshotLoadError("Policy alert/decision/promotion counts disagree with manifest or reconciliation JSON", "integrity");
  }

  const failures: PolicyFailureRow[] = failureRaw.map((row, idx) => ({
    failureId: requireString(row.failure_id, `policyFailures[${idx}].failure_id`),
    experimentId: row.experiment_id!,
    policyVersion: row.policy_version!,
    sessionDate: parseDate(row.session_date!, `policyFailures[${idx}].session_date`),
    ticker: parseTicker(row.ticker!, `policyFailures[${idx}].ticker`),
    role: parseRole(row.role!, `policyFailures[${idx}].role`),
    modelId: parseModelId(row.model_id!, `policyFailures[${idx}].model_id`),
    championVersionId: row.champion_version_id!,
    stage: row.stage!,
    reason: row.reason!,
    rawValue: row.raw_value!,
  }));

  const modelMetrics: PolicyModelMetricRow[] = metricRaw.map((row, idx) => ({
    split: row.split!,
    ticker: parseTickerOrMacro(row.ticker!, `policyModelMetrics[${idx}].ticker`),
    systemId: row.system_id!,
    modelName: row.model_name!,
    pairedN: parseIntString(row.paired_n!, `policyModelMetrics[${idx}].paired_n`),
    expectedEligibleAnchorCount: parseIntString(row.expected_eligible_anchor_count!, `policyModelMetrics[${idx}].expected_eligible_anchor_count`),
    pairedCoverage: parseNullableFinite(row.paired_coverage!, `policyModelMetrics[${idx}].paired_coverage`),
    mae: parseNullableFinite(row.mae!, `policyModelMetrics[${idx}].mae`),
    rmse: parseNullableFinite(row.rmse!, `policyModelMetrics[${idx}].rmse`),
    comparisonPanel: row.comparison_panel!,
    evaluationScope: row.evaluation_scope!,
  }));

  const comparisons: PolicyComparisonRow[] = comparisonRaw.map((row, idx) => ({
    comparisonId: row.comparison_id!,
    policySystem: row.policy_system!,
    comparatorSystem: row.comparator_system!,
    comparatorModel: row.comparator_model!,
    split: row.split!,
    ticker: parseTickerOrMacro(row.ticker!, `policyComparisons[${idx}].ticker`),
    pairedN: parseIntString(row.paired_n!, `policyComparisons[${idx}].paired_n`),
    expectedEligibleAnchorCount: parseIntString(row.expected_eligible_anchor_count!, `policyComparisons[${idx}].expected_eligible_anchor_count`),
    pairedCoverage: parseNullableFinite(row.paired_coverage!, `policyComparisons[${idx}].paired_coverage`),
    policyMae: parseNullableFinite(row.policy_mae!, `policyComparisons[${idx}].policy_mae`),
    comparatorMae: parseNullableFinite(row.comparator_mae!, `policyComparisons[${idx}].comparator_mae`),
    deltaMaeComparatorMinusPolicy: parseNullableFinite(row.delta_mae_comparator_minus_policy!, `policyComparisons[${idx}].delta_mae_comparator_minus_policy`),
    relativeImprovementPct: parseNullableFinite(row.relative_improvement_pct!, `policyComparisons[${idx}].relative_improvement_pct`),
    policyRmse: parseNullableFinite(row.policy_rmse!, `policyComparisons[${idx}].policy_rmse`),
    comparatorRmse: parseNullableFinite(row.comparator_rmse!, `policyComparisons[${idx}].comparator_rmse`),
    directionDefinition: row.direction_definition!,
    pairingPolicy: row.pairing_policy!,
    evaluationScope: row.evaluation_scope!,
    status: row.status!,
  }));

  const operationsSummary: PolicyOperationsRow[] = opsRaw.map((row, idx) => ({
    ticker: parseTickerOrMacro(row.ticker!, `policyOperationsSummary[${idx}].ticker`),
    initialChampionModelId: row.initial_champion_model_id!,
    finalChampionModelId: row.final_champion_model_id!,
    finalChampionVersionId: row.final_champion_version_id!,
    detectorObservations: parseIntString(row.detector_observations!, `policyOperationsSummary[${idx}].detector_observations`),
    alertCount: parseIntString(row.alert_count!, `policyOperationsSummary[${idx}].alert_count`),
    decisionCount: parseIntString(row.decision_count!, `policyOperationsSummary[${idx}].decision_count`),
    promotionCount: parseIntString(row.promotion_count!, `policyOperationsSummary[${idx}].promotion_count`),
    retainedCount: parseIntString(row.retained_count!, `policyOperationsSummary[${idx}].retained_count`),
    insufficientPairsCount: parseIntString(row.insufficient_pairs_count!, `policyOperationsSummary[${idx}].insufficient_pairs_count`),
    invalidDecisionCount: parseIntString(row.invalid_decision_count!, `policyOperationsSummary[${idx}].invalid_decision_count`),
    cooldownSuppressedCount: parseIntString(row.cooldown_suppressed_count!, `policyOperationsSummary[${idx}].cooldown_suppressed_count`),
    b3ToB3PromotionCount: parseIntString(row.b3_to_b3_promotion_count!, `policyOperationsSummary[${idx}].b3_to_b3_promotion_count`),
    servedInvalidForecastCount: parseIntString(row.served_invalid_forecast_count!, `policyOperationsSummary[${idx}].served_invalid_forecast_count`),
    shadowInvalidForecastCount: parseIntString(row.shadow_invalid_forecast_count!, `policyOperationsSummary[${idx}].shadow_invalid_forecast_count`),
    medianEvalToAlertLatencySessions: parseNullableFinite(row.median_eval_to_alert_latency_sessions!, `policyOperationsSummary[${idx}].median_eval_to_alert_latency_sessions`),
    medianDecisionToEffectiveLatencySessions: parseNullableFinite(row.median_decision_to_effective_latency_sessions!, `policyOperationsSummary[${idx}].median_decision_to_effective_latency_sessions`),
  }));

  const coverageSummary: PolicyCoverageRow[] = covRaw.map((row, idx) => ({
    ticker: parseTicker(row.ticker!, `policyCoverageSummary[${idx}].ticker`),
    expectedEligiblePredictionAnchors: parseIntString(row.expected_eligible_prediction_anchors!, `policyCoverageSummary[${idx}].expected_eligible_prediction_anchors`),
    servedForecastCount: parseIntString(row.served_forecast_count!, `policyCoverageSummary[${idx}].served_forecast_count`),
    shadowForecastCount: parseIntString(row.shadow_forecast_count!, `policyCoverageSummary[${idx}].shadow_forecast_count`),
    servedInvalidCount: parseIntString(row.served_invalid_count!, `policyCoverageSummary[${idx}].served_invalid_count`),
    shadowInvalidCount: parseIntString(row.shadow_invalid_count!, `policyCoverageSummary[${idx}].shadow_invalid_count`),
    servedMatureEvaluableCount: parseIntString(row.served_mature_evaluable_count!, `policyCoverageSummary[${idx}].served_mature_evaluable_count`),
    shadowMatureEvaluableCount: parseIntString(row.shadow_mature_evaluable_count!, `policyCoverageSummary[${idx}].shadow_mature_evaluable_count`),
    servedPendingCount: parseIntString(row.served_pending_count!, `policyCoverageSummary[${idx}].served_pending_count`),
    matchedAllSystemsN: parseIntString(row.matched_all_systems_n!, `policyCoverageSummary[${idx}].matched_all_systems_n`),
    servedForecastCoverage: parseNullableFinite(row.served_forecast_coverage!, `policyCoverageSummary[${idx}].served_forecast_coverage`),
    servedEvaluationCoverage: parseNullableFinite(row.served_evaluation_coverage!, `policyCoverageSummary[${idx}].served_evaluation_coverage`),
  }));

  return {
    status: "ready",
    manifest,
    reconciliation,
    forecasts,
    evaluations,
    detectorStream,
    decisionEvents,
    championTimeline,
    failures,
    modelMetrics,
    comparisons,
    operationsSummary,
    coverageSummary,
  };
}

export async function loadPolicySnapshot(
  fetcher: typeof fetch = fetch,
  baseHref: string = document.baseURI,
): Promise<PolicySnapshotState> {
  const assetUrl = (relative: string) => new URL(relative, baseHref).toString();
  let activeResponse: Response;
  try {
    activeResponse = await fetcher(assetUrl("snapshots/policy/ACTIVE.json"));
  } catch {
    return { status: "missing", message: "ยังไม่มี sidecar ของ Champion–Challenger Policy ใน build นี้" };
  }
  if (activeResponse.status === 404) {
    return { status: "missing", message: "ยังไม่ได้เผยแพร่ sidecar ของ Champion–Challenger Policy (snapshots/policy/ACTIVE.json)" };
  }
  if (!activeResponse.ok) {
    return { status: "error", message: `โหลด policy ACTIVE.json ไม่สำเร็จ (HTTP ${activeResponse.status})` };
  }

  try {
    const active = requireRecord(await activeResponse.json(), "Policy ACTIVE.json");
    if (active.schemaVersion !== POLICY_SCHEMA_VERSION) {
      throw new PolicySnapshotLoadError(`Unsupported policy ACTIVE schemaVersion: ${String(active.schemaVersion)}`, "integrity");
    }
    const evalId = requireString(active.activePolicyEvaluationId, "activePolicyEvaluationId");
    const manifestPath = requireString(active.manifestPath, "manifestPath");
    const manifestSha256 = requireHash(active.manifestSha256, "manifestSha256");
    if (!manifestPath.startsWith(`${evalId}/`) || manifestPath.includes("..")) {
      throw new PolicySnapshotLoadError("Policy ACTIVE.json manifestPath is unsafe or inconsistent", "integrity");
    }
    const manifestResponse = await fetcher(assetUrl(`snapshots/policy/${manifestPath}`));
    if (manifestResponse.status === 404) {
      throw new PolicySnapshotLoadError("Policy snapshot manifest is missing from snapshots/policy/", "missing");
    }
    if (!manifestResponse.ok) {
      throw new PolicySnapshotLoadError(`Policy manifest could not be loaded (HTTP ${manifestResponse.status})`, "network");
    }
    const manifestBytes = new Uint8Array(await manifestResponse.arrayBuffer());
    if (await sha256(manifestBytes) !== manifestSha256) {
      throw new PolicySnapshotLoadError("Policy manifest SHA-256 mismatch against ACTIVE.json", "integrity");
    }
    const manifest = validateManifest(JSON.parse(new TextDecoder("utf-8").decode(manifestBytes)), evalId);
    const directory = `snapshots/policy/${evalId}`;

    const recResponse = await fetcher(assetUrl(`${directory}/policy_reconciliation.json`));
    if (!recResponse.ok) {
      throw new PolicySnapshotLoadError(`Policy reconciliation JSON could not be loaded (HTTP ${recResponse.status})`, recResponse.status === 404 ? "missing" : "network");
    }
    const recBytes = new Uint8Array(await recResponse.arrayBuffer());
    if (await sha256(recBytes) !== manifest.reconciliationSha256) {
      throw new PolicySnapshotLoadError("policy_reconciliation.json SHA-256 mismatch", "integrity");
    }
    const reconciliation = requireRecord(JSON.parse(new TextDecoder("utf-8").decode(recBytes)), "policy_reconciliation.json");

    const responses = await Promise.all(FILE_KEYS.map((key) => fetcher(assetUrl(`${directory}/${manifest.files[key].path}`))));
    if (responses.some((response) => response.status === 404)) {
      throw new PolicySnapshotLoadError("A required policy snapshot CSV is missing.", "missing");
    }
    if (responses.some((response) => !response.ok)) {
      throw new PolicySnapshotLoadError("A policy snapshot CSV could not be loaded.", "network");
    }
    const bytesList = await Promise.all(responses.map((response) => response.arrayBuffer().then((buffer) => new Uint8Array(buffer))));
    const decoder = new TextDecoder("utf-8");
    const texts = {} as Record<PolicyFileKey, string>;
    for (let index = 0; index < FILE_KEYS.length; index += 1) {
      const key = FILE_KEYS[index]!;
      const bytes = bytesList[index]!;
      const expected = manifest.files[key];
      if (bytes.byteLength !== expected.bytes) {
        throw new PolicySnapshotLoadError(`Byte count mismatch for ${expected.path}`, "integrity");
      }
      if (await sha256(bytes) !== expected.sha256) {
        throw new PolicySnapshotLoadError(`SHA-256 mismatch for ${expected.path}`, "integrity");
      }
      texts[key] = decoder.decode(bytes);
    }
    return parseAndReconcilePolicyTables(manifest, reconciliation, texts);
  } catch (error) {
    if (error instanceof PolicySnapshotLoadError && error.kind === "missing") {
      return { status: "missing", message: error.message };
    }
    return { status: "error", message: error instanceof Error ? error.message : "Policy snapshot verification failed" };
  }
}

export function selectPolicyDayState(
  snapshot: PolicySnapshotReady,
  ticker: Ticker,
  requestedDate: string,
): PolicyDaySelection {
  const dateSet = new Set<string>();
  for (const row of snapshot.forecasts) if (row.ticker === ticker) dateSet.add(row.predictionDate);
  for (const row of snapshot.failures) if (row.ticker === ticker) dateSet.add(row.sessionDate);
  for (const row of snapshot.detectorStream) if (row.ticker === ticker) dateSet.add(row.evaluationDate);
  for (const row of snapshot.decisionEvents) if (row.ticker === ticker) dateSet.add(row.decisionDate);
  const availableDates = [...dateSet].sort();
  const date = requestedDate && availableDates.includes(requestedDate)
    ? requestedDate
    : availableDates[availableDates.length - 1] ?? requestedDate;

  const tickerTimeline = snapshot.championTimeline
    .filter((row) => row.ticker === ticker)
    .sort((left, right) => left.effectiveFromDate.localeCompare(right.effectiveFromDate) || left.timelineEventId.localeCompare(right.timelineEventId));
  const activeCandidates = tickerTimeline.filter((row) => row.effectiveFromDate <= date);
  const activeTimelineEntry = activeCandidates[activeCandidates.length - 1] ?? tickerTimeline[0] ?? null;

  const tickerEvents = snapshot.decisionEvents
    .filter((row) => row.ticker === ticker)
    .sort((left, right) => left.decisionDate.localeCompare(right.decisionDate) || left.eventId.localeCompare(right.eventId));
  const decisionsOnDate = tickerEvents.filter((row) => row.decisionDate === date);
  const pendingPromotionDecision = tickerEvents.find(
    (row) => row.decisionOutcome === "promoted" && row.decisionDate <= date && row.effectiveFromDate !== null && row.effectiveFromDate > date,
  ) ?? null;

  const servedForecast = snapshot.forecasts.find((row) => row.ticker === ticker && row.predictionDate === date && row.role === "SERVED_CHAMPION") ?? null;
  const shadowForecast = snapshot.forecasts.find((row) => row.ticker === ticker && row.predictionDate === date && row.role === "SHADOW_B3") ?? null;
  const servedEvaluation = servedForecast
    ? snapshot.evaluations.find((row) => row.policyPredictionId === servedForecast.policyPredictionId) ?? null
    : null;
  const shadowEvaluation = shadowForecast
    ? snapshot.evaluations.find((row) => row.policyPredictionId === shadowForecast.policyPredictionId) ?? null
    : null;
  const servedFailure = snapshot.failures.find((row) => row.ticker === ticker && row.sessionDate === date && row.role === "SERVED_CHAMPION") ?? null;
  const shadowFailure = snapshot.failures.find((row) => row.ticker === ticker && row.sessionDate === date && row.role === "SHADOW_B3") ?? null;
  const servedPendingLabel = servedForecast !== null && servedEvaluation === null && servedFailure === null;
  const detectorRowsOnDate = snapshot.detectorStream
    .filter((row) => row.ticker === ticker && row.evaluationDate === date)
    .sort((left, right) => left.feedOrderInSession - right.feedOrderInSession);

  return {
    ticker,
    date,
    availableDates,
    initialChampion: snapshot.manifest.initialChampion[ticker],
    activeTimelineEntry,
    pendingPromotionDecision,
    servedForecast,
    shadowForecast,
    servedEvaluation,
    shadowEvaluation,
    servedFailure,
    shadowFailure,
    servedPendingLabel,
    detectorRowsOnDate,
    decisionsOnDate,
    tickerEvents,
    tickerTimeline,
    tickerOperations: snapshot.operationsSummary.find((row) => row.ticker === ticker) ?? null,
    tickerCoverage: snapshot.coverageSummary.find((row) => row.ticker === ticker) ?? null,
    tickerMetrics: snapshot.modelMetrics.filter((row) => row.ticker === ticker),
    tickerComparisons: snapshot.comparisons.filter((row) => row.ticker === ticker),
    macroMetrics: snapshot.modelMetrics.filter((row) => row.ticker === "MACRO"),
    macroComparisons: snapshot.comparisons.filter((row) => row.ticker === "MACRO"),
  };
}
