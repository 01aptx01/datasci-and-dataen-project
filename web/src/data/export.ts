import type { ForecastFilter } from "./loadSnapshot.js";
import type { EvaluationRow, ForecastAuditRow, SnapshotManifest } from "./schemas.js";

export const forecastExportColumns = [
  "prediction_date", "ticker", "split", "model_name", "prediction_id", "forecast_status", "evaluation_status",
  "predicted_vol_annualized", "target_realized_vol_5d", "absolute_error", "target_end_date",
] as const;

function csvCell(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

export function buildForecastCsv(rows: ForecastAuditRow[], evaluations: Map<string, EvaluationRow>): string {
  const records = rows.map((row) => {
    const evaluation = row.split === "test" ? evaluations.get(row.predictionId) : undefined;
    const actual = evaluation?.targetRealizedVol5d ?? (row.split === "validation" ? row.targetRealizedVol5d : null);
    const error = evaluation?.absoluteError ?? (row.split === "validation" ? row.absoluteError : null);
    const fields = [
      row.predictionDate, row.ticker, row.split, row.modelName, row.predictionId, row.forecastStatus, row.evaluationStatus,
      row.predictedVolAnnualized === null ? "" : String(row.predictedVolAnnualized), actual === null ? "" : String(actual), error === null ? "" : String(error), row.targetEndDate,
    ];
    return fields.map(csvCell).join(",");
  });
  return `${forecastExportColumns.join(",")}\r\n${records.length > 0 ? `${records.join("\r\n")}\r\n` : ""}`;
}

export interface ExportMetadataInput {
  manifest: SnapshotManifest;
  filters: ForecastFilter;
  rowCount: number;
  sourceFiles: Array<{ path: string; sha256: string }>;
}

async function hashText(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (item) => item.toString(16).padStart(2, "0")).join("");
}

export async function buildExportMetadata(input: ExportMetadataInput, csv: string, createdAtUtc = new Date().toISOString()) {
  return {
    exportSchemaVersion: "1.0.0",
    createdAtUtc,
    source: {
      evaluationId: input.manifest.evaluationId,
      replayId: input.manifest.replayId,
      sourceZipSha256: input.manifest.sourceZipSha256,
      strictCutoff: input.manifest.strictCutoff,
      mode: input.manifest.mode,
      reportApproval: input.manifest.reportApproval,
      files: input.sourceFiles,
    },
    filters: input.filters,
    export: {
      filename: "filtered_forecasts.csv",
      sha256: await hashText(csv),
      bytes: new TextEncoder().encode(csv).byteLength,
      rowCount: input.rowCount,
      columns: forecastExportColumns,
      note: "Filtered projection of verified source columns; export hash is distinct from each frozen source hash.",
    },
  };
}
