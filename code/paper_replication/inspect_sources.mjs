import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const defaultSources = [
  "paper_replication/data/raw/IDC-DB/releases/V1.00/IDC_DB_V1_All_Tables.xlsx",
  "paper_replication/data/raw/IDC-DB/releases/V1.00/IDC_DB_V1_Aggregated_ADA_Values.xlsx",
  "paper_replication/data/raw/Frontiers_Table_1.xlsx",
  "paper_replication/data/raw/Frontiers_Table_2.xlsx",
];
const sources = process.argv.length > 2 ? process.argv.slice(2) : defaultSources;

for (const source of sources) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(source));
  const result = await workbook.inspect({
    kind: "workbook,sheet,table",
    maxChars: 50000,
    tableMaxRows: 8,
    tableMaxCols: 250,
    tableMaxCellChars: 240,
  });
  console.log(JSON.stringify({ source, inspection: result.ndjson }));
}
