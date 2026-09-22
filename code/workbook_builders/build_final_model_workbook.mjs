import fs from "node:fs/promises";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const payload = JSON.parse(await fs.readFile("final_intermediates/final_payload.json", "utf8"));
const wb = Workbook.create();

function colLetter(n) {
  let s = "";
  for (let x = n + 1; x > 0; x = Math.floor((x - 1) / 26)) s = String.fromCharCode(65 + ((x - 1) % 26)) + s;
  return s;
}
function matrix(records, columns) {
  return records.map(r => columns.map(c => r[c] ?? null));
}
const headerStyle = {fill:"#1F4E78",font:{bold:true,color:"#FFFFFF"},wrapText:true,verticalAlignment:"center"};
const subHeaderStyle = {fill:"#D9EAF7",font:{bold:true,color:"#17365D"},wrapText:true};

const readme = wb.worksheets.add("README");
readme.showGridLines = false;
readme.getRange("A1:F1").merge();
readme.getRange("A1").values = [["IDC Final Model-Ready Dataset"]];
readme.getRange("A1:F1").format = {fill:"#17365D",font:{bold:true,color:"#FFFFFF",size:16},horizontalAlignment:"left",verticalAlignment:"center"};
readme.getRange("A1:F1").format.rowHeight = 30;
readme.getRange("A3:B12").values = [
  ["Item","Final decision"],
  ["Modeling rows",2611],
  ["Primary continuous outcome","ada_frequency_percent"],
  ["Primary binary outcome","ada_high_10 (1 when ADA frequency ≥10%)"],
  ["Group-aware split","Use model_split_group; never randomly split rows from the same study across train/test"],
  ["Count-based/binomial model","Use only rows where binomial_count_model_eligible = TRUE"],
  ["Target leakage","Outcome-derived aggregate ADA columns were removed from Modeling_Data"],
  ["Nested observations","Rows with record_dependency_note require clustered/grouped analysis or sensitivity-row selection"],
  ["Manual pharmacology review","Completed; see Manual_Review_Log and cited URLs"],
  ["Duplicate handling","20 redundant source-observation copies removed; see Excluded_Duplicates"],
];
readme.getRange("A3:B3").format = headerStyle;
readme.getRange("A4:A12").format = subHeaderStyle;
readme.getRange("A3:B12").format.borders = {preset:"inside",style:"thin",color:"#D9E2F3"};
readme.getRange("A3:B12").format.wrapText = true;
readme.getRange("A:A").format.columnWidth = 28;
readme.getRange("B:B").format.columnWidth = 88;
readme.getRange("A14:F14").merge();
readme.getRange("A14").values = [["Important: 95 rows have ADA frequency values that do not reconcile within 1 percentage point to n_ada_positive / n_ada_assessed. They remain suitable for frequency-target modeling, but should not be used in binomial count models unless re-verified."]];
readme.getRange("A14:F14").format = {fill:"#FFF2CC",font:{bold:true,color:"#7F6000"},wrapText:true};
readme.getRange("A14:F14").format.rowHeight = 52;

const model = wb.worksheets.add("Modeling_Data");
model.showGridLines = false;
const mc = payload.model_columns;
const modelEnd = colLetter(mc.length - 1);
model.getRangeByIndexes(0,0,1,mc.length).values = [mc];
model.getRangeByIndexes(1,0,payload.model_rows.length,mc.length).values = matrix(payload.model_rows, mc);
model.getRange(`A1:${modelEnd}1`).format = headerStyle;
model.getRange(`A1:${modelEnd}1`).format.rowHeight = 38;
model.getRange(`A2:${modelEnd}${payload.model_rows.length+1}`).format.wrapText = false;
model.getRange(`A2:${modelEnd}${payload.model_rows.length+1}`).format.rowHeight = 18;
model.freezePanes.freezeRows(1);
model.freezePanes.freezeColumns(5);
model.tables.add(`A1:${modelEnd}${payload.model_rows.length+1}`, true, "ModelingDataTable");
for (let i=0;i<mc.length;i++) {
  const c = mc[i];
  const range = model.getRange(`${colLetter(i)}2:${colLetter(i)}${payload.model_rows.length+1}`);
  if (c === "ada_frequency_percent" || c === "ada_count_rate_percent" || c === "ada_count_delta_pp") range.format.numberFormat = "0.00";
  if (["n_ada_assessed","assessment_days","assessment_weeks"].includes(c)) range.format.numberFormat = "0.00";
  const longText = /description|sequence|population|note|reason|mechanism|criteria|assay/i.test(c);
  model.getRange(`${colLetter(i)}:${colLetter(i)}`).format.columnWidth = longText ? 38 : (/(^idc_|^trial_|_id$|molecule|target|moa_group)/i.test(c) ? 22 : 15);
}

function addDataSheet(name, columns, records, tableName) {
  const sh = wb.worksheets.add(name);
  sh.showGridLines = false;
  const end = colLetter(columns.length-1);
  sh.getRangeByIndexes(0,0,1,columns.length).values = [columns];
  if (records.length) sh.getRangeByIndexes(1,0,records.length,columns.length).values = matrix(records, columns);
  sh.getRange(`A1:${end}1`).format = headerStyle;
  sh.getRange(`A1:${end}1`).format.rowHeight = 34;
  sh.freezePanes.freezeRows(1);
  if (records.length) sh.tables.add(`A1:${end}${records.length+1}`, true, tableName);
  return {sh,end,rows:records.length+1};
}

const ex = addDataSheet("Excluded_Duplicates", payload.excluded_columns, payload.excluded_rows, "ExcludedDuplicatesTable");
ex.sh.getRange(`A2:${ex.end}${ex.rows}`).format.wrapText = false;
ex.sh.getRange(`A2:${ex.end}${ex.rows}`).format.rowHeight = 18;
for (let i=0;i<payload.excluded_columns.length;i++) {
  const c=payload.excluded_columns[i];
  ex.sh.getRange(`${colLetter(i)}:${colLetter(i)}`).format.columnWidth = /description|sequence|population|reason|mechanism|note/i.test(c) ? 36 : 16;
}

const rev = addDataSheet("Manual_Review_Log", payload.review_columns, payload.review_rows, "ManualReviewLogTable");
rev.sh.getRange("A:A").format.columnWidth = 12;
rev.sh.getRange("B:C").format.columnWidth = 24;
rev.sh.getRange("D:D").format.columnWidth = 20;
rev.sh.getRange("E:E").format.columnWidth = 72;
rev.sh.getRange("F:F").format.columnWidth = 88;
rev.sh.getRange(`A2:F${rev.rows}`).format.wrapText = true;
rev.sh.getRange(`A2:F${rev.rows}`).format.autofitRows();

const qc = addDataSheet("QC_Summary", payload.qc_columns, payload.qc_rows, "QCSummaryTable");
qc.sh.getRange("A:A").format.columnWidth = 46;
qc.sh.getRange("B:B").format.columnWidth = 18;
qc.sh.getRange("C:C").format.columnWidth = 16;
for (let r=1;r<payload.qc_rows.length+1;r++) {
  const status = payload.qc_rows[r-1].status;
  qc.sh.getRange(`C${r+1}`).format.fill = status === "PASS" ? "#E2F0D9" : status === "CAUTION" ? "#FFF2CC" : "#D9EAF7";
}

const fg = addDataSheet("Feature_Guide", payload.feature_columns, payload.feature_rows, "FeatureGuideTable");
fg.sh.getRange("A:A").format.columnWidth = 34;
fg.sh.getRange("B:B").format.columnWidth = 26;
fg.sh.getRange("C:C").format.columnWidth = 72;
fg.sh.getRange(`A2:C${fg.rows}`).format.wrapText = true;

await fs.mkdir("../outputs", {recursive:true});
for (const [sheetName, range, file] of [
  ["README","A1:F14","final_readme_preview.png"],
  ["Modeling_Data",`A1:O18`,"final_model_preview.png"],
  ["Excluded_Duplicates",`A1:L12`,"final_excluded_preview.png"],
  ["Manual_Review_Log",`A1:F21`,"final_review_preview.png"],
  ["QC_Summary",`A1:C15`,"final_qc_preview.png"],
  ["Feature_Guide",`A1:C25`,"final_feature_preview.png"],
]) {
  const img = await wb.render({sheetName, range, scale:1, format:"png"});
  await fs.writeFile(file, new Uint8Array(await img.arrayBuffer()));
}

console.log((await wb.inspect({kind:"table", sheetId:"QC_Summary", range:"A1:C15", include:"values,formulas", tableMaxRows:15, tableMaxCols:3, maxChars:5000})).ndjson);
console.log((await wb.inspect({kind:"match", searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options:{useRegex:true,maxResults:300}, summary:"final formula error scan", maxChars:2000})).ndjson);
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save("../outputs/IDC_modeling_table_final_model_ready.xlsx");
console.log(JSON.stringify({sheets:6,rows:payload.model_rows.length,columns:mc.length,output:"../outputs/IDC_modeling_table_final_model_ready.xlsx"}));
