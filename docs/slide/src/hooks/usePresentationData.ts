import { useCallback, useEffect, useState } from 'react';
import {
  type DriftTimelineRow,
  type H1ScatterRow,
  type PortfolioRiskRow,
  type SavedReplayRow,
  parseDriftTimelineCsv,
  parseForecastAuditCsv,
  parseH1ScatterCsv,
  parsePortfolioRiskCsv,
} from '../utils/stage06Csv';

type CsvResult<T> = { ok: boolean; rows: T[]; errorTh?: string };

export function usePresentationData() {
  const [weightsB, setWeightsB] = useState({ SPY: 50, IEF: 30, GLD: 20 });
  const [savedReplayRows, setSavedReplayRows] = useState<SavedReplayRow[] | null>(null);
  const [savedReplayFileName, setSavedReplayFileName] = useState<string | null>(null);
  const [portfolioRows, setPortfolioRows] = useState<PortfolioRiskRow[] | null>(null);
  const [portfolioFileName, setPortfolioFileName] = useState<string | null>(null);
  const [selectedCsvDateIdx, setSelectedCsvDateIdx] = useState(0);
  const [driftRows, setDriftRows] = useState<DriftTimelineRow[] | null>(null);
  const [driftFileName, setDriftFileName] = useState<string | null>(null);
  const [h1ScatterRows, setH1ScatterRows] = useState<H1ScatterRow[]>([]);
  const [loadErrors, setLoadErrors] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    const load = async <T,>(
      name: string,
      parse: (text: string) => CsvResult<T>,
      apply: (rows: T[]) => void,
    ) => {
      try {
        const response = await fetch(`${import.meta.env.BASE_URL}data/${name}.csv`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const result = parse(await response.text());
        if (!result.ok || result.rows.length === 0) throw new Error(result.errorTh || 'ไม่มีข้อมูลที่อ่านได้');
        if (!cancelled) apply(result.rows);
      } catch (error) {
        if (!cancelled) setLoadErrors((current) => [...current, `${name}.csv: ${String(error)}`]);
      }
    };

    void Promise.all([
      load('forecast_audit', parseForecastAuditCsv, (rows) => {
        setSavedReplayRows(rows);
        setSavedReplayFileName('forecast_audit.csv');
      }),
      load('portfolio_risk', parsePortfolioRiskCsv, (rows) => {
        setPortfolioRows(rows);
        setPortfolioFileName('portfolio_risk.csv');
      }),
      load('drift_error_timeline', parseDriftTimelineCsv, (rows) => {
        setDriftRows(rows);
        setDriftFileName('drift_error_timeline.csv');
      }),
      load('H1_scatter_data', (text) => ({ ok: true, rows: parseH1ScatterCsv(text) }), setH1ScatterRows),
    ]);
    return () => { cancelled = true; };
  }, []);

  const handleUploadSavedReplay = useCallback((rows: SavedReplayRow[], name: string) => {
    setSavedReplayRows(rows);
    setSavedReplayFileName(name);
  }, []);
  const handleClearSavedReplay = useCallback(() => {
    setSavedReplayRows(null);
    setSavedReplayFileName(null);
  }, []);
  const handleUploadPortfolioCsv = useCallback((rows: PortfolioRiskRow[], name: string) => {
    setPortfolioRows(rows);
    setPortfolioFileName(name);
    setSelectedCsvDateIdx(0);
  }, []);
  const handleClearPortfolioCsv = useCallback(() => {
    setPortfolioRows(null);
    setPortfolioFileName(null);
    setSelectedCsvDateIdx(0);
  }, []);
  const handleUploadDrift = useCallback((rows: DriftTimelineRow[], name: string) => {
    setDriftRows(rows);
    setDriftFileName(name);
  }, []);
  const handleClearDrift = useCallback(() => {
    setDriftRows(null);
    setDriftFileName(null);
  }, []);

  return {
    weightsB, setWeightsB,
    savedReplayRows, savedReplayFileName, handleUploadSavedReplay, handleClearSavedReplay,
    portfolioRows, portfolioFileName, selectedCsvDateIdx, setSelectedCsvDateIdx,
    handleUploadPortfolioCsv, handleClearPortfolioCsv,
    driftRows, driftFileName, handleUploadDrift, handleClearDrift,
    h1ScatterRows, loadErrors,
  };
}
