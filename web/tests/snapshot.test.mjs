import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { parseCsv } from "../dist/assets/data/csv.js";
import { loadSnapshot, verifySnapshotFileBytes, requireSnapshotFiles } from "../dist/assets/data/loadSnapshot.js";
import { parseForecastAuditRow, parsePolicy, parseSnapshotManifest } from "../dist/assets/data/schemas.js";

const policy = parsePolicy(JSON.parse(await readFile(new URL("../snapshot.policy.json", import.meta.url), "utf8")));
const snapshotDirectory = new URL(`../public/snapshots/${policy.identity.evaluationId}/`, import.meta.url);
const manifestJson = JSON.parse(await readFile(new URL("dashboard_snapshot_manifest.json", snapshotDirectory), "utf8"));
const manifest = parseSnapshotManifest(manifestJson, policy);
const auditBytes = new Uint8Array(await readFile(new URL(manifest.files.forecastAudit.path, snapshotDirectory)));
const evaluationBytes = new Uint8Array(await readFile(new URL(manifest.files.evaluation.path, snapshotDirectory)));
const auditText = new TextDecoder().decode(auditBytes);
const evaluationText = new TextDecoder().decode(evaluationBytes);

test("CSV parser preserves quoted commas, escaped quotes, and newlines", () => {
  const table = parseCsv('name,note\r\nSPY,"close,\"\"adjusted\"\"\r\nvalue"\r\n');
  assert.deepEqual(table.headers, ["name", "note"]);
  assert.equal(table.records[0].note, 'close,"adjusted"\r\nvalue');
});

test("verified snapshot files match the pinned SHA-256 values", async () => {
  await verifySnapshotFileBytes(manifest, policy, {
    [manifest.files.forecastAudit.path]: auditBytes,
    [manifest.files.evaluation.path]: evaluationBytes,
  });
});

test("the real frozen snapshot loads into typed Test sessions with Pending labels retained", async () => {
  const files = new Map([
    ["snapshot.policy.json", new TextEncoder().encode(JSON.stringify(JSON.parse(await readFile(new URL("../snapshot.policy.json", import.meta.url), "utf8"))))],
    [`snapshots/${policy.identity.evaluationId}/dashboard_snapshot_manifest.json`, new TextEncoder().encode(JSON.stringify(manifestJson))],
    [`snapshots/${policy.identity.evaluationId}/${manifest.files.forecastAudit.path}`, auditBytes],
    [`snapshots/${policy.identity.evaluationId}/${manifest.files.evaluation.path}`, evaluationBytes],
  ]);
  const fakeFetch = async (input) => {
    const key = new URL(String(input)).pathname.replace(/^\//, "");
    const bytes = files.get(key);
    return bytes ? new Response(bytes, { status: 200 }) : new Response("missing", { status: 404 });
  };
  const loaded = await loadSnapshot(fakeFetch, "http://localhost:4173/");
  assert.equal(loaded.status, "ready");
  if (loaded.status !== "ready") return;
  assert.equal(loaded.sessions.length, policy.expectedCounts.testForecastRows);
  assert.equal(loaded.manifest.expectedCounts.testPendingRows, 60);
  assert.equal(loaded.evaluations.size, policy.expectedCounts.testEvaluableRows);
  assert.ok(loaded.sessions.some((row) => row.evaluationStatus === "PENDING_LABEL" && row.targetRealizedVol5d === null && row.absoluteError === null));
});

test("missing required CSV files fail closed", () => {
  assert.throws(
    () => requireSnapshotFiles({}, [manifest.files.forecastAudit.path, manifest.files.evaluation.path]),
    /Required snapshot file missing/,
  );
});

test("a changed CSV byte fails the pinned hash check", async () => {
  const changed = new Uint8Array(auditBytes);
  changed[100] ^= 1;
  await assert.rejects(
    verifySnapshotFileBytes(manifest, policy, {
      [manifest.files.forecastAudit.path]: changed,
      [manifest.files.evaluation.path]: evaluationBytes,
    }),
    /SHA-256 mismatch/,
  );
});

test("an Evaluation ID or Replay ID mismatch is rejected", () => {
  assert.throws(
    () => parseSnapshotManifest({ ...manifestJson, evaluationId: "another-evaluation" }, policy),
    /evaluationId does not match/,
  );
  assert.throws(
    () => parseSnapshotManifest({ ...manifestJson, replayId: "another-replay" }, policy),
    /replayId does not match/,
  );
});

test("Pending rows preserve blank actual/error values and reject scored Pending values", () => {
  const pendingRecord = parseCsv(auditText).records.find((row) => row.split === "test" && row.evaluation_status === "PENDING_LABEL");
  const matureEvaluation = parseCsv(evaluationText).records[0];
  assert.ok(pendingRecord);
  assert.equal(pendingRecord.target_realized_vol_5d, "");
  assert.equal(pendingRecord.absolute_error, "");
  const pending = parseForecastAuditRow(pendingRecord);
  assert.equal(pending.targetRealizedVol5d, null);
  assert.equal(pending.absoluteError, null);

  assert.throws(
    () => parseForecastAuditRow({
      ...pendingRecord,
      target_realized_vol_5d: matureEvaluation.target_realized_vol_5d,
      absolute_error: matureEvaluation.absolute_error,
    }),
    /must not contain actual or error values/,
  );
});
