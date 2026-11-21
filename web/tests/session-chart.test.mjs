import assert from "node:assert/strict";
import test from "node:test";
import { renderSessionChart } from "../dist/assets/ui/sessionChart.js";

const points = [
  { predictionDate: "2025-01-02", predictionId: "pending-id", forecast: 0.1, actual: null, status: "PENDING_LABEL" },
  { predictionDate: "2025-01-03", predictionId: "mature-id", forecast: 0.12, actual: 0.11, status: "EVALUABLE" },
];

test("Replay chart marks the selected saved session and exposes a data table", () => {
  const html = renderSessionChart(points, "2025-01-03", "percent");
  assert.match(html, /aria-label="Recorded Forecast and mature Actual RV5; selected 2025-01-03"/);
  assert.match(html, /class="session-chart-dot session-chart-forecast selected"/);
  assert.match(html, /ดูค่ากราฟเป็นตาราง/);
  assert.match(html, /mature-id/);
});

test("Replay chart does not plot or table an Actual value when the caller withholds it", () => {
  const html = renderSessionChart([
    { predictionDate: "2025-01-02", predictionId: "pending-id", forecast: 0.1, actual: null, status: "PENDING_LABEL" },
  ], "2025-01-02", "percent");
  assert.match(html, /Forecast 10\.00%/);
  assert.match(html, /Pending · not scored/);
  assert.doesNotMatch(html, /Actual 99\.00%/);
  assert.doesNotMatch(html, /<td>99\.00%<\/td>/);
});
