import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { loadFeatureDrift } from "../dist/assets/data/featureDrift.js";
import { monitoringTabFromRoute, renderMonitoringFeatureDrift, renderReplayFeatureDriftCard } from "../dist/assets/featureDriftView.js";

const sidecarDirectory = new URL("../dist/feature-drift/current/", import.meta.url);
const manifestBytes = new Uint8Array(await readFile(new URL("feature_drift_manifest.json", sidecarDirectory)));
const manifest = JSON.parse(new TextDecoder().decode(manifestBytes));
const fileNames = [
  "feature_drift_manifest.json",
  "feature_drift_metrics.csv",
  "feature_drift_histograms.csv",
  "feature_drift_reference_summary.csv",
  "feature_drift_calibration.csv",
  "CHECKSUMS.sha256",
];
const fileBytes = new Map(await Promise.all(fileNames.map(async (name) => [
  `feature-drift/current/${name}`,
  new Uint8Array(await readFile(new URL(name, sidecarDirectory))),
])));
const expectedIdentity = {
  evaluationId: manifest.evaluationId,
  replayId: manifest.replayId,
  strictCutoff: manifest.strictCutoff,
};
const fakeFetch = (files = fileBytes) => async (input) => {
  const key = new URL(String(input)).pathname.replace(/^\//, "");
  const bytes = files.get(key);
  return bytes ? new Response(bytes, { status: 200 }) : new Response("missing", { status: 404 });
};
const loadedSidecar = loadFeatureDrift(expectedIdentity, fakeFetch(), "http://localhost:4173/");

test("verified Feature Drift sidecar loads with typed daily metrics and histograms", async () => {
  const loaded = await loadedSidecar;
  assert.equal(loaded.status, "ready");
  if (loaded.status !== "ready") return;
  assert.equal(loaded.manifest.diagnosticId, manifest.diagnosticId);
  assert.equal(loaded.metrics.length, manifest.coverage.testMetricRows);
  assert.equal(loaded.histogramsByScope.size, loaded.metrics.length);
  assert.ok(loaded.metrics.every((row) => row.asOfDate <= expectedIdentity.strictCutoff));
  assert.equal(loaded.manifest.source.pointInTimeSourceAvailabilityVerified, false);
});

test("Replay Feature Drift card shows the selected date and links the same context", async () => {
  const loaded = await loadedSidecar;
  assert.equal(loaded.status, "ready");
  if (loaded.status !== "ready") return;
  const row = loaded.metrics[0];
  const card = renderReplayFeatureDriftCard(loaded, row.asOfDate, row.ticker, "ONLINE_SGD");
  assert.match(card, new RegExp(`${row.ticker} · ${row.asOfDate}`));
  assert.match(card, /3 feature ที่เปลี่ยนเด่น/);
  assert.match(card, /model=ONLINE_SGD/);
  assert.match(card, new RegExp(`date=${row.asOfDate}`));
  assert.equal((card.match(/<li>/g) ?? []).length, 3);
  const baselineCard = renderReplayFeatureDriftCard(loaded, row.asOfDate, row.ticker, "CONSTANT_BASELINE");
  assert.match(baselineCard, /ข้อมูลประกอบด้าน input; Core 8 ใช้เป็น feature input ของ B2\/B3 เท่านั้น/);
});

test("Monitoring Feature Drift has accessible tabs, controls, chart, and distribution comparison", async () => {
  const loaded = await loadedSidecar;
  assert.equal(loaded.status, "ready");
  if (loaded.status !== "ready") return;
  const row = loaded.metrics[0];
  const selection = { ticker: row.ticker, date: row.asOfDate, feature: row.featureName, windowSize: row.windowSize, metric: "wasserstein_normalized", tab: "feature", model: "ONLINE_SGD" };
  const panel = renderMonitoringFeatureDrift(loaded, selection);
  assert.match(panel, /role="tablist"/);
  assert.match(panel, /aria-controls="monitor-feature-panel"/);
  assert.match(panel, /data-field="monitoring-date"/);
  assert.match(panel, /แนวโน้ม Wasserstein/);
  assert.match(panel, /<option value="wasserstein_normalized"[^>]*>W1 normalized<\/option>/);
  const trendPoints = [...panel.matchAll(/<circle class="st-fd-point[^\"]*"[^>]*>/g)];
  assert.equal(trendPoints.filter(([markup]) => markup.includes('tabindex="0"')).length, 1);
  assert.match(panel, /การกระจายเทียบกับ Train/);
  assert.doesNotMatch(panel, /B3 Error Drift|B3 Monitor ADWIN|monitor-error-tab/);
});

test("Monitoring exposes Feature Drift and Policy without the retired B3 Error Drift tab", () => {
  const panel = renderMonitoringFeatureDrift(
    { status: "missing", message: "No sidecar" },
    { ticker: "SPY", date: "2026-09-25", feature: "ret_1d_t", windowSize: 60, metric: "wasserstein_normalized", tab: "policy", model: "ONLINE_SGD" },
    "<strong>Champion policy panel</strong>",
  );
  assert.match(panel, /Feature Drift/);
  assert.match(panel, /Champion–Challenger Policy/);
  assert.match(panel, /id="monitor-policy-panel"[^>]*>/);
  assert.doesNotMatch(panel, /monitor-error-tab|monitor-error-panel|B3 Error Drift|B3 Monitor ADWIN/);
  assert.match(panel, /Champion policy panel/);
});

test("legacy error tab links open Feature Drift while policy links remain valid", () => {
  assert.equal(monitoringTabFromRoute("error"), "feature");
  assert.equal(monitoringTabFromRoute("feature"), "feature");
  assert.equal(monitoringTabFromRoute("policy"), "policy");
  assert.equal(monitoringTabFromRoute(null), null);
});

test("Feature Drift loader treats an absent manifest as unavailable", async () => {
  const loaded = await loadFeatureDrift(expectedIdentity, async () => new Response("missing", { status: 404 }), "http://localhost:4173/");
  assert.equal(loaded.status, "missing");
});

test("Feature Drift loader rejects sidecar bytes that do not match checksums", async () => {
  const changed = new Map(fileBytes);
  const original = changed.get("feature-drift/current/feature_drift_metrics.csv");
  const altered = new Uint8Array(original);
  altered[100] ^= 1;
  changed.set("feature-drift/current/feature_drift_metrics.csv", altered);
  const loaded = await loadFeatureDrift(expectedIdentity, fakeFetch(changed), "http://localhost:4173/");
  assert.equal(loaded.status, "error");
  if (loaded.status === "error") assert.match(loaded.message, /SHA-256 mismatch/i);
});

test("Feature Drift loader rejects a package for a different frozen replay", async () => {
  const loaded = await loadFeatureDrift({ ...expectedIdentity, replayId: "another-replay" }, fakeFetch(), "http://localhost:4173/");
  assert.equal(loaded.status, "error");
  if (loaded.status === "error") assert.match(loaded.message, /replayId/i);
});
