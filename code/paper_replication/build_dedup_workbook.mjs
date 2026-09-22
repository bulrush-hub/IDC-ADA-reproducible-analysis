import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const outputDir = path.join(root, "outputs", "paper_replication_dedup_scenarios");
const artifactDir = path.join(outputDir, "artifacts");
const previewDir = path.join(outputDir, "previews");
const payload = JSON.parse(await fs.readFile(path.join(artifactDir, "workbook_payload.json"), "utf8"));
await fs.mkdir(previewDir, { recursive: true });

const outputPath = path.join(outputDir, "IDC_dedup_scenarios_results.xlsx");
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
  range.format.rowHeight = 34;
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
  range.format.rowHeight = 36;
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

function wrapColumns(context, headers, rowHeight = 38) {
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
titleBand(readme, "IDC 去重场景分析 / Deduplication Scenarios", "N");
noteBand(readme, "两个独立输出口径；均保留真实来源行，不做跨试验字段合成，也不覆盖原 paper_replication 结果。", "N");
readme.getRange("A4:B13").values = [
  ["关键指标", "结果"],
  ["原始候选记录", payload.metadata.source_candidate_rows],
  ["场景 1：每种分子一行", payload.metadata.scenario_1_rows],
  ["场景 1：完整代理 GLM N", payload.metadata.scenario_1_model_n],
  ["场景 2：每种分子×疾病一行", payload.metadata.scenario_2_rows],
  ["场景 2：完整代理 GLM N", payload.metadata.scenario_2_model_n],
  ["未去重完整代理 GLM N", payload.metadata.baseline_model_n],
  ["选择规则版本", payload.metadata.selection_rule_version],
  ["原结果未覆盖", payload.metadata.original_results_untouched],
  ["生成时间 UTC", `UTC ${payload.metadata.generated_utc}`],
];
styleHeader(readme.getRange("A4:B4"), colors.teal);
styleBody(readme.getRange("A5:B13"));
readme.getRange("A5:A13").format = { fill: colors.paleBlue, font: { bold: true, color: colors.navy } };
readme.getRange("A:A").format.columnWidth = 34;
readme.getRange("B:B").format.columnWidth = 62;

readme.getRange("D4:N4").merge();
readme.getRange("D4").values = [["结论边界 / Interpretation guardrail"]];
styleHeader(readme.getRange("D4:N4"), colors.teal);
readme.getRange("D5:N8").merge();
readme.getRange("D5").values = [[
  "去重后完整模型只有 66 和 78 行，而模型含 17 个参数。顺序 deviance、系数与 p 值用于敏感性比较，不是独立验证，也不是论文 Figure 6 的精确复现。"
]];
readme.getRange("D5:N8").format = {
  fill: colors.paleAmber,
  font: { bold: true, color: "#7F6000", size: 10 },
  wrapText: true,
  verticalAlignment: "center",
};
readme.getRange("D9:N13").merge();
readme.getRange("D9").values = [[
  "代表行排序：人工审核且模型字段完整 > 模型字段完整 > 仅人工审核 > 其他；同层级按 ADA 频率最接近组内中位数、患者数更大、来源行号更小。"
]];
readme.getRange("D9:N13").format = {
  fill: colors.paleGreen,
  font: { color: colors.dark, size: 10 },
  wrapText: true,
  verticalAlignment: "center",
};
readme.getRange("D:N").format.columnWidth = 13;
readme.freezePanes.freezeRows(2);

const scenarioSummary = writeRecordsSheet(
  "Scenario_Summary",
  "去重场景摘要 / Scenario summary",
  "rows_removed_percent 与 high_ada_selected_percent 为比例；两个场景从同一 2,666 行候选集独立生成。",
  payload.tables.Scenario_Summary,
  "ScenarioSummaryTable",
  { freezeColumns: 2, headerFill: colors.teal },
);
setColumnWidth(scenarioSummary, "scenario_id", 42);
setColumnWidth(scenarioSummary, "group_definition", 54);
setColumnWidth(scenarioSummary, "selection_rule", 85);
setNumberFormat(scenarioSummary, ["rows_removed_percent", "high_ada_selected_percent"], "0.0%");
wrapColumns(scenarioSummary, ["group_definition", "selection_rule"], 46);

const selectionRules = writeRecordsSheet(
  "Selection_Rules",
  "代表行选择规则 / Representative-row rules",
  "每个分组只保留 selection_rank_within_group = 1 的真实来源行；完整审计表另存为 artifacts/selection_audit_*.csv。",
  payload.tables.Selection_Rules,
  "SelectionRulesTable",
  { freezeColumns: 1, headerFill: colors.teal },
);
setColumnWidth(selectionRules, "rule", 82);
setColumnWidth(selectionRules, "scenario_1", 48);
setColumnWidth(selectionRules, "scenario_2", 54);
setColumnWidth(selectionRules, "purpose", 68);
wrapColumns(selectionRules, ["rule", "scenario_1", "scenario_2", "purpose"], 52);

function formatDataSheet(context) {
  context.sheet.getRange(`A:${context.endColumn}`).format.columnWidth = 18;
  setColumnWidth(context, "scenario_id", 38);
  setColumnWidth(context, "molecule_key", 30);
  setColumnWidth(context, "disease_category_key", 34);
  setColumnWidth(context, "Molecule Assessed for ADA INN Name", 34);
  setColumnWidth(context, "Disease Indication Category", 34);
  setColumnWidth(context, "Disease Indication Description", 54);
  setColumnWidth(context, "replication_row_key", 42);
  setColumnWidth(context, "selection_tier_description", 46);
  setColumnWidth(context, "dose_proxy_assumption", 58);
  setColumnWidth(context, "interval_parse_rule", 52);
  setNumberFormat(context, ["group_ada_median", "group_ada_min", "group_ada_max", "ada_distance_from_group_median", "ada_frequency_percent", "sequence_length_proxy", "dose_interval_days_proxy", "dose_level_proxy"], "0.000");
}

const dataMolecule = writeRecordsSheet(
  "Data_Molecule",
  "数据表 1：每种药物分子仅保留一行",
  "分组键为标准化 INN 分子名；110 行、110 个唯一 molecule_key。",
  payload.tables.Data_Molecule,
  "DataMoleculeTable",
  { freezeColumns: 4, titleEndColumn: "N" },
);
formatDataSheet(dataMolecule);

const dataMolDisease = writeRecordsSheet(
  "Data_Mol_Disease",
  "数据表 2：每种药物在每个 disease_category 保留一行",
  "分组键为标准化 INN 分子名 + 原始 Disease Indication Category；146 行、146 个唯一组合。",
  payload.tables.Data_Molecule_Disease,
  "DataMolDiseaseTable",
  { freezeColumns: 5, titleEndColumn: "O" },
);
formatDataSheet(dataMolDisease);

const s6Comparison = writeRecordsSheet(
  "S6_Comparison",
  "论文、未去重代理与两种去重口径的顺序 deviance 对照",
  "Type-I sequential deviance 依赖变量进入顺序；p 值为卡方检验。去重结果只作为敏感性分析。",
  payload.tables.S6_Comparison,
  "S6ComparisonTable",
  { freezeColumns: 3, headerFill: colors.teal },
);
setColumnWidth(s6Comparison, "variable", 38);
setNumberFormat(s6Comparison, ["published_deviance", "all_public_rows_deviance", "one_per_molecule_deviance", "one_per_molecule_disease_category_deviance"], "0.000");
setNumberFormat(s6Comparison, ["published_p_value", "all_public_rows_p_value", "one_per_molecule_p_value", "one_per_molecule_disease_category_p_value"], "0.000E+00");

function formatDeviance(context) {
  setColumnWidth(context, "analysis_type", 42);
  setColumnWidth(context, "variable", 38);
  setColumnWidth(context, "formula_through_term", 92);
  setNumberFormat(context, ["deviance", "residual_deviance"], "0.000");
  setNumberFormat(context, ["p_value"], "0.000E+00");
  wrapColumns(context, ["formula_through_term"], 42);
}

const devianceMolecule = writeRecordsSheet("Deviance_Molecule", "顺序 deviance：每分子一行", "完整代理 GLM N=66；模型顺序与 paper_replication 代理分析一致。", payload.tables.Deviance_Molecule, "DevianceMoleculeTable", { freezeColumns: 3 });
formatDeviance(devianceMolecule);
const devianceMolDisease = writeRecordsSheet("Deviance_Mol_Disease", "顺序 deviance：每分子×疾病一行", "完整代理 GLM N=78；模型顺序与 paper_replication 代理分析一致。", payload.tables.Deviance_Molecule_Disease, "DevianceMolDiseaseTable", { freezeColumns: 3 });
formatDeviance(devianceMolDisease);

const fitSummary = writeRecordsSheet("Fit_Summary", "模型拟合摘要", "均为样本内代理 GLM 拟合摘要，不应作为交叉验证 performance。", payload.tables.Fit_Summary, "FitSummaryTable", { freezeColumns: 2, headerFill: colors.teal });
setColumnWidth(fitSummary, "scenario_id", 42);
setColumnWidth(fitSummary, "formula", 96);
setColumnWidth(fitSummary, "interpretation", 76);
setNumberFormat(fitSummary, ["high_ada_percent", "mcfadden_pseudo_r2"], "0.0%");
setNumberFormat(fitSummary, ["null_deviance", "residual_deviance", "deviance_explained", "aic"], "0.000");
wrapColumns(fitSummary, ["formula", "interpretation"], 50);

function formatCoefficients(context) {
  setColumnWidth(context, "scenario_id", 42);
  setColumnWidth(context, "term", 62);
  setNumberFormat(context, ["coefficient", "standard_error", "z_value", "odds_ratio", "odds_ratio_ci_low", "odds_ratio_ci_high"], "0.000");
  setNumberFormat(context, ["p_value"], "0.000E+00");
}
const coefMolecule = writeRecordsSheet("Coef_Molecule", "系数：每分子一行", "小样本、多参数；极端优势比可能反映分离或稀疏类别。", payload.tables.Coefficients_Molecule, "CoefMoleculeTable", { freezeColumns: 2 });
formatCoefficients(coefMolecule);
const coefMolDisease = writeRecordsSheet("Coef_Mol_Disease", "系数：每分子×疾病一行", "小样本、多参数；结合置信区间与稳健性结果解释。", payload.tables.Coefficients_Molecule_Disease, "CoefMolDiseaseTable", { freezeColumns: 2 });
formatCoefficients(coefMolDisease);

function formatOrder(context) {
  setColumnWidth(context, "variable", 38);
  setColumnWidth(context, "minimum_scenario", 72);
  setColumnWidth(context, "maximum_scenario", 72);
  setNumberFormat(context, ["proxy_paper_order_deviance", "minimum_deviance", "median_deviance", "maximum_deviance", "deviance_range", "range_to_paper_order_ratio"], "0.000");
}
const orderMolecule = writeRecordsSheet("OrderSens_Molecule", "顺序敏感性：每分子一行", "比较 15 个变量进入顺序场景；范围越大，Type-I deviance 越依赖顺序。", payload.tables.Order_Sensitivity_Molecule, "OrderMoleculeTable", { freezeColumns: 2, headerFill: colors.teal });
formatOrder(orderMolecule);
const orderMolDisease = writeRecordsSheet("OrderSens_Mol_Disease", "顺序敏感性：每分子×疾病一行", "比较 15 个变量进入顺序场景；用于识别变量间共享解释量。", payload.tables.Order_Sensitivity_Molecule_Disease, "OrderMolDiseaseTable", { freezeColumns: 2, headerFill: colors.teal });
formatOrder(orderMolDisease);

function formatDropOne(context) {
  setColumnWidth(context, "variable", 38);
  setColumnWidth(context, "interpretation", 76);
  setNumberFormat(context, ["conditional_deviance", "full_model_residual_deviance"], "0.000");
  setNumberFormat(context, ["p_value"], "0.000E+00");
  wrapColumns(context, ["interpretation"], 42);
}
const dropMolecule = writeRecordsSheet("DropOne_Molecule", "条件贡献：每分子一行", "Drop-one LRT 在完整模型中删除单一变量，较少受进入顺序影响。", payload.tables.Drop_One_Molecule, "DropMoleculeTable", { freezeColumns: 2 });
formatDropOne(dropMolecule);
const dropMolDisease = writeRecordsSheet("DropOne_Mol_Disease", "条件贡献：每分子×疾病一行", "与顺序 deviance 对照，判断显著性是否主要来自变量顺序。", payload.tables.Drop_One_Molecule_Disease, "DropMolDiseaseTable", { freezeColumns: 2 });
formatDropOne(dropMolDisease);

const outcomeBalance = writeRecordsSheet("Outcome_Balance", "ADA 结局分布", "high_ada 定义为 ADA frequency >=10%；同时列出已选全表和完整模型子集。", payload.tables.Outcome_Balance, "OutcomeBalanceTable", { freezeColumns: 2, headerFill: colors.teal });
setColumnWidth(outcomeBalance, "stage", 44);
setColumnWidth(outcomeBalance, "scenario_id", 42);
setNumberFormat(outcomeBalance, ["percent_of_stage"], "0.0%");

// Formula-linked chart helper: all plotted series are linked to the comparison table.
readme.getRange("P3:T3").values = [["Variable", "Published", "All public rows", "One/molecule", "One/molecule×disease"]];
styleHeader(readme.getRange("P3:T3"));
for (let i = 0; i < payload.tables.S6_Comparison.length; i += 1) {
  const row = i + 4;
  readme.getRange(`P${row}:T${row}`).formulas = [[
    `='S6_Comparison'!C${row}`,
    `='S6_Comparison'!D${row}`,
    `='S6_Comparison'!F${row}`,
    `='S6_Comparison'!I${row}`,
    `='S6_Comparison'!L${row}`,
  ]];
}
readme.getRange("Q4:T11").format.numberFormat = "0.000";
const chart = readme.charts.add("bar", readme.getRange("P3:T11"));
chart.title = "Sequential deviance across analysis definitions";
chart.hasLegend = true;
chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
chart.yAxis = { numberFormatCode: "0.0" };
chart.setPosition("D15", "N34");

const finalResidDfMolecule = payload.tables.Deviance_Molecule.find((row) => row.model_order === 8)?.residual_df;
const finalResidDfMolDisease = payload.tables.Deviance_Molecule_Disease.find((row) => row.model_order === 8)?.residual_df;
const moleculeDuplicates = payload.tables.Data_Molecule.length - new Set(payload.tables.Data_Molecule.map((row) => row.molecule_key)).size;
const molDiseaseDuplicates = payload.tables.Data_Molecule_Disease.length - new Set(payload.tables.Data_Molecule_Disease.map((row) => `${row.molecule_key}\u0000${row.disease_category_key}`)).size;
const qcRows = [
  { check: "Original paper_replication untouched", expected: true, observed: payload.metadata.original_results_untouched, result: payload.metadata.original_results_untouched ? "PASS" : "FAIL" },
  { check: "Source candidate rows", expected: 2666, observed: payload.metadata.source_candidate_rows, result: payload.metadata.source_candidate_rows === 2666 ? "PASS" : "FAIL" },
  { check: "Scenario 1 selected rows", expected: 110, observed: payload.tables.Data_Molecule.length, result: payload.tables.Data_Molecule.length === 110 ? "PASS" : "FAIL" },
  { check: "Scenario 1 duplicate molecule keys", expected: 0, observed: moleculeDuplicates, result: moleculeDuplicates === 0 ? "PASS" : "FAIL" },
  { check: "Scenario 2 selected rows", expected: 146, observed: payload.tables.Data_Molecule_Disease.length, result: payload.tables.Data_Molecule_Disease.length === 146 ? "PASS" : "FAIL" },
  { check: "Scenario 2 duplicate molecule+disease keys", expected: 0, observed: molDiseaseDuplicates, result: molDiseaseDuplicates === 0 ? "PASS" : "FAIL" },
  { check: "Scenario 1 complete-case N", expected: 66, observed: payload.metadata.scenario_1_model_n, result: payload.metadata.scenario_1_model_n === 66 ? "PASS" : "FAIL" },
  { check: "Scenario 2 complete-case N", expected: 78, observed: payload.metadata.scenario_2_model_n, result: payload.metadata.scenario_2_model_n === 78 ? "PASS" : "FAIL" },
  { check: "Scenario 1 sequential terms", expected: 8, observed: payload.tables.Deviance_Molecule.length, result: payload.tables.Deviance_Molecule.length === 8 ? "PASS" : "FAIL" },
  { check: "Scenario 2 sequential terms", expected: 8, observed: payload.tables.Deviance_Molecule_Disease.length, result: payload.tables.Deviance_Molecule_Disease.length === 8 ? "PASS" : "FAIL" },
  { check: "Scenario 1 final residual df", expected: 49, observed: finalResidDfMolecule, result: finalResidDfMolecule === 49 ? "PASS" : "FAIL" },
  { check: "Scenario 2 final residual df", expected: 61, observed: finalResidDfMolDisease, result: finalResidDfMolDisease === 61 ? "PASS" : "FAIL" },
];
const qc = writeRecordsSheet("QC", "质量控制 / Quality control", "PASS 表示机械一致性检查通过；生物医学解释仍受小样本、代理变量和代表行规则限制。", qcRows, "DedupQCTable", { headerFill: colors.teal });
setColumnWidth(qc, "check", 52);
setColumnWidth(qc, "expected", 42);
setColumnWidth(qc, "observed", 42);
setColumnWidth(qc, "result", 18);

const sheetNames = [
  "README", "Scenario_Summary", "Selection_Rules", "Data_Molecule", "Data_Mol_Disease",
  "S6_Comparison", "Deviance_Molecule", "Deviance_Mol_Disease", "Fit_Summary",
  "Coef_Molecule", "Coef_Mol_Disease", "OrderSens_Molecule", "OrderSens_Mol_Disease",
  "DropOne_Molecule", "DropOne_Mol_Disease", "Outcome_Balance", "QC",
];
for (const sheetName of sheetNames) {
  wb.worksheets.getItem(sheetName).getUsedRange().format.font.name = "Aptos";
}

const keyInspect = await wb.inspect({
  kind: "region",
  sheetId: "README",
  range: "A1:N34",
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
  ["README", "A1:N34"],
  ["Scenario_Summary", `A1:${scenarioSummary.endColumn}${scenarioSummary.rows.length + 3}`],
  ["Selection_Rules", `A1:${selectionRules.endColumn}${selectionRules.rows.length + 3}`],
  ["Data_Molecule", "A1:N30"],
  ["Data_Mol_Disease", "A1:O30"],
  ["S6_Comparison", `A1:${s6Comparison.endColumn}${s6Comparison.rows.length + 3}`],
  ["Deviance_Molecule", `A1:${devianceMolecule.endColumn}${devianceMolecule.rows.length + 3}`],
  ["Deviance_Mol_Disease", `A1:${devianceMolDisease.endColumn}${devianceMolDisease.rows.length + 3}`],
  ["Fit_Summary", `A1:${fitSummary.endColumn}${fitSummary.rows.length + 3}`],
  ["Coef_Molecule", `A1:${coefMolecule.endColumn}${coefMolecule.rows.length + 3}`],
  ["Coef_Mol_Disease", `A1:${coefMolDisease.endColumn}${coefMolDisease.rows.length + 3}`],
  ["OrderSens_Molecule", `A1:${orderMolecule.endColumn}${orderMolecule.rows.length + 3}`],
  ["OrderSens_Mol_Disease", `A1:${orderMolDisease.endColumn}${orderMolDisease.rows.length + 3}`],
  ["DropOne_Molecule", `A1:${dropMolecule.endColumn}${dropMolecule.rows.length + 3}`],
  ["DropOne_Mol_Disease", `A1:${dropMolDisease.endColumn}${dropMolDisease.rows.length + 3}`],
  ["Outcome_Balance", `A1:${outcomeBalance.endColumn}${outcomeBalance.rows.length + 3}`],
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
