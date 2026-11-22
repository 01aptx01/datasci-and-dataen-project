import React, { useMemo, useRef, useState } from 'react';
import {
  ETF_INFO,
  H1_RESULTS,
  H2_H3_RESULTS,
  MODEL_METRICS_TEST,
  PORTFOLIO_PRESETS,
  REPRESENTATIVE_COV_MATRIX,
  computePortfolioRisk,
} from '../data/reportData';
import {
  DriftTimelineRow,
  H1ScatterRow,
  PortfolioRiskRow,
  SavedReplayRow,
  parseDriftTimelineCsv,
  parseForecastAuditCsv,
  parsePortfolioRiskCsv,
} from '../utils/stage06Csv';

/* -------------------------------------------------------------------------- */
/* Slide 03: Interactive ETF Universe Explorer                                */
/* -------------------------------------------------------------------------- */
export function EtfUniverseInteractive() {
  const [selected, setSelected] = useState<'SPY' | 'IEF' | 'GLD'>('SPY');
  const active = ETF_INFO.find((e) => e.ticker === selected) ?? ETF_INFO[0];

  return (
    <div className="flex h-full flex-col justify-between gap-4">
      <div className="grid grid-cols-3 gap-3.5">
        {ETF_INFO.map((etf) => {
          const isActive = etf.ticker === selected;
          return (
            <button
              key={etf.ticker}
              type="button"
              onClick={() => setSelected(etf.ticker)}
              className={`cursor-pointer rounded-xl border p-4 text-left transition-all ${
                isActive
                  ? 'border-[#9E0B0F] bg-red-50/50 shadow-sm'
                  : 'border-zinc-200 bg-white hover:border-zinc-300'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-display text-[23px] font-bold" style={{ color: etf.color }}>
                  {etf.ticker}
                </span>
                <span className="font-mono-num text-[13px] text-zinc-500">
                  SD {etf.dailySdPct.toFixed(2)}%
                </span>
              </div>
              <p className="mt-1.5 text-[14px] font-medium text-zinc-700">{etf.assetClassTh}</p>
            </button>
          );
        })}
      </div>

      <div className="flex flex-1 flex-col justify-between rounded-xl border border-zinc-200 bg-zinc-50/80 p-5">
        <div>
          <div className="flex items-baseline justify-between border-b border-zinc-200 pb-3">
            <div>
              <span className="font-display text-[22px] font-bold" style={{ color: active.color }}>
                {active.ticker}
              </span>
              <span className="ml-2.5 text-[14.5px] text-zinc-500">{active.fullName}</span>
            </div>
            <span className="font-mono-num text-[13px] font-medium text-zinc-700">
              1,255 วันศึกษา + 61 วัน Warm-up
            </span>
          </div>
          <p className="mt-3 text-[16px] leading-relaxed text-zinc-800">{active.description}</p>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-3 text-[13.5px]">
          <div className="rounded-lg border border-zinc-200 bg-white px-3.5 py-3">
            <div className="text-zinc-500">SD รายวัน (Log Return)</div>
            <div className="font-mono-num mt-1 text-[18px] font-bold text-zinc-900">
              {active.dailySdPct.toFixed(2)}%
            </div>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white px-3.5 py-3">
            <div className="text-zinc-500">มัธยฐาน RV20 / สูงสุด</div>
            <div className="font-mono-num mt-1 text-[18px] font-bold text-zinc-900">
              {active.rv20MedianPct.toFixed(2)}% / {active.rv20MaxPct.toFixed(2)}%
            </div>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white px-3.5 py-3">
            <div className="text-zinc-500">เทียบแหล่งอิสระ</div>
            <div className="mt-1 text-[14px] font-bold text-emerald-700">
              {active.independentSource}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Slide 04: Unified End-to-End Pipeline & Quality Gate Diagram               */
/* -------------------------------------------------------------------------- */
const UNIFIED_STAGES = [
  {
    id: 'ingest',
    label: '1. รับข้อมูล (XNYS)',
    sub: 'yfinance + Raw Snapshot',
    detail:
      'Market Scheduler รอเวลาปิดตลาด XNYS ดึงข้อมูลราย ETF (auto_adjust=True) แล้วเก็บ Raw Snapshot แยกตาม run_id เพื่อย้อนตรวจได้เสมอ',
  },
  {
    id: 'quality',
    label: '2. ตรวจ Data Contract',
    sub: 'ผ่าน 3,948 · กักกัน 0',
    detail:
      'ตรวจค่าว่าง คีย์ซ้ำ (date, ticker) ความครบวันซื้อขาย XNYS และสูตรความผันผวน (ผ่าน 9/9 คู่) หากผิดกฎบังคับจะกักเฉพาะ ETF นั้นใน Quarantine',
  },
  {
    id: 'features',
    label: '3. Features & Labels',
    sub: 'แยก Pipeline กันรั่วไหล',
    detail:
      'Feature Pipeline ใช้ข้อมูลถึงวัน t เท่านั้น (8 ฟีเจอร์หลัก + สหสัมพันธ์ 20 วัน) แยกจาก Target Pipeline ที่สร้าง Forward RV5 จาก t+1 ถึง t+5',
  },
  {
    id: 'replay',
    label: '4. Train → Daily Replay',
    sub: 'ประเมิน B0–B3 ตามเวลา',
    detail:
      'แบ่ง Train / Validation / Test ตามเวลา ตัดรอยต่อ Purge 30 แถว จำลองรายวันแบบ Predict ก่อน แล้วอัปเดต B3 เฉพาะเมื่อ Label ครบ 5 วัน',
  },
  {
    id: 'portfolio',
    label: '5. ความเสี่ยงพอร์ต',
    sub: 'Forecast + Corr + Weight',
    detail:
      'นำค่าพยากรณ์ 3 ETF มารวมกับเมทริกซ์สหสัมพันธ์ย้อนหลัง 20 วัน และน้ำหนักที่ผู้ใช้เลือก (248 วัน Test สถานะ OK ทุกแถว)',
  },
];

export function UnifiedPipelineDiagram() {
  const [activeId, setActiveId] = useState<string>('quality');
  const active = UNIFIED_STAGES.find((s) => s.id === activeId) ?? UNIFIED_STAGES[1];

  return (
    <div className="flex h-full flex-col justify-between gap-3">
      <svg viewBox="0 0 610 236" className="w-full flex-1 rounded-xl border border-zinc-200 bg-zinc-50/70 p-2">
        <defs>
          <marker id="arrowUni" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M 0 1 L 8 5 L 0 9 z" fill="#52525B" />
          </marker>
          <marker id="arrowUniRed" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M 0 1 L 8 5 L 0 9 z" fill="#9E0B0F" />
          </marker>
        </defs>

        <line x1="175" y1="60" x2="210" y2="60" stroke="#52525B" strokeWidth="1.8" markerEnd="url(#arrowUni)" />
        <line x1="385" y1="60" x2="420" y2="60" stroke="#52525B" strokeWidth="1.8" markerEnd="url(#arrowUni)" />
        <path d="M 505 94 L 505 120 L 155 120 L 155 140" fill="none" stroke="#52525B" strokeWidth="1.8" markerEnd="url(#arrowUni)" />
        <line x1="278" y1="176" x2="328" y2="176" stroke="#9E0B0F" strokeWidth="2" markerEnd="url(#arrowUniRed)" />

        <g className="cursor-pointer" onClick={() => setActiveId('ingest')}>
          <rect
            x="16"
            y="26"
            width="158"
            height="68"
            rx="8"
            fill={activeId === 'ingest' ? '#FEF2F2' : '#FFFFFF'}
            stroke={activeId === 'ingest' ? '#9E0B0F' : '#D4D4D8'}
            strokeWidth={activeId === 'ingest' ? 2 : 1.5}
          />
          <text x="95" y="54" textAnchor="middle" className="fill-zinc-900 text-[13px] font-bold">1. รับข้อมูล (XNYS)</text>
          <text x="95" y="75" textAnchor="middle" className="fill-zinc-500 text-[11px]">yfinance + Raw Snapshot</text>
        </g>

        <g className="cursor-pointer" onClick={() => setActiveId('quality')}>
          <rect
            x="214"
            y="26"
            width="170"
            height="68"
            rx="8"
            fill={activeId === 'quality' ? '#FEF2F2' : '#FFFFFF'}
            stroke={activeId === 'quality' ? '#9E0B0F' : '#D4D4D8'}
            strokeWidth={activeId === 'quality' ? 2 : 1.5}
          />
          <text x="299" y="54" textAnchor="middle" className="fill-[#9E0B0F] text-[13px] font-bold">2. ตรวจ Data Contract</text>
          <text x="299" y="75" textAnchor="middle" className="fill-zinc-600 text-[11px]">Parquet · กักเฉพาะ ETF ผิด</text>
        </g>

        <g className="cursor-pointer" onClick={() => setActiveId('features')}>
          <rect
            x="424"
            y="26"
            width="168"
            height="68"
            rx="8"
            fill={activeId === 'features' ? '#FEF2F2' : '#FFFFFF'}
            stroke={activeId === 'features' ? '#9E0B0F' : '#D4D4D8'}
            strokeWidth={activeId === 'features' ? 2 : 1.5}
          />
          <text x="508" y="54" textAnchor="middle" className="fill-zinc-900 text-[13px] font-bold">3. Features &amp; Labels</text>
          <text x="508" y="75" textAnchor="middle" className="fill-zinc-500 text-[11px]">แยกตารางกันข้อมูลรั่วไหล</text>
        </g>

        <g className="cursor-pointer" onClick={() => setActiveId('replay')}>
          <rect
            x="45"
            y="144"
            width="230"
            height="68"
            rx="8"
            fill={activeId === 'replay' ? '#FEF2F2' : '#FFFFFF'}
            stroke={activeId === 'replay' ? '#9E0B0F' : '#D4D4D8'}
            strokeWidth={activeId === 'replay' ? 2 : 1.5}
          />
          <text x="160" y="172" textAnchor="middle" className="fill-zinc-900 text-[13px] font-bold">4. Train → Daily Replay</text>
          <text x="160" y="193" textAnchor="middle" className="fill-zinc-500 text-[11px]">Purge 30 แถว · ประเมิน B0–B3</text>
        </g>

        <g className="cursor-pointer" onClick={() => setActiveId('portfolio')}>
          <rect
            x="332"
            y="144"
            width="230"
            height="68"
            rx="8"
            fill={activeId === 'portfolio' ? '#9E0B0F' : '#18181B'}
          />
          <text x="447" y="172" textAnchor="middle" className="fill-white text-[13.5px] font-bold">5. ประมาณความเสี่ยงพอร์ต</text>
          <text x="447" y="193" textAnchor="middle" className="fill-zinc-200 text-[11px]">Forecast + Corr 20d + น้ำหนัก w</text>
        </g>
      </svg>

      <div className="rounded-xl border border-zinc-200 bg-white px-4.5 py-3.5">
        <div className="flex items-center justify-between">
          <span className="text-[15px] font-bold text-[#9E0B0F]">{active.label}</span>
          <span className="font-mono-num text-[12.5px] text-zinc-500">{active.sub}</span>
        </div>
        <p className="mt-1 text-[14.5px] leading-snug text-zinc-700">{active.detail}</p>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Slide 05: Interactive #1 — 5-Session Forward RV5 & Label Maturity          */
/* -------------------------------------------------------------------------- */
export function MaturityTimelineWidget() {
  const [dayOffset, setDayOffset] = useState<number>(0);
  const [simulatePendingCutoff, setSimulatePendingCutoff] = useState<boolean>(false);

  const isMature = !simulatePendingCutoff && dayOffset === 5;

  const days = [
    { offset: 0, label: 'วัน t', sub: 'สร้าง Forecast' },
    { offset: 1, label: 't+1', sub: 'r₁' },
    { offset: 2, label: 't+2', sub: 'r₂' },
    { offset: 3, label: 't+3', sub: 'r₃' },
    { offset: 4, label: 't+4', sub: 'r₄' },
    { offset: 5, label: 't+5', sub: 'target_end' },
  ];

  return (
    <div className="flex h-full flex-col justify-between gap-3">
      <div className="flex flex-1 flex-col justify-between rounded-xl border border-zinc-200 bg-zinc-50/80 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[15px] font-bold text-zinc-900">
            กฎปลดล็อกค่าจริง 5 วัน (Label Maturity Gate)
          </span>
          <span
            className={`rounded-md px-3 py-1 text-[12.5px] font-bold ${
              isMature ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
            }`}
          >
            {simulatePendingCutoff
              ? 'Pending ปลายช่วง (ตัดรอบก่อนครบ 5 วัน)'
              : isMature
              ? 'Mature · เปิดดูค่าจริงและอัปเดต B3 ได้'
              : `Pending · ยังไม่ครบ 5 วัน (${dayOffset}/5)`}
          </span>
        </div>

        <div className="mt-4 grid grid-cols-6 gap-2.5">
          {days.map((d) => {
            const reached = !simulatePendingCutoff && d.offset <= dayOffset;
            const isTargetEnd = d.offset === 5;
            const blockedCutoff = simulatePendingCutoff && d.offset >= 4;
            return (
              <button
                key={d.offset}
                type="button"
                onClick={() => {
                  setSimulatePendingCutoff(false);
                  setDayOffset(d.offset);
                }}
                className={`cursor-pointer rounded-xl border px-2 py-4 text-center transition-all ${
                  blockedCutoff
                    ? 'border-amber-300 bg-amber-50 text-amber-800'
                    : !simulatePendingCutoff && d.offset === dayOffset
                    ? 'border-[#9E0B0F] bg-[#9E0B0F] text-white shadow-sm'
                    : reached
                    ? isTargetEnd
                      ? 'border-emerald-500 bg-emerald-50 text-emerald-900'
                      : 'border-zinc-400 bg-white text-zinc-900'
                    : 'border-zinc-200 bg-zinc-100 text-zinc-400'
                }`}
              >
                <div className="font-mono-num text-[16px] font-bold">{d.label}</div>
                <div className="mt-1 text-[11.5px] opacity-90">{d.sub}</div>
              </button>
            );
          })}
        </div>

        <div className="mt-4 rounded-xl border border-zinc-200 bg-white px-4 py-3 text-[14px]">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-zinc-700">ค่าจริง (Actual Forward RV5):</span>
            {isMature ? (
              <span className="font-mono-num font-bold text-emerald-700">
                พร้อมประเมิน (target_end_date)
              </span>
            ) : (
              <span className="font-mono-num font-semibold text-amber-700">
                ล็อกไว้ (PENDING — ห้ามใช้ประเมินหรือฝึก)
              </span>
            )}
          </div>
        </div>

        <div className="no-print mt-4 flex flex-wrap items-center justify-between gap-2 text-[13px]">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setSimulatePendingCutoff(false);
                setDayOffset((prev) => (prev >= 5 ? 0 : prev + 1));
              }}
              className="cursor-pointer rounded-lg bg-[#9E0B0F] px-3.5 py-2 font-semibold text-white hover:bg-[#B81418]"
            >
              {dayOffset >= 5 && !simulatePendingCutoff ? 'กลับสู่วัน t' : 'เลื่อนวันถัดไป →'}
            </button>
            <button
              type="button"
              onClick={() => {
                setSimulatePendingCutoff(true);
                setDayOffset(3);
              }}
              className={`cursor-pointer rounded-lg border px-3 py-2 font-medium ${
                simulatePendingCutoff
                  ? 'border-amber-600 bg-amber-50 text-amber-900'
                  : 'border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50'
              }`}
            >
              จำลองปลายช่วง Pending
            </button>
          </div>

          <button
            type="button"
            onClick={() => {
              setSimulatePendingCutoff(false);
              setDayOffset(0);
            }}
            className="cursor-pointer rounded-lg border border-zinc-300 bg-white px-3 py-2 font-medium text-zinc-700 hover:bg-zinc-50"
          >
            รีเซ็ต
          </button>
        </div>
      </div>

      <p className="text-[13px] text-zinc-500">
        ปลายช่วง Test มี 60 รายการที่ยังไม่ครบ 5 วัน (Pending) จึงไม่นำมาคิดคะแนน Error
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Slide 06: 4 Models & Time-Split + Purge (Static Layout + Clean ClipPath)   */
/* -------------------------------------------------------------------------- */
export function ModelsAndSplitLab() {
  return (
    <div className="flex flex-col gap-3.5">
      <div className="grid grid-cols-4 gap-3.5">
        {MODEL_METRICS_TEST.map((m) => {
          const isB3 = m.id === 'B3';
          return (
            <div
              key={m.id}
              className={`rounded-xl border p-4 ${
                isB3
                  ? 'border-[#9E0B0F] bg-red-50/55 shadow-xs'
                  : 'border-zinc-200 bg-white'
              }`}
            >
              <div className="font-display text-[17px] font-bold text-[#9E0B0F]">{m.shortName}</div>
              <p className="mt-1.5 text-[13.5px] leading-snug text-zinc-700">{m.descriptionTh}</p>
            </div>
          );
        })}
      </div>

      {/* Time Split + Purge SVG with exact rounded ClipPath on Test box */}
      <svg viewBox="0 0 600 156" className="w-full rounded-xl border border-zinc-200 bg-white p-2">
        <defs>
          <clipPath id="testBoxClip">
            <rect x="416" y="36" width="168" height="70" rx="7" />
          </clipPath>
        </defs>

        <text x="16" y="22" className="fill-zinc-800 text-[13px] font-bold">
          การแบ่งข้อมูลตามลำดับเวลา (Train → Purge → Validation → Purge → Test)
        </text>

        <rect x="16" y="36" width="174" height="70" rx="7" fill="#27272A" />
        <text x="103" y="66" textAnchor="middle" className="fill-white text-[13.5px] font-bold">Train (3 ปี)</text>
        <text x="103" y="86" textAnchor="middle" className="font-mono-num fill-zinc-300 text-[10.5px]">27 ก.ย. 21 – 30 ก.ย. 24</text>

        <rect x="196" y="36" width="24" height="70" rx="4" fill="#FEE2E2" stroke="#9E0B0F" strokeWidth="1.2" />
        <text x="208" y="71" textAnchor="middle" transform="rotate(-90 208 71)" className="fill-[#9E0B0F] text-[10px] font-bold">Purge</text>

        <rect x="226" y="36" width="154" height="70" rx="7" fill="#2563EB" />
        <text x="303" y="66" textAnchor="middle" className="fill-white text-[13.5px] font-bold">Validation (1 ปี)</text>
        <text x="303" y="86" textAnchor="middle" className="font-mono-num fill-blue-100 text-[10.5px]">1 ต.ค. 24 – 30 ก.ย. 25</text>

        <rect x="386" y="36" width="24" height="70" rx="4" fill="#FEE2E2" stroke="#9E0B0F" strokeWidth="1.2" />
        <text x="398" y="71" textAnchor="middle" transform="rotate(-90 398 71)" className="fill-[#9E0B0F] text-[10px] font-bold">Purge</text>

        <g clipPath="url(#testBoxClip)">
          <rect x="416" y="36" width="168" height="70" fill="#9E0B0F" />
          <rect x="564" y="36" width="20" height="70" fill="#9E0B0F" />
        </g>
        <text x="500" y="66" textAnchor="middle" className="fill-white text-[13.5px] font-bold">Test (1 ปี)</text>
        <text x="500" y="86" textAnchor="middle" className="font-mono-num fill-red-100 text-[10.5px]">1 ต.ค. 25 – 25 ก.ย. 26</text>

        <text x="16" y="136" className="fill-zinc-600 text-[11.5px]">
          ตัด Purge 30 แถวระหว่างช่วงเพื่อกัน Label ข้าม Split · ปลายช่วง Test มี 60 รายการ Pending (5 วันสุดท้าย)
        </text>
      </svg>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Slide 07: Interactive #2 — Saved Replay Mini-Lab (Report + CSV Import)     */
/* -------------------------------------------------------------------------- */
export function SavedReplayMiniLab({
  rows,
  fileName,
  onUploadRows,
  onClearRows,
}: {
  rows: SavedReplayRow[] | null;
  fileName: string | null;
  onUploadRows: (rows: SavedReplayRow[], name: string) => void;
  onClearRows: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [tickerFilter, setTickerFilter] = useState<'SPY' | 'IEF' | 'GLD'>('SPY');
  const [modelFilter, setModelFilter] = useState<string>('ALL');
  const [asOfReveal, setAsOfReveal] = useState<boolean>(true);
  const [dateIndex, setDateIndex] = useState<number>(0);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const res = parseForecastAuditCsv(text);
    if (!res.ok) {
      setErrorMsg(res.errorTh || 'ไม่สามารถอ่านไฟล์ได้');
    } else {
      setErrorMsg(null);
      setDateIndex(0);
      onUploadRows(res.rows, file.name);
    }
    e.target.value = '';
  };

  const uniqueDates = useMemo(() => {
    if (!rows) return [];
    const set = new Set(rows.map((r) => r.predictionDate));
    return Array.from(set).sort();
  }, [rows]);

  const activeDate = uniqueDates[Math.min(dateIndex, Math.max(0, uniqueDates.length - 1))] ?? '';

  const filteredRows = useMemo(() => {
    if (!rows || !activeDate) return [];
    return rows.filter(
      (r) =>
        r.predictionDate === activeDate &&
        r.ticker === tickerFilter &&
        (modelFilter === 'ALL' || r.modelName.toUpperCase().includes(modelFilter))
    );
  }, [rows, activeDate, tickerFilter, modelFilter]);

  const modelList = useMemo(() => {
    if (!rows) return [];
    return Array.from(new Set(rows.map((r) => r.modelName)));
  }, [rows]);

  return (
    <div className="flex flex-1 flex-col gap-3.5">
      {/* CSV Import Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-4.5 py-3">
        <div className="text-[14px] text-zinc-800">
          <strong className="text-[#9E0B0F]">บันทึกคำพยากรณ์ชุด Test (Frozen Eval)</strong>
          {fileName && (
            <span className="font-mono-num ml-2 text-emerald-700">
              · โหลดแล้ว: {fileName}
            </span>
          )}
        </div>
        <div className="no-print flex items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={handleFile}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="cursor-pointer rounded-lg bg-[#9E0B0F] px-3.5 py-1.5 text-[12.5px] font-semibold text-white hover:bg-[#B81418]"
          >
            นำเข้า forecast_audit.csv / evaluation.csv
          </button>
          {rows && (
            <button
              type="button"
              onClick={() => {
                setErrorMsg(null);
                setDateIndex(0);
                onClearRows();
              }}
              className="cursor-pointer rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-[12.5px] font-medium text-zinc-700 hover:bg-zinc-100"
            >
              รีเซ็ต
            </button>
          )}
        </div>
      </div>

      {errorMsg && (
        <div className="rounded-lg border border-red-300 bg-red-50 px-3.5 py-2 text-[12.5px] text-red-800">
          {errorMsg}
        </div>
      )}

      {rows && uniqueDates.length > 0 ? (
        <div className="flex flex-1 flex-col gap-3 rounded-xl border border-zinc-200 bg-white p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-100 pb-2.5">
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setDateIndex((i) => Math.max(0, i - 1))}
                disabled={dateIndex === 0}
                className="cursor-pointer rounded border border-zinc-300 px-2.5 py-1 text-[12px] font-semibold disabled:opacity-40"
              >
                ← วันก่อนหน้า
              </button>
              <span className="font-mono-num rounded bg-zinc-100 px-3 py-1 text-[13px] font-bold text-zinc-900">
                {activeDate} ({dateIndex + 1}/{uniqueDates.length})
              </span>
              <button
                type="button"
                onClick={() => setDateIndex((i) => Math.min(uniqueDates.length - 1, i + 1))}
                disabled={dateIndex >= uniqueDates.length - 1}
                className="cursor-pointer rounded border border-zinc-300 px-2.5 py-1 text-[12px] font-semibold disabled:opacity-40"
              >
                วันถัดไป →
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-1.5">
              {(['SPY', 'IEF', 'GLD'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTickerFilter(t)}
                  className={`cursor-pointer rounded px-2.5 py-1 text-[12px] font-semibold ${
                    tickerFilter === t
                      ? 'bg-[#9E0B0F] text-white'
                      : 'border border-zinc-200 bg-white text-zinc-700'
                  }`}
                >
                  {t}
                </button>
              ))}
              <select
                value={modelFilter}
                onChange={(e) => setModelFilter(e.target.value)}
                aria-label="กรองโมเดล"
                className="rounded border border-zinc-300 bg-white px-2 py-1 text-[12px] text-zinc-800"
              >
                <option value="ALL">เทียบ B0–B3 ทั้งหมด</option>
                {modelList.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setAsOfReveal((v) => !v)}
                className={`cursor-pointer rounded border px-2.5 py-1 text-[12px] font-medium ${
                  asOfReveal
                    ? 'border-emerald-600 bg-emerald-50 text-emerald-800'
                    : 'border-zinc-300 bg-zinc-50 text-zinc-700'
                }`}
              >
                {asOfReveal ? 'As-of: แสดงค่าจริงเมื่อ Mature' : 'ซ่อนค่าจริง (วัน t)'}
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto rounded-lg border border-zinc-200">
            <table className="w-full text-left text-[13px]">
              <thead className="sticky top-0 border-b border-zinc-200 bg-zinc-100 text-zinc-700">
                <tr>
                  <th className="px-3.5 py-2.5 font-bold">โมเดล</th>
                  <th className="px-3.5 py-2.5 font-bold">Forecast (รายปี)</th>
                  <th className="px-3.5 py-2.5 font-bold">Actual 5 วัน</th>
                  <th className="px-3.5 py-2.5 font-bold">Abs. Error</th>
                  <th className="px-3.5 py-2.5 font-bold">สถานะ Label</th>
                </tr>
              </thead>
              <tbody className="font-mono-num divide-y divide-zinc-200">
                {filteredRows.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-3.5 py-6 text-center text-zinc-500">
                      ไม่พบข้อมูลสำหรับ {tickerFilter} ในวันที่ {activeDate}
                    </td>
                  </tr>
                ) : (
                  filteredRows.map((r, idx) => {
                    const isPending = r.labelStatus === 'PENDING' || r.evaluationStatus === 'PENDING';
                    const canShowActual = asOfReveal && !isPending && r.targetVol !== null;
                    return (
                      <tr key={idx}>
                        <td className="px-3.5 py-2.5 font-semibold text-zinc-900">{r.modelName}</td>
                        <td className="px-3.5 py-2.5">{(r.predictedVol * 100).toFixed(2)}%</td>
                        <td className="px-3.5 py-2.5">
                          {canShowActual ? (
                            `${(r.targetVol! * 100).toFixed(2)}%`
                          ) : (
                            <span className="text-amber-700">
                              {isPending ? 'PENDING (ยังไม่ครบ 5 วัน)' : 'ซ่อนไว้ (As-of t)'}
                            </span>
                          )}
                        </td>
                        <td className="px-3.5 py-2.5">
                          {canShowActual && r.absoluteError !== null ? r.absoluteError.toFixed(6) : '—'}
                        </td>
                        <td className="px-3.5 py-2.5">
                          <span
                            className={`font-sans text-[12px] font-bold ${
                              isPending ? 'text-amber-700' : 'text-emerald-700'
                            }`}
                          >
                            {r.labelStatus}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="flex flex-1 flex-col justify-between rounded-xl border border-zinc-200 bg-white p-6">
          <div className="border-b border-zinc-100 pb-3.5">
            <h4 className="font-display text-[19px] font-bold text-zinc-900">
              ผลตรวจนับคำพยากรณ์ชุด Test (248 วัน × 3 ETF × 4 โมเดล)
            </h4>
            <p className="mt-1 text-[13.5px] text-zinc-500">
              นำเข้าไฟล์ CSV จากเครื่องด้านบนเพื่อเลื่อนดูผลรายวันและทดสอบ As-of Reveal
            </p>
          </div>

          <div className="my-auto grid grid-cols-4 gap-4 py-4">
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-5">
              <div className="text-[13px] text-zinc-500">Forecast ที่สร้างได้</div>
              <div className="font-mono-num mt-2 text-[28px] font-bold text-zinc-900">2,976</div>
              <div className="mt-1 text-[13px] font-semibold text-emerald-700">ครอบคลุม 100% (2,976/2,976)</div>
            </div>
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-5">
              <div className="text-[13px] text-zinc-500">Label Mature (ประเมินได้)</div>
              <div className="font-mono-num mt-2 text-[28px] font-bold text-[#9E0B0F]">2,916</div>
              <div className="mt-1 text-[13px] font-semibold text-zinc-700">97.98% (ถึง 18 ก.ย. 2026)</div>
            </div>
            <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-5">
              <div className="text-[13px] text-amber-800">Label Pending (ปลายช่วง)</div>
              <div className="font-mono-num mt-2 text-[28px] font-bold text-amber-900">60</div>
              <div className="mt-1 text-[13px] text-amber-800">5 วันสุดท้าย · ไม่คิดคะแนน</div>
            </div>
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-5">
              <div className="text-[13px] text-zinc-500">Exception / Invalid</div>
              <div className="font-mono-num mt-2 text-[28px] font-bold text-emerald-700">0 / 0</div>
              <div className="mt-1 text-[13px] text-zinc-600">Common Panel 729 คู่</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Slide 08: Grouped MAE / RMSE Bar Chart + Coverage Bar                      */
/* -------------------------------------------------------------------------- */
export function ModelMaeChart() {
  const [metric, setMetric] = useState<'mae' | 'rmse'>('mae');
  const [hoverModel, setHoverModel] = useState<'B0' | 'B1' | 'B2' | 'B3' | null>(null);

  const categories = ['SPY', 'IEF', 'GLD', 'Macro'] as const;
  const maxVal = metric === 'mae' ? 0.15 : 0.21;
  const modelColors: Record<'B0' | 'B1' | 'B2' | 'B3', string> = {
    B0: '#A1A1AA',
    B1: '#64748B',
    B2: '#2563EB',
    B3: '#9E0B0F',
  };

  const activeRow = hoverModel
    ? MODEL_METRICS_TEST.find((m) => m.id === hoverModel)
    : MODEL_METRICS_TEST[3];

  return (
    <div className="flex h-full flex-col justify-between gap-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[13.5px] font-semibold text-zinc-700">
          เปรียบเทียบ {metric.toUpperCase()} บน Test (729 คู่ ETF/วัน · ค่ายิ่งต่ำยิ่งดี)
        </span>
        <div className="no-print flex rounded-lg border border-zinc-200 bg-zinc-100 p-0.5 text-[12.5px]">
          <button
            type="button"
            onClick={() => setMetric('mae')}
            className={`cursor-pointer rounded-md px-3 py-1 font-semibold ${
              metric === 'mae' ? 'bg-white text-[#9E0B0F] shadow-xs' : 'text-zinc-600'
            }`}
          >
            MAE
          </button>
          <button
            type="button"
            onClick={() => setMetric('rmse')}
            className={`cursor-pointer rounded-md px-3 py-1 font-semibold ${
              metric === 'rmse' ? 'bg-white text-[#9E0B0F] shadow-xs' : 'text-zinc-600'
            }`}
          >
            RMSE
          </button>
        </div>
      </div>

      <svg viewBox="0 0 540 258" className="w-full flex-1 rounded-xl border border-zinc-200 bg-white">
        {[0, 0.05, 0.10, 0.15].map((tick) => {
          const y = 210 - (tick / maxVal) * 168;
          return (
            <g key={tick}>
              <line x1="50" y1={y} x2="516" y2={y} stroke="#F4F4F5" strokeWidth="1" />
              <text x="44" y={y + 3} textAnchor="end" className="font-mono-num fill-zinc-400 text-[10.5px]">
                {tick.toFixed(2)}
              </text>
            </g>
          );
        })}

        {categories.map((cat, cIdx) => {
          const groupX = 72 + cIdx * 112;
          return (
            <g key={cat}>
              {MODEL_METRICS_TEST.map((m, mIdx) => {
                const val = m[metric][cat];
                const barH = (val / maxVal) * 168;
                const x = groupX + mIdx * 21;
                const y = 210 - barH;
                const dimmed = hoverModel && hoverModel !== m.id;
                return (
                  <g
                    key={m.id}
                    className="cursor-pointer"
                    onMouseEnter={() => setHoverModel(m.id)}
                    onMouseLeave={() => setHoverModel(null)}
                    style={{ opacity: dimmed ? 0.35 : 1, transition: 'opacity 140ms' }}
                  >
                    <rect x={x} y={y} width="17" height={barH} rx="2" fill={modelColors[m.id]} />
                    {m.id === 'B3' && (
                      <text
                        x={x + 2}
                        y={y - 6}
                        textAnchor="start"
                        paintOrder="stroke"
                        stroke="#FFFFFF"
                        strokeWidth="3.5"
                        strokeLinejoin="round"
                        className="font-mono-num fill-[#9E0B0F] text-[10px] font-bold"
                      >
                        {val.toFixed(3)}
                      </text>
                    )}
                  </g>
                );
              })}
              <text x={groupX + 39} y="229" textAnchor="middle" className="fill-zinc-800 text-[12.5px] font-bold">
                {cat === 'Macro' ? 'Macro เฉลี่ย' : cat}
              </text>
            </g>
          );
        })}

        <g transform="translate(65, 246)">
          {MODEL_METRICS_TEST.map((m, i) => (
            <g key={m.id} transform={`translate(${i * 112}, 0)`}>
              <rect x="0" y="-8" width="10" height="10" rx="2" fill={modelColors[m.id]} />
              <text x="14" y="0" className="fill-zinc-700 text-[11px] font-medium">
                {m.shortName}
              </text>
            </g>
          ))}
        </g>
      </svg>

      {activeRow && (
        <div className="font-mono-num flex items-center justify-between rounded-lg border border-zinc-200 bg-zinc-50 px-3.5 py-2 text-[12.5px] text-zinc-700">
          <span className="font-bold text-[#9E0B0F]">{activeRow.name}</span>
          <span>SPY: {activeRow[metric].SPY.toFixed(4)}</span>
          <span>IEF: {activeRow[metric].IEF.toFixed(4)}</span>
          <span>GLD: {activeRow[metric].GLD.toFixed(4)}</span>
          <span className="font-bold text-zinc-900">Macro: {activeRow[metric].Macro.toFixed(6)}</span>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Slide 09: Online SGD Protocol & ADWIN Monitor-Only + CSV Timeline          */
/* -------------------------------------------------------------------------- */
const PROTOCOL_STEPS = [
  { id: 1, label: '1. Predict', desc: 'ใช้ Features ณ วัน t ทำนายความผันผวนล่วงหน้า 5 วันก่อนเห็นคำตอบ' },
  { id: 2, label: '2. บันทึก Forecast', desc: 'จัดเก็บค่าทำนายและ prediction_id ลงบันทึกถาวร' },
  { id: 3, label: '3. ประเมินคำทำนายเก่า', desc: 'ตรวจสอบเฉพาะคำทำนายเก่าที่ครบ 5 วันและมี target_end_date ≤ วันนี้' },
  { id: 4, label: '4. ตรวจด้วย ADWIN', desc: 'ส่งความคลาดเคลื่อนเข้า ADWIN (delta = 0.002) เพื่อเฝ้าระวังเท่านั้น' },
  { id: 5, label: '5. อัปเดต B3', desc: 'ปรับน้ำหนัก Online SGD เพิ่มเติมจาก Label ที่เพิ่ง Mature (B2 ยังคงตรึง)' },
  { id: 6, label: '6. Checkpoint Hash', desc: 'บันทึกสถานะโมเดลพร้อมตรวจสอบ Hash เพื่อให้ทำซ้ำได้' },
];

export function OnlineSgdMonitoringLab({
  driftRows,
  driftFileName,
  onUploadDrift,
  onClearDrift,
}: {
  driftRows: DriftTimelineRow[] | null;
  driftFileName: string | null;
  onUploadDrift: (rows: DriftTimelineRow[], name: string) => void;
  onClearDrift: () => void;
}) {
  const [activeStep, setActiveStep] = useState<number>(4);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const curStep = PROTOCOL_STEPS.find((s) => s.id === activeStep) ?? PROTOCOL_STEPS[3];

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const res = parseDriftTimelineCsv(text);
    if (!res.ok) {
      setErrorMsg(res.errorTh || 'ไม่สามารถอ่านไฟล์ได้');
    } else {
      setErrorMsg(null);
      onUploadDrift(res.rows, file.name);
    }
    e.target.value = '';
  };

  const chartPts = useMemo(() => {
    if (!driftRows || driftRows.length === 0) return [];
    const count = Math.min(120, driftRows.length);
    const indices = new Set(
      Array.from({ length: count }, (_, i) => Math.round((i / Math.max(1, count - 1)) * (driftRows.length - 1)))
    );
    driftRows.forEach((row, index) => { if (row.adwinAlert) indices.add(index); });
    const maxErr = Math.max(0.05, ...driftRows.map((row) => row.errorValue));
    return Array.from(indices).sort((a, b) => a - b).map((index) => ({
      ...driftRows[index],
      x: 36 + (index / Math.max(1, driftRows.length - 1)) * 465,
      y: 125 - (driftRows[index].errorValue / maxErr) * 95,
    }));
  }, [driftRows]);

  const alertCount = driftRows?.filter((row) => row.adwinAlert).length ?? 0;
  const observationCount = driftRows?.length ?? 729;

  return (
    <div className="flex h-full flex-col justify-between gap-3.5">
      <div className="grid grid-cols-3 gap-2.5">
        {PROTOCOL_STEPS.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setActiveStep(s.id)}
            className={`cursor-pointer rounded-xl border px-3.5 py-3 text-left text-[13.5px] font-semibold transition-colors ${
              activeStep === s.id
                ? 'border-[#9E0B0F] bg-[#9E0B0F] text-white'
                : 'border-zinc-200 bg-white text-zinc-800 hover:bg-zinc-50'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4.5 py-3.5 text-[14.5px]">
        <strong className="text-[#9E0B0F]">{curStep.label}: </strong>
        <span className="text-zinc-800">{curStep.desc}</span>
      </div>

      <div className="flex flex-1 flex-col justify-between rounded-xl border border-zinc-200 bg-white p-4.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-[14px] font-bold text-zinc-900">
            ผลการเฝ้าระวัง ADWIN บนชุด Test: <span className="font-mono-num text-emerald-700">{alertCount} Alerts จาก {observationCount} ค่า</span>
            {driftFileName && <span className="ml-2 text-[12.5px] text-zinc-500">({driftFileName})</span>}
          </div>
          <div className="no-print flex items-center gap-1.5">
            <input ref={inputRef} type="file" accept=".csv" onChange={handleFile} className="hidden" />
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="cursor-pointer rounded border border-zinc-300 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-700 hover:bg-zinc-100"
            >
              นำเข้า drift_error_timeline.csv
            </button>
            {driftRows && (
              <button
                type="button"
                onClick={onClearDrift}
                className="cursor-pointer rounded border border-zinc-300 px-2.5 py-1.5 text-[12px] text-zinc-600"
              >
                รีเซ็ต
              </button>
            )}
          </div>
        </div>

        {errorMsg && <p className="mt-1.5 text-[12.5px] text-red-700">{errorMsg}</p>}

        {chartPts.length > 0 ? (
          <svg viewBox="0 0 520 155" className="mt-2 w-full flex-1">
            <line x1="36" y1="130" x2="502" y2="130" stroke="#E4E4E7" strokeWidth="1" />
            <path
              d={chartPts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')}
              fill="none"
              stroke="#9E0B0F"
              strokeWidth="2"
            />
            {chartPts
              .filter((p) => p.adwinAlert)
              .map((p, i) => (
                <circle key={i} cx={p.x} cy={p.y} r="4" fill="#DC2626" />
              ))}
            <text x="268" y="148" textAnchor="middle" className="fill-zinc-500 text-[10.5px]">
              ความคลาดเคลื่อนตามลำดับเวลา ({observationCount} คู่ ETF/วัน)
            </text>
          </svg>
        ) : (
          <p className="mt-3 text-[13.5px] leading-relaxed text-zinc-600">
            ADWIN (delta = 0.002) ทำหน้าที่เฝ้าระวังความคลาดเคลื่อนเท่านั้น ไม่สั่ง Reset หรือ Retrain อัตโนมัติ
          </p>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Slide 10: H1–H3 Statistical Evidence Switcher                              */
/* -------------------------------------------------------------------------- */
export function H1ToH3StatsLab({ scatterRows }: { scatterRows: H1ScatterRow[] }) {
  const [tab, setTab] = useState<'H1' | 'H2_H3'>('H2_H3');

  const zeroX = 68;
  const plotW = 448;
  const mapX = (v: number) => zeroX + (v / 0.022) * plotW;

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="no-print flex items-center gap-2">
        <button
          type="button"
          onClick={() => setTab('H2_H3')}
          className={`cursor-pointer rounded-lg px-4 py-2 text-[13px] font-bold transition-colors ${
            tab === 'H2_H3'
              ? 'bg-[#9E0B0F] text-white'
              : 'border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50'
          }`}
        >
          H2 &amp; H3: เปรียบเทียบ B3 บน Test (729 คู่)
        </button>
        <button
          type="button"
          onClick={() => setTab('H1')}
          className={`cursor-pointer rounded-lg px-4 py-2 text-[13px] font-bold transition-colors ${
            tab === 'H1'
              ? 'bg-[#9E0B0F] text-white'
              : 'border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50'
          }`}
        >
          H1: ความสัมพันธ์ RV5 → Forward RV5 บน Train (N=752)
        </button>
      </div>

      {tab === 'H2_H3' ? (
        <svg viewBox="0 0 560 288" className="w-full flex-1 rounded-xl border border-zinc-200 bg-white">
          <text x="20" y="28" className="fill-zinc-800 text-[13.5px] font-bold">
            ผลต่าง ΔMAE และช่วงความเชื่อมั่น 95% (Block Bootstrap 10 วัน · 2,000 รอบ + Holm)
          </text>

          <line x1={zeroX} y1="54" x2={zeroX} y2="222" stroke="#18181B" strokeWidth="1.5" strokeDasharray="4 3" />
          <text x={zeroX} y="242" textAnchor="middle" className="fill-zinc-700 text-[11.5px] font-semibold">
            0 (ไม่ต่าง)
          </text>

          {[0.005, 0.010, 0.015, 0.020].map((tick) => {
            const x = mapX(tick);
            return (
              <g key={tick}>
                <line x1={x} y1="54" x2={x} y2="222" stroke="#F4F4F5" strokeWidth="1" />
                <text x={x} y="242" textAnchor="middle" className="font-mono-num fill-zinc-400 text-[11px]">
                  +{tick.toFixed(3)}
                </text>
              </g>
            );
          })}

          {H2_H3_RESULTS.map((res, idx) => {
            const y = idx === 0 ? 110 : 180;
            // Anchor label strictly to the right of zeroX so it never crosses the dashed 0 line
            const labelX = Math.max(zeroX + 14, mapX(res.ciLow));
            return (
              <g key={res.id}>
                <text x="20" y={y + 4} className="fill-zinc-900 text-[14px] font-bold">{res.id}</text>
                <line x1={mapX(res.ciLow)} y1={y} x2={mapX(res.ciHigh)} y2={y} stroke="#9E0B0F" strokeWidth="4" strokeLinecap="round" />
                <line x1={mapX(res.ciLow)} y1={y - 7} x2={mapX(res.ciLow)} y2={y + 7} stroke="#9E0B0F" strokeWidth="2.2" />
                <line x1={mapX(res.ciHigh)} y1={y - 7} x2={mapX(res.ciHigh)} y2={y + 7} stroke="#9E0B0F" strokeWidth="2.2" />
                <circle cx={mapX(res.deltaMae)} cy={y} r="7" fill="#9E0B0F" />
                <text
                  x={labelX}
                  y={y - 16}
                  textAnchor="start"
                  paintOrder="stroke"
                  stroke="#FFFFFF"
                  strokeWidth="4"
                  strokeLinejoin="round"
                  className="font-mono-num fill-[#9E0B0F] text-[12px] font-bold"
                >
                  +{res.deltaMae.toFixed(6)} (adj. p = {res.adjustedP.toFixed(6)})
                </text>
              </g>
            );
          })}

          <text x="280" y="270" textAnchor="middle" className="fill-emerald-700 text-[12px] font-semibold">
            ค่าบวกหมายถึง B3 มี Error ต่ำกว่า · ปฏิเสธ H₀ ทั้ง H2 และ H3 ในชุด Test
          </text>
        </svg>
      ) : (
        <div className="grid flex-1 grid-cols-3 gap-3">
          {H1_RESULTS.map((r, idx) => {
            const color = idx === 0 ? '#9E0B0F' : idx === 1 ? '#1D4ED8' : '#B45309';
            const pts = scatterRows.filter((point) => point.ticker === r.ticker);
            const sx = (x: number) => 28 + (x / 0.45) * 145;
            const sy = (y: number) => 176 - (y / 0.45) * 146;
            return (
              <div key={r.ticker} className="flex flex-col justify-between rounded-xl border border-zinc-200 bg-white p-3.5">
                <div className="flex items-center justify-between">
                  <span className="font-display text-[16px] font-bold" style={{ color }}>{r.ticker} (Train)</span>
                  <span className="font-mono-num text-[12px] font-bold text-zinc-700">β = {r.beta.toFixed(3)}</span>
                </div>
                <svg viewBox="0 0 185 202" className="my-1 w-full flex-1">
                  <line x1="28" y1="176" x2="173" y2="176" stroke="#D4D4D8" strokeWidth="1" />
                  <line x1="28" y1="24" x2="28" y2="176" stroke="#D4D4D8" strokeWidth="1" />
                  {pts.map((pt, i) => (
                    <circle key={i} cx={sx(pt.x)} cy={sy(pt.y)} r="2.6" fill={color} opacity="0.45" />
                  ))}
                  <line
                    x1={sx(0.05)}
                    y1={sy(r.intercept + r.beta * 0.05)}
                    x2={sx(0.39)}
                    y2={sy(r.intercept + r.beta * 0.39)}
                    stroke={color}
                    strokeWidth="2.6"
                  />
                  <text x="100" y="194" textAnchor="middle" className="fill-zinc-500 text-[10px]">RV5 ย้อนหลัง</text>
                </svg>
                <div className="font-mono-num border-t border-zinc-100 pt-1.5 text-center text-[11px] text-zinc-600">
                  95% CI [{r.ciLow.toFixed(3)}, {r.ciHigh.toFixed(3)}]
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Slide 12: Interactive #3A — Portfolio Scenario A/B + Signed Contributions  */
/* -------------------------------------------------------------------------- */
export function PortfolioScenarioLab({
  weightsB,
  onChangeWeightsB,
  portfolioRows,
  portfolioFileName,
  selectedCsvDateIdx,
  onChangeCsvDateIdx,
  onUploadPortfolioCsv,
  onClearPortfolioCsv,
}: {
  weightsB: { SPY: number; IEF: number; GLD: number };
  onChangeWeightsB: (w: { SPY: number; IEF: number; GLD: number }) => void;
  portfolioRows: PortfolioRiskRow[] | null;
  portfolioFileName: string | null;
  selectedCsvDateIdx: number;
  onChangeCsvDateIdx: (idx: number) => void;
  onUploadPortfolioCsv: (rows: PortfolioRiskRow[], name: string) => void;
  onClearPortfolioCsv: () => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [csvError, setCsvError] = useState<string | null>(null);

  const activeCsvRow =
    portfolioRows && portfolioRows.length > 0
      ? portfolioRows[Math.min(selectedCsvDateIdx, portfolioRows.length - 1)]
      : null;

  const activeCov = activeCsvRow
    ? activeCsvRow.status === 'OK' ? activeCsvRow.covarianceMatrix : null
    : REPRESENTATIVE_COV_MATRIX;

  const weightsA = { SPY: 50, IEF: 30, GLD: 20 };
  const resA = computePortfolioRisk(weightsA, activeCov);
  const resB = computePortfolioRisk(weightsB, activeCov);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const parsed = parsePortfolioRiskCsv(text);
    if (!parsed.ok) {
      setCsvError(parsed.errorTh || 'ไม่สามารถอ่านไฟล์ได้');
    } else {
      setCsvError(null);
      onUploadPortfolioCsv(parsed.rows, file.name);
    }
    e.target.value = '';
  };

  const updateWeight = (key: 'SPY' | 'IEF' | 'GLD', val: number) => {
    const clean = Number.isFinite(val) ? Math.max(0, Math.min(100, val)) : 0;
    onChangeWeightsB({ ...weightsB, [key]: clean });
  };

  const parityDiff =
    activeCsvRow && activeCsvRow.storedVol !== null && resA.valid
      ? Math.abs(resA.sigmaDecimal - activeCsvRow.storedVol)
      : null;

  const contribsB = resB.valid && resB.contributionSharesPct ? resB.contributionSharesPct : null;
  const maxAbsShare = contribsB
    ? Math.max(20, Math.abs(contribsB.SPY), Math.abs(contribsB.IEF), Math.abs(contribsB.GLD))
    : 100;

  return (
    <div className="flex flex-col gap-2.5">
      {/* CSV & Date Selector Strip */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-3.5 py-2 text-[12px]">
        <div className="flex items-center gap-2">
          {activeCsvRow ? (
            <>
              <span className="font-bold text-emerald-700">Test · ONLINE_SGD จาก {portfolioFileName} ({portfolioRows?.length} วัน)</span>
              <button
                type="button"
                onClick={() => onChangeCsvDateIdx(Math.max(0, selectedCsvDateIdx - 1))}
                disabled={selectedCsvDateIdx === 0}
                className="cursor-pointer rounded border border-zinc-300 bg-white px-2 py-0.5 disabled:opacity-40"
              >
                ←
              </button>
              <span className="font-mono-num font-bold text-zinc-900">{activeCsvRow.predictionDate}</span>
              <button
                type="button"
                onClick={() =>
                  onChangeCsvDateIdx(Math.min((portfolioRows?.length ?? 1) - 1, selectedCsvDateIdx + 1))
                }
                disabled={selectedCsvDateIdx >= (portfolioRows?.length ?? 1) - 1}
                className="cursor-pointer rounded border border-zinc-300 bg-white px-2 py-0.5 disabled:opacity-40"
              >
                →
              </button>
              {parityDiff !== null && (
                <span className="font-mono-num text-[11px] text-zinc-500">
                  (Parity Δ {parityDiff.toExponential(1)})
                </span>
              )}
            </>
          ) : (
            <span className="text-zinc-600">
              เมทริกซ์ตัวอย่างเพื่อสาธิต (ค่าเฉลี่ย Test จริงของ 50/30/20 คือ 7.81%) · นำเข้า CSV เพื่อดูรายวันจริง
            </span>
          )}
        </div>

        <div className="no-print flex items-center gap-1.5">
          <input ref={inputRef} type="file" accept=".csv" onChange={handleFile} className="hidden" />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="cursor-pointer rounded-md bg-zinc-900 px-2.5 py-1 font-semibold text-white hover:bg-zinc-800"
          >
            นำเข้า portfolio_risk.csv
          </button>
          {portfolioRows && (
            <button
              type="button"
              onClick={onClearPortfolioCsv}
              className="cursor-pointer rounded-md border border-zinc-300 bg-white px-2 py-1 text-zinc-700"
            >
              ล้างไฟล์
            </button>
          )}
        </div>
      </div>

      {csvError && (
        <div className="rounded-lg border border-red-300 bg-red-50 px-3 py-1.5 text-[12px] text-red-800">
          {csvError}
        </div>
      )}

      {/* Scenario A vs B Side-by-Side */}
      <div className="grid grid-cols-12 gap-3">
        {/* Scenario A (Fixed Baseline 50/30/20) */}
        <div className="col-span-4 rounded-xl border border-zinc-200 bg-white p-3.5">
          <div className="text-[12px] font-bold text-zinc-500">Scenario A (ค่าเริ่มต้นคงที่)</div>
          <div className="font-mono-num mt-1 text-[14px] font-bold text-zinc-900">
            SPY 50% · IEF 30% · GLD 20%
          </div>
          <div className="mt-3 rounded-lg bg-zinc-50 p-2.5">
            <div className="text-[11.5px] text-zinc-500">ความเสี่ยงพอร์ต (รายปี)</div>
            <div className="font-mono-num text-[24px] font-bold text-zinc-900">
              {resA.valid ? `${resA.sigmaAnnualPct.toFixed(2)}%` : 'ไม่พร้อมคำนวณ'}
            </div>
            {!activeCsvRow && (
              <div className="text-[11px] text-zinc-500">ผลเฉลี่ย Test จริง: 7.81% (มัธยฐาน 7.68%)</div>
            )}
          </div>
        </div>

        {/* Scenario B (Editable + Sum-to-100 Validation) */}
        <div className="col-span-8 rounded-xl border border-[#9E0B0F]/40 bg-red-50/25 p-3.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-[12.5px] font-bold text-[#9E0B0F]">
              Scenario B (ปรับสัดส่วนทดลองเอง — ผลรวมต้องเท่ากับ 100%)
            </span>
            <div className="no-print flex items-center gap-1">
              {PORTFOLIO_PRESETS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => onChangeWeightsB({ ...p.weights })}
                  className="cursor-pointer rounded border border-zinc-300 bg-white px-2 py-0.5 text-[11px] font-semibold text-zinc-700 hover:bg-zinc-50"
                >
                  {p.id}
                </button>
              ))}
              <button
                type="button"
                onClick={() => onChangeWeightsB({ SPY: 50, IEF: 30, GLD: 20 })}
                className="cursor-pointer rounded border border-zinc-300 bg-white px-2 py-0.5 text-[11px] font-medium text-zinc-600"
              >
                รีเซ็ต
              </button>
            </div>
          </div>

          <div className="mt-2.5 grid grid-cols-3 gap-2.5 text-[12px]">
            {(['SPY', 'IEF', 'GLD'] as const).map((k) => (
              <label key={k} className="flex flex-col gap-1 rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5">
                <div className="flex items-center justify-between font-bold text-zinc-800">
                  <span>{k}</span>
                  <span className="font-mono-num">{weightsB[k].toFixed(1)}%</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={0.5}
                  value={weightsB[k]}
                  onChange={(e) => updateWeight(k, Number(e.target.value))}
                  className="accent-[#9E0B0F]"
                />
              </label>
            ))}
          </div>

          {/* Result & Guardrail */}
          <div className="mt-2.5 flex items-center justify-between rounded-lg border border-zinc-200 bg-white px-3 py-2">
            {resB.valid && resA.valid ? (
              <>
                <div>
                  <span className="text-[12px] text-zinc-500">ความเสี่ยงพอร์ต B: </span>
                  <span className="font-mono-num text-[20px] font-bold text-[#9E0B0F]">
                    {resB.sigmaAnnualPct.toFixed(2)}%
                  </span>
                  <span className="text-[12px] text-zinc-500"> / ปี</span>
                </div>
                <div className="font-mono-num text-[13px] font-semibold text-zinc-800">
                  ต่างจาก A: {resB.sigmaAnnualPct - resA.sigmaAnnualPct >= 0 ? '+' : ''}
                  {(resB.sigmaAnnualPct - resA.sigmaAnnualPct).toFixed(2)}%
                </div>
              </>
            ) : (
              <span className="text-[13px] font-bold text-red-700">
                ไม่สามารถคำนวณได้: {resB.errorTh || resA.errorTh}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Signed Risk Contributions Horizontal Bar Chart (supports negative contributions) */}
      <div className="rounded-xl border border-zinc-200 bg-white px-4 py-2.5">
        <div className="flex items-center justify-between text-[12px]">
          <span className="font-bold text-zinc-800">
            สัดส่วนการมีส่วนร่วมต่อความเสี่ยงของ Scenario B (Signed Risk Contributions · รองรับค่าลบ)
          </span>
          <span className="text-zinc-500">
            รวม = {resB.valid && resB.sigmaDecimal > 0 ? '100%' : 'ไม่นิยามเมื่อ σ = 0'}
          </span>
        </div>

        {contribsB ? (
          <svg viewBox="0 0 560 76" className="mt-1.5 w-full">
            {/* Center-left zero axis */}
            <line x1="170" y1="6" x2="170" y2="70" stroke="#71717A" strokeWidth="1.2" />
            {(['SPY', 'IEF', 'GLD'] as const).map((k, idx) => {
              const val = contribsB[k];
              const y = 10 + idx * 21;
              const barLen = (Math.abs(val) / maxAbsShare) * 290;
              const barX = val >= 0 ? 170 : 170 - barLen;
              const color = k === 'SPY' ? '#9E0B0F' : k === 'IEF' ? '#1D4ED8' : '#B45309';
              return (
                <g key={k}>
                  <text x="16" y={y + 12} className="font-mono-num fill-zinc-800 text-[11.5px] font-bold">
                    {k} ({weightsB[k].toFixed(0)}%)
                  </text>
                  <rect x={barX} y={y + 2} width={Math.max(2, barLen)} height="13" rx="2.5" fill={color} />
                  <text
                    x={val >= 0 ? 176 + barLen : barX - 6}
                    y={y + 12}
                    textAnchor={val >= 0 ? 'start' : 'end'}
                    className="font-mono-num fill-zinc-800 text-[11px] font-semibold"
                  >
                    {val >= 0 ? '+' : ''}
                    {val.toFixed(1)}%
                  </text>
                </g>
              );
            })}
          </svg>
        ) : (
          <div className="py-3 text-center text-[12px] text-zinc-500">
            {resB.valid ? 'สัดส่วน Risk Contribution ไม่นิยามเมื่อความเสี่ยงพอร์ตเท่ากับ 0' : 'กรุณาปรับน้ำหนักให้รวมเท่ากับ 100% เพื่อแสดงกราฟ'}
          </div>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Slide 13: Interactive #3B — User-Defined Annualized Volatility Budget      */
/* -------------------------------------------------------------------------- */
export function PortfolioBudgetLab({
  weightsB,
  portfolioRows,
}: {
  weightsB: { SPY: number; IEF: number; GLD: number };
  portfolioRows: PortfolioRiskRow[] | null;
}) {
  const [budgetPct, setBudgetPct] = useState<number>(8.2);
  const weightsA = { SPY: 50, IEF: 30, GLD: 20 };
  const dailyRisks = useMemo(() => {
    if (!portfolioRows) return null;
    const A: number[] = [];
    const B: number[] = [];
    for (const row of portfolioRows) {
      if (row.status !== 'OK') continue;
      const riskA = computePortfolioRisk(weightsA, row.covarianceMatrix);
      const riskB = computePortfolioRisk(weightsB, row.covarianceMatrix);
      if (riskA.valid) A.push(riskA.sigmaAnnualPct);
      if (riskB.valid) B.push(riskB.sigmaAnnualPct);
    }
    return { A, B };
  }, [portfolioRows, weightsB]);
  const average = (values: number[]) => values.reduce((sum, value) => sum + value, 0) / values.length;
  const resA = dailyRisks
    ? { valid: dailyRisks.A.length > 0, sigmaAnnualPct: average(dailyRisks.A) }
    : computePortfolioRisk(weightsA, REPRESENTATIVE_COV_MATRIX);
  const resB = dailyRisks
    ? { valid: dailyRisks.B.length > 0, sigmaAnnualPct: average(dailyRisks.B) }
    : computePortfolioRisk(weightsB, REPRESENTATIVE_COV_MATRIX);

  const classify = (val: number) => {
    const diff = val - budgetPct;
    if (val.toFixed(2) === budgetPct.toFixed(2)) return { label: 'เท่ากับงบที่ตั้งไว้', tone: 'text-amber-800 bg-amber-100' };
    if (diff < 0) return { label: `ต่ำกว่างบ ${Math.abs(diff).toFixed(2)}%`, tone: 'text-emerald-800 bg-emerald-100' };
    return { label: `สูงกว่างบ +${diff.toFixed(2)}%`, tone: 'text-red-800 bg-red-100' };
  };

  const rangeSummary = dailyRisks
    ? { validDays: dailyRisks.B.length, aboveBudgetDays: dailyRisks.B.filter((risk) => risk > budgetPct).length }
    : null;

  const maxAxis = 15;
  const budgetX = Math.min(480, Math.max(40, 40 + (budgetPct / maxAxis) * 440));

  return (
    <div className="flex h-full flex-col justify-between gap-3.5">
      <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-[15px] font-bold text-zinc-900">
              กำหนดเพดานความผันผวน (% ต่อปี)
            </div>
            <div className="text-[12.5px] text-zinc-500">
              {dailyRisks
                ? `เทียบค่าเฉลี่ยจากชุด Test ของ ONLINE_SGD (${dailyRisks.A.length} วัน)`
                : 'เทียบค่าจากเมทริกซ์ตัวอย่างเพื่อสาธิต'}
            </div>
          </div>
          <div className="no-print flex items-center gap-2">
            <input
              type="number"
              min={3}
              max={20}
              step={0.1}
              value={budgetPct}
              onChange={(e) => {
                const v = Number(e.target.value);
                if (Number.isFinite(v)) setBudgetPct(Math.max(1, Math.min(25, v)));
              }}
              aria-label="เพดานความผันผวนต่อปี"
              className="font-mono-num w-20 rounded-lg border border-zinc-300 bg-white px-2.5 py-1 text-right text-[15px] font-bold text-[#9E0B0F]"
            />
            <span className="text-[13px] font-semibold text-zinc-700">% / ปี</span>
            <button
              type="button"
              onClick={() => setBudgetPct(8.2)}
              className="cursor-pointer rounded-lg border border-zinc-300 bg-white px-2.5 py-1 text-[12px] text-zinc-700 hover:bg-zinc-100"
            >
              รีเซ็ต
            </button>
          </div>
        </div>

        <input
          type="range"
          min={4}
          max={14}
          step={0.1}
          value={Math.min(14, Math.max(4, budgetPct))}
          onChange={(e) => setBudgetPct(Number(e.target.value))}
          className="no-print mt-3 w-full accent-[#9E0B0F]"
        />
      </div>

      {/* Visual Gauge Comparison SVG */}
      <svg viewBox="0 0 520 148" className="w-full rounded-xl border border-zinc-200 bg-white">
        <text x="40" y="22" className="fill-zinc-700 text-[12px] font-bold">
          เทียบความผันผวนพอร์ตกับเพดานที่ผู้ใช้ตั้งไว้ ({budgetPct.toFixed(1)}% / ปี)
        </text>

        {/* Budget Threshold Line */}
        <line x1={budgetX} y1="34" x2={budgetX} y2="122" stroke="#18181B" strokeWidth="2" strokeDasharray="4 3" />
        <text x={budgetX} y="138" textAnchor="middle" className="font-mono-num fill-zinc-900 text-[11px] font-bold">
          เพดาน {budgetPct.toFixed(1)}%
        </text>

        {/* Bar A */}
        <text x="12" y="64" className="fill-zinc-800 text-[12px] font-bold">A</text>
        {resA.valid && (
          <>
            <rect
              x="40"
              y="48"
              width={Math.min(440, (resA.sigmaAnnualPct / maxAxis) * 440)}
              height="22"
              rx="4"
              fill={resA.sigmaAnnualPct <= budgetPct ? '#059669' : '#DC2626'}
            />
            <text
              x={48 + Math.min(440, (resA.sigmaAnnualPct / maxAxis) * 440)}
              y="63"
              className="font-mono-num fill-zinc-900 text-[12px] font-bold"
            >
              {resA.sigmaAnnualPct.toFixed(2)}%
            </text>
          </>
        )}

        {/* Bar B */}
        <text x="12" y="102" className="fill-[#9E0B0F] text-[12px] font-bold">B</text>
        {resB.valid && (
          <>
            <rect
              x="40"
              y="86"
              width={Math.min(440, (resB.sigmaAnnualPct / maxAxis) * 440)}
              height="22"
              rx="4"
              fill={resB.sigmaAnnualPct <= budgetPct ? '#059669' : '#9E0B0F'}
            />
            <text
              x={48 + Math.min(440, (resB.sigmaAnnualPct / maxAxis) * 440)}
              y="101"
              className="font-mono-num fill-zinc-900 text-[12px] font-bold"
            >
              {resB.sigmaAnnualPct.toFixed(2)}%
            </text>
          </>
        )}
      </svg>

      {/* Status Cards */}
      <div className="grid grid-cols-2 gap-3 text-[13px]">
        <div className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white px-4 py-2.5">
          <span className="font-bold text-zinc-800">Scenario A (50/30/20)</span>
          {resA.valid && (
            <span className={`rounded px-2 py-0.5 font-bold ${classify(resA.sigmaAnnualPct).tone}`}>
              {classify(resA.sigmaAnnualPct).label}
            </span>
          )}
        </div>
        <div className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white px-4 py-2.5">
          <span className="font-bold text-zinc-800">
            Scenario B ({weightsB.SPY.toFixed(0)}/{weightsB.IEF.toFixed(0)}/{weightsB.GLD.toFixed(0)})
          </span>
          {resB.valid ? (
            <span className={`rounded px-2 py-0.5 font-bold ${classify(resB.sigmaAnnualPct).tone}`}>
              {classify(resB.sigmaAnnualPct).label}
            </span>
          ) : (
            <span className="font-bold text-red-700">น้ำหนักไม่ครบ 100%</span>
          )}
        </div>
      </div>

      {rangeSummary && (
        <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-3.5 py-2 text-[12px] text-zinc-700">
          จากข้อมูล Test ของ ONLINE_SGD ({rangeSummary.validDays} วันที่มีข้อมูลครบ): พอร์ต B เกินงบ {budgetPct.toFixed(1)}% จำนวน{' '}
          <strong className="font-mono-num">{rangeSummary.aboveBudgetDays}</strong> วัน (ไม่ใช่ความน่าจะเป็นการขาดทุน)
        </div>
      )}
    </div>
  );
}
