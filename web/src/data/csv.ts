export interface CsvTable {
  headers: string[];
  records: Record<string, string>[];
}

export function parseCsv(text: string): CsvTable {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        field += character;
      }
      continue;
    }
    if (character === '"' && field.length === 0) quoted = true;
    else if (character === ",") {
      row.push(field);
      field = "";
    } else if (character === "\n" || character === "\r") {
      row.push(field);
      if (row.some((value) => value.length > 0)) rows.push(row);
      row = [];
      field = "";
      if (character === "\r" && text[index + 1] === "\n") index += 1;
    } else field += character;
  }

  if (quoted) throw new Error("CSV ended inside a quoted field");
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  if (rows.length === 0) throw new Error("CSV file has no header row");

  const headers = rows[0].map((header, index) => index === 0 ? header.replace(/^\uFEFF/, "") : header);
  if (new Set(headers).size !== headers.length || headers.some((header) => header.length === 0)) throw new Error("CSV header contains a blank or duplicate column name");
  const records = rows.slice(1).map((values, rowIndex) => {
    if (values.length !== headers.length) throw new Error(`CSV row ${rowIndex + 2} has ${values.length} fields; expected ${headers.length}`);
    return Object.fromEntries(headers.map((header, columnIndex) => [header, values[columnIndex]]));
  });
  return { headers, records };
}

export function assertExactHeaders(actual: string[], expected: string[], label: string): void {
  if (actual.length !== expected.length || actual.some((header, index) => header !== expected[index])) throw new Error(`${label} header does not match the pinned handoff schema`);
}
