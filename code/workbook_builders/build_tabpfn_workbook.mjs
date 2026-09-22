import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = path.resolve(".");
const payloadPath = path.join(root, "work", "tabpfn_artifacts", "tabpfn_workbook_payload.json");
const outputPath = path.join(root, "outputs", "IDC_TabPFN_comparison.xlsx");
const previewDir = path.join(root, "work", "tabpfn_workbook_previews");
const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));

const colors = {
  navy: "#17324D",
  teal: "#0F766E",
  blue: "#2563EB",
  slate: "#64748B",
  paleBlue: "#EAF2F8",
  paleTeal: "#DFF4F1",
  paleGreen: "#DCFCE7",
  paleRed: "#FEE2E2",
  paleAmber: "#FEF3C7",
  light: "#F8FAFC",
  grid: "#D7E0E8",
  dark: "#0F172A",
  white: "#FFFFFF",
};

const wb = Workbook.create();
const summary = wb.worksheets.add("Summary");
const test = wb.worksheets.add("Test_Comparison");
const cv = wb.worksheets.add("CV_Comparison");
const folds = wb.worksheets.add("CV_Folds");
const boot = wb.worksheets.add("Bootstrap_CI");
const importance = wb.worksheets.add("Feature_Importance");
const predictions = wb.worksheets.add("Predictions");
const runtime = wb.worksheets.add("Runtime_Environment");
const methods = wb.worksheets.add("Methods_Limitations");

for (const sheet of [summary, test, cv, folds, boot, importance, predictions, runtime, methods]) {
  sheet.showGridLines = false;
}

function styleTitle(sheet, range, title) {
  const r = sheet.getRange(range);
  r.merge();
  r.values = [[title]];
  r.format = {
    fill: colors.navy,
    font: { bold: true, color: colors.white, size: 18, name: "Aptos Display" },
    horizontalAlignment: "left",
    verticalAlignment: "center",
  };
  r.format.rowHeight = 32;
}

function styleSubtitle(sheet, range, text) {
  const r = sheet.getRange(range);
  r.merge();
  r.values = [[text]];
  r.format = {
    fill: colors.paleBlue,
    font: { color: colors.dark, size: 10, name: "Aptos" },
    verticalAlignment: "center",
    wrapText: true,
  };
  r.format.rowHeight = 28;
}

function styleHeader(range) {
  range.format = {
    fill: colors.teal,
    font: { bold: true, color: colors.white, name: "Aptos" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "thin", color: colors.teal },
  };
  range.format.rowHeight = 30;
}

function styleTableBody(range) {
  range.format = {
    font: { color: colors.dark, size: 10, name: "Aptos" },
    verticalAlignment: "center",
    borders: {
      insideHorizontal: { style: "thin", color: colors.grid },
      bottom: { style: "thin", color: colors.grid },
    },
  };
}

function tableFromRecords(sheet, startRow, startCol, headers, records, getters, name) {
  const headerRange = sheet.getRangeByIndexes(startRow, startCol, 1, headers.length);
  headerRange.values = [headers];
  styleHeader(headerRange);
  const rows = records.map((record) => getters.map((getter) => getter(record)));
  if (rows.length) {
    const body = sheet.getRangeByIndexes(startRow + 1, startCol, rows.length, headers.length);
    body.values = rows;
    styleTableBody(body);
  }
  const endRow = startRow + rows.length;
  const tableRange = sheet.getRangeByIndexes(startRow, startCol, rows.length + 1, headers.length);
  const table = sheet.tables.add(tableRange, true, name);
  table.style = "TableStyleMedium2";
  table.showBandedRows = true;
  table.showFilterButton = true;
  return { startRow, endRow, tableRange };
}

function boolDirection(higher) {
  return higher ? "Higher" : "Lower";
}

// Summary
styleTitle(summary, "A1:L1", "IDC TabPFN-3 Performance Comparison");
styleSubtitle(
  summary,
  "A2:L2",
  "Same 29 features, same study-group partition, and the same sealed 374-row test set. Positive relative improvement means TabPFN performs better."
);

const cards = [
  { range: "A3:C3", label: "Continuous MAE (pp)", row: 3, number: "0.000" },
  { range: "D3:F3", label: "Continuous R²", row: 5, number: "0.000" },
  { range: "G3:I3", label: "Binary ROC-AUC", row: 6, number: "0.000" },
  { range: "J3:L3", label: "Binary Brier", row: 10, number: "0.000" },
];
for (const [index, card] of cards.entries()) {
  const header = summary.getRange(card.range);
  header.merge();
  header.values = [[card.label]];
  header.format = {
    fill: index % 2 === 0 ? colors.paleTeal : colors.paleBlue,
    font: { bold: true, color: colors.navy, name: "Aptos" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
  };
  const startCol = index * 3;
  summary.getRangeByIndexes(3, startCol, 1, 3).values = [["Current RF", "TabPFN-3", "Relative gain"]];
  summary.getRangeByIndexes(3, startCol, 1, 3).format = {
    fill: colors.light,
    font: { bold: true, color: colors.slate, size: 9 },
    horizontalAlignment: "center",
  };
  const values = summary.getRangeByIndexes(4, startCol, 1, 3);
  values.formulas = [[
    `='Test_Comparison'!E${card.row}`,
    `='Test_Comparison'!G${card.row}`,
    `='Test_Comparison'!I${card.row}`,
  ]];
  values.format = {
    fill: colors.white,
    font: { bold: true, color: colors.dark, size: 13 },
    horizontalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: colors.grid },
  };
  summary.getRangeByIndexes(4, startCol, 1, 2).format.numberFormat = card.number;
  summary.getCell(4, startCol + 2).format.numberFormat = "0.0%";
}

summary.getRange("A7:E7").values = [["Metric", "Current RF", "TabPFN-3", "Relative improvement", "Winner"]];
styleHeader(summary.getRange("A7:E7"));
for (let i = 0; i < payload.test_comparison.length; i += 1) {
  const row = 8 + i;
  const source = 3 + i;
  summary.getRange(`A${row}:E${row}`).formulas = [[
    `='Test_Comparison'!B${source}`,
    `='Test_Comparison'!E${source}`,
    `='Test_Comparison'!G${source}`,
    `='Test_Comparison'!I${source}`,
    `='Test_Comparison'!J${source}`,
  ]];
}
styleTableBody(summary.getRange(`A8:E${7 + payload.test_comparison.length}`));
summary.getRange(`B8:C${7 + payload.test_comparison.length}`).format.numberFormat = "0.0000";
summary.getRange(`D8:D${7 + payload.test_comparison.length}`).format.numberFormat = "0.0%";
summary.getRange(`D8:D${7 + payload.test_comparison.length}`).conditionalFormats.add("cellIs", {
  operator: "greaterThan",
  formula: 0,
  format: { fill: colors.paleGreen, font: { color: "#166534", bold: true } },
});
summary.getRange(`D8:D${7 + payload.test_comparison.length}`).conditionalFormats.add("cellIs", {
  operator: "lessThan",
  formula: 0,
  format: { fill: colors.paleRed, font: { color: "#991B1B", bold: true } },
});

summary.getRange("A19:L19").merge();
summary.getRange("A19:L19").values = [["Decision guidance"]];
summary.getRange("A19:L19").format = { fill: colors.teal, font: { bold: true, color: colors.white } };
summary.getRange("A20:L21").merge();
summary.getRange("A20:L21").values = [[
  "TabPFN-3 is clearly stronger for continuous ADA-frequency prediction on the sealed test set, and its Brier/log-loss calibration gains are supported by study-group bootstrap. Keep the current random forest as a benchmark because grouped cross-validation gains are inconsistent and fixed-threshold F1/balanced accuracy do not improve."
]];
summary.getRange("A20:L21").format = { fill: colors.paleGreen, wrapText: true, verticalAlignment: "center", font: { color: colors.dark, size: 10 } };
summary.getRange("A22:L23").merge();
summary.getRange("A22:L23").values = [[
  "Limit: this is internal grouped validation, not external validation. Do not claim reliable extrapolation to entirely unseen molecules. TabPFN-3 weights/outputs are non-commercial unless separately licensed."
]];
summary.getRange("A22:L23").format = { fill: colors.paleAmber, wrapText: true, verticalAlignment: "center", font: { color: "#78350F", size: 10 } };

summary.getRange("A26:B26").values = [["Metric", "TabPFN relative improvement (%)"]];
styleHeader(summary.getRange("A26:B26"));
for (let i = 0; i < payload.test_comparison.length; i += 1) {
  const row = 27 + i;
  const source = 3 + i;
  summary.getRange(`A${row}:B${row}`).formulas = [[
    `='Test_Comparison'!B${source}`,
    `='Test_Comparison'!I${source}*100`,
  ]];
}
styleTableBody(summary.getRange(`A27:B${26 + payload.test_comparison.length}`));
summary.getRange(`B27:B${26 + payload.test_comparison.length}`).format.numberFormat = "0.0";
const chart = summary.charts.add("bar", summary.getRange(`A26:B${26 + payload.test_comparison.length}`));
chart.title = "TabPFN relative improvement on sealed test set (%)";
chart.titleTextStyle.fontSize = 12;
chart.hasLegend = false;
chart.xAxis = { numberFormatCode: "0.0" };
chart.yAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
chart.setPosition("N3", "V20");

summary.getRange("A1:V35").format.font.name = "Aptos";
summary.getRange("A:A").format.columnWidth = 25;
summary.getRange("B:D").format.columnWidth = 18;
summary.getRange("E:E").format.columnWidth = 20;
summary.getRange("F:L").format.columnWidth = 14;
summary.freezePanes.freezeRows(2);

// Test comparison with formula-driven calculations.
styleTitle(test, "A1:J1", "Sealed Test-Set Comparison");
const testHeaders = ["Outcome", "Metric", "Better", "Current model", "Current value", "TabPFN model", "TabPFN value", "Delta (Tab-current)", "Relative improvement", "Winner"];
test.getRange("A2:J2").values = [testHeaders];
styleHeader(test.getRange("A2:J2"));
const testRows = payload.test_comparison.map((r) => [
  r.outcome, r.metric, boolDirection(r.higher_is_better), r.current_model, r.current_value,
  r.tabpfn_model, r.tabpfn_value, null, null, null,
]);
test.getRangeByIndexes(2, 0, testRows.length, testHeaders.length).values = testRows;
for (let i = 0; i < testRows.length; i += 1) {
  const row = 3 + i;
  test.getRange(`H${row}:J${row}`).formulas = [[
    `=G${row}-E${row}`,
    `=IF(C${row}="Higher",H${row}/ABS(E${row}),-H${row}/ABS(E${row}))`,
    `=IF(I${row}>0,F${row},IF(I${row}<0,D${row},"Tie"))`,
  ]];
}
styleTableBody(test.getRange(`A3:J${2 + testRows.length}`));
test.tables.add(`A2:J${2 + testRows.length}`, true, "TestComparisonTable").style = "TableStyleMedium2";
test.getRange(`E3:I${2 + testRows.length}`).format.numberFormat = "0.0000";
test.getRange(`I3:I${2 + testRows.length}`).format.numberFormat = "0.0%";
test.getRange(`I3:I${2 + testRows.length}`).conditionalFormats.add("colorScale", {
  colors: [colors.paleRed, colors.white, colors.paleGreen],
  thresholds: ["min", "50%", "max"],
});
test.getRange("A:A").format.columnWidth = 15;
test.getRange("B:B").format.columnWidth = 23;
test.getRange("C:C").format.columnWidth = 11;
test.getRange("D:D").format.columnWidth = 18;
test.getRange("E:I").format.columnWidth = 18;
test.getRange("J:J").format.columnWidth = 18;
test.freezePanes.freezeRows(2);

// CV comparison.
styleTitle(cv, "A1:K1", "Development-Set 5-Fold GroupKFold Comparison");
const cvHeaders = ["Outcome", "Metric", "Better", "Current model", "Current mean", "Current SD", "TabPFN model", "TabPFN mean", "TabPFN SD", "TabPFN improvement", "Winner by mean"];
cv.getRange("A2:K2").values = [cvHeaders];
styleHeader(cv.getRange("A2:K2"));
const cvRows = payload.cv_comparison.map((r) => [
  r.outcome, r.metric, boolDirection(r.higher_is_better), r.current_model,
  r.current_cv_mean, r.current_cv_sd, r.tabpfn_model, r.tabpfn_cv_mean, r.tabpfn_cv_sd,
  null, null,
]);
cv.getRangeByIndexes(2, 0, cvRows.length, cvHeaders.length).values = cvRows;
for (let i = 0; i < cvRows.length; i += 1) {
  const row = 3 + i;
  cv.getRange(`J${row}:K${row}`).formulas = [[
    `=IF(C${row}="Higher",H${row}-E${row},E${row}-H${row})`,
    `=IF(J${row}>0,G${row},IF(J${row}<0,D${row},"Tie"))`,
  ]];
}
styleTableBody(cv.getRange(`A3:K${2 + cvRows.length}`));
cv.tables.add(`A2:K${2 + cvRows.length}`, true, "CVComparisonTable").style = "TableStyleMedium2";
cv.getRange(`E3:J${2 + cvRows.length}`).format.numberFormat = "0.0000";
cv.getRange(`J3:J${2 + cvRows.length}`).conditionalFormats.add("cellIs", {
  operator: "greaterThan", formula: 0, format: { fill: colors.paleGreen, font: { color: "#166534" } },
});
cv.getRange(`J3:J${2 + cvRows.length}`).conditionalFormats.add("cellIs", {
  operator: "lessThan", formula: 0, format: { fill: colors.paleRed, font: { color: "#991B1B" } },
});
cv.getRange("A:A").format.columnWidth = 15;
cv.getRange("B:B").format.columnWidth = 23;
cv.getRange("C:C").format.columnWidth = 11;
cv.getRange("D:K").format.columnWidth = 17;
cv.freezePanes.freezeRows(2);

// Fold-level results.
styleTitle(folds, "A1:O1", "TabPFN-3 Fold-Level Metrics");
const foldHeaders = ["Outcome", "Fold", "MAE", "RMSE", "R2", "ROC-AUC", "PR-AUC", "F1", "Balanced accuracy", "Brier", "Log loss", "Fit seconds", "Predict seconds", "Validation rows", "Validation groups"];
tableFromRecords(
  folds, 1, 0, foldHeaders, payload.cv_folds,
  [
    r=>r.outcome, r=>r.fold, r=>r.MAE, r=>r.RMSE, r=>r.R2, r=>r.ROC_AUC, r=>r.PR_AUC,
    r=>r.F1, r=>r.Balanced_Accuracy, r=>r.Brier, r=>r.Log_Loss, r=>r.fit_seconds,
    r=>r.predict_seconds, r=>r.validation_rows, r=>r.validation_groups,
  ],
  "CVFoldsTable"
);
folds.getRange(`C3:M${2 + payload.cv_folds.length}`).format.numberFormat = "0.0000";
folds.getRange("A:A").format.columnWidth = 15;
folds.getRange("B:B").format.columnWidth = 9;
folds.getRange("C:O").format.columnWidth = 16;
folds.freezePanes.freezeRows(2);

// Paired bootstrap.
styleTitle(boot, "A1:L1", "Paired Study-Group Bootstrap on the Sealed Test Set");
styleSubtitle(boot, "A2:L2", "Improvement is direction-normalized: positive values favor TabPFN. Resampling unit = model_split_group; 2,000 valid replicates.");
const bootHeaders = ["Outcome", "Metric", "Better", "Current", "TabPFN", "TabPFN improvement", "CI 2.5%", "CI 97.5%", "P(TabPFN better)", "Valid repeats", "Resampling unit", "Conclusion"];
tableFromRecords(
  boot, 2, 0, bootHeaders, payload.bootstrap,
  [
    r=>r.outcome, r=>r.metric, r=>boolDirection(r.higher_is_better), r=>r.current_value,
    r=>r.tabpfn_value, r=>r.tabpfn_improvement, r=>r.improvement_ci_2_5,
    r=>r.improvement_ci_97_5, r=>r.bootstrap_probability_tabpfn_better,
    r=>r.bootstrap_repeats_valid, r=>r.resampling_unit, r=>r.conclusion,
  ],
  "BootstrapTable"
);
boot.getRange(`D4:I${3 + payload.bootstrap.length}`).format.numberFormat = "0.0000";
boot.getRange(`I4:I${3 + payload.bootstrap.length}`).format.numberFormat = "0.0%";
boot.getRange(`L4:L${3 + payload.bootstrap.length}`).conditionalFormats.add("containsText", {
  text: "supported", format: { fill: colors.paleGreen, font: { color: "#166534", bold: true } },
});
boot.getRange(`L4:L${3 + payload.bootstrap.length}`).conditionalFormats.add("containsText", {
  text: "uncertain", format: { fill: colors.paleAmber, font: { color: "#92400E", bold: true } },
});
boot.getRange("A:A").format.columnWidth = 15;
boot.getRange("B:B").format.columnWidth = 23;
boot.getRange("C:K").format.columnWidth = 18;
boot.getRange("L:L").format.columnWidth = 29;
boot.freezePanes.freezeRows(3);

// Feature importance.
styleTitle(importance, "A1:F1", "TabPFN-3 Test-Set Permutation Importance");
styleSubtitle(importance, "A2:F2", "Continuous: increase in MAE after permutation. Binary: decrease in ROC-AUC. Positive values indicate predictive contribution, not causality.");
const impHeaders = ["Outcome", "Feature", "Importance mean", "Importance SD", "Repeats", "Definition"];
tableFromRecords(
  importance, 2, 0, impHeaders, payload.feature_importance,
  [r=>r.outcome, r=>r.feature, r=>r.importance_mean, r=>r.importance_sd, r=>r.repeats, r=>r.importance_definition],
  "FeatureImportanceTable"
);
importance.getRange(`C4:D${3 + payload.feature_importance.length}`).format.numberFormat = "0.0000";
importance.getRange(`C4:C${3 + payload.feature_importance.length}`).conditionalFormats.add("dataBar", { color: colors.teal, gradient: true });
importance.getRange("A:A").format.columnWidth = 15;
importance.getRange("B:B").format.columnWidth = 31;
importance.getRange("C:D").format.columnWidth = 18;
importance.getRange("E:E").format.columnWidth = 11;
importance.getRange("F:F").format.columnWidth = 36;
importance.freezePanes.freezeRows(3);

// Predictions.
styleTitle(predictions, "A1:I1", "Sealed Test-Set TabPFN Predictions");
const predHeaders = ["IDC row ID", "Study group", "Molecule", "ADA frequency actual (%)", "TabPFN regression raw (%)", "TabPFN regression clipped (%)", "ADA >=10% actual", "TabPFN probability", "TabPFN class at 0.5"];
tableFromRecords(
  predictions, 1, 0, predHeaders, payload.predictions,
  [
    r=>r.idc_row_id, r=>r.model_split_group, r=>r.molecule_inn_name,
    r=>r.ada_frequency_percent_actual, r=>r.tabpfn_regression_raw,
    r=>r.tabpfn_regression_clipped_0_100, r=>r.ada_high_10_actual,
    r=>r.tabpfn_probability_ada_high_10, r=>r.tabpfn_predicted_ada_high_10,
  ],
  "PredictionsTable"
);
predictions.getRange(`D3:F${2 + payload.predictions.length}`).format.numberFormat = "0.00";
predictions.getRange(`H3:H${2 + payload.predictions.length}`).format.numberFormat = "0.0000";
predictions.getRange("A:B").format.columnWidth = 19;
predictions.getRange("C:C").format.columnWidth = 28;
predictions.getRange("D:F").format.columnWidth = 24;
predictions.getRange("G:I").format.columnWidth = 21;
predictions.freezePanes.freezeRows(2);
predictions.freezePanes.freezeColumns(3);

// Runtime and metadata.
styleTitle(runtime, "A1:F1", "Runtime, Environment, and Reproducibility Metadata");
runtime.getRange("A3:B3").values = [["Metadata field", "Value"]];
styleHeader(runtime.getRange("A3:B3"));
const metadataRows = Object.entries(payload.metadata).map(([key, value]) => {
  if (value == null) return [key, ""];
  if (typeof value === "boolean") return [key, value ? "Yes" : "No"];
  if (key === "run_timestamp_utc") return [key, `${String(value)} UTC`];
  return [key, value];
});
runtime.getRangeByIndexes(3, 0, metadataRows.length, 2).values = metadataRows;
styleTableBody(runtime.getRangeByIndexes(3, 0, metadataRows.length, 2));
runtime.tables.add(runtime.getRangeByIndexes(2, 0, metadataRows.length + 1, 2), true, "MetadataTable").style = "TableStyleMedium2";
const runtimeStart = 5 + metadataRows.length;
runtime.getRangeByIndexes(runtimeStart, 0, 1, 3).values = [["Outcome", "Phase", "Seconds"]];
styleHeader(runtime.getRangeByIndexes(runtimeStart, 0, 1, 3));
runtime.getRangeByIndexes(runtimeStart + 1, 0, payload.runtime.length, 3).values = payload.runtime.map(r=>[r.outcome,r.phase,r.seconds]);
styleTableBody(runtime.getRangeByIndexes(runtimeStart + 1, 0, payload.runtime.length, 3));
runtime.tables.add(runtime.getRangeByIndexes(runtimeStart, 0, payload.runtime.length + 1, 3), true, "RuntimeTable").style = "TableStyleMedium2";
runtime.getRangeByIndexes(runtimeStart + 1, 2, payload.runtime.length, 1).format.numberFormat = "0.000";
runtime.getRange("A:A").format.columnWidth = 34;
runtime.getRange("B:B").format.columnWidth = 72;
runtime.getRange("C:C").format.columnWidth = 18;
runtime.freezePanes.freezeRows(3);

// Methods and limitations.
styleTitle(methods, "A1:H1", "Methods, Interpretation, and Use Limitations");
const sections = [
  ["Comparison design", "Same 29 primary features, same split_audit.csv, same 2,237-row development set and sealed 374-row test set. Molecule name and study/source identifiers are excluded from the primary features."],
  ["Preprocessing", "TabPFN receives native categorical columns with explicit category indices and numeric columns without one-hot encoding or scaling. The current random forest retains its existing imputation, scaling, and one-hot pipeline."],
  ["Model selection", "Development performance uses 5-fold GroupKFold by model_split_group. No row from the sealed test set is used to choose models or thresholds."],
  ["Binary threshold", "F1 and balanced accuracy use a fixed 0.5 probability threshold. No post-hoc threshold tuning was performed on the test set."],
  ["Uncertainty", "Paired bootstrap resamples model_split_group 2,000 times. Improvement is direction-normalized so positive values always favor TabPFN."],
  ["Feature importance", "Permutation importance measures predictive contribution on this test set. It is not a causal effect and correlated features may share importance."],
  ["Generalizability", "This is internal grouped validation. It does not establish performance for entirely unseen molecules or replace an external validation cohort."],
  ["Compute", "This run used torch 2.13.0+cpu. Full pipeline wall time was about 20.6 minutes. Speed is not a GPU benchmark."],
  ["License", "TabPFN-3 weights and outputs are covered by the TabPFN-3 Non-Commercial License v1.0. Commercial or production use requires separate authorization."],
  ["Official release", "https://pypi.org/project/tabpfn/"],
  ["Official release notes", "https://github.com/PriorLabs/TabPFN/releases/tag/v8.2.0"],
  ["Weight access", "https://docs.priorlabs.ai/how-to-access-gated-models"],
  ["Model license", "https://huggingface.co/Prior-Labs/tabpfn_3/blob/main/LICENSE"],
];
methods.getRange("A3:B3").values = [["Topic", "Audit note / source"]];
styleHeader(methods.getRange("A3:B3"));
methods.getRangeByIndexes(3, 0, sections.length, 2).values = sections;
styleTableBody(methods.getRangeByIndexes(3, 0, sections.length, 2));
methods.tables.add(methods.getRangeByIndexes(2, 0, sections.length + 1, 2), true, "MethodsTable").style = "TableStyleMedium2";
methods.getRange(`B4:B${3 + sections.length}`).format.wrapText = true;
methods.getRange(`B4:B${3 + sections.length}`).format.rowHeight = 40;
methods.getRange("A:A").format.columnWidth = 26;
methods.getRange("B:B").format.columnWidth = 105;
methods.freezePanes.freezeRows(3);

// Compact workbook checks before export.
const keyInspect = await wb.inspect({
  kind: "region",
  sheetId: "Summary",
  range: "A1:L23",
  maxChars: 5000,
});
const formulaErrors = await wb.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log("KEY_INSPECT\n" + keyInspect.ndjson);
console.log("FORMULA_ERRORS\n" + formulaErrors.ndjson);

await fs.mkdir(previewDir, { recursive: true });
for (const sheetName of ["Summary", "Test_Comparison", "CV_Comparison", "CV_Folds", "Bootstrap_CI", "Feature_Importance", "Predictions", "Runtime_Environment", "Methods_Limitations"]) {
  const preview = await wb.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(outputPath);

// Re-import the exported file and verify the serialized workbook.
const imported = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const overview = await imported.inspect({ kind: "workbook,sheet,table", maxChars: 7000, tableMaxRows: 3, tableMaxCols: 6 });
const exportedErrors = await imported.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "exported workbook formula error scan",
});
console.log("EXPORTED_OVERVIEW\n" + overview.ndjson);
console.log("EXPORTED_FORMULA_ERRORS\n" + exportedErrors.ndjson);
console.log(`OUTPUT=${outputPath}`);
