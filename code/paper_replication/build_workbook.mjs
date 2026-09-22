import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const artifactDir = path.join(root, "outputs", "paper_replication", "artifacts");
const outputDir = path.join(root, "outputs", "paper_replication");
const previewDir = path.join(outputDir, "previews");
const payload = JSON.parse(await fs.readFile(path.join(artifactDir, "workbook_payload.json"), "utf8"));
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const outputPath = path.join(outputDir, "IDC_paper_replication_results.xlsx");
const wb = Workbook.create();

const colors = {
  navy: "#17365D",
  blue: "#1F4E78",
  teal: "#0F766E",
  white: "#FFFFFF",
  paleBlue: "#D9EAF7",
  paleGreen: "#E2F0D9",
  paleAmber: "#FFF2CC",
  paleRed: "#FCE8E6",
  gray: "#F3F4F6",
  line: "#D9E2F3",
  dark: "#1F2937",
  muted: "#475569",
  orange: "#D97706",
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
  range.format.rowHeight = 32;
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
  range.format.rowHeight = 34;
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
  titleBand(sheet, title, endColumn);
  noteBand(sheet, note, endColumn);
  sheet.getRangeByIndexes(2, 0, 1, headers.length).values = [headers];
  styleHeader(sheet.getRangeByIndexes(2, 0, 1, headers.length), options.headerFill ?? colors.blue);
  if (rows.length) {
    sheet.getRangeByIndexes(3, 0, rows.length, headers.length).values = rows;
    styleBody(sheet.getRangeByIndexes(3, 0, rows.length, headers.length));
    sheet.tables.add(
      sheet.getRangeByIndexes(2, 0, rows.length + 1, headers.length),
      true,
      tableName,
    ).style = options.tableStyle ?? "TableStyleMedium2";
  }
  sheet.freezePanes.freezeRows(3);
  if (options.freezeColumns) sheet.freezePanes.freezeColumns(options.freezeColumns);
  sheet.showGridLines = false;
  sheet.getRange(`A1:${endColumn}${Math.max(rows.length + 3, 3)}`).format.font.name = "Aptos";
  return { sheet, headers, rows, endColumn };
}

function setColumnWidth(context, header, width) {
  const index = context.headers.indexOf(header);
  if (index >= 0) context.sheet.getRange(`${columnName(index + 1)}:${columnName(index + 1)}`).format.columnWidth = width;
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

const readme = wb.worksheets.add("README");
readme.showGridLines = false;
titleBand(readme, "IDC Paper Replication — Figure 6 / Table S6", "N");
noteBand(readme, "Independent workflow. Published results, strict-replication status, and public-data proxy results are separated throughout this workbook.", "N");
readme.getRange("A4:B11").values = [
  ["Run status", "Value"],
  ["Strict replication", payload.metadata.exact_status],
  ["Public-data proxy", payload.metadata.proxy_status],
  ["Published complete cases", payload.metadata.paper_expected_complete_cases],
  ["Proxy complete cases", payload.metadata.proxy_complete_cases],
  ["Raw ADA-frequency rows", payload.metadata.raw_clinical_rows],
  ["Exposed + outcome candidate rows", payload.metadata.candidate_rows],
  ["Frozen GitHub commit", payload.metadata.github_commit],
];
styleHeader(readme.getRange("A4:B4"));
styleBody(readme.getRange("A5:B11"));
readme.getRange("A5:A11").format = { fill: colors.paleBlue, font: { bold: true, color: colors.navy } };
readme.getRange("A:A").format.columnWidth = 30;
readme.getRange("B:B").format.columnWidth = 76;
readme.getRange("D4:N4").merge();
readme.getRange("D4").values = [["Interpretation guardrail"]];
styleHeader(readme.getRange("D4:N4"), colors.teal);
readme.getRange("D5:N8").merge();
readme.getRange("D5").values = [[
  "The published Figure 6 quantity is sequential (Type-I) deviance contribution from a logistic regression. It is not random-forest/TabPFN feature importance. The public-data proxy is diagnostic only because the author-derived epitope counts and row-level category mappings are not public."
]];
readme.getRange("D5:N8").format = {
  fill: colors.paleAmber,
  font: { bold: true, color: "#7F6000", size: 10 },
  wrapText: true,
  verticalAlignment: "center",
};
readme.getRange("D9:N11").merge();
readme.getRange("D9").values = [[
  "Strict next step: complete Manual_Review with author-derived values, save it as paper_replication/data/manual/paper_derived_variables.csv, then run the project-local .venv with --mode exact."
]];
readme.getRange("D9:N11").format = {
  fill: colors.paleGreen,
  font: { color: colors.dark, size: 10 },
  wrapText: true,
  verticalAlignment: "center",
};
readme.getRange("D:N").format.columnWidth = 13;

const sourceManifest = writeRecordsSheet(
  "Source_Manifest",
  "Frozen source manifest",
  "Hashes identify the exact local inputs used by this run. The user-provided original is the all-tables extraction source; Frontiers and GitHub copies are retained for value-level cross-checks.",
  payload.tables.Source_Manifest,
  "SourceManifestTable",
  { freezeColumns: 2 },
);
sourceManifest.sheet.getRange(`A:${sourceManifest.endColumn}`).format.columnWidth = 18;
setColumnWidth(sourceManifest, "source_role", 42);
setColumnWidth(sourceManifest, "path", 76);
setColumnWidth(sourceManifest, "sha256", 72);
setColumnWidth(sourceManifest, "origin_url", 78);
setColumnWidth(sourceManifest, "github_commit_if_applicable", 46);

const sourceComparison = writeRecordsSheet(
  "Source_Comparison",
  "User original versus author and Frontiers workbooks",
  "Binary equality checks the complete .xlsx container. Cell-value equality compares every populated cell in all six sheets using artifact-tool; zero differing cells means the data values are identical.",
  payload.tables.Source_Comparison,
  "SourceComparisonTable",
  { freezeColumns: 4, headerFill: colors.teal },
);
sourceComparison.sheet.getRange(`A:${sourceComparison.endColumn}`).format.columnWidth = 21;
setColumnWidth(sourceComparison, "comparator_id", 30);
setColumnWidth(sourceComparison, "sheet", 28);
setColumnWidth(sourceComparison, "user_value_sha256", 72);
setColumnWidth(sourceComparison, "comparator_value_sha256", 72);

const availability = writeRecordsSheet(
  "Source_Availability",
  "Exact-field availability audit",
  "FALSE means the public release does not contain the exact author-derived value or unique derivation rule required for Table S6.",
  payload.tables.Source_Availability,
  "SourceAvailabilityTable",
  { freezeColumns: 2, headerFill: colors.teal },
);
availability.sheet.getRange(`A:${availability.endColumn}`).format.columnWidth = 30;
setColumnWidth(availability, "public_source", 55);
setColumnWidth(availability, "implemented_public_proxy", 52);
setColumnWidth(availability, "strict_replication_requirement", 72);
availability.sheet.getRange(`A4:${availability.endColumn}${availability.rows.length + 3}`).format.wrapText = true;
availability.sheet.getRange(`A4:${availability.endColumn}${availability.rows.length + 3}`).format.rowHeight = 44;

const methodContractRows = [
  { item: "Outcome", implementation: "ADA frequency <10% vs >=10%", evidence: "Methods §2.4 / Figure 6", status: "LOCKED" },
  { item: "Population", implementation: "Therapeutic Exposed; complete cases across all eight factors", evidence: "Figure 1 + Table S6 residual df", status: "LOCKED / exact row list unavailable" },
  { item: "Complete-case N", implementation: "1,216 inferred", evidence: "First residual df 1,214 after intercept + 1-df epitope term", status: "INFERRED" },
  { item: "Model", implementation: "Binomial logistic GLM", evidence: "Methods §2.4", status: "LOCKED" },
  { item: "Contribution", implementation: "Sequential reduction in deviance; chi-square p-value", evidence: "Methods + Table S6", status: "LOCKED" },
  { item: "Formula order", implementation: "Epitope → disease → therapeutic MOA → comedication → dose → interval → year → route", evidence: "Residual-df sequence", status: "INFERRED" },
  { item: "Display order", implementation: "Sorted by deviance", evidence: "Figure 6 / Table S6", status: "LOCKED" },
  { item: "Strict input gate", implementation: "paper_replication/data/manual/paper_derived_variables.csv", evidence: "Local reproducibility contract", status: "REQUIRED" },
];
const methodContract = writeRecordsSheet(
  "Method_Contract",
  "Paper method contract",
  "Items marked INFERRED follow uniquely from the published residual degrees of freedom but remain unconfirmed without author code.",
  methodContractRows,
  "MethodContractTable",
  { headerFill: colors.teal },
);
methodContract.sheet.getRange("A:D").format.columnWidth = 28;
setColumnWidth(methodContract, "implementation", 78);
setColumnWidth(methodContract, "evidence", 48);
setColumnWidth(methodContract, "status", 35);
methodContract.sheet.getRange(`A4:D${methodContract.rows.length + 3}`).format.wrapText = true;
methodContract.sheet.getRange(`A4:D${methodContract.rows.length + 3}`).format.rowHeight = 38;

const funnel = writeRecordsSheet(
  "Sample_Funnel",
  "Analytic sample funnel",
  "The proxy reaches a near-sized but non-identical complete-case cohort; matching N alone would not establish exact replication.",
  payload.tables.Sample_Funnel,
  "SampleFunnelTable",
  { headerFill: colors.teal },
);
funnel.sheet.getRange("A:D").format.columnWidth = 34;
funnel.sheet.getRange("A:A").format.columnWidth = 10;
setColumnWidth(funnel, "note", 62);

const published = writeRecordsSheet(
  "Published_S6",
  "Published Supplementary Table S6",
  "Values transcribed from Frontiers Data Sheet 1; verified unchanged from the user-provided bioRxiv PDF.",
  payload.tables.Paper_Table_S6,
  "PublishedS6Table",
  { headerFill: colors.navy },
);
published.sheet.getRange(`A:${published.endColumn}`).format.columnWidth = 20;
setColumnWidth(published, "variable", 40);
setNumberFormat(published, ["deviance", "residual_deviance"], "0.000000");
setNumberFormat(published, ["p_value"], "0.00E+00");

const proxy = writeRecordsSheet(
  "Proxy_S6",
  "Public-data proxy sequential deviance",
  "Diagnostic only: sequence length replaces epitope count and deterministic text mappings replace unpublished author-derived labels.",
  payload.tables.Proxy_Table_S6,
  "ProxyS6Table",
  { headerFill: colors.orange },
);
proxy.sheet.getRange(`A:${proxy.endColumn}`).format.columnWidth = 20;
setColumnWidth(proxy, "variable", 40);
setColumnWidth(proxy, "formula_through_term", 88);
setNumberFormat(proxy, ["deviance", "residual_deviance"], "0.000000");
setNumberFormat(proxy, ["p_value"], "0.00E+00");

const comparison = writeRecordsSheet(
  "S6_Comparison",
  "Published vs public-data proxy",
  "Numerical differences identify missing derivation fidelity; they are not evidence that the publication is wrong.",
  payload.tables.S6_Comparison,
  "S6ComparisonTable",
  { headerFill: colors.orange },
);
comparison.sheet.getRange(`A:${comparison.endColumn}`).format.columnWidth = 19;
setColumnWidth(comparison, "variable", 40);
setColumnWidth(comparison, "interpretation", 78);
setNumberFormat(comparison, ["deviance", "residual_deviance", "proxy_deviance", "proxy_residual_deviance", "proxy_minus_paper_deviance"], "0.000000");
setNumberFormat(comparison, ["p_value", "proxy_p_value"], "0.00E+00");

const categories = writeRecordsSheet(
  "Category_Levels",
  "Proxy category-level audit",
  "Counts are shown before and after proxy complete-case filtering; rare levels make exact author mapping especially important.",
  payload.tables.Category_Levels,
  "CategoryLevelsTable",
  { headerFill: colors.teal },
);
categories.sheet.getRange("A:D").format.columnWidth = 30;
setColumnWidth(categories, "variable", 40);

const robustness = writeRecordsSheet(
  "Robustness_Comparison",
  "Published, sequential-proxy, and conditional-proxy deviance",
  "The conditional proxy is a drop-one likelihood-ratio test on the same fixed cohort. It removes entry-order dependence but does not replace missing author-derived variables.",
  payload.tables.Robustness_Comparison,
  "RobustnessComparisonTable",
  { headerFill: colors.teal },
);
robustness.sheet.getRange(`A:${robustness.endColumn}`).format.columnWidth = 21;
setColumnWidth(robustness, "variable", 40);
setNumberFormat(robustness, [
  "published_sequential_deviance",
  "proxy_sequential_deviance",
  "proxy_conditional_deviance",
  "minimum_deviance",
  "maximum_deviance",
  "deviance_range",
  "range_to_paper_order_ratio",
], "0.000000");
const robustnessChart = robustness.sheet.charts.add(
  "bar",
  robustness.sheet.getRange(`A3:D${robustness.rows.length + 3}`),
);
robustnessChart.title = "Deviance comparison: published and proxy diagnostics";
robustnessChart.hasLegend = true;
robustnessChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
robustnessChart.yAxis = { numberFormatCode: "0.0" };
robustnessChart.setPosition("A14", "H31");

const orderSensitivity = writeRecordsSheet(
  "Order_Sensitivity",
  "Type-I deviance order-sensitivity summary",
  "Each term is placed first and last while all other terms retain their paper-inferred relative order. A wide range means the sequential contribution is strongly order-dependent.",
  payload.tables.Order_Sensitivity,
  "OrderSensitivityTable",
  { headerFill: colors.orange },
);
orderSensitivity.sheet.getRange(`A:${orderSensitivity.endColumn}`).format.columnWidth = 22;
setColumnWidth(orderSensitivity, "variable", 40);
setColumnWidth(orderSensitivity, "minimum_scenario", 28);
setColumnWidth(orderSensitivity, "maximum_scenario", 28);
setNumberFormat(orderSensitivity, [
  "proxy_paper_order_deviance",
  "minimum_deviance",
  "median_deviance",
  "maximum_deviance",
  "deviance_range",
  "range_to_paper_order_ratio",
], "0.000000");

const orderScenarios = writeRecordsSheet(
  "Order_Scenarios",
  "Type-I deviance scenario-level audit",
  "Full deterministic scenario output. Use scenario_id and scenario_order to trace every summary minimum and maximum.",
  payload.tables.Order_Scenarios,
  "OrderScenariosTable",
  { freezeColumns: 3, headerFill: colors.orange },
);
orderScenarios.sheet.getRange(`A:${orderScenarios.endColumn}`).format.columnWidth = 20;
setColumnWidth(orderScenarios, "scenario_order", 115);
setColumnWidth(orderScenarios, "variable", 40);
setColumnWidth(orderScenarios, "formula_through_term", 88);
setNumberFormat(orderScenarios, ["deviance", "residual_deviance"], "0.000000");
setNumberFormat(orderScenarios, ["p_value"], "0.00E+00");

const dropOne = writeRecordsSheet(
  "Drop_One_LRT",
  "Conditional drop-one likelihood-ratio tests",
  "Every test compares the complete proxy model with a model omitting one term. This is order-independent but remains dependent on proxy definitions and the proxy complete-case cohort.",
  payload.tables.Drop_One_LRT,
  "DropOneLRTTable",
  { headerFill: colors.teal },
);
dropOne.sheet.getRange(`A:${dropOne.endColumn}`).format.columnWidth = 22;
setColumnWidth(dropOne, "variable", 40);
setColumnWidth(dropOne, "interpretation", 82);
setNumberFormat(dropOne, ["conditional_deviance", "full_model_residual_deviance"], "0.000000");
setNumberFormat(dropOne, ["p_value"], "0.00E+00");

const proxyMissingness = writeRecordsSheet(
  "Proxy_Missingness",
  "Proxy-field completeness audit",
  "Missingness is calculated in the exposed + non-missing ADA outcome candidate set. The final row is the complete-case intersection used by the proxy model.",
  payload.tables.Proxy_Missingness,
  "ProxyMissingnessTable",
  { headerFill: colors.teal },
);
proxyMissingness.sheet.getRange(`A:${proxyMissingness.endColumn}`).format.columnWidth = 24;
setColumnWidth(proxyMissingness, "variable", 42);
setColumnWidth(proxyMissingness, "proxy_field", 40);
setNumberFormat(proxyMissingness, ["missing_percent"], "0.0%");

const outcomeBalance = writeRecordsSheet(
  "Outcome_Balance",
  "ADA outcome balance before and after complete-case filtering",
  "The comparison exposes selection shifts introduced by requiring all eight proxy-model fields.",
  payload.tables.Outcome_Balance,
  "OutcomeBalanceTable",
  { headerFill: colors.teal },
);
outcomeBalance.sheet.getRange(`A:${outcomeBalance.endColumn}`).format.columnWidth = 25;
setColumnWidth(outcomeBalance, "stage", 42);
setColumnWidth(outcomeBalance, "outcome", 30);
setNumberFormat(outcomeBalance, ["percent_of_stage"], "0.0%");

const duplicateAudit = writeRecordsSheet(
  "Duplicate_ID_Audit",
  "Repeated public IDC row-identifier audit",
  "These rows share a source IDC Row identifier but have unique replication_row_key values. They are retained and surfaced for provenance review; no silent deletion is performed.",
  payload.tables.Duplicate_ID_Audit,
  "DuplicateIDAuditTable",
  { freezeColumns: 3, headerFill: colors.orange },
);
duplicateAudit.sheet.getRange(`A:${duplicateAudit.endColumn}`).format.columnWidth = 19;
setColumnWidth(duplicateAudit, "Molecule Assessed for ADA INN Name", 34);
setColumnWidth(duplicateAudit, "Disease Indication Description", 48);
setColumnWidth(duplicateAudit, "Dosing Description", 48);
setColumnWidth(duplicateAudit, "Therapeutic Dosing Schedule Description", 48);

const manualReview = writeRecordsSheet(
  "Manual_Review",
  "Strict-replication derived-variable template",
  "Do not approve proxy values as author-derived. Replace with author outputs, set review_status, record mapping_source/reviewer, and export as paper_replication/data/manual/paper_derived_variables.csv.",
  payload.tables.Manual_Review,
  "ManualReviewTable",
  { freezeColumns: 2, headerFill: colors.orange },
);
manualReview.sheet.getRange(`A:${manualReview.endColumn}`).format.columnWidth = 18;
for (const header of ["Mechanism of Action", "Disease Indication Description", "Co-administered drugs", "Dosing Description", "Therapeutic Dosing Schedule Description"]) {
  setColumnWidth(manualReview, header, 55);
}
setColumnWidth(manualReview, "mapping_source", 58);
setColumnWidth(manualReview, "review_status", 28);

const candidate = writeRecordsSheet(
  "Analytic_Candidate",
  "Public-data proxy analytic candidate",
  "One row per exposed ADA-frequency datapoint. All substituted fields retain a proxy suffix or parse-assumption field.",
  payload.tables.Analytic_Candidate,
  "AnalyticCandidateTable",
  { freezeColumns: 5 },
);
candidate.sheet.getRange(`A:${candidate.endColumn}`).format.columnWidth = 19;
setColumnWidth(candidate, "Molecule Assessed for ADA INN Name", 34);
setColumnWidth(candidate, "dose_proxy_assumption", 48);
setColumnWidth(candidate, "interval_parse_rule", 45);
setNumberFormat(candidate, ["ada_frequency_percent", "sequence_length_proxy", "dose_interval_days_proxy", "dose_level_proxy", "trial_year_completed"], "0.000");

// Formula-linked helper table and chart on README.
readme.getRange("O3:Q3").values = [["Variable", "Published deviance", "Proxy deviance"]];
styleHeader(readme.getRange("O3:Q3"));
const publishedRowByVariable = new Map(payload.tables.Paper_Table_S6.map((row, index) => [row.variable, index + 4]));
const proxyRowByVariable = new Map(payload.tables.Proxy_Table_S6.map((row, index) => [row.variable, index + 4]));
payload.tables.Paper_Table_S6.forEach((record, index) => {
  const row = index + 4;
  readme.getRange(`O${row}:Q${row}`).formulas = [[
    `='Published_S6'!C${publishedRowByVariable.get(record.variable)}`,
    `='Published_S6'!E${publishedRowByVariable.get(record.variable)}`,
    `='Proxy_S6'!E${proxyRowByVariable.get(record.variable)}`,
  ]];
});
readme.getRange("P4:Q11").format.numberFormat = "0.000";
const chart = readme.charts.add("bar", readme.getRange("O3:Q11"));
chart.title = "Published Table S6 vs public-data proxy";
chart.hasLegend = true;
chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
chart.yAxis = { numberFormatCode: "0.0" };
chart.setPosition("D13", "N31");
readme.getRange("A13:B22").values = [
  ["Key QC", "Result"],
  ["Published final residual df", payload.tables.Paper_Table_S6.find((row) => row.variable === "Route of Administration").residual_df],
  ["Expected published final residual df", 1199],
  ["Proxy final residual df", payload.tables.Proxy_Table_S6.find((row) => row.variable === "Route of Administration").residual_df],
  ["Duplicate replication_row_key values", payload.tables.Manual_Review.length - new Set(payload.tables.Manual_Review.map((row) => row.replication_row_key)).size],
  ["Duplicated source IDC row-ID rows", payload.metadata.candidate_duplicate_idc_row_identifier_rows],
  ["Order-sensitivity scenarios", payload.metadata.order_sensitivity_scenarios],
  ["Drop-one full-model residual df", payload.metadata.drop_one_full_model_residual_df],
  ["User source = GitHub binary", payload.metadata.user_source_binary_matches_author_github],
  ["User source = Frontiers cell values", payload.metadata.user_source_values_match_frontiers],
];
styleHeader(readme.getRange("A13:B13"), colors.teal);
styleBody(readme.getRange("A14:B22"));
readme.getRange("A14:A22").format = { fill: colors.paleBlue, font: { bold: true, color: colors.navy } };
readme.freezePanes.freezeRows(2);

const qcRows = [
  { check: "Raw clinical row count", expected: 3334, observed: payload.metadata.raw_clinical_rows, result: payload.metadata.raw_clinical_rows === 3334 ? "PASS" : "FAIL" },
  { check: "Published complete-case N", expected: 1216, observed: payload.metadata.paper_expected_complete_cases, result: payload.metadata.paper_expected_complete_cases === 1216 ? "PASS" : "FAIL" },
  { check: "Published final residual df", expected: 1199, observed: payload.tables.Paper_Table_S6.find((row) => row.variable === "Route of Administration").residual_df, result: payload.tables.Paper_Table_S6.find((row) => row.variable === "Route of Administration").residual_df === 1199 ? "PASS" : "FAIL" },
  { check: "Manual-review replication key uniqueness", expected: 0, observed: payload.tables.Manual_Review.length - new Set(payload.tables.Manual_Review.map((row) => row.replication_row_key)).size, result: payload.tables.Manual_Review.length === new Set(payload.tables.Manual_Review.map((row) => row.replication_row_key)).size ? "PASS" : "FAIL" },
  { check: "Duplicated public IDC row-ID rows", expected: "Source issue audited; no silent deletion", observed: payload.metadata.candidate_duplicate_idc_row_identifier_rows, result: payload.metadata.candidate_duplicate_idc_row_identifier_rows > 0 ? "WARN" : "PASS" },
  { check: "Order-sensitivity scenario count", expected: 15, observed: payload.metadata.order_sensitivity_scenarios, result: payload.metadata.order_sensitivity_scenarios === 15 ? "PASS" : "FAIL" },
  { check: "Drop-one/full-model residual df", expected: payload.tables.Proxy_Table_S6.find((row) => row.variable === "Route of Administration").residual_df, observed: payload.metadata.drop_one_full_model_residual_df, result: payload.metadata.drop_one_full_model_residual_df === payload.tables.Proxy_Table_S6.find((row) => row.variable === "Route of Administration").residual_df ? "PASS" : "FAIL" },
  { check: "User source vs author GitHub binary", expected: true, observed: payload.metadata.user_source_binary_matches_author_github, result: payload.metadata.user_source_binary_matches_author_github ? "PASS" : "FAIL" },
  { check: "User source vs Frontiers cell values", expected: true, observed: payload.metadata.user_source_values_match_frontiers, result: payload.metadata.user_source_values_match_frontiers ? "PASS" : "FAIL" },
  { check: "Strict replication status", expected: "Author-derived fields required", observed: payload.metadata.exact_status, result: payload.metadata.exact_status === "BLOCKED_EXACT_SOURCE_FIELDS" ? "EXPECTED BLOCK" : "CHECK" },
  { check: "Proxy result labeling", expected: "COMPLETED_PUBLIC_DATA_PROXY", observed: payload.metadata.proxy_status, result: payload.metadata.proxy_status === "COMPLETED_PUBLIC_DATA_PROXY" ? "PASS" : "FAIL" },
];
const qc = writeRecordsSheet(
  "QC",
  "Replication workflow quality control",
  "PASS verifies mechanical consistency. EXPECTED BLOCK is a provenance safeguard, not a pipeline failure.",
  qcRows,
  "QCTable",
  { headerFill: colors.teal },
);
qc.sheet.getRange("A:D").format.columnWidth = 34;
setColumnWidth(qc, "check", 42);
setColumnWidth(qc, "expected", 46);
setColumnWidth(qc, "observed", 58);

for (const sheetName of [
  "README", "Source_Manifest", "Source_Comparison", "Source_Availability", "Method_Contract", "Sample_Funnel",
  "Published_S6", "Proxy_S6", "S6_Comparison", "Category_Levels", "Robustness_Comparison",
  "Order_Sensitivity", "Order_Scenarios", "Drop_One_LRT", "Proxy_Missingness", "Outcome_Balance",
  "Duplicate_ID_Audit", "Manual_Review",
  "Analytic_Candidate", "QC",
]) {
  const sheet = wb.worksheets.getItem(sheetName);
  sheet.getUsedRange().format.font.name = "Aptos";
}

const keyInspect = await wb.inspect({
  kind: "region",
  sheetId: "README",
  range: "A1:N31",
  include: "values,formulas",
  maxChars: 10000,
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
  ["README", "A1:N31"],
  ["Source_Manifest", `A1:${sourceManifest.endColumn}${Math.min(sourceManifest.rows.length + 3, 18)}`],
  ["Source_Comparison", `A1:${sourceComparison.endColumn}${sourceComparison.rows.length + 3}`],
  ["Source_Availability", `A1:${availability.endColumn}${availability.rows.length + 3}`],
  ["Method_Contract", `A1:${methodContract.endColumn}${methodContract.rows.length + 3}`],
  ["Sample_Funnel", `A1:${funnel.endColumn}${funnel.rows.length + 3}`],
  ["Published_S6", `A1:${published.endColumn}${published.rows.length + 3}`],
  ["Proxy_S6", `A1:${proxy.endColumn}${proxy.rows.length + 3}`],
  ["S6_Comparison", `A1:${comparison.endColumn}${comparison.rows.length + 3}`],
  ["Category_Levels", `A1:${categories.endColumn}${categories.rows.length + 3}`],
  ["Robustness_Comparison", `A1:${robustness.endColumn}31`],
  ["Order_Sensitivity", `A1:${orderSensitivity.endColumn}${orderSensitivity.rows.length + 3}`],
  ["Order_Scenarios", `A1:${orderScenarios.endColumn}35`],
  ["Drop_One_LRT", `A1:${dropOne.endColumn}${dropOne.rows.length + 3}`],
  ["Proxy_Missingness", `A1:${proxyMissingness.endColumn}${proxyMissingness.rows.length + 3}`],
  ["Outcome_Balance", `A1:${outcomeBalance.endColumn}${outcomeBalance.rows.length + 3}`],
  ["Duplicate_ID_Audit", `A1:${duplicateAudit.endColumn}${duplicateAudit.rows.length + 3}`],
  ["Manual_Review", `A1:${manualReview.endColumn}35`],
  ["Analytic_Candidate", `A1:${candidate.endColumn}35`],
  ["QC", `A1:${qc.endColumn}${qc.rows.length + 3}`],
];
for (const [sheetName, range] of previewSpecs) {
  const preview = await wb.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(
    path.join(previewDir, `${sheetName}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
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
console.log((await imported.inspect({
  kind: "workbook,sheet,table",
  maxChars: 7000,
  tableMaxRows: 2,
  tableMaxCols: 5,
})).ndjson);
console.log(`OUTPUT=${outputPath}`);
