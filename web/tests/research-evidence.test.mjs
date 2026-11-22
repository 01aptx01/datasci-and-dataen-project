import assert from "node:assert/strict";
import test from "node:test";
import {
  hypothesisDecisionThai,
  hypothesisMethodThai,
  hypothesisQuestionThai,
  hypothesisStatusThai,
  renderHypothesisResultCard,
  summarizeH1EvidenceThai,
} from "../dist/assets/ui/researchEvidence.js";

const h1 = {
  ticker: "SPY",
  n: 752,
  expectedN: 752,
  trainStartDate: "2021-09-27",
  trainEndDate: "2024-09-23",
  beta: 0.567075260691333,
  intercept: 0.068,
  hacSe: 0.066,
  testStatistic: 8.57,
  pRaw: 4.99e-18,
  pHolm: 1.49e-17,
  ci95: [0.437, 0.696],
  hacLag: 5,
  decision: "reject_h0",
  interpretation: "source interpretation",
};

const h2 = {
  hypothesisId: "H2",
  tickerOrMacro: "MACRO",
  datasetSplit: "test",
  nExpected: 744,
  nPaired: 729,
  pairedNByTicker: { GLD: 243, IEF: 243, SPY: 243 },
  alpha: 0.05,
  method: "Synchronized moving-block bootstrap; 10 XNYS sessions; 2000 replicates; seed=42; Holm across H2/H3",
  testStatistic: 0.0035868694997349521,
  effectSize: 0.0035868694997349521,
  rawPValue: 0.0009995,
  adjustedPValue: 0.001999,
  confidenceInterval95: [0.001788, 0.005652],
  decision: "Reject H₀",
  interpretation: "source interpretation",
  statisticalStatus: "COMPUTED",
};

test("H1 Thai explanation interprets beta in percentage points and keeps the Train-only caveat", () => {
  const summary = summarizeH1EvidenceThai(h1);
  assert.match(summary, /ชุด Train/);
  assert.match(summary, /RV5 ย้อนหลัง/);
  assert.match(summary, /Forward RV5/);
  assert.match(summary, /เพิ่มขึ้น 1 จุดเปอร์เซ็นต์/);
  assert.match(summary, /0\.57 จุดเปอร์เซ็นต์/);
  assert.match(summary, /ไม่ยืนยันเหตุและผล/);
  assert.match(summary, /ไม่ยืนยันเหตุและผลหรือผลใน Test/);
});

test("H2 card explains the positive MAE difference, paired sample, and stored test decision in Thai", () => {
  const html = renderHypothesisResultCard(h2, "percent");
  assert.match(html, /B3 \(Online SGD\)/);
  assert.match(html, /B2 \(Static SGD\)/);
  assert.match(html, /<h4>.*หรือไม่\?<\/h4>/);
  assert.match(html, /คู่ข้อมูลที่ใช้ \/ คาดไว้/);
  assert.match(html, /729/);
  assert.match(html, /0\.36 จุดเปอร์เซ็นต์/);
  assert.match(html, /ค่าบวกหมายถึง B3 มี MAE ต่ำกว่า/);
  assert.match(html, /ไม่ได้แปลว่า B3 จะชนะทุก ETF หรือทุกวัน/);
  assert.match(html, /ปฏิเสธ H₀/);
});

test("H3 summary explains a negative delta and uses decimal units when selected", () => {
  const html = renderHypothesisResultCard({ ...h2, hypothesisId: "H3", effectSize: -0.01044799 }, "decimal");
  assert.match(html, /B1 \(Rolling 20D baseline\)/);
  assert.match(html, /-0\.0104/);
  assert.match(html, /ค่าติดลบหมายถึง B3 มี MAE สูงกว่า/);
});

test("H1–H3 labels, decisions, methods, and statuses have Thai descriptions", () => {
  assert.match(hypothesisQuestionThai("H1"), /Train/);
  assert.match(hypothesisQuestionThai("H2"), /B2 \(Static SGD\)/);
  assert.match(hypothesisQuestionThai("H3"), /B1 \(Rolling 20D baseline\)/);
  assert.match(hypothesisDecisionThai("Reject H₀"), /ปฏิเสธ H₀/);
  assert.match(hypothesisDecisionThai("fail_to_reject_h0"), /ยังไม่มีหลักฐานเพียงพอ/);
  assert.match(hypothesisMethodThai("H1", "OLS + Newey-West HAC maxlags=5; one-sided normal tail; Holm across SPY/IEF/GLD"), /ถดถอยเชิงเส้น/);
  assert.match(hypothesisMethodThai("H2", h2.method), /10 วันซื้อขาย/);
  assert.match(hypothesisMethodThai("H2", h2.method), /2,000 รอบ/);
  assert.equal(hypothesisStatusThai("COMPUTED"), "คำนวณสำเร็จ");
});
