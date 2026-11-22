import type { H1ResultRow, HypothesisResultRow } from "../data/schemas.js";

export type ResearchDisplayUnit = "decimal" | "percent";

function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] ?? character);
}

function formatAnnualized(value: number, unit: ResearchDisplayUnit): string {
  return unit === "percent" ? `${(value * 100).toFixed(2)}%` : value.toFixed(4);
}

function formatDelta(value: number, unit: ResearchDisplayUnit): string {
  const sign = value > 0 ? "+" : "";
  return unit === "percent"
    ? `${sign}${(value * 100).toFixed(2)} จุดเปอร์เซ็นต์`
    : `${sign}${value.toFixed(4)} (ทศนิยมรายปี)`;
}

function comparisonModel(hypothesisId: "H2" | "H3"): { id: string; name: string } {
  return hypothesisId === "H2"
    ? { id: "B2", name: "Static SGD" }
    : { id: "B1", name: "Rolling 20D baseline" };
}

export function hypothesisQuestionThai(hypothesisId: "H1" | "H2" | "H3"): string {
  if (hypothesisId === "H1") return "ในชุด Train ค่า RV5 ย้อนหลังช่วยบอกความผันผวนจริงใน 5 วันถัดไปได้หรือไม่?";
  const baseline = comparisonModel(hypothesisId);
  return `B3 (Online SGD) มีค่าความคลาดเคลื่อน MAE ต่ำกว่า ${baseline.id} (${baseline.name}) หรือไม่?`;
}

export function hypothesisDecisionThai(decision: string): string {
  const normalized = decision.trim().toLowerCase().replaceAll("₀", "0").replaceAll("_", " ").replace(/\s+/g, " ");
  if (/fail to reject|do not reject|not significant/.test(normalized)) return "ยังไม่มีหลักฐานเพียงพอให้ปฏิเสธ H₀";
  if (/insufficient|not computed|invalid/.test(normalized)) return "ยังสรุปผลไม่ได้ · หลักฐานไม่เพียงพอ";
  if (/reject h0/.test(normalized)) return "ปฏิเสธ H₀ · พบหลักฐานสอดคล้องกับสมมติฐานทางเลือก";
  return `ผลตามข้อมูล: ${decision}`;
}

export function hypothesisMethodThai(hypothesisId: "H1" | "H2" | "H3", method: string): string {
  if (hypothesisId === "H1") {
    const lag = /maxlags\s*=\s*(\d+)/i.exec(method)?.[1] ?? "5";
    return `ใช้การถดถอยเชิงเส้น OLS และวิธี Newey–West/HAC เพื่อรองรับความคลาดเคลื่อนที่สัมพันธ์กันตามเวลา (พิจารณาย้อนหลัง ${lag} วันซื้อขาย); ทดสอบว่าความสัมพันธ์เป็นบวกหรือไม่ แล้วปรับค่า p ด้วย Holm สำหรับ SPY, IEF และ GLD`;
  }
  const blockLength = /(\d+)\s+XNYS sessions/i.exec(method)?.[1] ?? "10";
  const replicates = Number((/[\d,]+(?=\s+replicates)/i.exec(method)?.[0] ?? "2,000").replaceAll(",", "")).toLocaleString("en-US");
  const seed = /seed\s*=\s*(\d+)/i.exec(method)?.[1] ?? "42";
  return `สุ่มข้อมูลซ้ำโดยยกช่วง ${blockLength} วันซื้อขายติดกันเป็นบล็อก และเลื่อนช่วงเดียวกันให้ทั้ง 3 ETF · ${replicates} รอบ · ค่าเริ่มสุ่ม (seed) ${seed} · ปรับค่า p ระหว่าง H2/H3 ด้วย Holm`;
}

export function hypothesisStatusThai(status: string): string {
  const normalized = status.trim().toUpperCase();
  if (normalized === "COMPUTED") return "คำนวณสำเร็จ";
  if (normalized === "") return "แหล่งข้อมูลไม่ได้ระบุสถานะ";
  if (normalized.includes("INVALID") || normalized.includes("FAILED")) return `วิธีคำนวณไม่ผ่านเงื่อนไข (${status})`;
  if (normalized.includes("INSUFFICIENT")) return `ข้อมูลไม่เพียงพอ (${status})`;
  if (normalized.includes("NOT_COMPUTED")) return `ยังไม่ได้คำนวณ (${status})`;
  return `สถานะ: ${status}`;
}

export function summarizeH1EvidenceThai(row: H1ResultRow): string {
  const direction = row.beta > 0 ? "สูงขึ้น" : row.beta < 0 ? "ต่ำลง" : "แทบไม่เปลี่ยน";
  const estimate = `${Math.abs(row.beta).toFixed(2)} จุดเปอร์เซ็นต์`;
  const normalizedDecision = row.decision.toLowerCase().replaceAll("₀", "0").replaceAll("_", " ");
  const conclusion = /^reject h0\b/.test(normalizedDecision) && row.beta > 0
    ? "ผลทดสอบสนับสนุนความสัมพันธ์เชิงบวกในชุด Train"
    : "ผลทดสอบยังไม่ให้หลักฐานเพียงพอสำหรับความสัมพันธ์เชิงบวกในชุด Train";
  return `ชุด Train ของ ${row.ticker}: เมื่อ RV5 ย้อนหลัง 5 วันเพิ่มขึ้น 1 จุดเปอร์เซ็นต์ ความผันผวนจริงใน 5 วันถัดไป (Forward RV5) มีความสัมพันธ์กับการ${direction}ประมาณ ${estimate} (β = ${row.beta.toFixed(3)}; ใช้ข้อมูล ${row.n.toLocaleString()} จุด). ${conclusion}. ผลนี้บอกความสัมพันธ์ ไม่ได้ยืนยันเหตุและผล และไม่ยืนยันผลใน Test`;
}

export function summarizeComparativeEvidenceThai(row: HypothesisResultRow, unit: ResearchDisplayUnit): string {
  if (row.hypothesisId !== "H2" && row.hypothesisId !== "H3") return "สรุปผลเปรียบเทียบไม่มีให้แสดง";
  const baseline = comparisonModel(row.hypothesisId);
  const meaning = row.effectSize > 0
    ? `ค่าบวกหมายถึง B3 มี MAE ต่ำกว่า ${baseline.id} โดยเฉลี่ย`
    : row.effectSize < 0
      ? `ค่าติดลบหมายถึง B3 มี MAE สูงกว่า ${baseline.id} โดยเฉลี่ย`
      : "ค่าใกล้ศูนย์หมายถึง MAE เฉลี่ยของทั้งสองโมเดลใกล้เคียงกัน";
  return `ผลต่าง ΔMAE = ${formatDelta(row.effectSize, unit)} · ${meaning} · จับคู่ข้อมูลได้ ${row.nPaired.toLocaleString()} จาก ${row.nExpected.toLocaleString()} คู่ · ผลรวมนี้ไม่ได้หมายความว่า B3 จะชนะทุก ETF หรือทุกวัน`;
}

export function renderHypothesisResultCard(row: HypothesisResultRow, unit: ResearchDisplayUnit): string {
  if (row.hypothesisId !== "H2" && row.hypothesisId !== "H3") return "";
  const pairCounts = Object.entries(row.pairedNByTicker).map(([ticker, count]) => `${ticker} ${count.toLocaleString()}`).join(" · ");
  const interval = row.confidenceInterval95.map((value) => formatAnnualized(value, unit)).join(", ");
  return `<article class="research-hypothesis-card"><div class="section-card-heading"><div><span class="section-overline">${row.hypothesisId} · ชุด Test · ค่าเฉลี่ยรวม ETF</span><h4>คำถามวิจัย · ${escapeHtml(hypothesisQuestionThai(row.hypothesisId))}</h4></div><span class="pill pill-neutral">${escapeHtml(hypothesisDecisionThai(row.decision))}</span></div><dl class="research-result-grid"><div><dt>ผลต่าง MAE (ΔMAE)</dt><dd>${formatDelta(row.effectSize, unit)}</dd></div><div><dt>ช่วงความเชื่อมั่น 95%</dt><dd>[${interval}]</dd></div><div><dt>จำนวนคู่ข้อมูลที่ใช้ / ที่คาดไว้</dt><dd>${row.nPaired.toLocaleString()} / ${row.nExpected.toLocaleString()}</dd></div><div><dt>จำนวนคู่ข้อมูลแยกตาม ETF</dt><dd>${escapeHtml(pairCounts)}</dd></div><div><dt>ค่า p หลังปรับ Holm</dt><dd>${row.adjustedPValue.toExponential(3)}</dd></div><div><dt>วิธีทดสอบ</dt><dd>${escapeHtml(hypothesisMethodThai(row.hypothesisId, row.method))}</dd></div><div><dt>สถานะการคำนวณ</dt><dd>${escapeHtml(hypothesisStatusThai(row.statisticalStatus))}</dd></div><div><dt>เกณฑ์ตัดสินผล</dt><dd>${(row.alpha * 100).toFixed(0)}% (α = ${row.alpha.toFixed(2)})</dd></div></dl><p class="research-interpretation"><strong>อ่านผล:</strong> ${escapeHtml(summarizeComparativeEvidenceThai(row, unit))}</p></article>`;
}
