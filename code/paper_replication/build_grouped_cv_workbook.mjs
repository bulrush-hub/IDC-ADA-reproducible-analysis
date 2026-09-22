import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const outputDir = path.join(root, "outputs", "paper_replication_grouped_cv");
const artifactDir = path.join(outputDir, "artifacts");
const previewDir = path.join(outputDir, "previews");
const payload = JSON.parse(await fs.readFile(path.join(artifactDir, "workbook_payload.json"), "utf8"));
await fs.mkdir(previewDir, { recursive: true });

const outputPath = path.join(outputDir, "IDC_grouped_nested_cv_results.xlsx");
const wb = Workbook.create();

const colors = {
  navy: "#17365D",
  blue: "#1F4E78",
  teal: "#0F766E",
  orange: "#D97706",
  white: "#FFFFFF",
  paleBlue: "#D9EAF7",
  paleGreen: "#E2F0D9",
  paleAmber: "#FFF2CC",
  paleRed: "#FCE8E6",
  line: "#D9E2F3",
  dark: "#1F2937",
};

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

function recordsMatrix(records) {
  if (!records.length) return { headers: ["No data"], rows: [] };
  const headers = Object.keys(records[0]);
  return {
    headers,
    rows: records.map((record) => headers.map((header) => record[header] ?? null)),
  };
}

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
  range.format.rowHeight = 36;
}

function styleHeader(range, fill = colors.blue) {
  range.format = {
    fill,
    font: { bold: true, color: colors.white },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "thin", color: colors.line },
  };
  range.format.rowHeight = 38;
}

function styleBody(range) {
  range.format = {
    font: { color: colors.dark, size: 9 },
    verticalAlignment: "center",
    borders: { preset: "inside", style: "thin", color: colors.line },
  };
}

function writeRecordsSheet(name, title, note, records, tableName, options = {}) {
  const sheet = wb.worksheets.add(name);
  const { headers, rows } = recordsMatrix(records);
  const endColumn = columnName(headers.length);
  const bandEndColumn = options.titleEndColumn ?? endColumn;
  titleBand(sheet, title, bandEndColumn);
  noteBand(sheet, note, bandEndColumn);
  sheet.getRangeByIndexes(2, 0, 1, headers.length).values = [headers];
  styleHeader(sheet.getRangeByIndexes(2, 0, 1, headers.length), options.headerFill ?? colors.blue);
  if (rows.length) {
    sheet.getRangeByIndexes(3, 0, rows.length, headers.length).values = rows;
    styleBody(sheet.getRangeByIndexes(3, 0, rows.length, headers.length));
    sheet.tables.add(sheet.getRangeByIndexes(2, 0, rows.length + 1, headers.length), true, tableName).style =
      options.tableStyle ?? "TableStyleMedium2";
  }
  sheet.freezePanes.freezeRows(3);
  if (options.freezeColumns) sheet.freezePanes.freezeColumns(options.freezeColumns);
  sheet.showGridLines = false;
  sheet.getRange(`A1:${endColumn}${Math.max(rows.length + 3, 3)}`).format.font.name = "Aptos";
  sheet.getRange(`A:${endColumn}`).format.columnWidth = options.defaultWidth ?? 18;
  return { sheet, headers, rows, endColumn };
}

function setColumnWidth(context, header, width) {
  const index = context.headers.indexOf(header);
  if (index >= 0) {
    const column = columnName(index + 1);
    context.sheet.getRange(`${column}:${column}`).format.columnWidth = width;
  }
}

function setNumberFormat(context, headers, format) {
  for (const header of headers) {
    const index = context.headers.indexOf(header);
    if (index >= 0 && context.rows.length) {
      const column = columnName(index + 1);
      context.sheet.getRange(`${column}4:${column}${context.rows.length + 3}`).format.numberFormat = format;
    }
  }
}

function wrapColumns(context, headers, rowHeight = 42) {
  for (const header of headers) {
    const index = context.headers.indexOf(header);
    if (index >= 0 && context.rows.length) {
      const column = columnName(index + 1);
      context.sheet.getRange(`${column}4:${column}${context.rows.length + 3}`).format.wrapText = true;
    }
  }
  if (context.rows.length) {
    context.sheet.getRange(`A4:${context.endColumn}${context.rows.length + 3}`).format.rowHeight = rowHeight;
  }
}

const readme = wb.worksheets.add("README");
readme.showGridLines = false;
titleBand(readme, "IDC ADA预测：按药物分组的重复嵌套交叉验证", "N");
noteBand(readme, "同一药物在任何一次内层或外层划分中只出现在训练或验证一侧；这是内部验证，不是外部验证。", "N");
readme.getRange("A4:B13").values = [
  ["评估设置", "结果"],
  ["外层验证", `${payload.metadata.repeats} repeats × ${payload.metadata.outer_folds} folds`],
  ["内层调参", `${payload.metadata.inner_folds} grouped folds; log loss`],
  ["分组键", payload.metadata.group_key],
  ["模型", payload.metadata.model],
  ["药物重叠", 0],
  ["Bootstrap", `${payload.metadata.bootstrap_replicates} molecule clusters`],
  ["未去重完整行/药物", "1,443 / 66"],
  ["每分子一行完整行/阳性", "66 / 13"],
  ["分子×疾病完整行/阳性", "78 / 13"],
];
styleHeader(readme.getRange("A4:B4"), colors.teal);
styleBody(readme.getRange("A5:B13"));
readme.getRange("A5:A13").format = { fill: colors.paleBlue, font: { bold: true, color: colors.navy } };
readme.getRange("A:A").format.columnWidth = 34;
readme.getRange("B:B").format.columnWidth = 58;

readme.getRange("D4:N4").merge();
readme.getRange("D4").values = [["主要结论 / Primary conclusion"]];
styleHeader(readme.getRange("D4:N4"), colors.teal);
readme.getRange("D5:N8").merge();
readme.getRange("D5").values = [[
  "严格按药物隔离后，三种口径的 ROC-AUC 置信区间均跨 0.5；两种去重模型在 0.5 阈值下均未识别出 High ADA。当前公开代理变量不足以支持对新药物的可靠 ADA 分类。"
]];
readme.getRange("D5:N8").format = {
  fill: colors.paleAmber,
  font: { bold: true, color: "#7F6000", size: 10 },
  wrapText: true,
  verticalAlignment: "center",
};
readme.getRange("D9:N13").merge();
readme.getRange("D9").values = [[
  "未去重模型的分子平衡 ROC-AUC 约 0.54；每分子一行约 0.41；分子×疾病约 0.40。低样本量和仅 13 个 High ADA 事件使区间很宽，不能据点估计对模型排序。"
]];
readme.getRange("D9:N13").format = {
  fill: colors.paleRed,
  font: { color: "#9C0006", size: 10 },
  wrapText: true,
  verticalAlignment: "center",
};
readme.getRange("D:N").format.columnWidth = 13;
readme.freezePanes.freezeRows(2);

const method = writeRecordsSheet("Method", "评估方法", "所有数据转换、模型调参和指标计算均在无药物泄漏的分组验证框架内完成。", payload.tables.Method, "GroupedCVMethodTable", { headerFill: colors.teal });
setColumnWidth(method, "item", 30);
setColumnWidth(method, "implementation", 70);
setColumnWidth(method, "purpose", 78);
wrapColumns(method, ["implementation", "purpose"], 50);

const cohort = writeRecordsSheet("Cohort_Summary", "三种分析口径的完整样本", "未去重数据虽然有1,443行，但独立药物仍只有66个；记录数不能替代独立分子数。", payload.tables.Cohort_Summary, "GroupedCVCohortTable", { freezeColumns: 2, headerFill: colors.teal });
setColumnWidth(cohort, "scenario_id", 42);
setColumnWidth(cohort, "scenario_label", 52);
setColumnWidth(cohort, "evaluation_unit", 66);
setNumberFormat(cohort, ["prevalence"], "0.0%");
wrapColumns(cohort, ["evaluation_unit"], 44);

const performanceWide = writeRecordsSheet("Performance_Wide", "交叉验证性能摘要", "row_weighted 对应随机记录；molecule_balanced 使每个药物总权重相同，是预测新药物的主要比较口径。", payload.tables.Performance_Wide, "GroupedCVPerformanceWide", { freezeColumns: 3, headerFill: colors.teal, titleEndColumn: "N" });
setColumnWidth(performanceWide, "scenario_id", 42);
setColumnWidth(performanceWide, "scenario_label", 52);
setColumnWidth(performanceWide, "weighting", 26);
setNumberFormat(performanceWide, ["prevalence", "roc_auc", "roc_auc_ci_low", "roc_auc_ci_high", "roc_auc_no_skill", "average_precision", "average_precision_ci_low", "average_precision_ci_high", "average_precision_no_skill", "balanced_accuracy_0_5", "balanced_accuracy_0_5_ci_low", "balanced_accuracy_0_5_ci_high", "balanced_accuracy_0_5_no_skill", "brier_score", "brier_score_ci_low", "brier_score_ci_high", "brier_score_no_skill", "log_loss", "log_loss_ci_low", "log_loss_ci_high", "log_loss_no_skill", "calibration_gap_predicted_minus_observed", "calibration_gap_predicted_minus_observed_ci_low", "calibration_gap_predicted_minus_observed_ci_high"], "0.000");

const performanceLong = writeRecordsSheet("Performance_Long", "完整性能指标及药物聚类置信区间", "95%区间由2,000次按药物聚类bootstrap产生；higher_is_better 指标方向需结合 no_skill_reference 判断。", payload.tables.Performance_Long, "GroupedCVPerformanceLong", { freezeColumns: 3, titleEndColumn: "O" });
setColumnWidth(performanceLong, "scenario_id", 42);
setColumnWidth(performanceLong, "scenario_label", 52);
setColumnWidth(performanceLong, "metric", 44);
setColumnWidth(performanceLong, "interpretation", 78);
setColumnWidth(performanceLong, "ci_method", 48);
setNumberFormat(performanceLong, ["prevalence", "estimate", "ci_low", "ci_high", "no_skill_reference"], "0.000");
wrapColumns(performanceLong, ["interpretation", "ci_method"], 42);

const repeats = writeRecordsSheet("Repeat_Metrics", "每次重复交叉验证的OOF指标", "用于观察折分变化；最终点估计使用每条记录10次OOF概率的均值。", payload.tables.Repeat_Metrics, "GroupedCVRepeatMetrics", { freezeColumns: 2, titleEndColumn: "N" });
setColumnWidth(repeats, "scenario_id", 42);
setNumberFormat(repeats, ["prevalence", "roc_auc", "average_precision", "balanced_accuracy_0_5", "accuracy_0_5", "sensitivity_0_5", "specificity_0_5", "brier_score", "log_loss", "mean_predicted_probability", "calibration_gap_predicted_minus_observed", "predicted_positive_rate_0_5"], "0.000");

const calibration = writeRecordsSheet("Calibration", "OOF概率校准分箱", "按预测概率五分位汇总；同时提供按行和按药物平衡的观察率。", payload.tables.Calibration, "GroupedCVCalibration", { freezeColumns: 3, headerFill: colors.teal });
setColumnWidth(calibration, "scenario_id", 42);
setColumnWidth(calibration, "weighting", 26);
setNumberFormat(calibration, ["mean_predicted_probability", "observed_high_ada_rate", "probability_min", "probability_max"], "0.0%");
setNumberFormat(calibration, ["effective_weight"], "0.000");

const importance = writeRecordsSheet("Permutation_Importance", "泄漏控制的置换重要性", "重要性为置换变量后外层测试 log loss 的增量；正值表示变量帮助预测，跨0表示不稳定。", payload.tables.Permutation_Importance, "GroupedCVImportance", { freezeColumns: 2, headerFill: colors.teal });
setColumnWidth(importance, "scenario_id", 42);
setColumnWidth(importance, "variable", 42);
setColumnWidth(importance, "source_column", 44);
setNumberFormat(importance, ["mean_delta_log_loss", "median_delta_log_loss", "ci_low", "ci_high"], "0.0000");
setNumberFormat(importance, ["positive_fraction"], "0.0%");

const penalties = writeRecordsSheet("Penalty_Summary", "内层正则化选择", "每个外层训练集独立选择L2；selection_percent 为150个场景×重复×外层折中的场景内比例。", payload.tables.Penalty_Summary, "GroupedCVPenalty", { freezeColumns: 1, headerFill: colors.teal });
setColumnWidth(penalties, "scenario_id", 42);
setNumberFormat(penalties, ["l2_penalty"], "0.000");
setNumberFormat(penalties, ["selection_percent"], "0.0%");

const folds = writeRecordsSheet("Fold_Diagnostics", "外层折诊断", "group_overlap 必须始终为0；稀有类别未出现在训练折时按训练折参考水平编码。", payload.tables.Fold_Diagnostics, "GroupedCVFolds", { freezeColumns: 3, titleEndColumn: "P" });
setColumnWidth(folds, "scenario_id", 42);
setNumberFormat(folds, ["selected_l2_penalty", "test_roc_auc", "test_average_precision", "test_brier_score", "test_log_loss"], "0.000");

const predictions = writeRecordsSheet("OOF_Predictions", "逐行OOF预测", "mean_oof_probability 为10次外层验证概率均值；同药物从未同时进入同一折的训练和测试数据。", payload.tables.OOF_Predictions, "GroupedCVPredictions", { freezeColumns: 5, titleEndColumn: "M" });
setColumnWidth(predictions, "scenario_id", 42);
setColumnWidth(predictions, "replication_row_key", 44);
setColumnWidth(predictions, "molecule_key", 30);
setColumnWidth(predictions, "Molecule Assessed for ADA INN Name", 34);
setColumnWidth(predictions, "Disease Indication Category", 36);
setNumberFormat(predictions, ["ada_frequency_percent"], "0.000");
setNumberFormat(predictions, ["mean_oof_probability", "sd_oof_probability"], "0.0%");

const qc = writeRecordsSheet("QC", "质量控制", "PASS表示机械一致性检查通过；科学解释仍受小样本、代理变量和无外部队列限制。", payload.tables.QC, "GroupedCVQC", { headerFill: colors.teal });
setColumnWidth(qc, "check", 58);
setColumnWidth(qc, "expected", 34);
setColumnWidth(qc, "observed", 34);

// Formula-backed helper table for the primary molecule-balanced chart.
const moleculeBalancedRows = new Map();
payload.tables.Performance_Wide.forEach((row, index) => {
  if (row.weighting === "molecule_balanced") moleculeBalancedRows.set(row.scenario_id, index + 4);
});
readme.getRange("P3:S3").values = [["Scenario", "ROC-AUC", "Average precision", "Balanced accuracy"]];
styleHeader(readme.getRange("P3:S3"));
const scenarioOrder = ["all_public_rows_grouped", "one_row_per_molecule", "one_row_per_molecule_disease_category"];
scenarioOrder.forEach((scenarioId, index) => {
  const row = index + 4;
  const sourceRow = moleculeBalancedRows.get(scenarioId);
  readme.getRange(`P${row}:S${row}`).formulas = [[
    `='Performance_Wide'!B${sourceRow}`,
    `='Performance_Wide'!H${sourceRow}`,
    `='Performance_Wide'!L${sourceRow}`,
    `='Performance_Wide'!P${sourceRow}`,
  ]];
});
readme.getRange("Q4:S6").format.numberFormat = "0.000";
const performanceChart = readme.charts.add("bar", readme.getRange("P3:S6"));
performanceChart.title = "Molecule-balanced OOF performance";
performanceChart.hasLegend = true;
performanceChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
performanceChart.yAxis = { numberFormatCode: "0.0", min: 0, max: 1 };
performanceChart.setPosition("D15", "N33");

// Formula-backed helper and chart for out-of-fold permutation importance.
importance.sheet.getRange("K30:N30").values = [["Variable", "All public rows", "One/molecule", "One/molecule×disease"]];
styleHeader(importance.sheet.getRange("K30:N30"));
const importanceRowMap = new Map();
payload.tables.Permutation_Importance.forEach((row, index) => {
  importanceRowMap.set(`${row.scenario_id}\u0000${row.variable}`, index + 4);
});
const importanceVariables = [
  "T cell Epitope Content", "Disease Indication", "Therapeutic Immune MOA Type",
  "Comedication Immune MOA Type", "Dose Level", "Dose Interval",
  "Year Trial was Completed", "Route of Administration",
];
const importanceShortLabels = [
  "T-cell proxy", "Disease", "Therapeutic MOA", "Comedication MOA",
  "Dose level", "Dose interval", "Trial year", "Route",
];
importanceVariables.forEach((variable, index) => {
  const row = index + 31;
  const sourceRows = scenarioOrder.map((scenarioId) => importanceRowMap.get(`${scenarioId}\u0000${variable}`));
  importance.sheet.getRange(`K${row}`).values = [[importanceShortLabels[index]]];
  importance.sheet.getRange(`L${row}:N${row}`).formulas = [[
    `='Permutation_Importance'!D${sourceRows[0]}`,
    `='Permutation_Importance'!D${sourceRows[1]}`,
    `='Permutation_Importance'!D${sourceRows[2]}`,
  ]];
});
importance.sheet.getRange("L31:N38").format.numberFormat = "0.0000";
importance.sheet.getRange("K:K").format.columnWidth = 24;
importance.sheet.getRange("L:N").format.columnWidth = 15;
const importanceChart = importance.sheet.charts.add("bar", importance.sheet.getRange("K30:N38"));
importanceChart.title = "OOF permutation importance (Δ log loss)";
importanceChart.hasLegend = true;
importanceChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
importanceChart.yAxis = { numberFormatCode: "0.000" };
importanceChart.setPosition("K3", "T27");

const sheetNames = [
  "README", "Method", "Cohort_Summary", "Performance_Wide", "Performance_Long",
  "Repeat_Metrics", "Calibration", "Permutation_Importance", "Penalty_Summary",
  "Fold_Diagnostics", "OOF_Predictions", "QC",
];
for (const sheetName of sheetNames) {
  wb.worksheets.getItem(sheetName).getUsedRange().format.font.name = "Aptos";
}

const keyInspect = await wb.inspect({
  kind: "region",
  sheetId: "README",
  range: "A1:N33",
  include: "values,formulas",
  maxChars: 12000,
});
console.log("KEY_INSPECT");
console.log(keyInspect.ndjson);

const errorsBefore = await wb.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan before export",
  maxChars: 4000,
});
console.log("FORMULA_ERRORS_BEFORE");
console.log(errorsBefore.ndjson);

const previewSpecs = [
  ["README", "A1:N33"],
  ["Method", `A1:${method.endColumn}${method.rows.length + 3}`],
  ["Cohort_Summary", `A1:${cohort.endColumn}${cohort.rows.length + 3}`],
  ["Performance_Wide", "A1:Q9"],
  ["Performance_Long", "A1:O25"],
  ["Repeat_Metrics", "A1:Q25"],
  ["Calibration", `A1:${calibration.endColumn}${calibration.rows.length + 3}`],
  ["Permutation_Importance", "A1:T38"],
  ["Penalty_Summary", `A1:${penalties.endColumn}${penalties.rows.length + 3}`],
  ["Fold_Diagnostics", "A1:P30"],
  ["OOF_Predictions", "A1:M30"],
  ["QC", `A1:${qc.endColumn}${qc.rows.length + 3}`],
];
for (const [sheetName, range] of previewSpecs) {
  const preview = await wb.render({ sheetName, range, scale: 1, format: "png" });
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
  maxChars: 4000,
});
console.log("FORMULA_ERRORS_AFTER");
console.log(errorsAfter.ndjson);
console.log((await imported.inspect({ kind: "workbook,sheet,table", maxChars: 7000, tableMaxRows: 2, tableMaxCols: 5 })).ndjson);
console.log(`OUTPUT=${outputPath}`);
