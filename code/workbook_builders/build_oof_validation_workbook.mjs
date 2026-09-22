import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const payloadPath = path.join(root, "work", "validation_stage2", "oof_workbook_payload.json");
const outputPath = path.join(root, "outputs", "IDC_OOF_validation_results.xlsx");
const previewDir = path.join(root, "work", "oof_workbook_previews");
const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
await fs.mkdir(previewDir, { recursive: true });

const wb = Workbook.create();
const summary = wb.worksheets.add("Summary");
const overall = wb.worksheets.add("Overall_Metrics");
const bootstrap = wb.worksheets.add("Bootstrap_CI");
const calibration = wb.worksheets.add("Calibration_Bins");
const thresholds = wb.worksheets.add("Thresholds");
const errors = wb.worksheets.add("Error_Bands");
const subgroups = wb.worksheets.add("Subgroups");
const folds = wb.worksheets.add("Fold_Audit");
const readiness = wb.worksheets.add("Split_Readiness");
const predictions = wb.worksheets.add("OOF_Predictions");
const methods = wb.worksheets.add("Methods_Sources");

const colors = {
  navy: "#16324F",
  teal: "#0F766E",
  teal2: "#0E8178",
  white: "#FFFFFF",
  paleBlue: "#EAF2F8",
  paleGreen: "#DCFCE7",
  paleAmber: "#FEF3C7",
  paleRed: "#FEE2E2",
  blueBand: "#D7EEF7",
  grid: "#D7E0E8",
  dark: "#1F2937",
  muted: "#475569",
};

function titleBand(sheet, title, endColumn) {
  const range = sheet.getRange(`A1:${endColumn}1`);
  range.merge();
  range.values = [[title]];
  range.format = {
    fill: colors.navy,
    font: { bold: true, color: colors.white, size: 16 },
    verticalAlignment: "center",
  };
  range.format.rowHeight = 30;
}

function noteBand(sheet, note, endColumn) {
  const range = sheet.getRange(`A2:${endColumn}2`);
  range.merge();
  range.values = [[note]];
  range.format = {
    fill: colors.paleBlue,
    font: { color: colors.dark, size: 9 },
    wrapText: true,
    verticalAlignment: "center",
  };
  range.format.rowHeight = 28;
}

function styleHeader(range) {
  range.format = {
    fill: colors.teal2,
    font: { bold: true, color: colors.white },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "thin", color: colors.teal },
  };
  range.format.rowHeight = 28;
}

function styleBody(range) {
  range.format = {
    font: { color: colors.dark, size: 9 },
    verticalAlignment: "center",
    borders: { preset: "inside", style: "thin", color: colors.grid },
  };
}

function recordsMatrix(records) {
  if (!records.length) return { headers: [], rows: [] };
  const headers = Object.keys(records[0]);
  return { headers, rows: records.map((record) => headers.map((header) => record[header] ?? null)) };
}

function writeRecordsSheet(sheet, title, note, records, tableName, options = {}) {
  const { headers, rows } = recordsMatrix(records);
  const endColumn = columnName(headers.length || 1);
  titleBand(sheet, title, endColumn);
  noteBand(sheet, note, endColumn);
  sheet.getRangeByIndexes(2, 0, 1, headers.length).values = [headers];
  styleHeader(sheet.getRangeByIndexes(2, 0, 1, headers.length));
  if (rows.length) {
    sheet.getRangeByIndexes(3, 0, rows.length, headers.length).values = rows;
    styleBody(sheet.getRangeByIndexes(3, 0, rows.length, headers.length));
    const table = sheet.tables.add(sheet.getRangeByIndexes(2, 0, rows.length + 1, headers.length), true, tableName);
    table.style = "TableStyleMedium2";
  }
  sheet.freezePanes.freezeRows(3);
  if (options.freezeColumns) sheet.freezePanes.freezeColumns(options.freezeColumns);
  sheet.showGridLines = false;
  sheet.getRange(`A1:${endColumn}${rows.length + 3}`).format.font.name = "Aptos";
  return { headers, rows, endColumn };
}

function columnName(number) {
  let value = number;
  let name = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    value = Math.floor((value - 1) / 26);
  }
  return name;
}

function headerColumn(headers, header) {
  return columnName(headers.indexOf(header) + 1);
}

const overallSheet = writeRecordsSheet(
  overall,
  "Development-Only OOF Overall Metrics",
  "Study scheme isolates model_split_group; molecule scheme isolates molecule_inn_name. Test outcomes are not used. Ideal binary calibration CITL/intercept = 0 and slope = 1.",
  payload.overall_metrics,
  "OverallMetricsTable",
  { freezeColumns: 2 },
);
overall.getRange(`${headerColumn(overallSheet.headers, "value")}4:${headerColumn(overallSheet.headers, "value")}${payload.overall_metrics.length + 3}`).format.numberFormat = "0.0000";
overall.getRange("A:E").format.columnWidth = 22;
overall.getRange("D:D").format.columnWidth = 36;

const bootstrapSheet = writeRecordsSheet(
  bootstrap,
  "Paired Cluster Bootstrap for OOF Model Differences",
  "Improvement is direction-normalized: positive values favor TabPFN-3. Study scheme resamples studies; molecule scheme resamples molecules. 2,000 replicates.",
  payload.paired_bootstrap,
  "OOFBootstrapTable",
  { freezeColumns: 2 },
);
for (const header of ["tabpfn_improvement", "ci_2_5", "ci_97_5", "probability_tabpfn_better"]) {
  const col = headerColumn(bootstrapSheet.headers, header);
  bootstrap.getRange(`${col}4:${col}${payload.paired_bootstrap.length + 3}`).format.numberFormat = header === "probability_tabpfn_better" ? "0.0%" : "0.0000";
}
bootstrap.getRange("A:J").format.columnWidth = 21;
bootstrap.getRange("I:I").format.columnWidth = 25;
bootstrap.getRange("J:J").format.columnWidth = 34;

const calibrationSheet = writeRecordsSheet(
  calibration,
  "OOF Binary Calibration Bins",
  "Ten quantile bins per validation scheme and model. The calibration chart on Summary is formula-linked to the study scheme rows.",
  payload.calibration_bins,
  "CalibrationBinsTable",
  { freezeColumns: 2 },
);
for (const header of ["mean_predicted", "observed_rate", "minimum_predicted", "maximum_predicted"]) {
  const col = headerColumn(calibrationSheet.headers, header);
  calibration.getRange(`${col}4:${col}${payload.calibration_bins.length + 3}`).format.numberFormat = "0.0%";
}
calibration.getRange("A:H").format.columnWidth = 22;

const thresholdSheet = writeRecordsSheet(
  thresholds,
  "Development OOF Threshold Sensitivity",
  "Exploratory only. These thresholds are not nested-CV estimates and must not be carried back to the sealed test set without a new locked protocol.",
  payload.threshold_sensitivity,
  "ThresholdSensitivityTable",
  { freezeColumns: 2 },
);
for (const header of ["threshold", "sensitivity", "specificity", "precision", "negative_predictive_value", "F1", "balanced_accuracy", "predicted_positive_rate"]) {
  const col = headerColumn(thresholdSheet.headers, header);
  thresholds.getRange(`${col}4:${col}${payload.threshold_sensitivity.length + 3}`).format.numberFormat = "0.0%";
}
thresholds.getRange("A:O").format.columnWidth = 20;
thresholds.getRange("J:J").format.columnWidth = 28;
thresholds.getRange("N:N").format.columnWidth = 48;

const errorSheet = writeRecordsSheet(
  errors,
  "Continuous OOF Error by Observed ADA Band",
  "Research-study GroupKFold OOF only. Positive bias means overprediction; negative bias means underprediction.",
  payload.error_by_actual_band,
  "ErrorBandsTable",
  { freezeColumns: 2 },
);
errors.getRange("A:F").format.columnWidth = 25;
errors.getRange("E:F").format.numberFormat = "0.000";

const subgroupSheet = writeRecordsSheet(
  subgroups,
  "Prespecified ADA-Relevant Subgroup Performance",
  "Study-scheme OOF descriptive results. Ready requires ≥50 rows, ≥20 studies, ≥10 positive and ≥10 negative rows; no causal interpretation.",
  payload.subgroup_performance,
  "SubgroupPerformanceTable",
  { freezeColumns: 3 },
);
subgroups.getRange("A:M").format.columnWidth = 20;
subgroups.getRange("B:B").format.columnWidth = 35;
subgroups.getRange("J:M").format.numberFormat = "0.0000";

const foldSheet = writeRecordsSheet(
  folds,
  "Fold-Level Metrics and Leakage Audit",
  "Primary overlap must be zero. Secondary overlap quantifies molecule overlap in study CV or study overlap in molecule CV.",
  payload.fold_metrics,
  "FoldAuditTable",
  { freezeColumns: 3 },
);
folds.getRange("A:V").format.columnWidth = 17;
folds.getRange("D:D").format.columnWidth = 18;
folds.getRange("E:E").format.columnWidth = 24;
folds.getRange("F:G").format.columnWidth = 22;
folds.getRange("I:I").format.columnWidth = 24;
folds.getRange("J:K").format.columnWidth = 21;
folds.getRange("T:T").format.columnWidth = 28;
folds.getRange("A3:V3").format.rowHeight = 42;

// Split/readiness combines partition overlap and subgroup readiness in two independent tables.
titleBand(readiness, "Split and Subgroup Readiness Audit", "K");
noteBand(readiness, "Identifiers may be inspected across partitions; test outcomes were not used. Readiness is based on development data only.", "K");
const overlapMatrix = recordsMatrix(payload.partition_overlap);
readiness.getRangeByIndexes(2, 0, 1, overlapMatrix.headers.length).values = [overlapMatrix.headers];
styleHeader(readiness.getRangeByIndexes(2, 0, 1, overlapMatrix.headers.length));
readiness.getRangeByIndexes(3, 0, overlapMatrix.rows.length, overlapMatrix.headers.length).values = overlapMatrix.rows;
styleBody(readiness.getRangeByIndexes(3, 0, overlapMatrix.rows.length, overlapMatrix.headers.length));
readiness.tables.add(readiness.getRangeByIndexes(2, 0, overlapMatrix.rows.length + 1, overlapMatrix.headers.length), true, "PartitionOverlapTable").style = "TableStyleMedium2";
const readinessStart = 6 + overlapMatrix.rows.length;
const readyMatrix = recordsMatrix(payload.readiness);
readiness.getRangeByIndexes(readinessStart - 1, 0, 1, readyMatrix.headers.length).values = [readyMatrix.headers];
styleHeader(readiness.getRangeByIndexes(readinessStart - 1, 0, 1, readyMatrix.headers.length));
readiness.getRangeByIndexes(readinessStart, 0, readyMatrix.rows.length, readyMatrix.headers.length).values = readyMatrix.rows;
styleBody(readiness.getRangeByIndexes(readinessStart, 0, readyMatrix.rows.length, readyMatrix.headers.length));
readiness.tables.add(readiness.getRangeByIndexes(readinessStart - 1, 0, readyMatrix.rows.length + 1, readyMatrix.headers.length), true, "SubgroupReadinessTable").style = "TableStyleMedium2";
readiness.freezePanes.freezeRows(3);
readiness.showGridLines = false;
readiness.getRange("A:J").format.columnWidth = 22;
readiness.getRange("B:B").format.columnWidth = 34;
readiness.getRange("G:G").format.columnWidth = 60;
readiness.getRange("H:H").format.columnWidth = 24;
readiness.getRange("K:K").format.columnWidth = 26;
readiness.getRange(`H${readinessStart + 1}:H${readinessStart + readyMatrix.rows.length}`).format.numberFormat = "0.0%";
readiness.getRange(`I${readinessStart + 1}:J${readinessStart + readyMatrix.rows.length}`).format.numberFormat = "0.0";
readiness.getRange(`G4:G${3 + overlapMatrix.rows.length}`).format.wrapText = true;
readiness.getRange(`A4:G${3 + overlapMatrix.rows.length}`).format.rowHeight = 34;

const predictionSheet = writeRecordsSheet(
  predictions,
  "Development-Only OOF Predictions",
  "Each development row appears once per validation scheme. These are out-of-fold predictions; sealed test rows are not included.",
  payload.oof_predictions,
  "OOFPredictionsTable",
  { freezeColumns: 5 },
);
predictions.getRange(`A:${predictionSheet.endColumn}`).format.columnWidth = 18;
predictions.getRange("B:C").format.columnWidth = 25;
predictions.getRange("D:D").format.columnWidth = 30;
predictions.getRange("I:I").format.columnWidth = 25;
predictions.getRange("J:J").format.columnWidth = 22;
predictions.getRange("K:K").format.columnWidth = 34;
predictions.getRange("L:M").format.columnWidth = 20;
predictions.getRange("D:D").format.columnWidth = 30;
for (const header of ["ada_frequency_percent", "rf_regression", "tabpfn_regression"]) {
  const col = headerColumn(predictionSheet.headers, header);
  predictions.getRange(`${col}4:${col}${payload.oof_predictions.length + 3}`).format.numberFormat = "0.000";
}
for (const header of ["rf_probability", "tabpfn_probability"]) {
  const col = headerColumn(predictionSheet.headers, header);
  predictions.getRange(`${col}4:${col}${payload.oof_predictions.length + 3}`).format.numberFormat = "0.0000";
}

// Summary formulas link directly to Overall_Metrics.
titleBand(summary, "IDC Development OOF Validation — RF vs TabPFN-3", "M");
noteBand(summary, "Two separate tasks: new-study validation and unseen-molecule stress testing. The sealed 374-row test set was not used for this stage.", "M");
summary.getRange("A4:E4").values = [["Metric", "RF — study", "TabPFN — study", "RF — molecule", "TabPFN — molecule"]];
styleHeader(summary.getRange("A4:E4"));
const metricOrder = ["MAE", "RMSE", "R2", "ROC_AUC", "PR_AUC", "Brier", "Log_Loss", "Calibration_slope"];
const overallRowMap = new Map();
payload.overall_metrics.forEach((record, index) => {
  overallRowMap.set(`${record.validation_scheme}|${record.model}|${record.metric}`, index + 4);
});
metricOrder.forEach((metric, index) => {
  const row = 5 + index;
  summary.getRange(`A${row}`).values = [[metric]];
  const keys = [
    `study|Random forest|${metric}`,
    `study|TabPFN-3|${metric}`,
    `molecule|Random forest|${metric}`,
    `molecule|TabPFN-3|${metric}`,
  ];
  summary.getRange(`B${row}:E${row}`).formulas = [[
    ...keys.map((key) => `='Overall_Metrics'!E${overallRowMap.get(key)}`),
  ]];
});
styleBody(summary.getRange("A5:E12"));
summary.getRange("B5:E12").format.numberFormat = "0.0000";

summary.getRange("A15:M15").values = [["Decision interpretation"]];
summary.getRange("A15:M15").merge();
summary.getRange("A15:M15").format = { fill: colors.teal, font: { bold: true, color: colors.white } };
summary.getRange("A16:M18").merge();
summary.getRange("A16:M18").values = [[
  "Study OOF: TabPFN-3 has lower MAE, but paired cluster-bootstrap intervals for all model differences cross zero. Molecule OOF: both classifiers fall to about ROC-AUC 0.64. The main unresolved problem is transfer to genuinely unseen molecules, not another round of test-set tuning."
]];
summary.getRange("A16:M18").format = { fill: colors.paleGreen, wrapText: true, verticalAlignment: "center", font: { color: colors.dark, size: 10 } };
summary.getRange("A19:M21").merge();
summary.getRange("A19:M21").values = [[
  "Calibration: TabPFN-3 is closer on overall probability level (study CITL near 0) but its slope is below 1, indicating overly extreme probabilities. Random forest slope is above 1 and CITL is negative. Neither model is ready for threshold-driven use without nested calibration and external validation."
]];
summary.getRange("A19:M21").format = { fill: colors.paleAmber, wrapText: true, verticalAlignment: "center", font: { color: "#78350F", size: 10 } };
summary.getRange("A22:M24").merge();
summary.getRange("A22:M24").values = [[
  "ADA-specific finding: both models underpredict observed ADA >50% by roughly 36–40 percentage points. Prioritize assay/drug-tolerance, sampling, concomitant therapy, dose schedule, and product-development context before adding more algorithmic complexity."
]];
summary.getRange("A22:M24").format = { fill: colors.paleRed, wrapText: true, verticalAlignment: "center", font: { color: "#7F1D1D", size: 10 } };

// Formula-backed chart helper: study calibration bins.
summary.getRange("O2:S2").values = [["Bin", "RF predicted", "RF observed", "TabPFN predicted", "TabPFN observed"]];
styleHeader(summary.getRange("O2:S2"));
const studyCalibration = payload.calibration_bins.filter((row) => row.validation_scheme === "study");
const calibrationRowMap = new Map();
payload.calibration_bins.forEach((record, index) => {
  calibrationRowMap.set(`${record.validation_scheme}|${record.model}|${record.bin}`, index + 4);
});
for (let bin = 0; bin < 10; bin += 1) {
  const row = 3 + bin;
  const rfSource = calibrationRowMap.get(`study|Random forest|${bin}`);
  const tabSource = calibrationRowMap.get(`study|TabPFN-3|${bin}`);
  summary.getRange(`O${row}:S${row}`).formulas = [[
    `='Calibration_Bins'!C${rfSource}+1`,
    `='Calibration_Bins'!E${rfSource}`,
    `='Calibration_Bins'!F${rfSource}`,
    `='Calibration_Bins'!E${tabSource}`,
    `='Calibration_Bins'!F${tabSource}`,
  ]];
}
summary.getRange("P3:S12").format.numberFormat = "0.0%";
const calChart = summary.charts.add("scatter", { chartType: "scatter", title: "Study OOF calibration by probability decile", hasLegend: true });
const rfSeries = calChart.series.add("Random forest");
rfSeries.categoryFormula = "'Summary'!$P$3:$P$12";
rfSeries.formula = "'Summary'!$Q$3:$Q$12";
rfSeries.fill = "#64748B";
const tabSeries = calChart.series.add("TabPFN-3");
tabSeries.categoryFormula = "'Summary'!$R$3:$R$12";
tabSeries.formula = "'Summary'!$S$3:$S$12";
tabSeries.fill = "#0F766E";
calChart.titleTextStyle.fontSize = 12;
calChart.xAxis = { numberFormatCode: "0%", min: 0, max: 1 };
calChart.yAxis = { numberFormatCode: "0%", min: 0, max: 1 };
calChart.setPosition("G3", "M14");

// Formula-backed threshold helper and chart.
summary.getRange("O15:Q15").values = [["Threshold", "RF F1", "TabPFN F1"]];
styleHeader(summary.getRange("O15:Q15"));
const thresholdRowMap = new Map();
payload.threshold_sensitivity.forEach((record, index) => {
  thresholdRowMap.set(`${record.model}|${record.threshold.toFixed(2)}`, index + 4);
});
payload.threshold_sensitivity.filter((row) => row.model === "Random forest").forEach((record, index) => {
  const row = 16 + index;
  const key = record.threshold.toFixed(2);
  summary.getRange(`O${row}:Q${row}`).formulas = [[
    `='Thresholds'!B${thresholdRowMap.get(`Random forest|${key}`)}`,
    `='Thresholds'!K${thresholdRowMap.get(`Random forest|${key}`)}`,
    `='Thresholds'!K${thresholdRowMap.get(`TabPFN-3|${key}`)}`,
  ]];
});
summary.getRange("O16:Q31").format.numberFormat = "0.0%";
const thresholdChart = summary.charts.add("line", summary.getRange("O15:Q31"));
thresholdChart.title = "Exploratory development OOF F1 by threshold";
thresholdChart.titleTextStyle.fontSize = 12;
thresholdChart.hasLegend = true;
thresholdChart.xAxis = { numberFormatCode: "0%" };
thresholdChart.yAxis = { numberFormatCode: "0%", min: 0, max: 1 };
thresholdChart.setPosition("G26", "M39");

summary.getRange("A1:S42").format.font.name = "Aptos";
summary.getRange("A:A").format.columnWidth = 32;
summary.getRange("B:E").format.columnWidth = 20;
summary.getRange("F:F").format.columnWidth = 3;
summary.getRange("G:M").format.columnWidth = 14;
summary.freezePanes.freezeRows(2);
summary.showGridLines = false;

// Methods and literature sources.
titleBand(methods, "Methods, Interpretation, and Literature Sources", "H");
noteBand(methods, "Primary and authoritative sources supporting the next-stage validation protocol. URLs are plain text for auditability.", "H");
const methodRows = [
  ["Estimand", "Study/treatment-arm level ADA frequency under observed product, study, and assay conditions; not patient-level individual risk."],
  ["Test lock", "All OOF and subgroup results use train+validation only. The 374-row sealed test outcome was not used."],
  ["Study validation", "5-fold GroupKFold by model_split_group; estimates transfer to new studies while molecules can recur."],
  ["Molecule validation", "5-fold GroupKFold by molecule_inn_name; no molecule overlap, but multi-arm study context may recur and is audited."],
  ["Thresholds", "Exploratory development-only sensitivity. No clinical threshold or test-set threshold update is claimed."],
  ["Calibration", "Report CITL, joint intercept, slope, calibration bins, Brier and log loss. Ideal CITL/intercept=0, slope=1."],
  ["Subgroups", "Assay platform/sensitivity status, assessment duration, sample size, disease, route and biosimilar status; descriptive, not causal."],
  ["Weights", "n_ada_assessed-weighted results are sensitivity analyses and do not create patient-level predictions."],
  ["License", "TabPFN-3 weights and outputs remain under the TabPFN-3 Non-Commercial License v1.0."],
];
methods.getRange("A3:B3").values = [["Topic", "Audit note"]];
styleHeader(methods.getRange("A3:B3"));
methods.getRangeByIndexes(3, 0, methodRows.length, 2).values = methodRows;
styleBody(methods.getRangeByIndexes(3, 0, methodRows.length, 2));
methods.getRange(`A4:B${methodRows.length + 3}`).format.wrapText = true;
methods.getRange(`A4:B${methodRows.length + 3}`).format.rowHeight = 42;
methods.getRange("A:A").format.columnWidth = 25;
methods.getRange("B:B").format.columnWidth = 95;
const sourceStart = methodRows.length + 6;
const sources = [
  ["TRIPOD+AI", "https://www.bmj.com/content/385/bmj-2023-078378"],
  ["PROBAST+AI", "https://www.bmj.com/content/388/bmj-2024-082505"],
  ["Prediction model development", "https://www.bmj.com/content/386/bmj-2023-078276"],
  ["External validation", "https://www.bmj.com/content/384/bmj-2023-074820"],
  ["Nested cross-validation", "https://pubmed.ncbi.nlm.nih.gov/16504092/"],
  ["External validation sample size", "https://pubmed.ncbi.nlm.nih.gov/34031906/"],
  ["TabPFN Nature paper", "https://www.nature.com/articles/s41586-024-08328-6"],
  ["FDA ADA assay guidance", "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/immunogenicity-testing-therapeutic-protein-products-developing-and-validating-assays-anti-drug"],
  ["EMA immunogenicity guideline", "https://www.ema.europa.eu/en/documents/scientific-guideline/guideline-immunogenicity-assessment-biotechnology-derived-therapeutic-proteins-first-version_en.pdf"],
];
methods.getRange(`A${sourceStart}:B${sourceStart}`).values = [["Source", "URL"]];
styleHeader(methods.getRange(`A${sourceStart}:B${sourceStart}`));
methods.getRangeByIndexes(sourceStart, 0, sources.length, 2).values = sources;
styleBody(methods.getRangeByIndexes(sourceStart, 0, sources.length, 2));
methods.tables.add(methods.getRangeByIndexes(sourceStart - 1, 0, sources.length + 1, 2), true, "LiteratureSourcesTable").style = "TableStyleMedium2";
methods.freezePanes.freezeRows(3);
methods.showGridLines = false;

// Workbook-wide final touches.
for (const sheetName of ["Summary", "Overall_Metrics", "Bootstrap_CI", "Calibration_Bins", "Thresholds", "Error_Bands", "Subgroups", "Fold_Audit", "Split_Readiness", "OOF_Predictions", "Methods_Sources"]) {
  const sheet = wb.worksheets.getItem(sheetName);
  const used = sheet.getUsedRange();
  used.format.font.name = "Aptos";
}

const keyInspect = await wb.inspect({
  kind: "region",
  sheetId: "Summary",
  range: "A1:M24",
  maxChars: 4500,
});
console.log("KEY_INSPECT");
console.log(keyInspect.ndjson);
const errorsBefore = await wb.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan before export",
});
console.log("FORMULA_ERRORS_BEFORE");
console.log(errorsBefore.ndjson);

for (const sheetName of ["Summary", "Overall_Metrics", "Bootstrap_CI", "Calibration_Bins", "Thresholds", "Error_Bands", "Subgroups", "Fold_Audit", "Split_Readiness", "OOF_Predictions", "Methods_Sources"]) {
  const renderOptions = sheetName === "OOF_Predictions"
    ? { sheetName, range: "A1:R50", scale: 1, format: "png" }
    : { sheetName, autoCrop: "all", scale: 1, format: "png" };
  const preview = await wb.render(renderOptions);
  await fs.writeFile(path.join(previewDir, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(outputPath);
const imported = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const errorsAfter = await imported.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan after export",
});
console.log("FORMULA_ERRORS_AFTER");
console.log(errorsAfter.ndjson);
const structure = await imported.inspect({ kind: "workbook,sheet,table", maxChars: 4500, tableMaxRows: 2, tableMaxCols: 4 });
console.log("STRUCTURE");
console.log(structure.ndjson);
console.log(`OUTPUT=${outputPath}`);
