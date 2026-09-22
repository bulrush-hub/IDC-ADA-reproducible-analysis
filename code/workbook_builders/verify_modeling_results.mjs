import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const source = "../outputs/IDC_modeling_results.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(source));

console.log((await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 4000,
})).ndjson);

console.log((await workbook.inspect({
  kind: "table",
  sheetId: "Executive_Summary",
  range: "A1:N34",
  include: "values,formulas",
  tableMaxRows: 34,
  tableMaxCols: 14,
  maxChars: 12000,
})).ndjson);

console.log((await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "exported workbook formula error scan",
  maxChars: 3000,
})).ndjson);

const image = await workbook.render({
  sheetName: "Executive_Summary",
  range: "A1:N34",
  scale: 1,
  format: "png",
});
await fs.writeFile(
  "modeling_previews/exported_summary.png",
  new Uint8Array(await image.arrayBuffer()),
);
