import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = process.cwd();
const rawDir = path.join(root, "paper_replication", "data", "raw");
const processedDir = path.join(root, "paper_replication", "data", "processed");
const allTablesPath = path.join(rawDir, "User_IDC_DB_V1_All_Tables.xlsx");
const aggregatePath = path.join(rawDir, "Frontiers_Table_1.xlsx");

await fs.mkdir(processedDir, { recursive: true });

function recordsFromSheet(workbook, sheetName, headerRowIndex = 0) {
  const sheet = workbook.worksheets.getItem(sheetName);
  const values = sheet.getUsedRange().values;
  if (!Array.isArray(values) || values.length <= headerRowIndex) {
    throw new Error(`No rows found in ${sheetName}`);
  }
  const selectedHeaders = values[headerRowIndex]
    .map((value, index) => ({ header: String(value ?? "").trim(), index }))
    .filter(({ header }) => header.length > 0);
  return values.slice(headerRowIndex + 1)
    .map((row) => Object.fromEntries(
      selectedHeaders.map(({ header, index }) => [header, row[index] ?? null]),
    ))
    .filter((record) => Object.values(record).some(
      (value) => value !== null && value !== undefined && String(value).trim() !== "",
    ));
}

function keyValueRecordsFromSheet(workbook, sheetName) {
  const sheet = workbook.worksheets.getItem(sheetName);
  return sheet.getUsedRange().values
    .map((row) => ({ variable: row[0] ?? null, definition: row[1] ?? null }))
    .filter((record) => record.variable !== null || record.definition !== null);
}

async function saveJson(name, records) {
  const target = path.join(processedDir, `${name}.json`);
  await fs.writeFile(target, `${JSON.stringify(records, null, 2)}\n`, "utf8");
  return { name, rows: records.length, target: path.relative(root, target).replaceAll("\\", "/") };
}

const allTables = await SpreadsheetFile.importXlsx(await FileBlob.load(allTablesPath));
const aggregate = await SpreadsheetFile.importXlsx(await FileBlob.load(aggregatePath));

const outputs = [];
outputs.push(await saveJson("therapeutic", recordsFromSheet(allTables, "Therapeutic")));
outputs.push(await saveJson("sequence", recordsFromSheet(allTables, "Sequence")));
outputs.push(await saveJson("clinical_trial", recordsFromSheet(allTables, "Clinical Trial")));
outputs.push(await saveJson("variables_explained", keyValueRecordsFromSheet(allTables, "Variables Explained")));
outputs.push(await saveJson("controlled_language", recordsFromSheet(allTables, "Controlled Language", 1)));
outputs.push(await saveJson("aggregated_ada", recordsFromSheet(aggregate, "in")));

await fs.writeFile(
  path.join(processedDir, "extraction_manifest.json"),
  `${JSON.stringify({
    generated_utc: new Date().toISOString(),
    input_workbooks: [
      path.relative(root, allTablesPath).replaceAll("\\", "/"),
      path.relative(root, aggregatePath).replaceAll("\\", "/"),
    ],
    outputs,
  }, null, 2)}\n`,
  "utf8",
);

console.log(JSON.stringify(outputs, null, 2));
