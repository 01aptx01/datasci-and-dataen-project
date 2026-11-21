export interface TeamMember {
  index: number;
  name: string;
  studentId: string;
}

export interface EtfInfo {
  ticker: 'SPY' | 'IEF' | 'GLD';
  assetClassTh: string;
  fullName: string;
  dailySdPct: number;
  rv20MedianPct: number;
  rv20MaxPct: number;
  vol2022Pct: number | null;
  color: string;
  description: string;
  independentSource: string;
}

export interface ModelMetricRow {
  id: 'B0' | 'B1' | 'B2' | 'B3';
  name: string;
  shortName: string;
  descriptionTh: string;
  mae: { SPY: number; IEF: number; GLD: number; Macro: number };
  rmse: { SPY: number; IEF: number; GLD: number; Macro: number };
}

export interface H1Result {
  ticker: 'SPY' | 'IEF' | 'GLD';
  n: number;
  beta: number;
  intercept: number;
  pLabel: string;
  ciLow: number;
  ciHigh: number;
  decision: string;
}

export interface H2H3Result {
  id: 'H2' | 'H3';
  labelTh: string;
  baselineName: string;
  pairs: number;
  deltaMae: number;
  pctBetter: number;
  adjustedP: number;
  ciLow: number;
  ciHigh: number;
  decision: string;
}

export interface PortfolioPreset {
  id: '50/30/20' | '60/20/20' | '33.3/33.3/33.3';
  label: string;
  weights: { SPY: number; IEF: number; GLD: number };
  meanPct: number;
  medianPct: number;
  noteTh: string;
}

export interface PresenterNoteItem {
  slideNumber: number;
  duration: string;
  talkingPoints: string[];
  sourceNote: string;
}

export const COURSE_INFO = {
  course: 'CSS 342 Data Science and Data Engineering',
  academicYear: 'ปีการศึกษา 2569',
  projectTitleLine1: 'ระบบเตรียมข้อมูลและพยากรณ์',
  projectTitleLine2: 'ความผันผวน 5 วันซื้อขาย สำหรับพอร์ต ETF',
  subtitle: 'Adaptive Portfolio Risk Lab · พยากรณ์ → ประเมินผล → สำรวจความเสี่ยงพอร์ต',
};

export const EXPERIMENT_IDENTITY = {
  evalId: '82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2',
  replayId: '3cbf81eb9242d8894d2f67f39065a17ff1ef55a2e098773aead915949ab11b12',
  ingestionRun: 'run_20261115_180400_321d',
  featureRun: 'feat_20261115T181907_bdfc78c4',
  dataCutoff: '2026-09-25',
  testRange: '1 ต.ค. 2025 – 25 ก.ย. 2026',
  studyRange: '27 ก.ย. 2021 – 25 ก.ย. 2026',
};

export const TEAM_MEMBERS: TeamMember[] = [
  { index: 1, name: 'นายธีรนันท์ ภักดีขันท์', studentId: '67090500410' },
  { index: 2, name: 'นายวิศรุต มรรคจินดา', studentId: '67090500418' },
  { index: 3, name: 'นายกนกพล มีศรีสวัสดิ์', studentId: '67090500424' },
  { index: 4, name: 'นายภูวนาถ ปันเขื่อนขัติ', studentId: '67090500436' },
];

export const SLIDE_TITLES: string[] = [
  'Adaptive Portfolio Risk Lab',
  'ทำไมต้องพยากรณ์ความผันผวน ไม่ใช่ทายราคาขึ้นลง?',
  'สินทรัพย์ 3 กลุ่ม (SPY · IEF · GLD) และคำถามวิจัย',
  'จากข้อมูลดิบสู่คำพยากรณ์ที่ตรวจสอบย้อนกลับได้',
  'เป้าหมาย 5 วันข้างหน้า (Forward RV5) และเกณฑ์ Mature',
  '4 โมเดลภายใต้กติกาแบ่งข้อมูลตามเวลาเดียวกัน',
  'ห้องทดลองย้อนรอยคำพยากรณ์ที่บันทึกไว้ (Saved Replay)',
  'ผลการทดสอบบนชุด Test: B3 มี Error ต่ำสุด',
  'การทำงานของ Online SGD และการเฝ้าระวังด้วย ADWIN',
  'หลักฐานเชิงสถิติ H1–H3 จากชุดข้อมูลตามลำดับเวลา',
  'สะพานสู่การเงิน: จาก Forecast รายตัวสู่ความเสี่ยงพอร์ต',
  'ห้องจำลองพอร์ต: เทียบ Scenario A กับ Scenario B',
  'งบความผันผวนที่ผู้ใช้กำหนดเอง (Volatility Budget)',
  'สิ่งที่อ้างได้ และข้อจำกัดที่ต้องเปิดเผย',
  'สรุปผล ก้าวถัดไป และแหล่งอ้างอิงหลักฐาน',
];

// Slides that display empirical results get the discreet historical/cutoff footer
export const RESULT_SLIDES = new Set<number>([3, 4, 7, 8, 9, 10, 11, 12, 13, 14]);

export const PRESENTER_NOTES: PresenterNoteItem[] = [
  {
    slideNumber: 1,
    duration: '0:25',
    talkingPoints: [
      'แนะนำโครงงาน Adaptive Portfolio Risk Lab สำหรับพอร์ต ETF 3 สินทรัพย์',
      'ชี้แกนหลัก 3 ขั้น: พยากรณ์ความผันผวน 5 วัน → ประเมินผลตามลำดับเวลา → สำรวจความเสี่ยงพอร์ต',
    ],
    sourceNote: 'รายงานบทที่ 1 (หน้า 1–2)',
  },
  {
    slideNumber: 2,
    duration: '0:35',
    talkingPoints: [
      'อธิบายความต่างระหว่างผลตอบแทน (ทิศทางขึ้น/ลง) กับความผันผวน (ขนาดการแกว่ง)',
      'ย้ำว่าความผันผวนที่พยากรณ์ได้ไม่ได้บอกว่าสินทรัพย์จะกำไรหรือขาดทุน',
    ],
    sourceNote: 'รายงานบทที่ 1.1 และ 7.1',
  },
  {
    slideNumber: 3,
    duration: '0:35',
    talkingPoints: [
      'แนะนำ SPY (หุ้น), IEF (พันธบัตร 7–10 ปี), GLD (ทองคำ) ในช่วง 5 ปี (1,255 วันซื้อขาย + Warm-up 61 วัน)',
      'แสดงสถิติ EDA: IEF แกว่งน้อยสุด (0.49%) และปี 2022 SPY แกว่งถึง 24.26%/ปี',
      'ตั้งคำถามวิจัยหลัก: Online SGD ลด Error จาก Static ได้จริงหรือไม่',
    ],
    sourceNote: 'รายงานบทที่ 2.1–2.2 และ 6.1–6.2',
  },
  {
    slideNumber: 4,
    duration: '0:45',
    talkingPoints: [
      'ไล่เรียง Pipeline 1 (XNYS Scheduler → yfinance → Raw Snapshot → ตรวจ Data Contract → Parquet/Quarantine)',
      'ชี้ผลตรวจคุณภาพ: 3,948 แถว, วันขาด 0, กักกัน 0, เทียบแหล่งอิสระ Tiingo/SPDR ผ่าน 100/100 วัน',
      'ย้ำการแยก Feature Pipeline กับ Target Pipeline เพื่อไม่ให้ข้อมูลอนาคตรั่วไหล',
    ],
    sourceNote: 'รายงานบทที่ 3–4 (run_20261115_180400_321d)',
  },
  {
    slideNumber: 5,
    duration: '0:45',
    talkingPoints: [
      'กดเลื่อนวันจำลอง t → t+5 ให้ผู้ชมเห็นว่าคำตอบจริงใช้ Log Return ของวัน t+1 ถึง t+5',
      'อธิบายสถานะ Pending (ยังไม่ครบ 5 วัน ห้ามใช้ประเมินหรือสอน B3) จนกว่าจะถึง t+5 จึงเป็น Mature',
    ],
    sourceNote: 'รายงานบทที่ 5.3 และ 7.1',
  },
  {
    slideNumber: 6,
    duration: '0:45',
    talkingPoints: [
      'แนะนำ B0 (คงที่), B1 (RV20), B2 (Static SGD), B3 (Online SGD) โดย B2/B3 ใช้ฟีเจอร์ 8 ตัวและ RobustScaler จาก Train',
      'ชี้จุดตัด Purge 30 แถวระหว่าง Train / Validation / Test เพื่อป้องกัน Label ข้าม Split',
    ],
    sourceNote: 'รายงานบทที่ 7.2–7.3',
  },
  {
    slideNumber: 7,
    duration: '1:15',
    talkingPoints: [
      'แสดงยอดสรุปจริงบน Test: ทำนายครบ 2,976 รายการ (100%), ประเมินได้ 2,916 (97.98%), Pending 60 รายการปลายช่วง',
      'หากนำเข้า forecast_audit.csv สามารถกดเลื่อนดูวันที่ XNYS จริง กรอง ETF/โมเดล และทดสอบ As-of reveal ที่ซ่อนค่า Pending ได้',
    ],
    sourceNote: 'รายงานบทที่ 8.3 (Frozen Eval / Replay ID)',
  },
  {
    slideNumber: 8,
    duration: '0:50',
    talkingPoints: [
      'ชี้ Macro MAE บน Test: B3 ได้ 0.048892 ต่ำที่สุด ลดจาก B2 ได้ 6.83% และจาก B1 ได้ 17.61%',
      'สลับดู RMSE และย้ำว่า GLD มี Error สูงกว่า SPY/IEF จึงต้องดูแยกตาม ETF ควบคู่กับค่าเฉลี่ย Macro',
    ],
    sourceNote: 'รายงานบทที่ 8.1 (729 คู่ ETF/วัน)',
  },
  {
    slideNumber: 9,
    duration: '0:45',
    talkingPoints: [
      'อธิบายลำดับรายวัน: Predict → บันทึก → ประเมินคำทำนายเก่าที่ Mature → ส่งเข้า ADWIN → อัปเดต B3 → Checkpoint Hash',
      'ย้ำว่า ADWIN (delta=0.002) เป็นเพียงผู้เฝ้าระวัง ไม่ได้สั่ง Reset/Retrain และพบ 0 Alerts บน Test 729 ค่า',
    ],
    sourceNote: 'รายงานบทที่ 7.3 และ 8.3',
  },
  {
    slideNumber: 10,
    duration: '0:55',
    talkingPoints: [
      'คลิกสลับ H1 (Train N=752, OLS+HAC lag 5: SPY β=0.567, IEF 0.275, GLD 0.190)',
      'แสดง H2 (vs B2: ΔMAE +0.003587, adj. p=0.001999) และ H3 (vs B1: ΔMAE +0.010448, adj. p=0.005997)',
      'ย้ำว่าผลนี้สนับสนุนในชุด Test ที่ศึกษา ไม่ใช่หลักฐานความเป็นเหตุและผลหรือรับประกันอนาคต',
    ],
    sourceNote: 'รายงานบทที่ 8.2 (Block Bootstrap + Holm)',
  },
  {
    slideNumber: 11,
    duration: '0:45',
    talkingPoints: [
      'อธิบายสมการพอร์ต Σ = D·R·D และ σ_พอร์ต = √(wᵀΣw)',
      'ชี้ข้อดีเชิงระบบ: เปลี่ยนน้ำหนัก w ได้ทันทีโดยใช้ Forecast ราย ETF และสหสัมพันธ์ย้อนหลัง 20 วันชุดเดิม ไม่ต้องฝึกโมเดลใหม่',
    ],
    sourceNote: 'รายงานบทที่ 7.4 และ 8.3 (248 วัน สถานะ OK ทุกแถว)',
  },
  {
    slideNumber: 12,
    duration: '1:25',
    talkingPoints: [
      'เทียบ Scenario A (50/30/20 → เฉลี่ย 7.81%) กับ Scenario B ที่ปรับน้ำหนักเองหรือเลือกสัดส่วนทดสอบจริง (60/20/20 → 8.47%, เท่ากัน → 8.94%)',
      'ชี้กราฟสัดส่วนความเสี่ยงแบบมีเครื่องหมาย (Signed Risk Contributions) และลองนำเข้า portfolio_risk.csv เพื่อดูวันจริงได้',
    ],
    sourceNote: 'รายงานบทที่ 9 (ผลพอร์ต 248 วัน)',
  },
  {
    slideNumber: 13,
    duration: '0:50',
    talkingPoints: [
      'ลองตั้งเพดานงบความผันผวน (เช่น 8.20% ต่อปี) เพื่อดูว่า Scenario A และ B ต่ำกว่าหรือเกินเพดานที่กำหนด',
      'ย้ำชัดเจนว่าเกณฑ์นี้ผู้ใช้ตั้งขึ้นเพื่อสาธิต ไม่ใช่คำแนะนำการลงทุนหรือการประเมินผลตอบแทน',
    ],
    sourceNote: 'กรอบการวิเคราะห์ความเสี่ยงเชิงสาธิต (บทที่ 7.4, 9, 10)',
  },
  {
    slideNumber: 14,
    duration: '0:45',
    talkingPoints: [
      'เปิดเผยข้อจำกัด 4 ด้านอย่างตรงไปตรงมา: Simulated Historical Replay ยังไม่ยืนยัน point-in-time',
      'ขอบเขต 3 ETF ช่วง Test เดียว, Correlation proxy ไม่รวมกำไร/ต้นทุนธุรกรรม, H1 working tree dirty, High-vol IEF n=0',
    ],
    sourceNote: 'รายงานบทที่ 10',
  },
  {
    slideNumber: 15,
    duration: '0:35',
    talkingPoints: [
      'สรุป 3 ความสำเร็จหลัก: Pipeline ตรวจสอบได้, B3 ลด Error ได้ใน Test นี้, ต่อยอดสู่ Risk Scenario พอร์ตได้',
      'ระบุงานต่อไป: ตรวจ point-in-time, ขยายตลาด/สินทรัพย์ และพัฒนางาน Dashboard D3–D7 ต่อจาก D1–D2',
    ],
    sourceNote: 'รายงานบทที่ 11',
  },
];

export const ETF_INFO: EtfInfo[] = [
  {
    ticker: 'SPY',
    assetClassTh: 'หุ้นสหรัฐฯ (S&P 500)',
    fullName: 'SPDR S&P 500 ETF Trust',
    dailySdPct: 1.08,
    rv20MedianPct: 13.63,
    rv20MaxPct: 52.43,
    vol2022Pct: 24.26,
    color: '#9E0B0F',
    description: 'สะท้อนตลาดหุ้นสหรัฐฯ ขนาดใหญ่ มีช่วงแกว่งแรงในปี 2022 สูงถึง 24.26% ต่อปี',
    independentSource: '100/100 วัน ตรงเกณฑ์กับ Tiingo',
  },
  {
    ticker: 'IEF',
    assetClassTh: 'พันธบัตรรัฐบาลสหรัฐฯ 7–10 ปี',
    fullName: 'iShares 7–10 Year Treasury Bond ETF',
    dailySdPct: 0.49,
    rv20MedianPct: 8.15,
    rv20MaxPct: 15.80,
    vol2022Pct: null,
    color: '#1D4ED8',
    description: 'สินทรัพย์ความผันผวนต่ำสุดในกลุ่ม (SD รายวัน 0.49%) ใช้ถ่วงสมดุลความเสี่ยงพอร์ต',
    independentSource: '100/100 วัน ตรงเกณฑ์กับ Tiingo',
  },
  {
    ticker: 'GLD',
    assetClassTh: 'ทองคำแท่ง',
    fullName: 'SPDR Gold Shares',
    dailySdPct: 1.19,
    rv20MedianPct: 14.70,
    rv20MaxPct: 58.26,
    vol2022Pct: 15.27,
    color: '#B45309',
    description: 'มีค่ากลาง RV20 สูงสุด 14.70% (สูงสุด 58.26%) และสหสัมพันธ์กับหุ้นเปลี่ยนตามสภาวะตลาด',
    independentSource: '100/100 วัน ตรงถึงระดับเซนต์กับ SPDR',
  },
];

export const MODEL_METRICS_TEST: ModelMetricRow[] = [
  {
    id: 'B0',
    name: 'B0 · Constant Baseline',
    shortName: 'B0 คงที่',
    descriptionTh: 'ใช้ค่าเฉลี่ย Forward RV5 ในช่วง Train แยกตาม ETF เป็นค่าพยากรณ์คงที่',
    mae: { SPY: 0.051733, IEF: 0.037564, GLD: 0.138264, Macro: 0.075854 },
    rmse: { SPY: 0.059999, IEF: 0.039898, GLD: 0.193562, Macro: 0.119245 },
  },
  {
    id: 'B1',
    name: 'B1 · Rolling 20-Day',
    shortName: 'B1 RV20',
    descriptionTh: 'นำค่าความผันผวนย้อนหลัง 20 วัน (RV20) ณ วันอ้างอิงมาใช้พยากรณ์โดยตรง',
    mae: { SPY: 0.044734, IEF: 0.012243, GLD: 0.121045, Macro: 0.059340 },
    rmse: { SPY: 0.057443, IEF: 0.015497, GLD: 0.162580, Macro: 0.099953 },
  },
  {
    id: 'B2',
    name: 'B2 · Static SGD',
    shortName: 'B2 Static',
    descriptionTh: 'SGDRegressor ฝึกจาก Train + RobustScaler ครั้งเดียว แล้วตรึงสถานะไว้',
    mae: { SPY: 0.039142, IEF: 0.011510, GLD: 0.106786, Macro: 0.052479 },
    rmse: { SPY: 0.054414, IEF: 0.014623, GLD: 0.162022, Macro: 0.099039 },
  },
  {
    id: 'B3',
    name: 'B3 · Online SGD',
    shortName: 'B3 Online',
    descriptionTh: 'เริ่มเหมือน B2 แล้วอัปเดตเพิ่มทุกครั้งที่คำตอบใหม่ครบ 5 วัน (Mature)',
    mae: { SPY: 0.038557, IEF: 0.011503, GLD: 0.096618, Macro: 0.048892 },
    rmse: { SPY: 0.053692, IEF: 0.014564, GLD: 0.151913, Macro: 0.093403 },
  },
];

export const H1_RESULTS: H1Result[] = [
  {
    ticker: 'SPY',
    n: 752,
    beta: 0.567075,
    intercept: 0.068015,
    pLabel: '< 0.001 (1.50×10⁻¹⁷)',
    ciLow: 0.437446,
    ciHigh: 0.696705,
    decision: 'ปฏิเสธ H₀',
  },
  {
    ticker: 'IEF',
    n: 752,
    beta: 0.274968,
    intercept: 0.059759,
    pLabel: '< 0.001 (2.94×10⁻⁶)',
    ciLow: 0.159690,
    ciHigh: 0.390246,
    decision: 'ปฏิเสธ H₀',
  },
  {
    ticker: 'GLD',
    n: 752,
    beta: 0.190001,
    intercept: 0.107131,
    pLabel: '0.002354',
    ciLow: 0.058244,
    ciHigh: 0.321757,
    decision: 'ปฏิเสธ H₀',
  },
];

export const H2_H3_RESULTS: H2H3Result[] = [
  {
    id: 'H2',
    labelTh: 'H2: B3 เทียบกับ Static SGD (B2)',
    baselineName: 'B2 (Static SGD)',
    pairs: 729,
    deltaMae: 0.003587,
    pctBetter: 6.83,
    adjustedP: 0.001999,
    ciLow: 0.001789,
    ciHigh: 0.005652,
    decision: 'ปฏิเสธ H₀',
  },
  {
    id: 'H3',
    labelTh: 'H3: B3 เทียบกับ Rolling 20-Day (B1)',
    baselineName: 'B1 (RV20 ย้อนหลัง)',
    pairs: 729,
    deltaMae: 0.010448,
    pctBetter: 17.61,
    adjustedP: 0.005997,
    ciLow: 0.002738,
    ciHigh: 0.019148,
    decision: 'ปฏิเสธ H₀',
  },
];

export const PORTFOLIO_PRESETS: PortfolioPreset[] = [
  {
    id: '50/30/20',
    label: '50% / 30% / 20% (ค่าเริ่มต้น)',
    weights: { SPY: 50, IEF: 30, GLD: 20 },
    meanPct: 7.81,
    medianPct: 7.68,
    noteTh: 'ความผันผวนเฉลี่ยต่ำสุดใน 3 สัดส่วนที่ทดสอบจริงบน Test (248 วัน)',
  },
  {
    id: '60/20/20',
    label: '60% / 20% / 20% (เน้นหุ้น)',
    weights: { SPY: 60, IEF: 20, GLD: 20 },
    meanPct: 8.47,
    medianPct: 8.31,
    noteTh: 'เพิ่มน้ำหนักหุ้น SPY เป็น 60% ทำให้ความผันผวนพอร์ตขยับขึ้นเป็น 8.47%',
  },
  {
    id: '33.3/33.3/33.3',
    label: '33.3% / 33.3% / 33.3% (เท่ากัน)',
    weights: { SPY: 33.33, IEF: 33.33, GLD: 33.34 },
    meanPct: 8.94,
    medianPct: 8.79,
    noteTh: 'แบ่งเท่ากันทั้ง 3 กอง รับความผันผวนจากทองคำมากขึ้น (เฉลี่ย 8.94%)',
  },
];

// Representative 3x3 covariance matrix calibrated to Report §6.2 & §9 (used when no CSV row is loaded)
export const REPRESENTATIVE_COV_MATRIX: number[][] = (() => {
  const v = [0.1185, 0.062, 0.1845]; // SPY, IEF, GLD annualized decimal vols
  const c = [
    [1.0, 0.10, 0.15],
    [0.10, 1.0, 0.30],
    [0.15, 0.30, 1.0],
  ];
  return [0, 1, 2].map((i) => [0, 1, 2].map((j) => v[i] * v[j] * c[i][j]));
})();

export interface PortfolioComputationResult {
  valid: boolean;
  errorTh?: string;
  sigmaAnnualPct: number;
  sigmaDecimal: number;
  contributionsPct: { SPY: number; IEF: number; GLD: number } | null;
  contributionSharesPct: { SPY: number; IEF: number; GLD: number } | null;
}

/**
 * Validates weights (finite, non-negative, sum to 100% within tolerance) and 3x3 PSD covariance matrix,
 * then computes σp = sqrt(w^T Σ w) and signed risk contributions RC_i = w_i (Σw)_i / σp.
 */
export function computePortfolioRisk(
  weightsPct: { SPY: number; IEF: number; GLD: number },
  cov: number[][] | null
): PortfolioComputationResult {
  const wArr = [weightsPct.SPY, weightsPct.IEF, weightsPct.GLD];
  if (wArr.some((x) => !Number.isFinite(x) || x < 0)) {
    return {
      valid: false,
      errorTh: 'น้ำหนักต้องเป็นตัวเลขที่ไม่ติดลบ',
      sigmaAnnualPct: NaN,
      sigmaDecimal: NaN,
      contributionsPct: null,
      contributionSharesPct: null,
    };
  }
  const sumW = wArr[0] + wArr[1] + wArr[2];
  if (Math.abs(sumW - 100) > 0.05) {
    return {
      valid: false,
      errorTh: `ผลรวมน้ำหนักต้องเท่ากับ 100% (ปัจจุบัน ${sumW.toFixed(2)}%)`,
      sigmaAnnualPct: NaN,
      sigmaDecimal: NaN,
      contributionsPct: null,
      contributionSharesPct: null,
    };
  }

  if (!cov || cov.length !== 3 || cov.some((r) => r.length !== 3 || r.some((v) => !Number.isFinite(v)))) {
    return {
      valid: false,
      errorTh: 'เมทริกซ์ความแปรปรวนร่วม (Covariance) ไม่ครบหรือไม่ถูกต้อง',
      sigmaAnnualPct: NaN,
      sigmaDecimal: NaN,
      contributionsPct: null,
      contributionSharesPct: null,
    };
  }

  // Symmetry check (tol 1e-8) and PSD leading principal minors check
  for (let i = 0; i < 3; i++) {
    if (cov[i][i] < -1e-12) {
      return {
        valid: false,
        errorTh: 'เมทริกซ์ Covariance ผิดปกติ (ค่าความแปรปรวนแนวทแยงติดลบ)',
        sigmaAnnualPct: NaN,
        sigmaDecimal: NaN,
        contributionsPct: null,
        contributionSharesPct: null,
      };
    }
    for (let j = i + 1; j < 3; j++) {
      if (Math.abs(cov[i][j] - cov[j][i]) > 1e-6) {
        return {
          valid: false,
          errorTh: 'เมทริกซ์ Covariance ไม่สมมาตร',
          sigmaAnnualPct: NaN,
          sigmaDecimal: NaN,
          contributionsPct: null,
          contributionSharesPct: null,
        };
      }
    }
  }

  const w = [wArr[0] / 100, wArr[1] / 100, wArr[2] / 100];
  const sigmaW = [0, 1, 2].map((i) => cov[i][0] * w[0] + cov[i][1] * w[1] + cov[i][2] * w[2]);
  const variance = w[0] * sigmaW[0] + w[1] * sigmaW[1] + w[2] * sigmaW[2];

  if (!Number.isFinite(variance) || variance < -1e-12) {
    return {
      valid: false,
      errorTh: 'เมทริกซ์ Covariance ไม่เป็น Positive Semi-Definite',
      sigmaAnnualPct: NaN,
      sigmaDecimal: NaN,
      contributionsPct: null,
      contributionSharesPct: null,
    };
  }

  const sigmaDec = Math.sqrt(Math.max(0, variance));
  if (sigmaDec <= 1e-12) {
    return {
      valid: true,
      sigmaAnnualPct: 0,
      sigmaDecimal: 0,
      contributionsPct: { SPY: 0, IEF: 0, GLD: 0 },
      contributionSharesPct: null, // undefined share when σp = 0
    };
  }

  const rc = [0, 1, 2].map((i) => (w[i] * sigmaW[i]) / sigmaDec);
  return {
    valid: true,
    sigmaAnnualPct: sigmaDec * 100,
    sigmaDecimal: sigmaDec,
    contributionsPct: {
      SPY: rc[0] * 100,
      IEF: rc[1] * 100,
      GLD: rc[2] * 100,
    },
    contributionSharesPct: {
      SPY: (rc[0] / sigmaDec) * 100,
      IEF: (rc[1] / sigmaDec) * 100,
      GLD: (rc[2] / sigmaDec) * 100,
    },
  };
}
