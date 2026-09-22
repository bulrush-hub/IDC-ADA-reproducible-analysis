import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = process.cwd();
const artifactDir = path.join(root, "outputs", "paper_replication", "artifacts");
const sources = [
  {
    id: "user_original",
    path: path.join(root, "paper_replication", "data", "raw", "User_IDC_DB_V1_All_Tables.xlsx"),
  },
  {
    id: "author_github_v1_00",
    path: path.join(root, "paper_replication", "data", "raw", "IDC-DB", "releases", "V1.00", "IDC_DB_V1_All_Tables.xlsx"),
  },
  {
    id: "frontiers_table_2",
    path: path.join(root, "paper_replication", "data", "raw", "Frontiers_Table_2.xlsx"),
  },
];
const sheetNames = [
  "Licensing",
  "Therapeutic",
  "Sequence",
  "Clinical Trial",
  "Variables Explained",
  "Controlled Language",
];

function normalizeCell(value) {
  if (value === null || value === undefined) return null;
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "number") {
    if (Number.isNaN(value)) return "__NaN__";
    if (!Number.isFinite(value)) return value > 0 ? "__Infinity__" : "__-Infinity__";
    return Object.is(value, -0) ? 0 : value;
  }
  return value;
}

function canonicalMatrix(values) {
  return values.map((row) => row.map(normalizeCell));
}

function sha256Buffer(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex").toUpperCase();
}

function sha256Json(value) {
  return sha256Buffer(Buffer.from(JSON.stringify(value), "utf8"));
}

function csvEscape(value) {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

async function loadSource(source) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(source.path));
  const sheets = {};
  for (const sheetName of sheetNames) {
    const values = canonicalMatrix(
      workbook.worksheets.getItem(sheetName).getUsedRange(true).values,
    );
    sheets[sheetName] = {
      rows: values.length,
      columns: Math.max(0, ...values.map((row) => row.length)),
      value_sha256: sha256Json(values),
      values,
    };
  }
  const binary = await fs.readFile(source.path);
  return {
    id: source.id,
    path: path.relative(root, source.path).replaceAll("\\", "/"),
    bytes: binary.length,
    binary_sha256: sha256Buffer(binary),
    sheets,
  };
}

function compareSheet(baseline, comparator, maxExamples = 25) {
  const maxRows = Math.max(baseline.rows, comparator.rows);
  const maxColumns = Math.max(baseline.columns, comparator.columns);
  let differingCells = 0;
  const examples = [];
  for (let rowIndex = 0; rowIndex < maxRows; rowIndex += 1) {
    for (let columnIndex = 0; columnIndex < maxColumns; columnIndex += 1) {
      const left = baseline.values[rowIndex]?.[columnIndex] ?? null;
      const right = comparator.values[rowIndex]?.[columnIndex] ?? null;
      if (JSON.stringify(left) !== JSON.stringify(right)) {
        differingCells += 1;
        if (examples.length < maxExamples) {
          examples.push({
            row_1_based: rowIndex + 1,
            column_1_based: columnIndex + 1,
            user_value: left,
            comparator_value: right,
          });
        }
      }
    }
  }
  return {
    user_rows: baseline.rows,
    comparator_rows: comparator.rows,
    user_columns: baseline.columns,
    comparator_columns: comparator.columns,
    user_value_sha256: baseline.value_sha256,
    comparator_value_sha256: comparator.value_sha256,
    exact_cell_values: differingCells === 0,
    differing_cells: differingCells,
    first_differences: examples,
  };
}

await fs.mkdir(artifactDir, { recursive: true });
const loaded = [];
for (const source of sources) loaded.push(await loadSource(source));
const baseline = loaded[0];
const comparisons = [];
for (const comparator of loaded.slice(1)) {
  const sheets = {};
  for (const sheetName of sheetNames) {
    sheets[sheetName] = compareSheet(baseline.sheets[sheetName], comparator.sheets[sheetName]);
  }
  comparisons.push({
    comparator_id: comparator.id,
    binary_identical_to_user: baseline.binary_sha256 === comparator.binary_sha256,
    all_sheet_values_identical_to_user: Object.values(sheets).every((sheet) => sheet.exact_cell_values),
    sheets,
  });
}

const audit = {
  generated_utc: new Date().toISOString(),
  baseline_id: baseline.id,
  sources: loaded.map(({ id, path: sourcePath, bytes, binary_sha256 }) => ({
    id,
    path: sourcePath,
    bytes,
    binary_sha256,
  })),
  comparisons,
};
await fs.writeFile(
  path.join(artifactDir, "source_workbook_value_comparison.json"),
  `${JSON.stringify(audit, null, 2)}\n`,
  "utf8",
);

const csvRows = [[
  "comparator_id",
  "binary_identical_to_user",
  "all_sheet_values_identical_to_user",
  "sheet",
  "user_rows",
  "comparator_rows",
  "user_columns",
  "comparator_columns",
  "exact_cell_values",
  "differing_cells",
  "user_value_sha256",
  "comparator_value_sha256",
]];
for (const comparison of comparisons) {
  for (const [sheetName, sheet] of Object.entries(comparison.sheets)) {
    csvRows.push([
      comparison.comparator_id,
      comparison.binary_identical_to_user,
      comparison.all_sheet_values_identical_to_user,
      sheetName,
      sheet.user_rows,
      sheet.comparator_rows,
      sheet.user_columns,
      sheet.comparator_columns,
      sheet.exact_cell_values,
      sheet.differing_cells,
      sheet.user_value_sha256,
      sheet.comparator_value_sha256,
    ]);
  }
}
await fs.writeFile(
  path.join(artifactDir, "source_workbook_value_comparison.csv"),
  `${csvRows.map((row) => row.map(csvEscape).join(",")).join("\n")}\n`,
  "utf8",
);

console.log(JSON.stringify({
  sources: audit.sources,
  comparisons: comparisons.map((comparison) => ({
    comparator_id: comparison.comparator_id,
    binary_identical_to_user: comparison.binary_identical_to_user,
    all_sheet_values_identical_to_user: comparison.all_sheet_values_identical_to_user,
    differing_cells: Object.fromEntries(
      Object.entries(comparison.sheets).map(([sheetName, sheet]) => [sheetName, sheet.differing_cells]),
    ),
  })),
}, null, 2));
