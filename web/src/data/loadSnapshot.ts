import { assertExactHeaders, parseCsv } from "./csv.js";
import {
  parseEvaluationRow,
  parseForecastAuditRow,
  parsePolicy,
  parseSnapshotManifest,
  type EvaluationRow,
  type ForecastAuditRow,
  type SnapshotManifest,
  type SnapshotPolicy,
  type Ticker,
  type ModelName,
} from "./schemas.js";

export type SnapshotState =
  | { status: "loading" }
  | { status: "ready"; policy: SnapshotPolicy; manifest: SnapshotManifest; sessions: ForecastAuditRow[]; evaluations: Map<string, EvaluationRow> }
  | { status: "missing"; message: string }
  | { status: "error"; message: string };

export class SnapshotLoadError extends Error {
  constructor(message: string, readonly kind: "missing" | "integrity" | "network") {
    super(message);
    this.name = "SnapshotLoadError";
  }
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

export async function verifySnapshotFileBytes(
  manifest: SnapshotManifest,
  policy: SnapshotPolicy,
  files: Record<string, Uint8Array | undefined>,
): Promise<void> {
  requireSnapshotFiles(files, [manifest.files.forecastAudit.path, manifest.files.evaluation.path]);
  const artifacts = [
    { artifact: manifest.files.forecastAudit, expected: policy.memberSha256[policy.members.forecastAudit] },
    { artifact: manifest.files.evaluation, expected: policy.memberSha256[policy.members.evaluation] },
  ];
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
    const [auditResponse, evaluationResponse] = await Promise.all([
      fetcher(assetUrl(`${directory}/${manifest.files.forecastAudit.path}`)),
      fetcher(assetUrl(`${directory}/${manifest.files.evaluation.path}`)),
    ]);
    if (auditResponse.status === 404 || evaluationResponse.status === 404) throw new SnapshotLoadError("A required verified CSV is missing from the snapshot.", "missing");
    if (!auditResponse.ok || !evaluationResponse.ok) throw new SnapshotLoadError("A snapshot CSV could not be loaded.", "network");
    const [auditBytes, evaluationBytes] = await Promise.all([
      auditResponse.arrayBuffer().then((buffer) => new Uint8Array(buffer)),
      evaluationResponse.arrayBuffer().then((buffer) => new Uint8Array(buffer)),
    ]);
    await verifySnapshotFileBytes(manifest, policy, {
      [manifest.files.forecastAudit.path]: auditBytes,
      [manifest.files.evaluation.path]: evaluationBytes,
    });
    const decoder = new TextDecoder("utf-8");
    const auditRows = parseForecastAudit(decoder.decode(auditBytes), policy);
    const evaluationRows = parseEvaluation(decoder.decode(evaluationBytes), policy);
    verifyCounts(auditRows, evaluationRows, manifest);
    return { status: "ready", policy, manifest, sessions: auditRows.filter((row) => row.split === "test"), evaluations: validateEvaluationJoin(auditRows, evaluationRows) };
  } catch (error) {
    if (error instanceof SnapshotLoadError && error.kind === "missing") return { status: "missing", message: error.message };
    return { status: "error", message: error instanceof Error ? error.message : "Snapshot schema validation failed." };
  }
}

export function selectRecordedSessions(rows: ForecastAuditRow[], ticker: Ticker, model: ModelName): ForecastAuditRow[] {
  return rows.filter((row) => row.ticker === ticker && row.modelName === model).sort((left, right) => left.predictionDate.localeCompare(right.predictionDate));
}
