import {
  selectPolicyDayState,
  type PolicyDecisionOutcome,
  type PolicySnapshotState,
} from "./data/policySnapshot.js";
import type { Ticker } from "./data/schemas.js";

const esc = (value: unknown): string => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char] ?? char);
const pct = (value: number | null): string => value === null || !Number.isFinite(value) ? "—" : `${(value * 100).toFixed(2)} pp`;
const pctRatio = (value: number | null): string => value === null || !Number.isFinite(value) ? "—" : `${(value * 100).toFixed(2)}%`;
const signedPp = (value: number | null): string => value === null || !Number.isFinite(value) ? "—" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)} pp`;
const signedRelPct = (value: number | null): string => value === null || !Number.isFinite(value) ? "—" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
const shortHash = (value: string): string => value ? value.slice(0, 12) : "—";

const MODEL_LABELS: Record<string, string> = {
  B0: "B0 · Constant Baseline",
  B1: "B1 · Rolling 20D",
  B2: "B2 · Static SGD",
  B3: "B3 · Online SGD (Snapshot)",
  B4: "B4 · HAR-X (OLS)",
};

const OUTCOME_META: Record<PolicyDecisionOutcome, { label: string; cls: string }> = {
  promoted: { label: "Promoted · สลับรุ่นวันถัดไป", cls: "st-fd-status st-policy-promoted" },
  retained: { label: "Retained · คงแชมเปี้ยนเดิม", cls: "st-fd-status st-fd-no-signal" },
  insufficient_pairs: { label: "ข้อมูลไม่พอ (< 30 คู่)", cls: "st-fd-status st-fd-limited" },
  invalid: { label: "Invalid · ประเมินเกณฑ์ไม่ได้", cls: "st-fd-status st-fd-signal" },
  cooldown_suppressed: { label: "Cooldown · ข้ามการสลับ", cls: "st-fd-status st-fd-limited" },
};

function outcomeBadge(outcome: PolicyDecisionOutcome): string {
  const meta = OUTCOME_META[outcome];
  return `<span class="${meta.cls}">${esc(meta.label)}</span>`;
}

function modelCaption(modelId: string): string {
  return MODEL_LABELS[modelId] ?? modelId;
}

export function renderReplayPolicyCard(
  policyState: PolicySnapshotState,
  date: string,
  ticker: Ticker,
): string {
  const link = `#/monitoring?${esc(new URLSearchParams({ tab: "policy", ticker, date }).toString())}`;
  if (policyState.status === "loading") {
    return `<section class="st-card st-policy-replay-card"><div class="st-section-heading"><h2>Champion–Challenger Policy</h2><span>กำลังตรวจ sidecar</span></div><p>กำลังโหลดและตรวจ checksum ของนโยบายสลับรุ่น (Simulated Historical Replay)</p></section>`;
  }
  if (policyState.status === "missing") {
    return `<section class="st-card st-policy-replay-card"><div class="st-section-heading"><h2>Champion–Challenger Policy</h2><span>ยังไม่มี policy snapshot</span></div><p>${esc(policyState.message)} · ไม่สร้างเหตุการณ์หรือ alert สมมติ</p></section>`;
  }
  if (policyState.status === "error") {
    return `<section class="st-card st-policy-replay-card"><div class="st-section-heading"><h2>Champion–Challenger Policy</h2><span>ตรวจสอบไม่ผ่าน</span></div><p>${esc(policyState.message)}</p></section>`;
  }
  const day = selectPolicyDayState(policyState, ticker, date);
  const active = day.activeTimelineEntry;
  const activeModel = active ? `${active.toModelId} (${active.toChampionVersionId})` : day.initialChampion;
  const alertsTotal = day.tickerOperations?.alertCount ?? 0;
  const promosTotal = day.tickerOperations?.promotionCount ?? 0;
  const dayAlert = day.decisionsOnDate.length
    ? `พบ decision บนวันนี้: ${day.decisionsOnDate.map((item) => OUTCOME_META[item.decisionOutcome].label).join(", ")}`
    : day.pendingPromotionDecision
      ? `อนุมัติ promotion แล้วเมื่อ ${day.pendingPromotionDecision.decisionDate} · เริ่มมีผล ${day.pendingPromotionDecision.effectiveFromDate}`
      : `ไม่มี ADWIN alert บนวันนี้ (ทั้งช่วง Test: ${alertsTotal} alerts · ${promosTotal} switches)`;
  const servedText = day.servedFailure
    ? `Invalid (${day.servedFailure.reason})`
    : day.servedForecast
      ? `${pct(day.servedForecast.predictedVolAnnualized)}${day.servedPendingLabel ? " · Pending label" : ""}`
      : "ไม่มีแถวในวันนี้";
  const shadowText = day.shadowFailure
    ? `Invalid (${day.shadowFailure.reason})`
    : day.shadowForecast
      ? pct(day.shadowForecast.predictedVolAnnualized)
      : "—";
  return `<section class="st-card st-policy-replay-card">`
    + `<div class="st-section-heading"><div><h2>Champion–Challenger Policy (Exploratory v${esc(policyState.manifest.policyVersion)})</h2><span class="st-fd-context">Simulated Historical Replay · ${esc(ticker)} · ${esc(day.date)} · แยกจาก H1–H3</span></div><span class="st-fd-status st-fd-no-signal">Active: ${esc(activeModel)}</span></div>`
    + `<div class="st-fd-selected-metrics"><div><span>โมเดลหลักที่ใช้ในวันนี้</span><strong>${esc(activeModel)}</strong></div><div><span>ค่าพยากรณ์จากโมเดลหลัก</span><strong>${esc(servedText)}</strong></div><div><span>ค่าพยากรณ์จาก B3 ที่ใช้เปรียบเทียบ</span><strong>${esc(shadowText)}</strong></div></div>`
    + `<p class="st-fd-method-note">${esc(dayAlert)} · ค่าเสิร์ฟมาจาก frozen champion snapshot ขณะที่ Shadow B3 อัปเดตต่อเนื่องแยกต่างหาก</p>`
    + `<a class="st-fd-detail-link" href="${link}">เปิดดูรายละเอียด Policy &amp; Timeline →</a>`
    + `</section>`;
}

export function renderPolicyMonitoringPanel(
  policyState: PolicySnapshotState,
  selection: { ticker: Ticker; date: string },
): string {
  if (policyState.status === "loading") {
    return `<div class="st-fd-tab-panel"><p>กำลังตรวจสอบและโหลด Champion–Challenger Policy snapshot…</p></div>`;
  }
  if (policyState.status === "missing") {
    return `<div class="st-fd-tab-panel"><p class="st-fd-empty">${esc(policyState.message)} · แดชบอร์ดนี้ไม่สร้าง alert หรือประวัติการสลับรุ่นจำลองเมื่อไม่มี snapshot ที่ผ่านการตรวจ checksum</p></div>`;
  }
  if (policyState.status === "error") {
    return `<div class="st-fd-tab-panel"><div class="st-policy-error" role="alert"><strong>Policy Snapshot ไม่ผ่านการตรวจสอบ Integrity</strong><p>${esc(policyState.message)}</p></div></div>`;
  }

  const day = selectPolicyDayState(policyState, selection.ticker, selection.date);
  const manifest = policyState.manifest;
  const tickers: Ticker[] = ["SPY", "IEF", "GLD"];
  const tickerOptions = tickers.map((item) => `<option value="${item}"${item === day.ticker ? " selected" : ""}>${item}</option>`).join("");
  const dateOptions = day.availableDates.map((item) => `<option value="${esc(item)}"${item === day.date ? " selected" : ""}>${esc(item)}</option>`).join("");
  const quickDates = [
    ...day.tickerEvents.map((ev) => ({ date: ev.decisionDate, label: `Alert ${ev.decisionDate} (${ev.decisionOutcome})` })),
    ...day.tickerEvents.filter((ev) => ev.effectiveFromDate).map((ev) => ({ date: ev.effectiveFromDate!, label: `Effective ${ev.effectiveFromDate}` })),
  ];
  const quickJumpHtml = quickDates.length
    ? `<div class="st-policy-jumps"><span>วันเหตุการณ์สำคัญ (${esc(day.ticker)}):</span>${quickDates.map((item) => `<button type="button" class="st-policy-jump-btn${item.date === day.date ? " st-active" : ""}" data-action="monitoring-date-point" data-date="${esc(item.date)}">${esc(item.label)}</button>`).join("")}</div>`
    : "";

  const active = day.activeTimelineEntry;
  const activeVersion = active ? active.toChampionVersionId : "v001";
  const activeModelId = active ? active.toModelId : day.initialChampion;
  const activeHash = active ? shortHash(active.toStateSha256) : "—";
  const activeEffective = active ? active.effectiveFromDate : "—";

  const pendingNotice = day.pendingPromotionDecision
    ? `<div class="st-policy-callout st-policy-callout-warn"><strong>Pending Promotion (มีผลวันทำการถัดไป):</strong> ตัดสินใจ promote เป็น <code>${esc(day.pendingPromotionDecision.championVersionIdAfter)}</code> (${esc(day.pendingPromotionDecision.championModelIdAfter)}) เมื่อ <strong>${esc(day.pendingPromotionDecision.decisionDate)}</strong> · วันนี้ (${esc(day.date)}) ยังคงเสิร์ฟ <code>${esc(activeVersion)}</code> และรุ่นใหม่จะเริ่มเสิร์ฟตั้งแต่ <strong>${esc(day.pendingPromotionDecision.effectiveFromDate)}</strong> เพื่อป้องกัน look-ahead</div>`
    : "";

  const servedStatusText = day.servedFailure
    ? `INVALID (${day.servedFailure.reason} · raw=${day.servedFailure.rawValue} · ไม่ clip ค่า)`
    : day.servedPendingLabel
      ? "PENDING_LABEL (รอ target 5 วันครบกำหนด)"
      : day.servedEvaluation
        ? `MATURE · Evaluated ${day.servedEvaluation.evaluationDate}`
        : day.servedForecast
          ? "FORECAST_RECORDED"
          : "NO_ROW";
  const shadowStatusText = day.shadowFailure
    ? `INVALID (${day.shadowFailure.reason})`
    : day.shadowEvaluation
      ? `MATURE · Evaluated ${day.shadowEvaluation.evaluationDate}`
      : day.shadowForecast
        ? "PENDING_LABEL"
        : "NO_ROW";

  const detectorSummary = day.detectorRowsOnDate.length
    ? day.detectorRowsOnDate.map((row) =>
      `<tr><td>${esc(row.predictionDate)}</td><td>${esc(row.evaluationDate)}</td><td><code>${esc(row.championVersionId)}</code> (${esc(row.championModelId)})</td><td>${pct(row.absoluteError)}</td><td>${row.adwinWidth}</td><td>${row.adwinEstimation.toFixed(4)}</td><td>${row.driftDetected ? `<span class="st-fd-status st-fd-signal">ALERT · ${esc(row.driftDirection)}</span>` : `<span class="st-fd-status st-fd-no-signal">No signal</span>`}</td><td>${row.triggeredDecision ? "Triggered" : "—"}</td></tr>`
    ).join("")
    : "";

  const eventsSection = day.tickerEvents.length
    ? `<div class="st-table-wrap"><table class="st-table"><thead><tr><th>วัน Alert / Decision</th><th>วันมีผล (Effective)</th><th>ผลตัดสิน</th><th>เหตุผล</th><th>Paired MAE (Champ vs B3)</th><th>คู่เทียบ (n/W)</th><th>Rel. Impr.</th><th>Champion ก่อน → หลัง</th><th>Rollback Target</th></tr></thead><tbody>${day.tickerEvents.map((ev) =>
      `<tr${ev.decisionDate === day.date || ev.effectiveFromDate === day.date ? ' class="st-fd-selected-row"' : ""}>`
      + `<td><strong>${esc(ev.decisionDate)}</strong><br><small>pred ${esc(ev.triggerPredictionDate)}</small></td>`
      + `<td>${ev.effectiveFromDate ? `<strong>${esc(ev.effectiveFromDate)}</strong>` : "—"}</td>`
      + `<td>${outcomeBadge(ev.decisionOutcome)}</td>`
      + `<td><code>${esc(ev.decisionReason)}</code>${ev.cooldownActive ? `<br><small>cooldown left: ${ev.cooldownRemainingBefore}</small>` : ""}</td>`
      + `<td>${pct(ev.championWindowMae)} vs ${pct(ev.shadowB3WindowMae)}</td>`
      + `<td>${ev.validPairCount} / ${ev.comparisonWindowPairs} <small>(min ${ev.minimumPairs})</small></td>`
      + `<td>${signedRelPct(ev.relativeImprovement)} <small>(เกณฑ์ ≥ ${(ev.minRelativeImprovement * 100).toFixed(1)}%)</small></td>`
      + `<td><code>${esc(ev.championVersionIdBefore)}</code> (${esc(ev.championModelIdBefore)}) → <code>${esc(ev.championVersionIdAfter)}</code> (${esc(ev.championModelIdAfter)})</td>`
      + `<td>${ev.rollbackTargetVersionId ? `<code>${esc(ev.rollbackTargetVersionId)}</code> (${esc(shortHash(ev.rollbackTargetStateSha256))})` : "—"}</td>`
      + `</tr>`
    ).join("")}</tbody></table></div>`
    : `<div class="st-fd-empty"><strong>ไม่พบ ADWIN Alert หรือการสลับรุ่นใน snapshot นี้ (${esc(day.ticker)})</strong><p>ตรวจพบ 0 alerts จากทั้งหมด ${(day.tickerOperations?.detectorObservationCount ?? 0).toLocaleString()} mature served observations · คง initial champion <code>${esc(day.initialChampion)}</code> ตลอดช่วง Test โดยไม่มีการสร้างเหตุการณ์สมมติ</p></div>`;

  const timelineRows = day.tickerTimeline.map((row) =>
    `<tr${row.effectiveFromDate === day.date || row.decisionDate === day.date ? ' class="st-fd-selected-row"' : ""}>`
    + `<td><code>${esc(row.toChampionVersionId)}</code></td>`
    + `<td>${esc(row.eventType)}</td>`
    + `<td>${esc(modelCaption(row.toModelId))}</td>`
    + `<td>${esc(row.decisionDate ?? "—")}</td>`
    + `<td><strong>${esc(row.effectiveFromDate)}</strong></td>`
    + `<td><code>${esc(shortHash(row.toStateSha256))}</code></td>`
    + `<td>${row.rollbackTargetVersionId ? `<code>${esc(row.rollbackTargetVersionId)}</code>` : "—"}</td>`
    + `<td>${esc(row.reason)}</td>`
    + `</tr>`
  ).join("");

  const comparisonRows = [...day.tickerComparisons, ...day.macroComparisons].map((row) =>
    `<tr><td><strong>${esc(row.ticker)}</strong></td><td><code>${esc(row.comparisonId)}</code></td><td>${esc(row.comparatorStrategy)}</td><td>${row.pairedN.toLocaleString()}</td><td>${pct(row.policyMae)}</td><td>${pct(row.comparatorMae)}</td><td>${signedPp(row.deltaMaeComparatorMinusPolicy)}</td><td>${signedRelPct(row.relativeMaeImprovement)}</td><td>${esc(row.status)}</td></tr>`
  ).join("");

  const ops = day.tickerOperations;
  const cov = day.servedCoverage;

  return `<div class="st-fd-tab-panel">`
    + `<div class="st-policy-banner"><div><strong>การทดลองสลับโมเดลย้อนหลัง (Simulated Historical Replay) · Policy v${esc(manifest.policyVersion)}</strong><p>Champion คือโมเดลหลักที่ใช้พยากรณ์ ส่วน Challenger คือ B3 ที่นำมาเปรียบเทียบ นโยบายจะพิจารณาสลับรุ่นเมื่อมีสัญญาณและผ่านเกณฑ์ที่กำหนด ผลนี้เป็นการจำลองย้อนหลัง ไม่ใช่การพยากรณ์สด แยกจากผลทดสอบ H1–H3 และยังไม่ได้ยืนยันความพร้อมของข้อมูลต้นทาง ณ เวลาจริง</p></div><span class="st-secondary-badge">Eval ${esc(shortHash(manifest.policyEvaluationId))}</span></div>`
    + `<div class="st-secondary-pair st-policy-signal-grid">`
    + `<div class="st-lineage-status"><span>Champion–Challenger Signal</span><strong>Policy ADWIN (Served Mature Error)</strong><p>ตรวจ error ของแชมเปี้ยนที่เสิร์ฟจริงและตัดสินใจสลับรุ่นด้วย paired window 60 วัน (min 30, ≥5%, cooldown 20)</p></div>`
    + `<div class="st-lineage-status"><span>Input Distribution Signal</span><strong>Feature Drift (W1 / PSI)</strong><p>วัดการเปลี่ยนกระจายตัวของ Core 8 features เทียบ Train ไม่ใช่ตัวสั่ง promote โมเดล</p></div>`
    + `</div>`
    + `<div class="st-fd-toolbar st-policy-toolbar"><label>ETF<select data-field="monitoring-ticker">${tickerOptions}</select></label><label>วันที่ตรวจ<select data-field="monitoring-date">${dateOptions}</select></label></div>`
    + quickJumpHtml
    + pendingNotice
    + `<section class="st-card"><div class="st-fd-subheading"><div><h3>สถานะ Champion ณ วันที่ ${esc(day.date)} (${esc(day.ticker)})</h3><p>Initial Champion จาก Validation cutover: <strong>${esc(modelCaption(day.initialChampion))}</strong> · รุ่นที่เสิร์ฟจริง ณ วันนี้มีผลตั้งแต่ ${esc(activeEffective)}</p></div><span class="st-fd-status st-fd-no-signal">Active: ${esc(activeVersion)} · ${esc(activeModelId)}</span></div>`
    + `<div class="st-fd-selected-metrics"><div><span>รุ่นโมเดลหลักที่ใช้</span><strong>${esc(activeVersion)} · ${esc(activeModelId)}</strong><small>state ${esc(activeHash)}</small></div><div><span>โมเดลหลัก: พยากรณ์ / ผลจริง</span><strong>${day.servedForecast ? pct(day.servedForecast.predictedVolAnnualized) : "—"} / ${day.servedEvaluation ? pct(day.servedEvaluation.targetRealizedVol5d) : "—"}</strong><small>${esc(servedStatusText)}</small></div><div><span>B3 เปรียบเทียบ: พยากรณ์ / ผลจริง</span><strong>${day.shadowForecast ? pct(day.shadowForecast.predictedVolAnnualized) : "—"} / ${day.shadowEvaluation ? pct(day.shadowEvaluation.targetRealizedVol5d) : "—"}</strong><small>${esc(shadowStatusText)}</small></div></div>`
    + `<div class="st-fd-selected-metrics"><div><span>จำนวนแจ้งเตือน / ตัดสินใจ / สลับโมเดล (${esc(day.ticker)})</span><strong>${ops ? `${ops.alertCount} / ${ops.decisionEventCount} / ${ops.promotionCount}` : "—"}</strong><small>Retained ${ops?.retainedCount ?? 0} · Insuff ${ops?.insufficientPairsCount ?? 0} · Cooldown ${ops?.cooldownSuppressedCount ?? 0}</small></div><div><span>สัดส่วนพยากรณ์สำเร็จ / ประเมินได้</span><strong>${cov ? `${pctRatio(cov.publishRate)} / ${pctRatio(cov.matureEvaluationRate)}` : "—"}</strong><small>Pending ${cov?.pendingLabels ?? 0} · Invalid ${cov?.invalidForecasts ?? 0}</small></div><div><span>จำนวนคู่ข้อมูลที่เปรียบเทียบได้ (${esc(day.ticker)})</span><strong>${cov ? cov.matchedCommonPanelN.toLocaleString() : "—"}</strong><small>Mean maturity lag: ${ops?.meanLabelMaturityLagCalendarDays !== null && ops?.meanLabelMaturityLagCalendarDays !== undefined ? `${ops.meanLabelMaturityLagCalendarDays.toFixed(2)} d` : "—"}</small></div></div>`
    + (detectorSummary
      ? `<details><summary>รายละเอียด ADWIN: ความคลาดเคลื่อน ที่ครบกำหนดในวันนี้ (${day.detectorRowsOnDate.length} แถว)</summary><div class="st-table-wrap"><table class="st-table"><thead><tr><th>Prediction Date</th><th>Eval Date</th><th>Champion</th><th>Abs Error</th><th>ADWIN Width</th><th>ADWIN Est.</th><th>Signal</th><th>Decision</th></tr></thead><tbody>${detectorSummary}</tbody></table></div></details>`
      : `<p class="st-fd-method-note">ไม่มี served error ที่ครบกำหนดประเมินเข้าสู่ ADWIN ในวันที่ ${esc(day.date)} (อาจยังรอ target maturity 5 วันซื้อขาย หรือเป็นวันก่อน label แรกครบกำหนด)</p>`)
    + `</section>`
    + `<section class="st-card"><div class="st-fd-subheading"><div><h3>ประวัติ ADWIN Alert และการตัดสินใจ (${esc(day.ticker)})</h3><p>ทุกเหตุการณ์ตัดสินใจต้องอ้างอิงจาก ADWIN alert จริง 1:1 และแสดงเหตุผลของทุกสถานะ</p></div><span>${day.tickerEvents.length} เหตุการณ์</span></div>${eventsSection}</section>`
    + `<section class="st-card"><div class="st-fd-subheading"><div><h3>Model Version Timeline (${esc(day.ticker)})</h3><p>ลำดับรุ่นแชมเปี้ยนตั้งแต่ Validation cutover และการสลับเป็น Frozen B3 Snapshot ใน session ถัดไป</p></div><span>${day.tickerTimeline.length} รุ่น</span></div><div class="st-table-wrap"><table class="st-table"><thead><tr><th>Version</th><th>Event Type</th><th>Model</th><th>Decision Date</th><th>Effective Date</th><th>State Hash</th><th>Rollback Target</th><th>เหตุผล</th></tr></thead><tbody>${timelineRows}</tbody></table></div></section>`
    + `<section class="st-card"><div class="st-fd-subheading"><div><h3>เปรียบเทียบความคลาดเคลื่อนจากข้อมูลที่จับคู่ได้ (${esc(day.ticker)} &amp; MACRO)</h3><p>MAE ยิ่งต่ำยิ่งดี · ส่วนต่าง = MAE คู่เทียบ − MAE Policy: ค่าบวกหมายถึง Policy คลาดเคลื่อนน้อยกว่า · ผลเชิงสำรวจบนชุด Test</p></div><span>Matched Panel</span></div><div class="st-table-wrap"><table class="st-table"><thead><tr><th>ขอบเขต</th><th>รหัสเปรียบเทียบ</th><th>คู่เทียบ</th><th>จำนวนคู่</th><th>Policy MAE</th><th>คู่เทียบ MAE</th><th>ส่วนต่าง</th><th>ส่วนต่างสัมพัทธ์</th><th>สถานะ</th></tr></thead><tbody>${comparisonRows}</tbody></table></div></section>`
    + `<details class="st-policy-ids"><summary>รหัสอ้างอิงเชิงเทคนิค</summary><p class="st-fd-method-note">Policy Config Fingerprint: <code>${esc(manifest.policyConfigFingerprint)}</code> · Replay Experiment ID: <code>${esc(manifest.policyReplayExperimentId)}</code> · Evaluation ID: <code>${esc(manifest.policyEvaluationId)}</code></p></details>`
    + `</div>`;
}
