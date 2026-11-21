type DisplayUnit = "decimal" | "percent";

export interface SessionChartPoint {
  predictionDate: string;
  predictionId: string;
  forecast: number | null;
  actual: number | null;
  status: string;
}

function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] ?? character);
}

function formatVol(value: number | null, unit: DisplayUnit): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return unit === "percent" ? `${(value * 100).toFixed(2)}%` : value.toFixed(4);
}

function lines(points: SessionChartPoint[], key: "forecast" | "actual", x: (index: number) => number, y: (value: number) => number, cssClass: string): string {
  const segments: Array<Array<{ index: number; value: number }>> = [];
  let segment: Array<{ index: number; value: number }> = [];
  points.forEach((point, index) => {
    const value = point[key];
    if (value === null || !Number.isFinite(value) || value < 0) {
      if (segment.length) segments.push(segment);
      segment = [];
      return;
    }
    segment.push({ index, value });
  });
  if (segment.length) segments.push(segment);
  return segments.map((items) => `<polyline class="${cssClass}" points="${items.map((item) => `${x(item.index).toFixed(1)},${y(item.value).toFixed(1)}`).join(" ")}" />`).join("");
}

export function renderSessionChart(points: SessionChartPoint[], selectedDate: string, unit: DisplayUnit): string {
  const validValues = points.flatMap((point) => [point.forecast, point.actual]).filter((value): value is number => value !== null && Number.isFinite(value) && value >= 0);
  if (points.length === 0 || validValues.length === 0) {
    return `<div class="session-chart-empty" role="status">ไม่มีค่าที่ใช้วาดกราฟจาก saved records ใน selection นี้</div>`;
  }

  const width = 880;
  const height = 246;
  const left = 64;
  const right = 848;
  const top = 34;
  const bottom = 204;
  const maxValue = Math.max(...validValues) * 1.08 || 1;
  const x = (index: number) => left + index * ((right - left) / Math.max(points.length - 1, 1));
  const y = (value: number) => bottom - (value / maxValue) * (bottom - top);
  const selectedIndex = points.findIndex((point) => point.predictionDate === selectedDate);
  const selectedPoint = selectedIndex >= 0 ? points[selectedIndex] : undefined;
  const forecastLines = lines(points, "forecast", x, y, "session-chart-line session-chart-forecast");
  const actualLines = lines(points, "actual", x, y, "session-chart-line session-chart-actual");
  const dots = points.map((point, index) => {
    const selected = point.predictionDate === selectedDate;
    const forecast = point.forecast !== null && Number.isFinite(point.forecast) && point.forecast >= 0
      ? `<circle class="session-chart-dot session-chart-forecast${selected ? " selected" : ""}" cx="${x(index).toFixed(1)}" cy="${y(point.forecast).toFixed(1)}" r="${selected ? 5 : 2.3}"><title>${escapeHtml(point.predictionDate)} · Forecast ${formatVol(point.forecast, unit)} · ${escapeHtml(point.status)} · ${escapeHtml(point.predictionId)}</title></circle>`
      : "";
    const actual = point.actual !== null && Number.isFinite(point.actual) && point.actual >= 0
      ? `<circle class="session-chart-dot session-chart-actual${selected ? " selected" : ""}" cx="${x(index).toFixed(1)}" cy="${y(point.actual).toFixed(1)}" r="${selected ? 4.5 : 2.8}"><title>${escapeHtml(point.predictionDate)} · Actual ${formatVol(point.actual, unit)} · ${escapeHtml(point.predictionId)}</title></circle>`
      : "";
    return forecast + actual;
  }).join("");
  const marker = selectedIndex >= 0
    ? `<line class="session-chart-selection" x1="${x(selectedIndex).toFixed(1)}" y1="${top}" x2="${x(selectedIndex).toFixed(1)}" y2="${bottom}" />`
    : "";
  const rows = points.map((point) => `<tr${point.predictionDate === selectedDate ? ' class="selected-session-row"' : ""}><th scope="row">${escapeHtml(point.predictionDate)}</th><td>${formatVol(point.forecast, unit)}</td><td>${formatVol(point.actual, unit)}</td><td>${point.status === "PENDING_LABEL" ? "Pending · not scored" : escapeHtml(point.status)}</td><td><code>${escapeHtml(point.predictionId)}</code></td></tr>`).join("");
  const selectedText = selectedPoint ? `selected ${escapeHtml(selectedPoint.predictionDate)}` : `selected ${escapeHtml(selectedDate)}`;
  const actualLegend = points.some((point) => point.actual !== null) ? "Actual · mature/evaluable only" : "Actual · hidden until mature";
  return `<div class="session-chart-visual"><div class="chart-scroll"><svg class="session-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Recorded Forecast and mature Actual RV5; ${selectedText}"><line x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}" class="chart-axis"/><line x1="${left}" y1="${top}" x2="${left}" y2="${bottom}" class="chart-axis"/><line x1="${left}" y1="${(top + bottom) / 2}" x2="${right}" y2="${(top + bottom) / 2}" class="chart-gridline"/><text x="8" y="${top + 4}" class="chart-date-label">${formatVol(maxValue, unit)}</text><text x="${left}" y="${height - 7}" class="chart-date-label">${escapeHtml(points[0].predictionDate)}</text><text x="${right}" y="${height - 7}" text-anchor="end" class="chart-date-label">${escapeHtml(points[points.length - 1].predictionDate)}</text>${marker}${forecastLines}${actualLines}${dots}</svg></div><div class="chart-legend"><span><i class="session-chart-legend-forecast"></i>Forecast · saved</span><span><i class="session-chart-legend-actual"></i>${actualLegend}</span><span>${points.length.toLocaleString()} recorded dates · ${selectedPoint ? escapeHtml(selectedPoint.predictionDate) : "selected date unavailable"}</span></div></div><details class="chart-data-details" id="session-chart-data" data-persist-open><summary>ดูค่ากราฟเป็นตาราง · ${points.length.toLocaleString()} วัน</summary><div class="table-scroll"><table class="data-table session-chart-table"><caption class="visually-hidden">Saved Forecast and mature Actual values for this Replay selection</caption><thead><tr><th scope="col">Prediction date</th><th scope="col">Forecast</th><th scope="col">Actual · mature only</th><th scope="col">Source status</th><th scope="col">Prediction ID</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
}
