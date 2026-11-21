/**
 * Pure client-side CSV parser and validators for Stage06 handoff CSVs
 * (forecast_audit.csv / evaluation.csv / portfolio_risk.csv / drift_error_timeline.csv).
 */

export interface SavedReplayRow {
  predictionDate: string;
  split: string;
  ticker: 'SPY' | 'IEF' | 'GLD' | string;
  modelName: string;
  predictedVol: number;
  targetVol: number | null;
  absoluteError: number | null;
  labelStatus: 'MATURE' | 'PENDING' | string;
  forecastStatus: string;
  evaluationStatus: 'EVALUABLE' | 'PENDING' | string;
  targetStartDate?: string;
  targetEndDate?: string;
  predictionId?: string;
}

export interface PortfolioRiskRow {
  predictionDate: string;
  split: string;
  modelName: string;
  storedVol: number | null;
  covarianceMatrix: number[][] | null;
  status: string;
}

export interface DriftTimelineRow {
  predictionDate: string;
  ticker: string;
  errorValue: number;
  adwinAlert: boolean;
}

export interface H1ScatterRow {
  ticker: string;
  x: number;
  y: number;
}

function parseCsvLines(text: string): { headers: string[]; rows: Record<string, string>[] } {
  const clean = text.replace(/^\uFEFF/, '').trim();
  if (!clean) return { headers: [], rows: [] };

  const parseLine = (line: string): string[] => {
    const out: string[] = [];
    let cur = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        if (inQuotes && line[i + 1] === '"') {
          cur += '"';
          i++;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (ch === ',' && !inQuotes) {
        out.push(cur.trim());
        cur = '';
      } else {
        cur += ch;
      }
    }
    out.push(cur.trim());
    return out;
  };

  // Split by newlines respecting quotes
  const rawRecords: string[] = [];
  let buf = '';
  let inQ = false;
  for (let i = 0; i < clean.length; i++) {
    const c = clean[i];
    if (c === '"') {
      inQ = !inQ;
      buf += c;
    } else if ((c === '\n' || c === '\r') && !inQ) {
      if (buf.trim()) rawRecords.push(buf);
      buf = '';
      if (c === '\r' && clean[i + 1] === '\n') i++;
    } else {
      buf += c;
    }
  }
  if (buf.trim()) rawRecords.push(buf);

  if (rawRecords.length < 2) return { headers: [], rows: [] };
  const headers = parseLine(rawRecords[0]).map((h) => h.trim());
  const rows: Record<string, string>[] = [];

  for (let r = 1; r < rawRecords.length; r++) {
    const vals = parseLine(rawRecords[r]);
    const rec: Record<string, string> = {};
    headers.forEach((h, idx) => {
      rec[h] = vals[idx] ?? '';
    });
    rows.push(rec);
  }
  return { headers, rows };
}

export function parseForecastAuditCsv(text: string): {
  ok: boolean;
  errorTh?: string;
  rows: SavedReplayRow[];
} {
  const { headers, rows } = parseCsvLines(text);
  const required = ['prediction_date', 'split', 'ticker', 'model_name', 'predicted_vol_annualized'];
  const missing = required.filter((col) => !headers.includes(col));
  if (missing.length > 0) {
    return {
      ok: false,
      errorTh: `ไฟล์ไม่ตรงรูปแบบ forecast_audit/evaluation ขาดคอลัมน์: ${missing.join(', ')}`,
      rows: [],
    };
  }

  const parsed: SavedReplayRow[] = [];
  for (const r of rows) {
    if ((r['split'] || '').toLowerCase() !== 'test') continue;
    const pred = Number(r['predicted_vol_annualized']);
    if (!r['prediction_date'] || !r['ticker'] || r['predicted_vol_annualized'] === '' || !Number.isFinite(pred)) continue;

    const labelStatus = (r['label_status'] || 'MATURE').toUpperCase();
    const evalStatus = (r['evaluation_status'] || (labelStatus === 'PENDING' ? 'PENDING' : 'EVALUABLE')).toUpperCase();
    const isPending = labelStatus === 'PENDING' || evalStatus.startsWith('PENDING');

    const rawTarget = Number(r['target_realized_vol_5d']);
    const rawErr = Number(r['absolute_error']);

    parsed.push({
      predictionDate: r['prediction_date'],
      split: 'test',
      ticker: r['ticker'],
      modelName: r['model_name'],
      predictedVol: pred,
      // Strictly never expose Actual or Error when source status is PENDING
      targetVol: !isPending && r['target_realized_vol_5d'] !== '' && Number.isFinite(rawTarget) ? rawTarget : null,
      absoluteError: !isPending && r['absolute_error'] !== '' && Number.isFinite(rawErr) ? rawErr : null,
      labelStatus,
      forecastStatus: (r['forecast_status'] || 'VALID').toUpperCase(),
      evaluationStatus: evalStatus,
      targetStartDate: r['target_start_date'] || undefined,
      targetEndDate: r['target_end_date'] || undefined,
      predictionId: r['prediction_id'] || undefined,
    });
  }

  if (parsed.length === 0) {
    return { ok: false, errorTh: 'ไม่พบแถวข้อมูลชุด Test ที่อ่านได้ในไฟล์นี้', rows: [] };
  }

  return { ok: true, rows: parsed };
}

function tryParseCovMatrix(raw: Record<string, string>): number[][] | null {
  const jsonStr = raw['covariance_matrix'] || raw['cov_matrix'];
  if (jsonStr) {
    try {
      const m = JSON.parse(jsonStr);
      if (Array.isArray(m) && m.length === 3 && m.every((row) => Array.isArray(row) && row.length === 3)) {
        const matrix = m.map((row) => row.map(Number));
        return matrix.flat().every(Number.isFinite) ? matrix : null;
      }
    } catch {
      return null;
    }
  }

  // Fallback to flat column names if exported flat (cov_spy_spy, cov_spy_ief, ...)
  const keys = [
    ['cov_spy_spy', 'cov_spy_ief', 'cov_spy_gld'],
    ['cov_spy_ief', 'cov_ief_ief', 'cov_ief_gld'],
    ['cov_spy_gld', 'cov_ief_gld', 'cov_gld_gld'],
  ];
  if (keys.flat().every((k) => k in raw)) {
    const matrix = keys.map((row) => row.map((k) => Number(raw[k])));
    return matrix.flat().every(Number.isFinite) ? matrix : null;
  }

  return null;
}

export function parsePortfolioRiskCsv(text: string): {
  ok: boolean;
  errorTh?: string;
  rows: PortfolioRiskRow[];
} {
  const { headers, rows } = parseCsvLines(text);
  const required = ['prediction_date', 'split', 'model_name', 'portfolio_status', 'portfolio_vol_annualized'];
  const missing = required.filter((col) => !headers.includes(col));
  if (missing.length > 0) {
    return {
      ok: false,
      errorTh: `ไฟล์ไม่ตรงรูปแบบ portfolio_risk.csv (ขาดคอลัมน์: ${missing.join(', ')})`,
      rows: [],
    };
  }

  const parsed: PortfolioRiskRow[] = [];
  for (const r of rows) {
    if ((r['split'] || '').toLowerCase() !== 'test' || r['model_name'] !== 'ONLINE_SGD' || !r['prediction_date']) continue;
    const storedVolNum = Number(r['portfolio_vol_annualized']);
    parsed.push({
      predictionDate: r['prediction_date'],
      split: 'test',
      modelName: r['model_name'],
      storedVol: r['portfolio_vol_annualized'] !== '' && Number.isFinite(storedVolNum) ? storedVolNum : null,
      covarianceMatrix: tryParseCovMatrix(r),
      status: (r['portfolio_status'] || '').toUpperCase(),
    });
  }

  parsed.sort((a, b) => a.predictionDate.localeCompare(b.predictionDate));

  if (parsed.length === 0) {
    return { ok: false, errorTh: 'ไม่พบข้อมูลพอร์ตชุด Test ของ ONLINE_SGD ในไฟล์นี้', rows: [] };
  }

  return { ok: true, rows: parsed };
}

export function parseDriftTimelineCsv(text: string): {
  ok: boolean;
  errorTh?: string;
  rows: DriftTimelineRow[];
} {
  const { headers, rows } = parseCsvLines(text);
  if (!headers.includes('prediction_date')) {
    return {
      ok: false,
      errorTh: 'ไฟล์ไม่ตรงรูปแบบ drift_error_timeline.csv (ต้องมี prediction_date)',
      rows: [],
    };
  }

  const parsed: DriftTimelineRow[] = [];
  for (const r of rows) {
    const errRaw = r['absolute_error_adwin'] || r['absolute_error_evaluation'] || r['absolute_error'] || r['rolling_mae_20'] || r['error'] || r['mae'];
    const errVal = Number(errRaw);
    if (!r['prediction_date'] || !errRaw || !Number.isFinite(errVal)) continue;
    const alertFlag = String(r['adwin_alert'] ?? r['drift_detected'] ?? 'false').toLowerCase();
    parsed.push({
      predictionDate: r['prediction_date'],
      ticker: r['ticker'] || 'MACRO',
      errorValue: errVal,
      adwinAlert: alertFlag === 'true' || alertFlag === '1',
    });
  }

  if (parsed.length === 0) {
    return { ok: false, errorTh: 'ไม่พบข้อมูลค่าความคลาดเคลื่อนในไฟล์นี้', rows: [] };
  }

  return { ok: true, rows: parsed };
}

export function parseH1ScatterCsv(text: string): H1ScatterRow[] {
  const { headers, rows } = parseCsvLines(text);
  if (!['ticker', 'rv_5d', 'target_realized_vol_5d'].every((name) => headers.includes(name))) {
    throw new Error('Invalid H1_scatter_data.csv header');
  }
  return rows.flatMap((row) => {
    const x = Number(row['rv_5d']);
    const y = Number(row['target_realized_vol_5d']);
    return row['rv_5d'] && row['target_realized_vol_5d'] && Number.isFinite(x) && Number.isFinite(y)
      ? [{ ticker: row['ticker'], x, y }]
      : [];
  });
}
