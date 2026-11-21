import { assertExactHeaders, parseCsv } from "./csv.js";
import { computePortfolioVolatility } from "./portfolio.js";
import {
  parseEvaluationRow,
  parseForecastAuditRow,
  parseModelMetricRow,
  parsePairComparisonRow,
  parseCoverageRow,
  parsePortfolioRiskRow,
  parseRollingMae20Row,
  parseDriftTimelineRow,
  parseH1ScatterRow,
  parseH1ResultRow,
  parseH1SensitivityRow,
  parseHypothesisResultRow,
  parseBootstrapDiagnosticRow,
  parseHighVolatilityMetricRow,
  parsePolicy,
  parseSnapshotManifest,
  type EvaluationRow,
  type ForecastAuditRow,
  type SnapshotManifest,
  type SnapshotPolicy,
  type Ticker,
  type ModelName,
  type ModelMetricRow,
  type PairComparisonRow,
  type CoverageRow,
  type PortfolioRiskRow,
  type RollingMae20Row,
  type DriftTimelineRow,
  type H1ScatterRow,
  type H1ResultRow,
  type H1SensitivityRow,
  type HypothesisResultRow,
  type BootstrapDiagnosticRow,
  type HighVolatilityMetricRow,
} from "./schemas.js";

export type SnapshotState =
  | { status: "loading" }
  | {
      status: "ready";
      policy: SnapshotPolicy;
      manifest: SnapshotManifest;
      sessions: ForecastAuditRow[];
      forecasts: ForecastAuditRow[];
      evaluations: Map<string, EvaluationRow>;
      modelMetrics: ModelMetricRow[];
      pairComparisons: PairComparisonRow[];
      coverage: CoverageRow[];
      portfolioRisk: PortfolioRiskRow[];
      rollingMae20: RollingMae20Row[];
      driftTimeline: DriftTimelineRow[];
      h1Scatter: H1ScatterRow[];
      h1Results: H1ResultRow[];
      h1Sensitivity: H1SensitivityRow[];
      hypothesisResults: HypothesisResultRow[];
      bootstrapDiagnostics: BootstrapDiagnosticRow[];
      highVolatilityMetrics: HighVolatilityMetricRow[];
    }
  | { status: "missing"; message: string }
  | { status: "error"; message: string };

export class SnapshotLoadError extends Error {
  constructor(message: string, readonly kind: "missing" | "integrity" | "network") {
    super(message);
    this.name = "SnapshotLoadError";
  }
}

export interface ForecastFilter {
  split: "test" | "validation";
  ticker: Ticker;
  models: ModelName[];
  status: "all" | "mature" | "pending" | "invalid";
  from: string;
  to: string;
}

export async function sha256(bytes: ArrayBuffer | Uint8Array): Promise<string> {
  const payload = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const exactBuffer = new ArrayBuffer(payload.byteLength);
  new Uint8Array(exactBuffer).set(payload);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", exactBuffer);
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

export function requireSnapshotFiles(files: Record<string, Uint8Array | undefined>, required: string[]): void {
  const missing = required.filter((name) => files[name] === undefined);
  if (missing.length > 0) throw new SnapshotLoadError(`Required snapshot file missing: ${missing.join(", ")}`, "missing");
}

export function parseForecastAudit(text: string, policy: SnapshotPolicy): ForecastAuditRow[] {
  const table = parseCsv(text);
  assertExactHeaders(table.headers, policy.expectedHeaders.forecastAudit, "forecast_audit.csv");
  return table.records.map((record, index) => {
    try {
      return parseForecastAuditRow(record);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Invalid source row";
      throw new SnapshotLoadError(`forecast_audit.csv row ${index + 2}: ${detail}`, "integrity");
    }
  });
}

export function parseEvaluation(text: string, policy: SnapshotPolicy): EvaluationRow[] {
  const table = parseCsv(text);
  assertExactHeaders(table.headers, policy.expectedHeaders.evaluation, "evaluation.csv");
  return table.records.map((record, index) => {
    try {
      return parseEvaluationRow(record);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Invalid source row";
      throw new SnapshotLoadError(`evaluation.csv row ${index + 2}: ${detail}`, "integrity");
    }
  });
}

function parseRows<T>(text: string, expected: string[], filename: string, parser: (record: Record<string, string>) => T): T[] {
  const table = parseCsv(text);
  assertExactHeaders(table.headers, expected, filename);
  return table.records.map((record, index) => {
    try {
      return parser(record);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Invalid source row";
      throw new SnapshotLoadError(`${filename} row ${index + 2}: ${detail}`, "integrity");
    }
  });
}

export function parseModelMetrics(text: string, policy: SnapshotPolicy): ModelMetricRow[] {
  return parseRows(text, policy.expectedHeaders.modelMetrics, "model_metrics.csv", parseModelMetricRow);
}

export function parsePairComparisons(text: string, policy: SnapshotPolicy): PairComparisonRow[] {
  return parseRows(text, policy.expectedHeaders.pairComparisons, "pair_comparisons.csv", parsePairComparisonRow);
}

export function parseCoverage(text: string, policy: SnapshotPolicy): CoverageRow[] {
  return parseRows(text, policy.expectedHeaders.coverage, "coverage.csv", parseCoverageRow);
}

export function parsePortfolioRisk(text: string, policy: SnapshotPolicy): PortfolioRiskRow[] {
  return parseRows(text, policy.expectedHeaders.portfolioRisk, "portfolio_risk.csv", parsePortfolioRiskRow);
}

export function parseRollingMae20(text: string, policy: SnapshotPolicy): RollingMae20Row[] {
  return parseRows(text, policy.expectedHeaders.rollingMae20, "rolling_mae20.csv", parseRollingMae20Row);
}

export function parseDriftTimeline(text: string, policy: SnapshotPolicy): DriftTimelineRow[] {
  return parseRows(text, policy.expectedHeaders.driftErrorTimeline, "drift_error_timeline.csv", parseDriftTimelineRow);
}

export function parseH1Scatter(text: string, policy: SnapshotPolicy): H1ScatterRow[] {
  return parseRows(text, policy.expectedHeaders.h1ScatterData, "H1_scatter_data.csv", parseH1ScatterRow);
}

export function parseH1Results(text: string, policy: SnapshotPolicy): H1ResultRow[] {
  return parseRows(text, policy.expectedHeaders.h1Results, "H1_results.csv", parseH1ResultRow);
}

export function parseH1Sensitivity(text: string, policy: SnapshotPolicy): H1SensitivityRow[] {
  return parseRows(text, policy.expectedHeaders.h1Sensitivity, "H1_sensitivity.csv", parseH1SensitivityRow);
}

export function parseHypothesisResults(text: string, policy: SnapshotPolicy): HypothesisResultRow[] {
  return parseRows(text, policy.expectedHeaders.hypothesisResults, "hypothesis_results.csv", parseHypothesisResultRow);
}

export function parseBootstrapDiagnostics(text: string, policy: SnapshotPolicy): BootstrapDiagnosticRow[] {
  return parseRows(text, policy.expectedHeaders.bootstrapDiagnostics, "bootstrap_diagnostics.csv", parseBootstrapDiagnosticRow);
}

export function parseHighVolatilityMetrics(text: string, policy: SnapshotPolicy): HighVolatilityMetricRow[] {
  return parseRows(text, policy.expectedHeaders.highVolatilityMetrics, "high_volatility_metrics.csv", parseHighVolatilityMetricRow);
}

export async function verifySnapshotFileBytes(
  manifest: SnapshotManifest,
  policy: SnapshotPolicy,
  files: Record<string, Uint8Array | undefined>,
): Promise<void> {
  const artifacts = (Object.keys(policy.publicOutputs) as (keyof SnapshotPolicy["publicOutputs"])[]).map((key) => ({
    artifact: manifest.files[key],
    expected: policy.memberSha256[policy.members[key]],
  }));
  requireSnapshotFiles(files, artifacts.map(({ artifact }) => artifact.path));
  for (const { artifact, expected } of artifacts) {
    const bytes = files[artifact.path];
    if (!bytes) throw new SnapshotLoadError(`Required snapshot file missing: ${artifact.path}`, "missing");
    const digest = await sha256(bytes);
    if (digest !== artifact.sha256 || digest !== expected) throw new SnapshotLoadError(`SHA-256 mismatch for ${artifact.path}`, "integrity");
    if (bytes.byteLength !== artifact.bytes) throw new SnapshotLoadError(`Byte length mismatch for ${artifact.path}`, "integrity");
  }
}

function validateEvaluationJoin(auditRows: ForecastAuditRow[], evaluationRows: EvaluationRow[]): Map<string, EvaluationRow> {
  const evaluationById = new Map<string, EvaluationRow>();
  for (const evaluation of evaluationRows) {
    if (evaluationById.has(evaluation.predictionId)) throw new SnapshotLoadError(`Duplicate evaluation prediction_id: ${evaluation.predictionId}`, "integrity");
    evaluationById.set(evaluation.predictionId, evaluation);
  }
  const auditById = new Map(auditRows.filter((row) => row.split === "test").map((row) => [row.predictionId, row]));
  for (const evaluation of evaluationRows) {
    const audit = auditById.get(evaluation.predictionId);
    if (!audit || audit.evaluationStatus !== "EVALUABLE") throw new SnapshotLoadError(`evaluation.csv row has no matching evaluable Test forecast: ${evaluation.predictionId}`, "integrity");
    if (
      audit.predictionDate !== evaluation.predictionDate || audit.ticker !== evaluation.ticker || audit.modelName !== evaluation.modelName ||
      audit.targetStartDate !== evaluation.targetStartDate || audit.targetEndDate !== evaluation.targetEndDate ||
      !sameNumber(audit.targetRealizedVol5d, evaluation.targetRealizedVol5d) ||
      !sameNumber(audit.absoluteError, evaluation.absoluteError) ||
      !sameNumber(audit.predictedVolAnnualized, evaluation.predictedVolAnnualized)
    ) throw new SnapshotLoadError(`evaluation.csv values disagree with forecast audit for ${evaluation.predictionId}`, "integrity");
  }
  const evaluableTest = auditRows.filter((row) => row.split === "test" && row.evaluationStatus === "EVALUABLE");
  if (evaluableTest.length !== evaluationRows.length) throw new SnapshotLoadError("Test evaluation rows do not cover the verified evaluable forecast set", "integrity");
  return evaluationById;
}

function sameNumber(left: number | null, right: number): boolean {
  return left !== null && Math.abs(left - right) <= 1e-12;
}

function verifyCounts(rows: ForecastAuditRow[], evaluations: EvaluationRow[], manifest: SnapshotManifest): void {
  if (rows.length !== manifest.expectedCounts.forecastAuditRows || evaluations.length !== manifest.expectedCounts.evaluationRows) throw new SnapshotLoadError("Snapshot row counts do not match the verified manifest", "integrity");
  const testRows = rows.filter((row) => row.split === "test");
  const matureRows = testRows.filter((row) => row.evaluationStatus === "EVALUABLE");
  const pendingRows = testRows.filter((row) => row.evaluationStatus === "PENDING_LABEL");
  if (testRows.length !== manifest.expectedCounts.testForecastRows || matureRows.length !== manifest.expectedCounts.testEvaluableRows || pendingRows.length !== manifest.expectedCounts.testPendingRows) {
    throw new SnapshotLoadError("Test maturity counts do not match the verified handoff identity", "integrity");
  }
  if (new Set(rows.map((row) => row.predictionId)).size !== rows.length) throw new SnapshotLoadError("forecast_audit.csv contains duplicate prediction IDs", "integrity");
}

function validateAdditionalSources(
  auditRows: ForecastAuditRow[],
  evaluations: EvaluationRow[],
  portfolio: PortfolioRiskRow[],
  rolling: RollingMae20Row[],
  drift: DriftTimelineRow[],
  h1Scatter: H1ScatterRow[],
  h1Results: H1ResultRow[],
  h1Sensitivity: H1SensitivityRow[],
  hypotheses: HypothesisResultRow[],
  bootstrap: BootstrapDiagnosticRow[],
  highVolatility: HighVolatilityMetricRow[],
  manifest: SnapshotManifest,
): void {
  const { expectedCounts } = manifest;
  const countPairs: [number, number, string][] = [
    [portfolio.length, expectedCounts.portfolioRiskRows, "portfolio_risk.csv"],
    [rolling.length, expectedCounts.rollingMae20Rows, "rolling_mae20.csv"],
    [drift.length, expectedCounts.driftErrorTimelineRows, "drift_error_timeline.csv"],
    [h1Scatter.length, expectedCounts.h1ScatterDataRows, "H1_scatter_data.csv"],
    [h1Results.length, expectedCounts.h1ResultsRows, "H1_results.csv"],
    [h1Sensitivity.length, expectedCounts.h1SensitivityRows, "H1_sensitivity.csv"],
    [hypotheses.length, expectedCounts.hypothesisResultsRows, "hypothesis_results.csv"],
    [bootstrap.length, expectedCounts.bootstrapDiagnosticsRows, "bootstrap_diagnostics.csv"],
    [highVolatility.length, expectedCounts.highVolatilityMetricsRows, "high_volatility_metrics.csv"],
  ];
  for (const [actual, expected, filename] of countPairs) if (actual !== expected) throw new SnapshotLoadError(`${filename} row count does not match the verified manifest`, "integrity");

  const keyed = <T>(rows: T[], keyFor: (row: T) => string, filename: string): Map<string, T> => {
    const map = new Map<string, T>();
    for (const row of rows) {
      const key = keyFor(row);
      if (map.has(key)) throw new SnapshotLoadError(`${filename} contains duplicate scope rows`, "integrity");
      map.set(key, row);
    }
    return map;
  };
  const auditByScope = keyed(auditRows, (row) => `${row.split}:${row.predictionDate}:${row.ticker}:${row.modelName}`, "forecast_audit.csv");
  const portfolioByScope = keyed(portfolio, (row) => `${row.split}:${row.predictionDate}:${row.modelName}`, "portfolio_risk.csv");
  for (const row of portfolio) {
    if (row.status !== "OK" || row.covariance === null || row.portfolioVol === null || row.missingInputs.length > 0) continue;
    const parity = computePortfolioVolatility(row.covariance, row.sourceWeights);
    if (Math.abs(parity - row.portfolioVol) > 1e-10) throw new SnapshotLoadError(`portfolio_risk.csv stored covariance does not reproduce its portfolio value for ${row.predictionDate} ${row.modelName}`, "integrity");
    const defaultParity = computePortfolioVolatility(row.covariance, [0.5, 0.3, 0.2]);
    if (Math.abs(defaultParity - row.portfolioVol) > 1e-10) throw new SnapshotLoadError(`portfolio_risk.csv default 50/30/20 risk does not reproduce its stored value for ${row.predictionDate} ${row.modelName}`, "integrity");
    if (!row.correlationReady || row.correlations.spyIef === null || row.correlations.spyGld === null || row.correlations.iefGld === null) {
      throw new SnapshotLoadError(`portfolio_risk.csv lacks ready 20-session correlations for ${row.predictionDate} ${row.modelName}`, "integrity");
    }
    const correlationMatrix = [
      [1, row.correlations.spyIef, row.correlations.spyGld],
      [row.correlations.spyIef, 1, row.correlations.iefGld],
      [row.correlations.spyGld, row.correlations.iefGld, 1],
    ];
    for (let first = 0; first < 3; first += 1) {
      for (let second = 0; second < 3; second += 1) {
        const firstForecast = row.forecastVols[first];
        const secondForecast = row.forecastVols[second];
        if (firstForecast === null || secondForecast === null) throw new SnapshotLoadError(`portfolio_risk.csv has incomplete forecast inputs for ${row.predictionDate} ${row.modelName}`, "integrity");
        const expectedCovariance = firstForecast * secondForecast * correlationMatrix[first][second];
        if (Math.abs(row.covariance[first][second] - expectedCovariance) > 1e-10) throw new SnapshotLoadError(`portfolio_risk.csv covariance does not match the stored 20-session correlations for ${row.predictionDate} ${row.modelName}`, "integrity");
      }
    }
    for (let index = 0; index < 3; index += 1) {
      const ticker = (["SPY", "IEF", "GLD"] as const)[index];
      const forecast = auditByScope.get(`${row.split}:${row.predictionDate}:${ticker}:${row.modelName}`);
      if (!forecast || forecast.forecastStatus !== row.forecastStatuses[index] || forecast.predictedVolAnnualized === null || row.forecastVols[index] === null || Math.abs(forecast.predictedVolAnnualized - row.forecastVols[index]) > 1e-12) {
        throw new SnapshotLoadError(`portfolio_risk.csv forecast inputs disagree with the audit snapshot for ${row.predictionDate} ${ticker} ${row.modelName}`, "integrity");
      }
    }
  }
  const rollingByScope = keyed(rolling, (row) => `${row.split}:${row.ticker}:${row.modelName}:${row.windowEnd}`, "rolling_mae20.csv");
  const evaluableById = new Map(evaluations.filter((row) => row.modelName === "ONLINE_SGD").map((row) => [row.predictionId, row]));
  const driftIds = new Set<string>();
  for (const row of drift) {
    if (driftIds.has(row.predictionId)) throw new SnapshotLoadError("drift_error_timeline.csv contains duplicate prediction IDs", "integrity");
    driftIds.add(row.predictionId);
    const evaluation = evaluableById.get(row.predictionId);
    if (!evaluation || evaluation.predictionDate !== row.predictionDate || evaluation.ticker !== row.ticker || Math.abs(evaluation.absoluteError - row.absoluteErrorEvaluation) > 1e-12) {
      throw new SnapshotLoadError(`drift_error_timeline.csv row does not match a verified B3 Test evaluation: ${row.predictionId}`, "integrity");
    }
  }
  if (driftIds.size !== evaluableById.size || drift.some((row) => row.driftDetected || row.alertRecordPresent)) throw new SnapshotLoadError("Drift source IDs or recorded alert count do not match the pinned B3 Test snapshot", "integrity");

  const h1ByTicker = keyed(h1Results, (row) => row.ticker, "H1_results.csv");
  const sensitivityByScope = keyed(h1Sensitivity, (row) => `${row.ticker}:${row.hacMaxlags}`, "H1_sensitivity.csv");
  const scatterCounts = new Map<string, number>();
  keyed(h1Scatter, (row) => `${row.date}:${row.ticker}`, "H1_scatter_data.csv");
  for (const row of h1Scatter) scatterCounts.set(row.ticker, (scatterCounts.get(row.ticker) ?? 0) + 1);
  for (const ticker of ["SPY", "IEF", "GLD"] as const) {
    const primary = h1ByTicker.get(ticker);
    const sensitivity = sensitivityByScope.get(`${ticker}:5`);
    if (!primary || !sensitivity || scatterCounts.get(ticker) !== primary.n || sensitivity.n !== primary.n || Math.abs(primary.beta - sensitivity.beta) > 1e-12) throw new SnapshotLoadError(`H1 Train source rows do not reconcile for ${ticker}`, "integrity");
  }

  const hypothesisByScope = keyed(hypotheses, (row) => `${row.hypothesisId}:${row.tickerOrMacro}`, "hypothesis_results.csv");
  if (hypothesisByScope.size !== 5 || !["SPY", "IEF", "GLD"].every((ticker) => hypothesisByScope.has(`H1:${ticker}`)) || !hypothesisByScope.has("H2:MACRO") || !hypothesisByScope.has("H3:MACRO")) throw new SnapshotLoadError("hypothesis_results.csv does not contain the pinned H1–H3 scope", "integrity");
  const bootstrapByScope = keyed(bootstrap, (row) => `${row.hypothesisId}:${row.blockLength}`, "bootstrap_diagnostics.csv");
  if (bootstrapByScope.size !== 4 || !["H2", "H3"].every((hypothesis) => [5, 20].every((blockLength) => bootstrapByScope.has(`${hypothesis}:${blockLength}`)))) throw new SnapshotLoadError("bootstrap_diagnostics.csv does not contain the pinned sensitivity rows", "integrity");
  const highVolByScope = keyed(highVolatility, (row) => `${row.split}:${row.ticker}:${row.modelName}`, "high_volatility_metrics.csv");
  if (highVolByScope.size !== 12 || highVolatility.some((row) => row.split === "test" && row.ticker === "IEF" && (row.highVolAnchorCount !== 0 || row.highVolCommonEvaluableN !== 0 || row.mae !== null || row.rmse !== null))) throw new SnapshotLoadError("High-volatility subset counts do not match the pinned source; IEF Test must remain insufficient evidence", "integrity");
  void rollingByScope;
  void portfolioByScope;
}

export async function loadSnapshot(fetcher: typeof fetch = fetch, baseHref: string = document.baseURI): Promise<SnapshotState> {
  const assetUrl = (relative: string) => new URL(relative, baseHref).toString();
  let policyResponse: Response;
  try {
    policyResponse = await fetcher(assetUrl("snapshot.policy.json"));
  } catch {
    return { status: "missing", message: "Snapshot policy is not available from this local build." };
  }
  if (policyResponse.status === 404) return { status: "missing", message: "Pinned snapshot policy is missing from this build." };
  if (!policyResponse.ok) return { status: "error", message: `Snapshot policy could not be loaded (HTTP ${policyResponse.status}).` };

  try {
    const policy = parsePolicy(await policyResponse.json());
    const directory = `snapshots/${policy.identity.evaluationId}`;
    const manifestResponse = await fetcher(assetUrl(`${directory}/dashboard_snapshot_manifest.json`));
    if (manifestResponse.status === 404) return { status: "missing", message: "Verified snapshot files are not present. Rebuild with the handoff ZIP available." };
    if (!manifestResponse.ok) throw new SnapshotLoadError(`Snapshot manifest could not be loaded (HTTP ${manifestResponse.status}).`, "network");
    const manifest = parseSnapshotManifest(await manifestResponse.json(), policy);
    const outputKeys = Object.keys(policy.publicOutputs) as (keyof SnapshotPolicy["publicOutputs"])[];
    const responses = await Promise.all(outputKeys.map((key) => fetcher(assetUrl(`${directory}/${manifest.files[key].path}`))));
    if (responses.some((response) => response.status === 404)) throw new SnapshotLoadError("A required verified CSV is missing from the snapshot.", "missing");
    if (responses.some((response) => !response.ok)) throw new SnapshotLoadError("A snapshot CSV could not be loaded.", "network");
    const fileBytes = await Promise.all(responses.map((response) => response.arrayBuffer().then((buffer) => new Uint8Array(buffer))));
    const outputFiles = Object.fromEntries(outputKeys.map((key, index) => [manifest.files[key].path, fileBytes[index]])) as Record<string, Uint8Array>;
    await verifySnapshotFileBytes(manifest, policy, outputFiles);
    const decoder = new TextDecoder("utf-8");
    const content = Object.fromEntries(outputKeys.map((key, index) => [key, decoder.decode(fileBytes[index])])) as Record<keyof SnapshotPolicy["publicOutputs"], string>;
    const auditRows = parseForecastAudit(content.forecastAudit, policy);
    const evaluationRows = parseEvaluation(content.evaluation, policy);
    const modelMetrics = parseModelMetrics(content.modelMetrics, policy);
    const pairComparisons = parsePairComparisons(content.pairComparisons, policy);
    const coverage = parseCoverage(content.coverage, policy);
    const portfolioRisk = parsePortfolioRisk(content.portfolioRisk, policy);
    const rollingMae20 = parseRollingMae20(content.rollingMae20, policy);
    const driftTimeline = parseDriftTimeline(content.driftErrorTimeline, policy);
    const h1Scatter = parseH1Scatter(content.h1ScatterData, policy);
    const h1Results = parseH1Results(content.h1Results, policy);
    const h1Sensitivity = parseH1Sensitivity(content.h1Sensitivity, policy);
    const hypothesisResults = parseHypothesisResults(content.hypothesisResults, policy);
    const bootstrapDiagnostics = parseBootstrapDiagnostics(content.bootstrapDiagnostics, policy);
    const highVolatilityMetrics = parseHighVolatilityMetrics(content.highVolatilityMetrics, policy);
    verifyCounts(auditRows, evaluationRows, manifest);
    if (modelMetrics.length !== manifest.expectedCounts.modelMetricsRows || pairComparisons.length !== manifest.expectedCounts.pairComparisonsRows || coverage.length !== manifest.expectedCounts.coverageRows) {
      throw new SnapshotLoadError("D3 source row counts do not match the verified manifest", "integrity");
    }
    if (new Set(modelMetrics.map((row) => `${row.ticker}:${row.modelName}`)).size !== modelMetrics.length || new Set(pairComparisons.map((row) => `${row.comparisonId}:${row.ticker}`)).size !== pairComparisons.length || new Set(coverage.map((row) => `${row.split}:${row.ticker}:${row.modelName}`)).size !== coverage.length) {
      throw new SnapshotLoadError("A D3 source CSV contains duplicate scope rows", "integrity");
    }
    validateAdditionalSources(auditRows, evaluationRows, portfolioRisk, rollingMae20, driftTimeline, h1Scatter, h1Results, h1Sensitivity, hypothesisResults, bootstrapDiagnostics, highVolatilityMetrics, manifest);
    return {
      status: "ready", policy, manifest, sessions: auditRows.filter((row) => row.split === "test"), forecasts: auditRows,
      evaluations: validateEvaluationJoin(auditRows, evaluationRows), modelMetrics, pairComparisons, coverage,
      portfolioRisk, rollingMae20, driftTimeline, h1Scatter, h1Results, h1Sensitivity, hypothesisResults, bootstrapDiagnostics, highVolatilityMetrics,
    };
  } catch (error) {
    if (error instanceof SnapshotLoadError && error.kind === "missing") return { status: "missing", message: error.message };
    return { status: "error", message: error instanceof Error ? error.message : "Snapshot schema validation failed." };
  }
}

export function selectRecordedSessions(rows: ForecastAuditRow[], ticker: Ticker, model: ModelName): ForecastAuditRow[] {
  return rows.filter((row) => row.ticker === ticker && row.modelName === model).sort((left, right) => left.predictionDate.localeCompare(right.predictionDate));
}

export function filterForecastRows(rows: ForecastAuditRow[], filter: ForecastFilter): ForecastAuditRow[] {
  return rows.filter((row) => {
    if (row.split !== filter.split || row.ticker !== filter.ticker || !filter.models.includes(row.modelName)) return false;
    if (filter.from && row.predictionDate < filter.from) return false;
    if (filter.to && row.predictionDate > filter.to) return false;
    if (filter.status === "mature" && row.evaluationStatus !== "EVALUABLE") return false;
    if (filter.status === "pending" && row.evaluationStatus !== "PENDING_LABEL") return false;
    if (filter.status === "invalid" && row.evaluationStatus !== "INVALID_FORECAST" && row.evaluationStatus !== "MISSING_FORECAST") return false;
    return true;
  }).sort((left, right) => left.predictionDate.localeCompare(right.predictionDate) || left.modelName.localeCompare(right.modelName));
}
