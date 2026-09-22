import fs from "node:fs/promises";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

process.on("uncaughtException", (error) => {
  console.error(`BUILD_ERROR: ${error?.message ?? error}`);
  const lines = String(error?.stack ?? "").split("\n");
  console.error(lines.slice(-8).join("\n"));
  process.exit(1);
});

const payload = JSON.parse(
  await fs.readFile("modeling_artifacts/workbook_payload.json", "utf8"),
);
const wb = Workbook.create();

const colors = {
  navy: "#17365D",
  blue: "#1F4E78",
  teal: "#0F766E",
  paleBlue: "#D9EAF7",
  paleTeal: "#DDEBF7",
  amber: "#FFF2CC",
  red: "#FCE8E6",
  green: "#E2F0D9",
  gray: "#F3F4F6",
  line: "#D9E2F3",
  white: "#FFFFFF",
};

function colLetter(index) {
  let out = "";
  for (let n = index + 1; n > 0; n = Math.floor((n - 1) / 26)) {
    out = String.fromCharCode(65 + ((n - 1) % 26)) + out;
  }
  return out;
}

function matrix(records, columns) {
  return records.map((row) => columns.map((column) => row[column] ?? null));
}

function addDataSheet(name, records, tableName) {
  const sheet = wb.worksheets.add(name);
  sheet.showGridLines = false;
  const columns = records.length ? Object.keys(records[0]) : ["No data"];
  const end = colLetter(columns.length - 1);
  sheet.getRangeByIndexes(0, 0, 1, columns.length).values = [columns];
  if (records.length) {
    sheet.getRangeByIndexes(1, 0, records.length, columns.length).values = matrix(records, columns);
    sheet.tables.add(`A1:${end}${records.length + 1}`, true, tableName);
  }
  sheet.getRange(`A1:${end}1`).format = {
    fill: colors.blue,
    font: { bold: true, color: colors.white },
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRange(`A1:${end}1`).format.rowHeight = 46;
  sheet.freezePanes.freezeRows(1);
  return { sheet, columns, end, rows: records.length + 1 };
}

function headerIndex(columns, header) {
  const index = columns.indexOf(header);
  if (index < 0) throw new Error(`Missing column ${header}`);
  return index;
}

function styleColumns(ctx) {
  for (let i = 0; i < ctx.columns.length; i += 1) {
    const name = ctx.columns[i];
    const column = colLetter(i);
    let width = 15;
    if (/feature|scenario|model|column|molecule|group|method|platform|dtype|partition/i.test(name)) width = 25;
    if (name === "method") width = 38;
    if (name === "scenario") width = 36;
    if (name === "transformed_feature") width = 46;
    if (["feature", "raw_feature", "target_group", "moa_group"].includes(name)) width = 36;
    if (/idc_row_id|model_split_group/i.test(name)) width = 22;
    if (/note|description|interpretation/i.test(name)) width = 42;
    ctx.sheet.getRange(`${column}:${column}`).format.columnWidth = width;
    if (/percent|prevalence|rate/i.test(name)) {
      ctx.sheet.getRange(`${column}2:${column}${ctx.rows}`).format.numberFormat = "0.00";
    }
    if (name === "high_ada_rate") {
      ctx.sheet.getRange(`${column}2:${column}${ctx.rows}`).format.numberFormat = "0.0%";
    }
    if (["ada_mean", "ada_median", "ada_q25", "ada_q75", "ada_frequency_percent_actual", "ada_frequency_percent_predicted"].includes(name)) {
      ctx.sheet.getRange(`${column}2:${column}${ctx.rows}`).format.numberFormat = "0.00";
    }
    if (/probability/i.test(name)) {
      ctx.sheet.getRange(`${column}2:${column}${ctx.rows}`).format.numberFormat = "0.000";
    }
    if (/AUC|R2|Brier|F1|Accuracy|importance|coefficient|p_value|MAE|RMSE|Log_Loss/i.test(name)) {
      ctx.sheet.getRange(`${column}2:${column}${ctx.rows}`).format.numberFormat = "0.0000";
    }
  }
  if (ctx.rows > 1) {
    ctx.sheet.getRange(`A2:${ctx.end}${ctx.rows}`).format.wrapText = false;
    ctx.sheet.getRange(`A2:${ctx.end}${ctx.rows}`).format.rowHeight = 18;
  }
}

const performanceRecords = payload.tables.Model_Performance;
const performanceColumns = Object.keys(performanceRecords[0]);
const featureRecords = payload.tables.Feature_Importance;
const featureColumns = Object.keys(featureRecords[0]);
const sensitivityRecords = payload.tables.Sensitivity;

const summary = wb.worksheets.add("Executive_Summary");
summary.showGridLines = false;
summary.getRange("A1:N1").merge();
summary.getRange("A1").values = [["IDC ADA Modeling Results"]];
summary.getRange("A1:N1").format = {
  fill: colors.navy,
  font: { bold: true, color: colors.white, size: 16 },
  verticalAlignment: "center",
};
summary.getRange("A1:N1").format.rowHeight = 30;

const validation = payload.results.validation;
const selected = payload.results.selected_models;
const split = payload.results.split_summary;
summary.getRange("A3:B10").values = [
  ["Data / split audit", "Value"],
  ["Input rows", validation.rows],
  ["Study groups", validation.unique_model_split_groups],
  ["ADA >=10% prevalence", validation.high_ada_prevalence],
  ["Count-model eligible rows", validation.count_model_eligible_rows],
  ["Count-frequency mismatch rows", validation.count_mismatch_rows],
  ["Dependency-flagged rows", validation.dependency_flag_rows],
  ["Input SHA-256", payload.results.metadata.input_sha256],
];
summary.getRange("A3:B3").format = {
  fill: colors.blue,
  font: { bold: true, color: colors.white },
};
summary.getRange("A4:A10").format = { fill: colors.paleBlue, font: { bold: true, color: colors.navy } };
summary.getRange("B6").format.numberFormat = "0.0%";
summary.getRange("A3:B10").format.borders = { preset: "inside", style: "thin", color: colors.line };
summary.getRange("A:A").format.columnWidth = 30;
summary.getRange("B:B").format.columnWidth = 72;

summary.getRange("D3:E7").values = [
  ["Selected model", "Development-set decision"],
  ["Continuous ADA frequency", selected.continuous],
  ["ADA >=10% binary", selected.binary],
  ["Count outcome", selected.binomial_count],
  ["Selection rule", "5-fold GroupKFold on train + validation; test kept untouched"],
];
summary.getRange("D3:E3").format = {
  fill: colors.teal,
  font: { bold: true, color: colors.white },
};
summary.getRange("D4:D7").format = { fill: colors.green, font: { bold: true, color: colors.navy } };
summary.getRange("D3:E7").format.borders = { preset: "inside", style: "thin", color: colors.line };
summary.getRange("D:D").format.columnWidth = 27;
summary.getRange("E:E").format.columnWidth = 46;
summary.getRange("E7").format.wrapText = true;

const perf = addDataSheet("Model_Performance", performanceRecords, "ModelPerformanceTable");
styleColumns(perf);
const fi = addDataSheet("Feature_Importance", featureRecords, "FeatureImportanceTable");
styleColumns(fi);
const coefficients = addDataSheet("Coefficients", payload.tables.Coefficients, "CoefficientTable");
styleColumns(coefficients);
const sensitivity = addDataSheet("Sensitivity", sensitivityRecords, "SensitivityTable");
styleColumns(sensitivity);
const profile = addDataSheet("Data_Profile", payload.tables.Data_Profile, "DataProfileTable");
styleColumns(profile);
const target = addDataSheet("Target_Summary", payload.tables.Target_Summary, "TargetSummaryTable");
styleColumns(target);
const moa = addDataSheet("MOA_Summary", payload.tables.MOA_Summary, "MOASummaryTable");
styleColumns(moa);
const splitAudit = addDataSheet("Split_Audit", payload.tables.Split_Audit, "SplitAuditTable");
styleColumns(splitAudit);
const predictions = addDataSheet("Test_Predictions", payload.tables.Test_Predictions, "TestPredictionsTable");
styleColumns(predictions);

function performanceRow(outcome, model) {
  const index = performanceRecords.findIndex(
    (row) => row.outcome === outcome && row.model === model,
  );
  if (index < 0) throw new Error(`Performance row not found: ${outcome}/${model}`);
  return index + 2;
}

function performanceFormula(outcome, model, metric) {
  const row = performanceRow(outcome, model);
  const column = colLetter(headerIndex(performanceColumns, metric));
  return `='Model_Performance'!${column}${row}`;
}

summary.getRange("D9:E16").values = [
  ["Held-out test metric", "Value"],
  ["Continuous MAE (pp)", null],
  ["Continuous RMSE (pp)", null],
  ["Continuous R2", null],
  ["Binary ROC-AUC", null],
  ["Binary PR-AUC", null],
  ["Binary Brier", null],
  ["Count weighted MAE (pp)", null],
];
summary.getRange("E10:E16").formulas = [
  [performanceFormula("continuous", selected.continuous, "test_MAE")],
  [performanceFormula("continuous", selected.continuous, "test_RMSE")],
  [performanceFormula("continuous", selected.continuous, "test_R2")],
  [performanceFormula("binary", selected.binary, "test_ROC_AUC")],
  [performanceFormula("binary", selected.binary, "test_PR_AUC")],
  [performanceFormula("binary", selected.binary, "test_Brier")],
  [performanceFormula("binomial_count", selected.binomial_count, "test_weighted_MAE_pp")],
];
summary.getRange("D9:E9").format = {
  fill: colors.blue,
  font: { bold: true, color: colors.white },
};
summary.getRange("D10:D16").format = { fill: colors.paleBlue, font: { bold: true, color: colors.navy } };
summary.getRange("D9:E16").format.borders = { preset: "inside", style: "thin", color: colors.line };
summary.getRange("E10:E16").format.numberFormat = "0.000";

summary.getRange("A12:B16").values = [
  ["Partition", "Rows"],
  ["Train", split.train.rows],
  ["Validation", split.validation.rows],
  ["Test", split.test.rows],
  ["Leakage check", "0 overlapping study groups"],
];
summary.getRange("A12:B12").format = {
  fill: colors.teal,
  font: { bold: true, color: colors.white },
};
summary.getRange("A13:A16").format = { fill: colors.green, font: { bold: true, color: colors.navy } };
summary.getRange("A12:B16").format.borders = { preset: "inside", style: "thin", color: colors.line };

const heldOutRows = featureRecords
  .map((row, index) => ({ row, sheetRow: index + 2 }))
  .filter(({ row }) => row.method === "held-out permutation importance");
const continuousTop = heldOutRows
  .filter(({ row }) => row.outcome === "continuous")
  .slice(0, 10);
const binaryTop = heldOutRows
  .filter(({ row }) => row.outcome === "binary")
  .slice(0, 10);
const featureCol = colLetter(headerIndex(featureColumns, "feature"));
const importanceCol = colLetter(headerIndex(featureColumns, "importance_mean"));
const shortFeatureLabel = (name) => ({
  therapeutic_comparator: "comparator",
  labelled_as_biosimilar: "biosimilar label",
  route_clean: "route",
  antibody_backbone_clean: "antibody backbone",
  target_group: "target group",
  log_assessment_days: "follow-up time",
  log_n_ada_assessed: "sample size",
  protein_modality: "protein modality",
  log_dose_mg_extracted: "dose",
  ada_assay_platform: "assay platform",
  randomized_or_not: "randomization",
  disease_category_clean: "disease category",
}[name] ?? String(name).replaceAll("_", " "));

summary.getRange("A18:B28").values = [
  ["Continuous feature", "Permutation importance"],
  ...continuousTop.map(() => [null, null]),
];
summary.getRange("D18:E28").values = [
  ["Binary feature", "Permutation importance"],
  ...binaryTop.map(() => [null, null]),
];
summary.getRange("A19:B28").formulas = continuousTop.map(({ sheetRow }) => [
  `='Feature_Importance'!${featureCol}${sheetRow}`,
  `='Feature_Importance'!${importanceCol}${sheetRow}`,
]);
summary.getRange("D19:E28").formulas = binaryTop.map(({ sheetRow }) => [
  `='Feature_Importance'!${featureCol}${sheetRow}`,
  `='Feature_Importance'!${importanceCol}${sheetRow}`,
]);
summary.getRange("A18:B18").format = { fill: colors.blue, font: { bold: true, color: colors.white } };
summary.getRange("D18:E18").format = { fill: colors.teal, font: { bold: true, color: colors.white } };
summary.getRange("B19:B28").format.numberFormat = "0.0000";
summary.getRange("E19:E28").format.numberFormat = "0.0000";

summary.getRange("P18:Q28").values = [
  ["Feature", "Importance"],
  ...continuousTop.map(({ row }) => [shortFeatureLabel(row.feature), null]),
];
summary.getRange("Q19:Q28").formulas = continuousTop.map(({ sheetRow }) => [
  `='Feature_Importance'!${importanceCol}${sheetRow}`,
]);
summary.getRange("S18:T28").values = [
  ["Feature", "Importance"],
  ...binaryTop.map(({ row }) => [shortFeatureLabel(row.feature), null]),
];
summary.getRange("T19:T28").formulas = binaryTop.map(({ sheetRow }) => [
  `='Feature_Importance'!${importanceCol}${sheetRow}`,
]);

const contChart = summary.charts.add("bar", summary.getRange("P18:Q28"));
contChart.title = "Continuous model: top permutation features";
contChart.hasLegend = false;
contChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
contChart.yAxis = { numberFormatCode: "0.00" };
contChart.setPosition("G3", "N16");

const binChart = summary.charts.add("bar", summary.getRange("S18:T28"));
binChart.title = "Binary model: top permutation features";
binChart.hasLegend = false;
binChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
binChart.yAxis = { numberFormatCode: "0.00" };
binChart.setPosition("G18", "N31");

const unseenContinuous = sensitivityRecords.find(
  (row) => row.scenario === "Unseen-molecule holdout" && row.outcome === "continuous",
);
const unseenBinary = sensitivityRecords.find(
  (row) => row.scenario === "Unseen-molecule holdout" && row.outcome === "binary",
);
summary.getRange("A31:N34").merge();
summary.getRange("A31").values = [[
  `Generalization caution: on unseen molecules, continuous R2 = ${Number(unseenContinuous.R2).toFixed(3)} and binary ROC-AUC = ${Number(unseenBinary.ROC_AUC).toFixed(3)}. The model is stronger for study-group holdout within the observed drug space than for genuinely new molecules. Feature importance is predictive, not causal.`,
]];
summary.getRange("A31:N34").format = {
  fill: colors.amber,
  font: { bold: true, color: "#7F6000" },
  wrapText: true,
  verticalAlignment: "center",
};

const config = wb.worksheets.add("Run_Config");
config.showGridLines = false;
config.getRange("A1:F1").merge();
config.getRange("A1").values = [["Run configuration and reproducibility"]];
config.getRange("A1:F1").format = {
  fill: colors.navy,
  font: { bold: true, color: colors.white, size: 15 },
};
const metadataRows = Object.entries(payload.results.metadata).map(([key, value]) => [
  key,
  key === "run_timestamp_utc" ? `UTC ${String(value)}` : String(value),
]);
config.getRangeByIndexes(2, 0, metadataRows.length + 1, 2).values = [
  ["Metadata", "Value"],
  ...metadataRows,
];
config.getRange("A3:B3").format = { fill: colors.blue, font: { bold: true, color: colors.white } };
config.getRange("A4:A20").format = { fill: colors.paleBlue, font: { bold: true, color: colors.navy } };
config.getRange("A:A").format.columnWidth = 32;
config.getRange("B:B").format.columnWidth = 82;
config.getRange("D3:E9").values = [
  ["Rule", "Implementation"],
  ["Environment", "Project-local .venv only"],
  ["Split", "ADA-frequency strata + model_split_group isolation"],
  ["Model selection", "5-fold GroupKFold on train + validation"],
  ["Test use", "Held out until final evaluation"],
  ["Primary feature policy", "Exclude molecule identity and source/study identifiers"],
  ["Count model", "Only binomial_count_model_eligible = TRUE; assessed count used as weight"],
];
config.getRange("D3:E3").format = { fill: colors.teal, font: { bold: true, color: colors.white } };
config.getRange("D4:D9").format = { fill: colors.green, font: { bold: true, color: colors.navy } };
config.getRange("D:D").format.columnWidth = 28;
config.getRange("E:E").format.columnWidth = 74;
config.getRange("D3:E9").format.wrapText = true;

for (const ctx of [perf, fi, coefficients, sensitivity, profile, target, moa, splitAudit, predictions]) {
  const selectedIndex = ctx.columns.indexOf("selected");
  if (selectedIndex >= 0 && ctx.rows > 1) {
    const c = colLetter(selectedIndex);
    ctx.sheet.getRange(`${c}2:${c}${ctx.rows}`).conditionalFormats.add("cellIs", {
      operator: "equal",
      formula: 1,
      format: { fill: colors.green, font: { bold: true, color: colors.navy } },
    });
  }
}

await fs.mkdir("modeling_previews", { recursive: true });
const previewSpecs = [
  ["Executive_Summary", "A1:N34", "summary.png"],
  ["Model_Performance", "A1:AE12", "performance.png"],
  ["Feature_Importance", "A1:J25", "importance.png"],
  ["Coefficients", "A1:I25", "coefficients.png"],
  ["Sensitivity", "A1:Q12", "sensitivity.png"],
  ["Data_Profile", "A1:E25", "profile.png"],
  ["Target_Summary", "A1:H20", "target.png"],
  ["MOA_Summary", "A1:H20", "moa.png"],
  ["Split_Audit", "A1:E20", "split.png"],
  ["Test_Predictions", "A1:G20", "predictions.png"],
  ["Run_Config", "A1:F20", "config.png"],
];
for (const [sheetName, range, filename] of previewSpecs) {
  const image = await wb.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(
    `modeling_previews/${filename}`,
    new Uint8Array(await image.arrayBuffer()),
  );
}

console.log((await wb.inspect({
  kind: "table",
  sheetId: "Executive_Summary",
  range: "A1:N34",
  include: "values,formulas",
  tableMaxRows: 34,
  tableMaxCols: 14,
  maxChars: 12000,
})).ndjson);
console.log((await wb.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
  maxChars: 3000,
})).ndjson);

const output = await SpreadsheetFile.exportXlsx(wb);
await output.save("../outputs/IDC_modeling_results.xlsx");
console.log(JSON.stringify({
  sheets: 11,
  output: "../outputs/IDC_modeling_results.xlsx",
}));
