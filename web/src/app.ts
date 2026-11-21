import { loadSnapshot, selectRecordedSessions, type SnapshotState } from "./data/loadSnapshot.js";
import { modelId, modelLabel, type ModelName, type Ticker } from "./data/schemas.js";

interface RouteDefinition {
  path: string;
  label: string;
  thai: string;
  description: string;
  icon: string;
}

const routes: RouteDefinition[] = [
  { path: "/overview", label: "Overview", thai: "ภาพรวม", description: "สถานะและขอบเขตของชุดผลที่ตรวจแล้ว", icon: "overview" },
  { path: "/models", label: "Models", thai: "เปรียบเทียบโมเดล", description: "ผลเปรียบเทียบ B0–B3 จาก snapshot", icon: "models" },
  { path: "/forecasts", label: "Forecasts", thai: "สำรวจ Forecast", description: "อ่านเฉพาะ forecast ที่บันทึกไว้", icon: "forecasts" },
  { path: "/portfolio", label: "Portfolio", thai: "ทดลองน้ำหนักพอร์ต", description: "ความเสี่ยงพอร์ตจาก covariance ที่บันทึกไว้", icon: "portfolio" },
  { path: "/drift", label: "Drift", thai: "Online Learning & ADWIN", description: "ผล monitor จากชุดทดลองที่ตรึงไว้", icon: "drift" },
  { path: "/research", label: "Research", thai: "หลักฐาน H1–H3", description: "หลักฐานสถิติที่คำนวณไว้ใน Stage 06", icon: "research" },
  { path: "/provenance", label: "Provenance", thai: "ที่มาและคุณภาพข้อมูล", description: "IDs, hashes และข้อจำกัดของ snapshot", icon: "provenance" },
  { path: "/guide", label: "Guide", thai: "คู่มือวิธีอ่านผล", description: "ความหมายของข้อมูลและข้อจำกัด", icon: "guide" },
];

const modelNames: ModelName[] = ["CONSTANT_BASELINE", "ROLLING_20D_BASELINE", "STATIC_SGD", "ONLINE_SGD"];
const tickerNames: Ticker[] = ["SPY", "IEF", "GLD"];
const tickerLabel: Record<Ticker, string> = { SPY: "SPY · US equities", IEF: "IEF · Treasury bonds", GLD: "GLD · Gold" };
const iconShapes: Record<string, string> = {
  overview: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  models: '<path d="M4 19V5M4 19h17"/><rect x="7" y="11" width="3" height="5" rx="1"/><rect x="13" y="7" width="3" height="9" rx="1"/><rect x="19" y="4" width="2" height="12" rx="1"/>',
  forecasts: '<path d="M3 12h4l3-7 4 14 3-7h4"/><circle cx="10" cy="5" r="1"/><circle cx="14" cy="19" r="1"/>',
  portfolio: '<path d="M12 3v9h9M20.5 15A9 9 0 1 1 9 3.5M15 3.5A9 9 0 0 1 20.5 9"/>',
  drift: '<path d="M3 12c3-8 6 8 9 0s6 8 9 0M3 5h18M3 19h18"/>',
  research: '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3M8 15h8"/>',
  provenance: '<path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z"/><path d="m9 12 2 2 4-4"/>',
  guide: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 0 4 22zM4 5v17M8 7h8M8 11h7"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  arrowLeft: '<path d="m14 18-6-6 6-6"/>',
  arrowRight: '<path d="m10 18 6-6-6-6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  lock: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
};

interface ViewState {
  snapshot: SnapshotState;
  routePath: string;
  mobileMenuOpen: boolean;
  moreOpen: boolean;
  ticker: Ticker;
  model: ModelName;
  sessionIndex: number;
  attempt: number;
}

function icon(name: string, size = 20): string {
  return `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${iconShapes[name] ?? ""}</svg>`;
}

function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] ?? character);
}

function currentRoute(): string {
  const route = window.location.hash.replace(/^#/, "");
  return routes.some((item) => item.path === route) ? route : "/overview";
}

function navLink(route: RouteDefinition, active: boolean, extraClass = ""): string {
  return `<a class="nav-link${active ? " active" : ""}${extraClass ? ` ${extraClass}` : ""}" href="#${route.path}" ${active ? 'aria-current="page"' : ""}>${icon(route.icon, 19)}<span>${route.label}</span>${active ? '<span class="nav-active-mark" aria-hidden="true"></span>' : ""}</a>`;
}

function loadingState(): string {
  return `<section aria-live="polite" class="state-panel loading-state"><div class="loading-mark" aria-hidden="true"><span></span><span></span><span></span></div><div><h3>กำลังตรวจสอบ Frozen Snapshot</h3><p>กำลังตรวจ hash, Evaluation ID, Replay ID และ schema ก่อนแสดงข้อมูล</p></div></section>`;
}

function emptyState(title: string, message: string, action = ""): string {
  return `<section class="empty-state" role="status"><div class="empty-state-icon">${icon("lock", 22)}</div><div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p>${action}</div></section>`;
}

function errorState(message: string, title = "หยุดแสดงผลเพื่อป้องกันข้อมูลผิดชุด"): string {
  return `<section class="error-state" role="alert"><div class="error-icon">!</div><div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p><button class="button button-secondary" type="button" data-action="retry">ตรวจอีกครั้ง</button></div></section>`;
}

function snapshotBanner(snapshot: SnapshotState): string {
  if (snapshot.status === "loading") return `<section class="snapshot-banner loading" aria-live="polite"><div class="snapshot-banner-icon"><span class="pulse-dot"></span></div><div class="snapshot-banner-copy"><strong>กำลังตรวจสอบ snapshot</strong><span>ตรวจ SHA-256, source IDs และ schema ก่อนเปิดข้อมูล</span></div><div class="snapshot-banner-badges"><span class="pill pill-neutral">ไม่ใช่ข้อมูลสด</span></div></section>`;
  if (snapshot.status === "missing") return `<section class="snapshot-banner missing" aria-live="polite"><div class="snapshot-banner-icon">!</div><div class="snapshot-banner-copy"><strong>ยังโหลด snapshot ไม่ได้</strong><span>${escapeHtml(snapshot.message)}</span></div><div class="snapshot-banner-badges"><span class="pill pill-neutral">ไม่ใช่ข้อมูลสด</span></div></section>`;
  if (snapshot.status === "error") return `<section class="snapshot-banner error" aria-live="polite"><div class="snapshot-banner-icon">!</div><div class="snapshot-banner-copy"><strong>หยุดแสดงผล · ตรวจพบปัญหา</strong><span>${escapeHtml(snapshot.message)}</span></div><div class="snapshot-banner-badges"><span class="pill pill-neutral">ไม่ใช่ข้อมูลสด</span></div></section>`;
  return `<section class="snapshot-banner ready" aria-live="polite"><div class="snapshot-banner-icon">${icon("check", 18)}</div><div class="snapshot-banner-copy"><strong>ตรวจ Frozen Snapshot ผ่าน</strong><span>${escapeHtml(snapshot.manifest.mode)} · Review snapshot · รายงานยังรออนุมัติ</span></div><div class="snapshot-banner-badges"><span class="pill pill-neutral">ไม่ใช่ข้อมูลสด</span><span class="pill pill-pending">Report approval pending</span></div></section>`;
}

function overviewPage(snapshot: SnapshotState): string {
  if (snapshot.status === "loading") return loadingState();
  if (snapshot.status === "missing") return emptyState("ยังไม่มี Frozen Snapshot", "ไม่มีตัวเลขหรือกราฟแสดงจนกว่า source ZIP จะผ่านการตรวจสอบและโหลดไฟล์ครบ");
  if (snapshot.status === "error") return emptyState("ข้อมูลถูกซ่อนไว้ระหว่างตรวจสอบ", "ตัวตรวจพบความไม่ตรงกัน จึงหยุดแสดงผลจาก snapshot นี้");
  const manifest = snapshot.manifest;
  const routeCards = routes.filter((route) => route.path !== "/overview").map((route, index) => `<button class="route-card" type="button" data-route="${route.path}"><span class="route-card-icon route-color-${index}">${icon(route.icon, 19)}</span><span class="route-card-title"><strong>${escapeHtml(route.thai)}</strong><small>${escapeHtml(route.label)}</small></span><span class="route-card-arrow">${icon("arrowRight", 17)}</span></button>`).join("");
  return `
    <section class="hero-card">
      <div class="hero-copy"><div class="hero-badge"><span class="hero-badge-dot"></span> EXPERIMENT SNAPSHOT VERIFIED</div><h2>สำรวจความผันผวน<br class="desktop-break" />จากผลทดลองที่บันทึกไว้</h2><p>พื้นที่อ่านผลแบบ read-only สำหรับ SPY, IEF และ GLD ใช้ข้อมูล Frozen Snapshot ชุดเดียวตลอดการสำรวจ</p><button class="button button-primary" type="button" data-route="/forecasts">เปิด Recorded Session ${icon("arrowRight", 17)}</button></div>
      <div class="hero-graphic" aria-hidden="true"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="hero-orbit-core"><span>RV5</span><small>FROZEN</small></div><span class="orbit-point point-spy">SPY</span><span class="orbit-point point-ief">IEF</span><span class="orbit-point point-gld">GLD</span><div class="hero-graphic-caption">XNYS · 5 trading sessions</div></div>
    </section>
    <div class="overview-grid">
      <section class="overview-section-card identity-overview-card"><div class="section-card-heading"><div><span class="section-overline">SOURCE IDENTITY</span><h3>ชุดข้อมูลที่กำลังอ่าน</h3></div><span class="verified-badge">${icon("check", 13)} VERIFIED</span></div><div class="identity-pair"><span>Evaluation ID</span><code>${escapeHtml(manifest.evaluationId)}</code></div><div class="identity-pair"><span>Replay ID</span><code>${escapeHtml(manifest.replayId)}</code></div><div class="identity-meta-row"><span>Strict cutoff</span><strong>${escapeHtml(manifest.strictCutoff)}</strong><span class="meta-divider"></span><span>Source mode</span><strong>Simulated Historical Replay</strong></div></section>
      <section class="overview-section-card phase-card"><div class="section-card-heading"><div><span class="section-overline">CURRENT PHASE</span><h3>พื้นที่ทำงานแบบอ่านอย่างเดียว</h3></div><span class="phase-index">01</span></div><p>Snapshot ผ่านการตรวจ checksum และ schema แล้ว หน้านี้ยังไม่แสดง model metrics, hypothesis results หรือ portfolio calculations</p><div class="phase-check-list"><span>${icon("check", 15)} App Shell พร้อม</span><span>${icon("check", 15)} Snapshot adapter ผ่าน</span><span class="phase-next">ขั้นต่อไป · D3 data views</span></div></section>
    </div>
    <section class="route-preview-section"><div class="section-heading-row"><div><span class="section-overline">EXPLORE THE LAB</span><h3>เลือกพื้นที่สำรวจ</h3></div><span class="route-count">08 PAGES</span></div><div class="route-card-grid">${routeCards}</div></section>`;
}

function sessionCard(state: ViewState): string {
  if (state.snapshot.status === "loading") return loadingState();
  if (state.snapshot.status === "missing") return emptyState("Recorded sessions ยังไม่พร้อม", "เมื่อ snapshot files ไม่ครบ จะไม่สร้างวันที่หรือ forecast ขึ้นมาแทน");
  if (state.snapshot.status === "error") return errorState(state.snapshot.message);
  const available = selectRecordedSessions(state.snapshot.sessions, state.ticker, state.model);
  const index = Math.max(0, Math.min(state.sessionIndex, available.length - 1));
  const row = available[index];
  const modelOptions = modelNames.map((model) => `<option value="${model}" ${state.model === model ? "selected" : ""}>${modelId(model)} · ${escapeHtml(modelLabel(model))}</option>`).join("");
  const tickerOptions = tickerNames.map((ticker) => `<option value="${ticker}" ${state.ticker === ticker ? "selected" : ""}>${ticker}</option>`).join("");
  const dateOptions = available.map((session, sessionIndex) => `<option value="${sessionIndex}" ${index === sessionIndex ? "selected" : ""}>${escapeHtml(session.predictionDate)}</option>`).join("");
  if (!row) return `<section class="session-card"><div class="eyebrow"><span class="eyebrow-dot"></span> RECORDED SESSION · TEST</div><h2 id="session-title">สำรวจผลที่บันทึกไว้</h2><div class="session-filters"><label class="field-label">สินทรัพย์<select data-field="ticker">${tickerOptions}</select></label><label class="field-label">โมเดล<select data-field="model">${modelOptions}</select></label></div>${emptyState("ไม่มีบันทึกสำหรับตัวกรองนี้", "ไม่พบแถวใน snapshot ที่ผ่านการตรวจสอบสำหรับสินทรัพย์และโมเดลที่เลือก ลองเปลี่ยนตัวกรอง")}</section>`;
  const evaluation = state.snapshot.evaluations.get(row.predictionId);
  const pending = row.evaluationStatus === "PENDING_LABEL";
  const isEvaluable = row.evaluationStatus === "EVALUABLE" && evaluation !== undefined;
  const validForecast = row.forecastStatus === "VALID" && row.predictedVolAnnualized !== null;
  const format = (value: number | null | undefined) => value === null || value === undefined ? "—" : value.toFixed(6);
  const statusClass = pending ? "status-pending" : isEvaluable ? "status-evaluable" : "status-neutral";
  const statusLabel = pending ? "PENDING · ยังไม่ครบช่วงเป้าหมาย" : isEvaluable ? "EVALUABLE · ประเมินได้" : row.evaluationStatus;
  const actualLabel = pending ? "Target ยังไม่ mature ณ cutoff" : "Annualized decimal · evaluation.csv";
  const errorLabel = pending ? "ยังไม่ให้คะแนน" : "ค่าที่บันทึกใน Stage 06";
  const noActualWarning = row.evaluationStatus === "EVALUABLE" && !evaluation ? '<p class="error-inline">ไม่พบแถวประเมินที่จับคู่กับ prediction ID นี้ จึงซ่อน actual/error</p>' : "";
  const noForecastWarning = !validForecast ? '<p class="error-inline">ไม่มีค่าพยากรณ์ที่ใช้แสดงได้ตามสถานะใน source row</p>' : "";
  return `
    <section class="session-card" aria-labelledby="session-title">
      <div class="session-head"><div><div class="eyebrow"><span class="eyebrow-dot"></span> RECORDED SESSION · TEST</div><h2 id="session-title">สำรวจผลที่บันทึกไว้</h2><p>เลื่อนไปยังวัน XNYS ที่มีอยู่ใน Frozen Snapshot เท่านั้น การเปลี่ยนวันไม่เรียก Replay หรือคำนวณโมเดลใหม่</p></div><span class="readonly-pill">${icon("lock", 14)} ดูอย่างเดียว</span></div>
      <div class="session-filters"><label class="field-label">สินทรัพย์<select data-field="ticker">${tickerOptions}</select></label><label class="field-label">โมเดล<select data-field="model">${modelOptions}</select></label><label class="field-label">วันที่บันทึกไว้<select aria-label="เลือกวันที่บันทึกไว้" data-field="date">${dateOptions}</select></label></div>
      <div class="session-date-row"><button class="icon-button" type="button" aria-label="วันก่อนหน้า" data-action="previous" ${index === 0 ? "disabled" : ""}>${icon("arrowLeft")}</button><div class="session-date"><span>วันทำนาย · XNYS</span><strong>${escapeHtml(row.predictionDate)}</strong><small>บันทึกที่ ${index + 1} จาก ${available.length}</small></div><button class="icon-button" type="button" aria-label="วันถัดไป" data-action="next" ${index >= available.length - 1 ? "disabled" : ""}>${icon("arrowRight")}</button></div>
      <div class="session-status-row"><span class="status-chip ${statusClass}">${escapeHtml(statusLabel)}</span><span class="status-chip status-outline">Forecast · ${escapeHtml(row.forecastStatus)}</span><span class="session-horizon">ช่วงเป้าหมาย ${escapeHtml(row.targetStartDatePrediction)} → ${escapeHtml(row.targetEndDatePrediction)}</span></div>
      <div class="session-values"><div class="session-value-card"><span>Forecast RV5</span><strong>${validForecast ? format(row.predictedVolAnnualized) : "—"}</strong><small>Annualized decimal · จาก forecast_audit.csv</small></div><div class="session-value-card${pending ? " muted-value" : ""}"><span>Actual RV5</span><strong>${pending ? "—" : format(evaluation?.targetRealizedVol5d)}</strong><small>${actualLabel}</small></div><div class="session-value-card${pending ? " muted-value" : ""}"><span>Absolute error</span><strong>${pending ? "—" : format(evaluation?.absoluteError)}</strong><small>${errorLabel}</small></div></div>
      ${pending ? '<p class="pending-note"><span>i</span> Target ยังไม่ครบ 5 วันซื้อขายก่อน strict cutoff จึงไม่แสดง actual หรือ error เป็นศูนย์</p>' : ""}${noActualWarning}${noForecastWarning}
      <div class="session-footer"><span>Prediction ID <code>${escapeHtml(row.predictionId)}</code></span><span>${escapeHtml(tickerLabel[state.ticker])} · ${modelId(state.model)}</span></div>
      <div class="session-actions"><span>เปลี่ยนเฉพาะการเลือก observation ที่บันทึกไว้</span><button type="button" class="text-button" data-action="reset">Reset ไปวันแรก</button></div>
    </section>`;
}

function emptyPage(title: string, description: string, source: string): string {
  return `<div class="page-stack">${emptyState(title, description)}<div class="source-placeholder"><span class="source-placeholder-icon">${icon("lock", 16)}</span><div><strong>Source ที่เตรียมไว้</strong><p>${escapeHtml(source)}</p></div><span class="source-placeholder-tag">NEXT PHASE</span></div></div>`;
}

function provenancePage(snapshot: SnapshotState): string {
  if (snapshot.status === "loading") return loadingState();
  if (snapshot.status !== "ready") return emptyState("ยังไม่มี provenance ที่ผ่านการตรวจ", "ซ่อน Source IDs และ checksums จนกว่า adapter จะยืนยัน snapshot ได้");
  const { manifest } = snapshot;
  const files = Object.entries(manifest.files).map(([, file]) => `<div class="source-file-row"><div class="file-type-mark">CSV</div><div class="source-file-details"><strong>${escapeHtml(file.path)}</strong><small>${file.rowCount.toLocaleString()} source rows · ${file.headers.length} columns</small></div><code>${escapeHtml(file.sha256)}</code></div>`).join("");
  return `<div class="page-stack"><section class="provenance-summary-card"><div class="provenance-summary-top"><div><span class="section-overline">FROZEN SOURCE</span><h2>ที่มาและขอบเขต</h2></div><span class="verified-badge">${icon("check", 13)} SOURCE VERIFIED</span></div><p>ทั้งสองไฟล์ CSV มาจาก handoff ZIP ที่ pin ไว้ ตรวจ outer SHA-256, manifest ภายใน ZIP และ member hashes ก่อนอ่านข้อมูล</p><div class="provenance-pills"><span class="pill pill-neutral">${escapeHtml(manifest.mode)}</span><span class="pill pill-pending">Report approval pending</span><span class="pill pill-neutral">Point-in-time source not verified</span></div><div class="identity-pair"><span>Evaluation ID</span><code>${escapeHtml(manifest.evaluationId)}</code></div><div class="identity-pair"><span>Replay ID</span><code>${escapeHtml(manifest.replayId)}</code></div><div class="identity-pair"><span>Handoff commit</span><code>${escapeHtml(manifest.sourceHandoffCommit)}</code></div><div class="identity-pair"><span>ZIP SHA-256</span><code>${escapeHtml(manifest.sourceZipSha256)}</code></div></section><section class="source-file-card"><div class="section-card-heading"><div><span class="section-overline">PUBLIC DATA SUBSET</span><h3>ไฟล์ที่ใช้ใน D1–D2</h3></div><span class="pill pill-neutral">CSV · READ ONLY</span></div>${files}<p class="source-footnote">Manifest JSON และ handoff identity ถูกใช้ตอน build เพื่อตรวจสอบ IDs แต่ไม่ถูกเผยแพร่เป็น data table เพิ่มเติม</p></section><section class="limitation-card"><span class="limitation-mark">i</span><p>Snapshot นี้เป็นผลจาก Simulated Historical Replay ไม่ยืนยันว่าข้อมูลตลาดแต่ละรายการเข้าถึงได้ ณ วันที่จำลอง และยังไม่ใช่รายงานที่ได้รับอนุมัติ</p></section></div>`;
}

function guidePage(): string {
  const definitions = [
    ["Forward Realized Volatility (RV5)", "ความผันผวนที่วัดจากผลตอบแทนจริงใน 5 วันซื้อขายถัดไป ใช้หน่วย annualized decimal"],
    ["Pending label", "ข้อมูล forecast มีอยู่แล้ว แต่ยังไม่ครบช่วงเป้าหมาย 5 วัน ณ cutoff จึงยังไม่มี actual และไม่มี error ให้คะแนน"],
    ["Recorded session", "การเลื่อนดูวันที่ใน CSV ที่บันทึกไว้แล้วเท่านั้น ไม่มีการเรียก Train, Replay หรือ inference"],
    ["Simulated Historical Replay", "ผลการทดลองย้อนหลังที่สร้างจาก snapshot ตามวันจำลอง ไม่ยืนยัน point-in-time data availability และไม่ใช่ forecast สด"],
  ];
  return `<div class="page-stack"><section class="guide-intro"><span class="section-overline">READ THE EVIDENCE</span><h2>วิธีอ่านผลโดยไม่ตีความเกินข้อมูล</h2><p>Dashboard นี้เป็นพื้นที่สำรวจผลจากการทดลองที่ตรึงไว้ ปุ่มและตัวกรองเปลี่ยนเฉพาะแถวที่กำลังดู</p></section><div class="glossary-grid">${definitions.map(([term, definition], index) => `<article class="glossary-card"><span class="glossary-number">0${index + 1}</span><h3>${term}</h3><p>${definition}</p></article>`).join("")}</div><div class="limitation-card"><span class="limitation-mark">!</span><p>ผล Test เป็นหลักฐานจาก frozen sample เท่านั้น ไม่รับรองผลในอนาคต และไม่ควรตีความเป็นคำแนะนำซื้อขาย</p></div></div>`;
}

function pageContent(state: ViewState): string {
  if (state.routePath === "/overview") return overviewPage(state.snapshot);
  if (state.routePath === "/forecasts") return sessionCard(state);
  if (state.routePath === "/provenance") return provenancePage(state.snapshot);
  if (state.routePath === "/guide") return guidePage();
  if (state.routePath === "/models") return emptyPage("ยังไม่แสดงผลเปรียบเทียบโมเดลใน D1–D2", "Snapshot นี้ผ่านการตรวจแล้ว แต่หน้า Model Metrics จะเชื่อมใน D3 เท่านั้น จึงไม่มีการใส่ตัวเลขตัวอย่างหรือคำนวณ metric ซ้ำ", "model_metrics.csv · pair_comparisons.csv");
  if (state.routePath === "/portfolio") return emptyPage("เครื่องมือคำนวณพอร์ตอยู่ใน D4", "ยังไม่มีการคำนวณ portfolio risk ในรอบนี้ หน้านี้จะใช้เฉพาะ covariance ที่บันทึกไว้และจะไม่ประมาณ correlation ใหม่", "portfolio_risk.csv · stored covariance_matrix");
  if (state.routePath === "/drift") return emptyPage("ผล Drift จะแสดงใน D5", "หน้านี้จะอ่าน rolling MAE และ ADWIN ที่ Stage 06 บันทึกไว้ โดยไม่มี marker หรือ update event ที่สร้างขึ้นเอง", "rolling_mae20.csv · drift_error_timeline.csv");
  return emptyPage("หลักฐาน H1–H3 จะแสดงใน D5", "ค่า p, confidence interval และการตัดสินใจจะอ่านจากผล Stage 06 โดยไม่ทำ hypothesis inference ใน browser", "H1_results.csv · hypothesis_results.csv · bootstrap_diagnostics.csv");
}

function shell(state: ViewState): string {
  const route = routes.find((item) => item.path === state.routePath) ?? routes[0];
  const identity = state.snapshot.status === "ready" ? "VERIFIED REVIEW SNAPSHOT" : state.snapshot.status === "loading" ? "VERIFYING SNAPSHOT" : "SNAPSHOT NOT LOADED";
  const snapshotId = state.snapshot.status === "ready" ? state.snapshot.manifest.evaluationId : "ID withheld until verification";
  const sidebarLinks = routes.map((item) => navLink(item, item.path === state.routePath)).join("");
  const mobilePrimary = routes.slice(0, 3).map((item) => navLink(item, item.path === state.routePath)).join("");
  const secondaryRoutes = routes.slice(3);
  const mobileDrawer = state.mobileMenuOpen ? `<div class="mobile-nav-overlay" data-action="close-menu"><nav class="mobile-drawer" aria-label="เมนูทั้งหมด"><div class="drawer-heading"><strong>ไปยังหน้า</strong><button class="icon-button" type="button" data-action="close-menu" aria-label="ปิดเมนู">×</button></div>${sidebarLinks}</nav></div>` : "";
  const morePanel = state.moreOpen ? `<div class="mobile-more-panel" aria-label="More pages">${secondaryRoutes.map((item) => navLink(item, item.path === state.routePath)).join("")}</div>` : "";
  return `<div class="app-frame">
    <aside class="sidebar" aria-label="Main navigation"><div class="brand-lockup"><div class="brand-mark">A</div><div><strong>Adaptive Risk Lab</strong><span>DEDS · RESEARCH WORKBENCH</span></div></div><div class="sidebar-section-label">WORKSPACE</div><nav class="sidebar-nav">${sidebarLinks}</nav><div class="sidebar-bottom"><div class="sidebar-status-mark">${icon("lock", 16)}<span>Read-only snapshot</span></div><div class="sidebar-caption">ผลลัพธ์ที่ตรึงไว้สำหรับทบทวน<br />ไม่มีการเรียก ML pipeline</div><span class="version-label">D1–D2 FOUNDATION</span></div></aside>
    <div class="app-main"><header class="mobile-topbar"><a class="mobile-brand" href="#/overview"><span class="brand-mark small">A</span><strong>Adaptive Risk Lab</strong></a><button class="icon-button mobile-menu-button" type="button" aria-label="เปิดเมนู" aria-expanded="${state.mobileMenuOpen}" data-action="toggle-menu">${icon("menu")}</button></header>${mobileDrawer}<main class="workspace"><div class="top-identity-row"><div class="breadcrumbs"><span>DEDS</span><span class="breadcrumb-separator">/</span><strong>Adaptive Portfolio Risk Lab</strong></div><div class="identity-state"><span class="identity-dot ${state.snapshot.status}"></span>${identity}</div></div><div class="page-heading-row"><div><div class="page-kicker">RESEARCH WORKBENCH <span>·</span> FROZEN DATASET</div><h1>${escapeHtml(route.thai)}</h1><p>${escapeHtml(route.description)}</p></div><button class="snapshot-id-button" type="button" title="คัดลอก Evaluation ID และ Replay ID ที่ pin ไว้" data-action="copy-id"><span class="snapshot-id-icon">${icon("lock", 15)}</span><span><small>PINNED EVALUATION</small><strong>${escapeHtml(snapshotId.slice(0, 12))}${state.snapshot.status === "ready" ? "…" : ""}</strong></span><span class="copy-hint">COPY</span></button></div>${snapshotBanner(state.snapshot)}${state.snapshot.status === "missing" ? errorState(state.snapshot.message, "ยังไม่มีไฟล์ snapshot ที่ตรวจสอบแล้ว") : state.snapshot.status === "error" ? errorState(state.snapshot.message) : ""}<div class="page-content">${pageContent(state)}</div><footer class="app-footer"><span>DEDS · Adaptive Portfolio Risk Lab</span><span>${icon("lock", 13)} Read-only · No live forecast</span></footer></main><nav class="mobile-bottom-nav" aria-label="Navigation">${mobilePrimary}<button class="nav-link mobile-more-link${state.moreOpen ? " active" : ""}" type="button" aria-expanded="${state.moreOpen}" data-action="toggle-more">${icon("menu", 19)}<span>More</span></button></nav>${morePanel}</div>
  </div>`;
}

function render(root: HTMLElement, state: ViewState): void {
  root.innerHTML = shell(state);
  const route = routes.find((item) => item.path === state.routePath);
  document.title = `${route?.label ?? "Overview"} · Adaptive Portfolio Risk Lab`;
}

async function reload(root: HTMLElement, state: ViewState): Promise<void> {
  state.snapshot = { status: "loading" };
  state.attempt += 1;
  render(root, state);
  state.snapshot = await loadSnapshot();
  render(root, state);
}

export function startApp(root: HTMLElement): void {
  const state: ViewState = {
    snapshot: { status: "loading" },
    routePath: currentRoute(),
    mobileMenuOpen: false,
    moreOpen: false,
    ticker: "SPY",
    model: "ONLINE_SGD",
    sessionIndex: 0,
    attempt: 0,
  };

  const updateRoute = () => {
    state.routePath = currentRoute();
    state.mobileMenuOpen = false;
    state.moreOpen = false;
    state.sessionIndex = 0;
    render(root, state);
  };
  window.addEventListener("hashchange", updateRoute);
  root.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const button = target?.closest<HTMLElement>("[data-action], [data-route]");
    if (!button) return;
    const route = button.dataset.route;
    if (route) { window.location.hash = route; return; }
    switch (button.dataset.action) {
      case "toggle-menu": state.mobileMenuOpen = !state.mobileMenuOpen; render(root, state); break;
      case "close-menu": if (target === button || button.classList.contains("mobile-nav-overlay")) { state.mobileMenuOpen = false; render(root, state); } break;
      case "toggle-more": state.moreOpen = !state.moreOpen; render(root, state); break;
      case "previous": state.sessionIndex = Math.max(0, state.sessionIndex - 1); render(root, state); break;
      case "next": state.sessionIndex += 1; render(root, state); break;
      case "reset": state.sessionIndex = 0; render(root, state); break;
      case "retry": void reload(root, state); break;
      case "copy-id": {
        if (state.snapshot.status === "ready") void navigator.clipboard?.writeText(`Evaluation ID: ${state.snapshot.manifest.evaluationId}\nReplay ID: ${state.snapshot.manifest.replayId}`);
        break;
      }
    }
  });
  root.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) return;
    if (target.dataset.field === "ticker" && tickerNames.includes(target.value as Ticker)) { state.ticker = target.value as Ticker; state.sessionIndex = 0; }
    if (target.dataset.field === "model" && modelNames.includes(target.value as ModelName)) { state.model = target.value as ModelName; state.sessionIndex = 0; }
    if (target.dataset.field === "date") state.sessionIndex = Number(target.value);
    render(root, state);
  });
  if (!window.location.hash) window.location.hash = "/overview";
  render(root, state);
  void loadSnapshot().then((snapshot) => { state.snapshot = snapshot; render(root, state); });
}
