import {
  featureDriftScopeKey,
  type DriftMetricName,
  type DriftTicker,
  type DriftWindowSize,
  type FeatureDriftMetric,
  type FeatureDriftState,
} from "./data/featureDrift.js";
import type { ModelName } from "./data/schemas.js";

export interface FeatureDriftViewSelection {
  ticker: DriftTicker;
  date: string;
  feature: string;
  windowSize: DriftWindowSize;
  metric: DriftMetricName;
  tab: "feature" | "error";
  model: ModelName;
}

const escapeHtml = (value: unknown): string => String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] ?? character);
const formatMetric = (value: number): string => value.toLocaleString("en-US", { maximumFractionDigits: 4 });
const featureLabels: Record<string, string> = {
  ret_1d_t: "ผลตอบแทนวันนี้",
  ret_lag_1d: "ผลตอบแทนวันก่อน",
  ret_lag_2d: "ผลตอบแทน 2 วันก่อน",
  ret_trailing_5d: "ผลตอบแทนสะสม 5 วัน",
  ret_trailing_20d: "ผลตอบแทนสะสม 20 วัน",
  rv_5d: "ความผันผวน 5 วัน",
  rv_20d: "ความผันผวน 20 วัน",
  rv_60d: "ความผันผวน 60 วัน",
};
const statusLabels: Record<string, string> = {
  DRIFT_SIGNAL: "W1 เกินเกณฑ์",
  NO_SIGNAL: "W1 ไม่เกินเกณฑ์",
  INSUFFICIENT_DATA: "ข้อมูลไม่พอ",
  UNCOMPUTABLE_SCALE: "คำนวณสเกลไม่ได้",
  CALIBRATION_LIMITATION: "ข้อจำกัดการปรับเกณฑ์",
};
const modelLabels: Record<string, string> = {
  CONSTANT_BASELINE: "B0 · Constant baseline",
  ROLLING_20D_BASELINE: "B1 · Rolling 20D",
  STATIC_SGD: "B2 · Static SGD",
  ONLINE_SGD: "B3 · Online SGD",
};
const metricLabel = (metric: DriftMetricName): string => metric === "psi" ? "PSI" : "Wasserstein แบบ normalized";
const metricValue = (row: FeatureDriftMetric, metric: DriftMetricName): number | null => metric === "psi" ? row.psi : row.wassersteinNormalized;
const metricThreshold = (row: FeatureDriftMetric, metric: DriftMetricName): number | null => metric === "psi" ? row.psiThreshold : row.wassersteinThreshold;
const optionalMetric = (value: number | null): string => value === null ? "—" : formatMetric(value);

function selectionQuery(selection: FeatureDriftViewSelection): string {
  const query = new URLSearchParams({
    date: selection.date,
    ticker: selection.ticker,
    model: selection.model,
    feature: selection.feature,
    window: String(selection.windowSize),
    metric: selection.metric,
    tab: selection.tab,
  });
  return query.toString();
}

function linkToMonitoring(selection: FeatureDriftViewSelection): string {
  return `#/monitoring?${escapeHtml(selectionQuery(selection))}`;
}

function featureName(feature: string): string {
  return `${escapeHtml(featureLabels[feature] ?? feature)} <code>${escapeHtml(feature)}</code>`;
}

function statusBadge(status: string): string {
  const style = status === "DRIFT_SIGNAL" ? "st-fd-status st-fd-signal" : status === "NO_SIGNAL" ? "st-fd-status st-fd-no-signal" : "st-fd-status st-fd-limited";
  return `<span class="${style}">${escapeHtml(statusLabels[status] ?? status)}</span>`;
}

function selectedDateMetrics(state: Extract<FeatureDriftState, { status: "ready" }>, ticker: DriftTicker, date: string, window: DriftWindowSize): FeatureDriftMetric[] {
  return state.metrics.filter((row) => row.ticker === ticker && row.asOfDate === date && row.windowSize === window);
}

function metricComparison(row: FeatureDriftMetric): string {
  return `<span class="st-fd-comparison">W1 <strong>${optionalMetric(row.wassersteinNormalized)}</strong><small>เกณฑ์ ${optionalMetric(row.wassersteinThreshold)}</small></span><span class="st-fd-comparison">PSI <strong>${optionalMetric(row.psi)}</strong><small>เกณฑ์ ${optionalMetric(row.psiThreshold)}</small></span>`;
}

export function renderReplayFeatureDriftCard(
  drift: FeatureDriftState,
  date: string,
  ticker: DriftTicker,
  model: ModelName,
): string {
  if (drift.status === "loading") return `<section class="st-card st-fd-replay-card"><div class="st-section-heading"><h2>Feature Drift</h2><span>กำลังตรวจข้อมูล</span></div><p>กำลังโหลดผลตรวจการกระจายของ feature</p></section>`;
  if (drift.status === "missing") return `<section class="st-card st-fd-replay-card"><div class="st-section-heading"><h2>Feature Drift</h2><span>ยังไม่มีผลตรวจ</span></div><p>${escapeHtml(drift.message)}</p></section>`;
  if (drift.status === "error") return `<section class="st-card st-fd-replay-card"><div class="st-section-heading"><h2>Feature Drift</h2><span>ตรวจสอบไม่ผ่าน</span></div><p>${escapeHtml(drift.message)}</p></section>`;
  const rows = selectedDateMetrics(drift, ticker, date, 60).sort((left, right) => {
    const ratio = (value: number | null, threshold: number | null) => value === null || threshold === null ? 0 : value / Math.max(threshold, Number.EPSILON);
    const leftScore = Math.max(ratio(left.wassersteinNormalized, left.wassersteinThreshold), ratio(left.psi, left.psiThreshold));
    const rightScore = Math.max(ratio(right.wassersteinNormalized, right.wassersteinThreshold), ratio(right.psi, right.psiThreshold));
    return rightScore - leftScore;
  }).slice(0, 3);
  if (!rows.length) return `<section class="st-card st-fd-replay-card"><div class="st-section-heading"><h2>Feature Drift</h2><span>ไม่มีผลสำหรับวันนี้</span></div><p>ไม่มีแถวตรวจ Feature Drift สำหรับ ${escapeHtml(ticker)} วันที่ ${escapeHtml(date)} · ไม่แทนวันที่อื่นให้อัตโนมัติ</p></section>`;
  const first = rows[0]!;
  const selection: FeatureDriftViewSelection = { ticker, date, model, feature: first.featureName, windowSize: 60, metric: "wasserstein_normalized", tab: "feature" };
  const items = rows.map((row) => `<li>${featureName(row.featureName)}${statusBadge(row.status)}<div class="st-fd-replay-values">${metricComparison(row)}</div></li>`).join("");
  const modelContext = model === "STATIC_SGD" || model === "ONLINE_SGD"
    ? `บริบทโมเดล ${escapeHtml(modelLabels[model])} · Core 8 เป็น feature input ของ B2/B3`
    : `บริบทโมเดล ${escapeHtml(modelLabels[model])} · เป็นข้อมูลประกอบด้าน input; Core 8 ใช้เป็น feature input ของ B2/B3 เท่านั้น`;
  return `<section class="st-card st-fd-replay-card"><div class="st-section-heading"><div><h2>Feature Drift</h2><span class="st-fd-context">${escapeHtml(ticker)} · ${escapeHtml(date)} · หน้าต่าง 60 วันซื้อขาย</span></div><span>3 feature ที่เปลี่ยนเด่น</span></div><ol class="st-fd-top-features">${items}</ol><p class="st-fd-model-note">${modelContext} · ไม่ได้วัดผลตอบแทนหรือระบุสาเหตุ</p><p class="st-fd-method-note">เทียบกับ Train และเกณฑ์ heuristic ที่ปรับจาก Validation · ไม่ใช่การทดสอบสมมติฐาน</p><a class="st-fd-detail-link" href="${linkToMonitoring(selection)}">ดูรายละเอียดใน Monitoring →</a></section>`;
}

function renderMetricTable(rows: FeatureDriftMetric[], selectedFeature: string): string {
  const ordered = [...rows].sort((left, right) => left.featureName.localeCompare(right.featureName));
  const body = ordered.map((row) => `<tr${row.featureName === selectedFeature ? " class=\"st-fd-selected-row\"" : ""}><th scope="row">${featureName(row.featureName)}</th><td>${optionalMetric(row.wassersteinNormalized)}</td><td>${optionalMetric(row.psi)}</td><td>${statusBadge(row.status)}</td></tr>`).join("");
  return `<div class="st-table-wrap"><table class="st-table st-fd-feature-table"><caption class="st-sr-only">ผลตรวจ Feature Drift ราย feature ณ วันที่เลือก</caption><thead><tr><th scope="col">Feature</th><th scope="col">Wasserstein normalized</th><th scope="col">PSI</th><th scope="col">สถานะ W1</th></tr></thead><tbody>${body}</tbody></table></div>`;
}

function trendChart(
  series: FeatureDriftMetric[],
  selection: FeatureDriftViewSelection,
  metric: DriftMetricName,
): string {
  if (!series.length) return `<p class="st-fd-empty">ไม่มีข้อมูล trend สำหรับตัวเลือกนี้</p>`;
  const validValues = series.map((row) => metricValue(row, metric)).filter((value): value is number => value !== null);
  const threshold = series.map((row) => metricThreshold(row, metric)).find((value): value is number => value !== null) ?? null;
  if (!validValues.length) return `<p class="st-fd-empty">ค่าของ ${escapeHtml(metricLabel(metric))} ยังสรุปไม่ได้ในช่วงที่เลือก · แสดงเป็นช่องว่างตามข้อมูลต้นทาง</p>`;
  const width = 960;
  const left = 56;
  const right = 940;
  const top = 18;
  const bottom = 146;
  const maximum = Math.max(...validValues, ...(threshold === null ? [] : [threshold]), 0.0001) * 1.12;
  const x = (index: number) => left + (right - left) * index / Math.max(series.length - 1, 1);
  const y = (value: number) => bottom - value / maximum * (bottom - top);
  const segments: FeatureDriftMetric[][] = [];
  let segment: FeatureDriftMetric[] = [];
  for (const row of series) {
    if (metricValue(row, metric) === null) {
      if (segment.length) segments.push(segment);
      segment = [];
    } else segment.push(row);
  }
  if (segment.length) segments.push(segment);
  const lineMarkup = segments.filter((run) => run.length > 1).map((run) => {
    const points = run.map((row) => {
      const index = series.indexOf(row);
      return `${x(index).toFixed(1)},${y(metricValue(row, metric)!).toFixed(1)}`;
    }).join(" ");
    return `<polyline class="st-fd-series" points="${points}"/>`;
  }).join("");
  const thresholdY = threshold === null ? null : y(threshold).toFixed(1);
  const focusDate = series.some((row) => row.asOfDate === selection.date && metricValue(row, metric) !== null)
    ? selection.date
    : series.find((row) => metricValue(row, metric) !== null)?.asOfDate;
  const circles = series.flatMap((row, index) => {
    const value = metricValue(row, metric);
    if (value === null) return [];
    const selected = row.asOfDate === selection.date;
    return [`<circle class="st-fd-point${selected ? " st-fd-point-selected" : ""}" cx="${x(index).toFixed(1)}" cy="${y(value).toFixed(1)}" r="${selected ? 5 : 2.6}" tabindex="${row.asOfDate === focusDate ? "0" : "-1"}" role="button" data-action="monitoring-date-point" data-date="${escapeHtml(row.asOfDate)}" aria-label="เลือก ${escapeHtml(row.asOfDate)} ค่า ${escapeHtml(metricLabel(metric))} ${formatMetric(value)}"><title>${escapeHtml(row.asOfDate)} · ${formatMetric(value)} · ${escapeHtml(statusLabels[row.status] ?? row.status)}</title></circle>`];
  }).join("");
  const thresholdMarkup = thresholdY === null ? "" : `<line class="st-fd-threshold" x1="${left}" y1="${thresholdY}" x2="${right}" y2="${thresholdY}"/><text x="${right - 2}" y="${Number(thresholdY) - 5}" text-anchor="end">เกณฑ์ ${formatMetric(threshold!)}</text>`;
  const thresholdLegend = threshold === null ? "<span>ไม่มีเกณฑ์สำหรับตัวเลือกนี้</span>" : `<span><i class="st-fd-legend-threshold"></i>เกณฑ์ Validation 95th percentile · ${formatMetric(threshold)}</span>`;
  return `<div class="st-fd-chart-wrap"><svg class="st-fd-trend-chart" viewBox="0 0 ${width} 174" role="group" aria-label="แนวโน้ม ${escapeHtml(metricLabel(metric))} ของ ${escapeHtml(selection.ticker)} ${escapeHtml(featureLabels[selection.feature] ?? selection.feature)}"><line x1="${left}" y1="${top}" x2="${left}" y2="${bottom}"/><line x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}"/><line class="st-fd-gridline" x1="${left}" y1="${((top + bottom) / 2).toFixed(1)}" x2="${right}" y2="${((top + bottom) / 2).toFixed(1)}"/>${thresholdMarkup}${lineMarkup}${circles}<text x="${left}" y="166">${escapeHtml(series[0]!.asOfDate)}</text><text x="${right}" y="166" text-anchor="end">${escapeHtml(series[series.length - 1]!.asOfDate)}</text><text x="${left - 4}" y="${top + 4}" text-anchor="end">${formatMetric(maximum)}</text></svg><div class="st-fd-chart-legend"><span><i class="st-fd-legend-current"></i>${escapeHtml(metricLabel(metric))}</span>${thresholdLegend}<span>${series.length.toLocaleString()} วัน · เลือกจุดเพื่อเปลี่ยนวันที่</span></div></div>`;
}

function histogramPanel(
  drift: Extract<FeatureDriftState, { status: "ready" }>,
  row: FeatureDriftMetric | undefined,
  selection: FeatureDriftViewSelection,
): string {
  if (!row) return `<p class="st-fd-empty">ไม่มีแถวสำหรับวันที่เลือก จึงไม่แสดงการกระจาย</p>`;
  const key = featureDriftScopeKey(row.asOfDate, row.ticker, row.featureName, row.windowSize);
  const bins = drift.histogramsByScope.get(key) ?? [];
  if (!bins.length) return `<p class="st-fd-empty">ข้อมูลช่วงนี้ไม่พอสำหรับแสดง histogram</p>`;
  const binText = (value: number) => value === Number.NEGATIVE_INFINITY ? "−∞" : value === Number.POSITIVE_INFINITY ? "+∞" : value.toPrecision(4);
  const maxPct = Math.max(...bins.flatMap((bin) => [bin.referencePct, bin.currentPct]), 0.001);
  const tableRows = bins.map((bin) => `<tr><th scope="row">${binText(bin.lowerEdge)} – ${binText(bin.upperEdge)}</th><td>${bin.referenceCount.toLocaleString()} <small>(${(bin.referencePct * 100).toFixed(1)}%)</small></td><td>${bin.currentCount.toLocaleString()} <small>(${(bin.currentPct * 100).toFixed(1)}%)</small></td></tr>`).join("");
  const barRows = bins.map((bin) => `<div class="st-fd-bin-row"><span>${binText(bin.lowerEdge)}–${binText(bin.upperEdge)}</span><div class="st-fd-bin-bars"><i class="st-fd-bin-reference" style="width:${(bin.referencePct / maxPct * 100).toFixed(1)}%" title="Train ${(bin.referencePct * 100).toFixed(1)}%"></i><i class="st-fd-bin-current" style="width:${(bin.currentPct / maxPct * 100).toFixed(1)}%" title="วันที่เลือก ${(bin.currentPct * 100).toFixed(1)}%"></i></div></div>`).join("");
  return `<section class="st-fd-distribution"><div class="st-fd-subheading"><div><h3>การกระจายเทียบกับ Train</h3><p>${escapeHtml(selection.ticker)} · ${featureName(selection.feature)} · ${selection.windowSize} วัน</p></div><div class="st-fd-chart-legend"><span><i class="st-fd-legend-reference"></i>Train</span><span><i class="st-fd-legend-current"></i>วันที่เลือก</span></div></div><div class="st-fd-bin-chart" aria-hidden="true">${barRows}</div><details><summary>ดูจำนวนและสัดส่วนในแต่ละช่วง</summary><div class="st-table-wrap"><table class="st-table"><thead><tr><th>ช่วงค่า</th><th>Train</th><th>วันที่เลือก</th></tr></thead><tbody>${tableRows}</tbody></table></div></details></section>`;
}

function renderFeaturePanel(
  drift: Extract<FeatureDriftState, { status: "ready" }>,
  selection: FeatureDriftViewSelection,
): string {
  const selectedRows = selectedDateMetrics(drift, selection.ticker, selection.date, selection.windowSize);
  const selected = selectedRows.find((row) => row.featureName === selection.feature);
  const series = drift.metrics.filter((row) => row.ticker === selection.ticker && row.featureName === selection.feature && row.windowSize === selection.windowSize).sort((left, right) => left.asOfDate.localeCompare(right.asOfDate));
  const signalCount = selectedRows.filter((row) => row.status === "DRIFT_SIGNAL").length;
  const noSignalCount = selectedRows.filter((row) => row.status === "NO_SIGNAL").length;
  const limitedCount = selectedRows.length - signalCount - noSignalCount;
  const selectedDayLabel = selected ? `${signalCount} เกินเกณฑ์ · ${noSignalCount} ไม่เกินเกณฑ์ · ${limitedCount} ยังสรุปไม่ได้` : "ไม่มีผลสำหรับวันที่เลือก";
  const tickers: DriftTicker[] = ["SPY", "IEF", "GLD"];
  const dates = [...new Set(drift.metrics.filter((row) => row.ticker === selection.ticker).map((row) => row.asOfDate))].sort();
  const tickerOptions = tickers.map((value) => `<option value="${value}"${value === selection.ticker ? " selected" : ""}>${value}</option>`).join("");
  const dateOptions = dates.map((value) => `<option value="${value}"${value === selection.date ? " selected" : ""}>${value}</option>`).join("");
  const featureOptions = drift.manifest.configuration.core_features.map((value) => `<option value="${escapeHtml(value)}"${value === selection.feature ? " selected" : ""}>${escapeHtml(featureLabels[value] ?? value)} · ${escapeHtml(value)}</option>`).join("");
  const toolbar = `<div class="st-fd-toolbar"><label>ETF<select data-field="monitoring-ticker">${tickerOptions}</select></label><label>วันที่ตรวจ<select data-field="monitoring-date">${dateOptions}</select></label><label>Feature<select data-field="monitoring-feature">${featureOptions}</select></label><label>หน้าต่าง<select data-field="monitoring-window"><option value="60"${selection.windowSize === 60 ? " selected" : ""}>60 วันซื้อขาย</option><option value="120"${selection.windowSize === 120 ? " selected" : ""}>120 วันซื้อขาย</option></select></label><label>ตัวชี้วัด<select data-field="monitoring-metric"><option value="wasserstein_normalized"${selection.metric === "wasserstein_normalized" ? " selected" : ""}>W1 normalized</option><option value="psi"${selection.metric === "psi" ? " selected" : ""}>PSI</option></select></label></div>`;
  const selectionMeta = `<div class="st-fd-selection-meta"><strong>${escapeHtml(selection.ticker)} · ${escapeHtml(selection.date)} · ${selection.windowSize} วันซื้อขาย</strong><span>${escapeHtml(selectedDayLabel)}</span><span>บริบทโมเดล ${escapeHtml(modelLabels[selection.model] ?? selection.model)} · Drift เป็นการตรวจการกระจายข้อมูล ไม่ขึ้นกับรุ่นโมเดล</span></div>`;
  const selectedMetrics = selected ? `<div class="st-fd-selected-metrics"><div><span>ค่าปัจจุบัน</span><strong>${optionalMetric(metricValue(selected, selection.metric))}</strong></div><div><span>เกณฑ์ Validation 95%</span><strong>${optionalMetric(metricThreshold(selected, selection.metric))}</strong></div><div><span>ขนาดหน้าต่าง</span><strong>${selected.currentN.toLocaleString()} / ${selection.windowSize} วัน</strong></div></div>` : "";
  const limitedReason = selected && ["INSUFFICIENT_DATA", "UNCOMPUTABLE_SCALE", "CALIBRATION_LIMITATION"].includes(selected.status)
    ? `<p class="st-fd-method-note">${escapeHtml(selected.statusReason)}</p>` : "";
  const trend = `<section class="st-card st-fd-trend-card"><div class="st-fd-subheading"><div><h3>แนวโน้ม ${escapeHtml(metricLabel(selection.metric))}</h3><p>${featureName(selection.feature)} · เทียบเกณฑ์จาก Validation เท่านั้น</p></div>${selected ? statusBadge(selected.status) : ""}</div>${selectedMetrics}${limitedReason}${trendChart(series, selection, selection.metric)}<p class="st-fd-method-note">Wasserstein แสดงผลแบบหารด้วย IQR ของ Train · PSI ใช้ขอบ bin ที่ตรึงจาก Train และ smoothing 0.5 · สถานะเป็นเกณฑ์ W1 และค่า PSI แสดงแยก · ไม่ใช่การยืนยัน drift เชิงสาเหตุ</p></section>`;
  const allFeatures = `<section class="st-card st-fd-all-features"><div class="st-fd-subheading"><div><h3>ทุก feature ณ วันที่เลือก</h3><p>สถานะคำนวณจาก W1 normalized; ค่า PSI เทียบเกณฑ์แยกต่างหาก</p></div><span>${selectedRows.length} จาก ${drift.manifest.configuration.core_features.length} feature</span></div>${selectedRows.length ? renderMetricTable(selectedRows, selection.feature) : `<p class="st-fd-empty">ไม่มีแถวผลตรวจสำหรับวันที่นี้ · ไม่มีการแทนวันข้อมูลอื่น</p>`}</section>`;
  return `<div class="st-fd-tab-panel">${toolbar}${selectionMeta}${trend}${histogramPanel(drift, selected, selection)}${allFeatures}</div>`;
}

export function renderMonitoringFeatureDrift(
  drift: FeatureDriftState,
  selection: FeatureDriftViewSelection,
  errorPanel: string,
): string {
  const tabs = `<div class="st-fd-tabs" role="tablist" aria-label="ชนิดการติดตาม"><button id="monitor-feature-tab" type="button" role="tab" aria-selected="${selection.tab === "feature"}" aria-controls="monitor-feature-panel" tabindex="${selection.tab === "feature" ? "0" : "-1"}" data-action="monitoring-tab" data-tab="feature">Feature Drift</button><button id="monitor-error-tab" type="button" role="tab" aria-selected="${selection.tab === "error"}" aria-controls="monitor-error-panel" tabindex="${selection.tab === "error" ? "0" : "-1"}" data-action="monitoring-tab" data-tab="error">Error Drift · ADWIN</button></div>`;
  const featureContent = drift.status === "ready" ? renderFeaturePanel(drift, selection)
    : drift.status === "loading" ? `<p>กำลังโหลดผลตรวจ Feature Drift…</p>`
      : `<p class="st-fd-empty">${drift.status === "error" ? `ผลตรวจไม่ผ่านการตรวจสอบ: ${escapeHtml(drift.message)}` : escapeHtml(drift.message)}</p>`;
  const featureTab = `<div role="tabpanel" id="monitor-feature-panel" aria-labelledby="monitor-feature-tab"${selection.tab === "feature" ? "" : " hidden"}>${featureContent}</div>`;
  const errorTab = `<div role="tabpanel" id="monitor-error-panel" aria-labelledby="monitor-error-tab"${selection.tab === "error" ? "" : " hidden"}>${errorPanel}</div>`;
  return `<section class="st-card st-fd-monitoring">${tabs}${featureTab}${errorTab}</section>`;
}
