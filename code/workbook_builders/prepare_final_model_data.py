import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

INPUT = Path("../outputs/IDC_modeling_table_cleaned_annotated_corrected.xlsx")
OUT_DIR = Path("final_intermediates")
OUT_DIR.mkdir(exist_ok=True)

df = pd.read_excel(INPUT, sheet_name="Sheet1")
input_rows = len(df)
df["source_excel_row"] = np.arange(2, len(df) + 2)
df["idc_row_id_original"] = df["idc_row_id"]
df["trial_id_original"] = df["trial_id"]
df["external_source_id_original"] = df["external_source_id"]

# Source-observation fields end before pre-existing aggregate/derived group columns.
aggregate_start = list(df.columns).index("cohort_group_id")
source_observation_columns = list(df.columns[:aggregate_start])
duplicate_mask = df.duplicated(subset=source_observation_columns, keep="first")
excluded = df.loc[duplicate_mask].copy()
excluded["exclusion_reason"] = (
    "Duplicate source observation; redundant copy differed only through stale or cross-matched aggregate fields."
)
df = df.loc[~duplicate_mask].copy()

df["record_review_status"] = "Not individually reviewed"
df["record_review_note"] = pd.NA
df["record_dependency_note"] = pd.NA

def mark(mask, note):
    df.loc[mask, "record_review_status"] = "Approved"
    df.loc[mask, "record_review_note"] = note

# Correct incomplete source identifier for the Maini et al. infliximab dose/MTX study.
m = df["trial_id"].eq("CT0736")
df.loc[m, "external_source_id"] = "10.1002/1529-0131(199809)41:9<1552::AID-ART5>3.0.CO;2-W"
mark(m, "Six legitimate dose-by-methotrexate strata retained; source DOI completed and row IDs made unique.")

# Baert et al.: the concomitant treatment category included AZA, 6-MP, or MTX, not MTX alone.
m = df["trial_id"].eq("CT0737") & df["coadministered_drugs"].notna()
df.loc[m, "coadministered_drugs"] = "Immunosuppressive therapy"
mark(df["trial_id"].eq("CT0737"), "Two mutually exclusive immunosuppressive-therapy strata retained.")

# Bartelds et al.: both 12% (with MTX) and 38% (without MTX) are subgroups of the same primary cohort.
m = df["trial_id"].eq("CT0745") & df["coadministered_drugs"].notna()
df.loc[m, "external_source_id"] = "10.1136/ard.2006.065615"
df.loc[m, "coadministered_drugs"] = "Methotrexate"
mark(df["trial_id"].eq("CT0745"), "Two mutually exclusive methotrexate strata retained; primary-study DOI restored.")

# West et al.: one row carried CT0685 despite the source and row ID belonging to CT0751.
m = df["idc_row_id"].eq("CT0751_A1_001")
df.loc[m, "trial_id"] = "CT0751"
df.loc[m & df["coadministered_drugs"].notna(), "coadministered_drugs"] = "Immunomodulator therapy"
mark(m, "Trial ID harmonized to CT0751; two mutually exclusive immunomodulator strata retained.")

# CLASSIC II is a distinct maintenance publication from CLASSIC I.
m = df["idc_row_id"].eq("CT0752_A1_001") & df["assessment_days"].eq(392)
df.loc[m, "external_source_id"] = "10.1136/gut.2006.106781"
df.loc[m, "coadministered_drugs"] = "Immunosuppressive therapy"
df.loc[m, "patient_population"] = (
    "CLASSIC II maintenance cohort; 84 participants received concomitant immunosuppressive therapy."
)
df.loc[m, "dosing_description"] = (
    "Adalimumab maintenance 40 mg every other week or weekly through week 56 (CLASSIC II)."
)
mark(df["idc_row_id"].eq("CT0752_A1_001"), "CLASSIC I induction and CLASSIC II maintenance observations retained under one dependency group.")
df.loc[df["idc_row_id"].eq("CT0752_A1_001"), "record_dependency_note"] = (
    "Longitudinally related CLASSIC I/II observations; keep in the same model split group."
)

# ACCENT I overall and concomitant-medication subgroup overlap; retain both but make dependency explicit.
m = df["idc_row_id"].eq("CT0742_A1_001")
mark(m, "Overall cohort and nested concomitant-medication subgroup retained with dependency warning.")
df.loc[m, "record_dependency_note"] = (
    "Nested subgroup and overall cohort overlap; use grouped/clustered analysis or select one sensitivity-analysis row."
)

# CT0725 combined two unrelated publications/drugs under one internal study ID.
m = df["idc_row_id"].eq("CT0725_A1_001")
mark(m, "Two independent publications separated into CT0725 and CT0725B model study IDs.")

# Re-key legitimate multiple observations. Keep original identifiers in *_original fields.
def set_row(mask, row_id, trial_id=None):
    if int(mask.sum()) != 1:
        raise AssertionError((row_id, int(mask.sum())))
    df.loc[mask, "idc_row_id"] = row_id
    if trial_id is not None:
        df.loc[mask, "trial_id"] = trial_id

set_row(m & df["molecule_inn_name"].eq("Adalimumab"), "CT0725_A1_001", "CT0725")
set_row(m & df["molecule_inn_name"].eq("Etanercept"), "CT0725B_A1_001", "CT0725B")

for arm in ("A1", "A2", "A3"):
    base = df["idc_row_id"].eq(f"CT0736_{arm}_001")
    set_row(base & df["coadministered_drugs"].notna(), f"CT0736_{arm}_001")
    set_row(base & df["coadministered_drugs"].isna(), f"CT0736_{arm}_002")

for trial in ("CT0737", "CT0742", "CT0745", "CT0751"):
    base = df["idc_row_id"].eq(f"{trial}_A1_001")
    set_row(base & df["coadministered_drugs"].notna(), f"{trial}_A1_001")
    set_row(base & df["coadministered_drugs"].isna(), f"{trial}_A1_002")

base = df["idc_row_id"].eq("CT0752_A1_001")
set_row(base & df["assessment_days"].eq(28), "CT0752_A1_001")
set_row(base & df["assessment_days"].eq(392), "CT0752_A1_002")

# Recalculate basic categorical flags after reviewed co-medication corrections.
df["has_coadministered_drugs"] = df["coadministered_drugs"].notna().astype(int)
df["comedication_missing"] = df["coadministered_drugs"].isna().astype(int)
df["ada_fraction"] = df["ada_frequency_percent"] / 100
df["ada_high_10"] = (df["ada_frequency_percent"] >= 10).astype("Int64")

# Final pharmacology decisions.
moa = {
    "Cetuximab": ("Receptor blockade/antagonism", "Binds EGFR and competitively blocks ligand binding and downstream receptor signaling."),
    "Necitumumab": ("Receptor blockade/antagonism", "Binds the EGFR ligand-binding site and blocks ligand-stimulated EGFR activation."),
    "Reslizumab": ("Ligand neutralization", "Binds and neutralizes IL-5, preventing IL-5 receptor engagement and eosinophil signaling."),
    "Faricimab": ("Ligand neutralization", "Bispecific antibody that simultaneously inhibits VEGF-A and angiopoietin-2, suppressing two complementary angiogenic pathways."),
    "Trebananib": ("Ligand neutralization", "Peptibody that binds angiopoietin-1 and angiopoietin-2 and prevents their interaction with the Tie2 receptor, thereby inhibiting angiogenesis."),
    "Isatuximab": ("Immune-cell targeting/modulation", "Targets CD38-positive cells predominantly through ADCC and ADCP, with additional CDC, direct-cell-death, and CD38-enzymatic effects."),
    "GSK3174998": ("Receptor agonism", "Agonistic anti-OX40 antibody that activates OX40 costimulatory signaling."),
    "Utomilumab": ("Receptor agonism", "Agonistic antibody to the T-cell costimulatory receptor 4-1BB/CD137."),
    "Moxetumomab pasudotox": ("Targeted payload delivery", "CD22-directed immunotoxin delivering truncated Pseudomonas exotoxin to CD22-positive cells."),
    "Bimekizumab": ("Ligand neutralization", "Neutralizes IL-17A and IL-17F and prevents signaling through the IL-17 receptor complex."),
    "Itepekimab": ("Ligand neutralization", "Neutralizes IL-33 and inhibits IL-33-mediated signaling."),
    "Oleclumab": ("Immune checkpoint blockade", "Inhibits CD73 ectonucleotidase activity, reducing immunosuppressive extracellular adenosine production."),
}
for molecule, (group, desc) in moa.items():
    m = df["molecule_inn_name"].eq(molecule)
    df.loc[m, "mechanism_of_action_reviewed"] = desc
    df.loc[m, "moa_group"] = group
    df.loc[m, "moa_classification_source"] = "Manual review with cited primary/regulatory source"
    df.loc[m, "moa_review_flag"] = True
    df.loc[m, "moa_review_note"] = "Approved in final pre-modeling pharmacology review."

# Final model-control fields.
count_available = df["n_ada_assessed"].notna() & df["n_ada_positive"].notna() & df["n_ada_assessed"].gt(0)
count_rate = df["n_ada_positive"] / df["n_ada_assessed"] * 100
count_delta = (count_rate - df["ada_frequency_percent"]).abs()
df["ada_count_consistency_status"] = np.select(
    [~count_available, count_delta.le(1.0)],
    ["COUNT_DATA_MISSING", "PASS"],
    default="REVIEW_COUNT_MISMATCH",
)
df["ada_count_rate_percent"] = count_rate
df["ada_count_delta_pp"] = count_delta
df["binomial_count_model_eligible"] = count_available & count_delta.le(1.0)
df["model_split_group"] = df["trial_id"]
df["modeling_include"] = True

required = ["idc_row_id","trial_id","therapeutic_id","molecule_inn_name","ada_frequency_percent","target_clean","moa_group"]
df["modeling_ready"] = df[required].notna().all(axis=1)

# Outcome-derived columns are excluded from Modeling_Data to prevent target leakage.
leakage_columns = [
    "ada_fraction", "n_ada_positive", "cohort_group_id", "cohort_ADA", "max_ADA_time", "N_at_max_ADA",
    "trial_group_id", "trial_ADA", "N_of_trial_ADA", "INN_group_id", "INN_ADA", "N_of_INN_ADA",
    "PR_group_id", "PRID_ADA", "N_of_PRID_ADA", "ada_high_10_original",
]
model_columns = [c for c in df.columns if c not in leakage_columns]
model = df[model_columns].copy()

review_log = [
    ["MR-001","Molecule identity","CT0269_A1_001","Approved","Bevacizumab corrected to Pinatuzumab Vedotin because PR_0454/RG-7593 and CD22-MMAE mechanism identify pinatuzumab vedotin.","https://www.accessdata.fda.gov/drugsatfda_docs/label/2006/0125085s074lbl.pdf | https://pmc.ncbi.nlm.nih.gov/articles/PMC9834635/"],
    ["MR-002","MOA classification","Cetuximab","Approved","EGFR receptor blockade/antagonism.","https://www.accessdata.fda.gov/drugsatfda_docs/label/2007/125084s103lbl.pdf"],
    ["MR-003","MOA classification","Necitumumab","Approved","EGFR receptor blockade/antagonism.","https://www.accessdata.fda.gov/drugsatfda_docs/nda/2015/125547Orig1s000SumR.pdf"],
    ["MR-004","MOA classification","Reslizumab","Approved","Classified as ligand neutralization: it binds IL-5; antagonist in labeling does not mean it binds the receptor.","https://www.accessdata.fda.gov/drugsatfda_docs/label/2019/0761033s010lbl.pdf"],
    ["MR-005","MOA description","Faricimab","Approved","Completed dual VEGF-A/Ang-2 inhibition description.","https://www.accessdata.fda.gov/drugsatfda_docs/label/2022/761235s000lbl.pdf"],
    ["MR-006","MOA description","Trebananib","Approved","Ang1/2 sequestration preventing Tie2 binding.","https://pubmed.ncbi.nlm.nih.gov/24950985/"],
    ["MR-007","MOA classification","Isatuximab","Approved","Immune-cell targeting/modulation; ADCC is more prevalent than CDC.","https://aacrjournals.org/clincancerres/article/25/10/3176/10772/The-Mechanism-of-Action-of-the-Anti-CD38"],
    ["MR-008","MOA confirmation","GSK3174998","Approved","OX40 agonist.","https://pmc.ncbi.nlm.nih.gov/articles/PMC10030671/"],
    ["MR-009","MOA confirmation","Utomilumab","Approved","4-1BB/CD137 agonist.","https://aacrjournals.org/clincancerres/article/24/8/1816/81312/Phase-I-Study-of-Single-Agent-Utomilumab-PF"],
    ["MR-010","MOA confirmation","Moxetumomab pasudotox","Approved","CD22-directed exotoxin payload.","https://www.accessdata.fda.gov/drugsatfda_docs/label/2020/761104s003lbl.pdf"],
    ["MR-011","MOA confirmation","Bimekizumab","Approved","Dual IL-17A/IL-17F neutralization.","https://www.accessdata.fda.gov/drugsatfda_docs/label/2024/761151s005s006s007lbl.pdf"],
    ["MR-012","MOA confirmation","Itepekimab","Approved","IL-33 targeting/neutralization.","https://pmc.ncbi.nlm.nih.gov/articles/PMC8841494/"],
    ["MR-013","MOA confirmation","Oleclumab","Approved","CD73 inhibition reduces extracellular adenosine.","https://pubmed.ncbi.nlm.nih.gov/37016126/"],
    ["MR-014","Duplicate resolution","20 redundant rows","Approved","Removed source-identical copies created by stale/cross-matched aggregate fields; aggregate ADA columns excluded from Modeling_Data as leakage.","Internal row-level comparison"],
    ["MR-015","Record structure","CT0736","Approved","Six dose-by-MTX strata retained and uniquely keyed.","https://doi.org/10.1002/1529-0131(199809)41:9%3C1552::AID-ART5%3E3.0.CO;2-W"],
    ["MR-016","Record structure","CT0737","Approved","Two mutually exclusive immunosuppressive-therapy strata retained.","https://www.nejm.org/doi/full/10.1056/NEJMoa020888"],
    ["MR-017","Record structure","CT0745","Approved","MTX and no-MTX strata retained; primary DOI restored.","https://pmc.ncbi.nlm.nih.gov/articles/PMC1955110/"],
    ["MR-018","Record structure","CT0751","Approved","Incorrect CT0685 value harmonized to CT0751; two immunomodulator strata retained.","https://pubmed.ncbi.nlm.nih.gov/18691349/"],
    ["MR-019","Source correction","CT0752_A1_002","Approved","CLASSIC II maintenance DOI and dosing restored; dependency with CLASSIC I documented.","https://pmc.ncbi.nlm.nih.gov/articles/PMC2701613/"],
    ["MR-020","Dependency warning","CT0742","Approved with restriction","Overall ACCENT I cohort and nested medication subgroup retained; grouped/clustered analysis required.","https://doi.org/10.1016/S0140-6736(02)08512-4"],
]

feature_rows = []
outcomes = {"ada_frequency_percent":"Continuous outcome", "ada_high_10":"Binary outcome"}
group_only = {"idc_row_id","trial_id","therapeutic_id","external_source_id","model_split_group"}
weights = {"n_ada_assessed"}
audit_prefixes = ("source_","record_","modeling_","idc_row_id_original","trial_id_original","external_source_id_original","ada_count_","binomial_")
for c in model.columns:
    if c in outcomes:
        role, use = outcomes[c], "Target only; never use as predictor"
    elif c in group_only:
        role, use = "Identifier/group", "Use for joins or group-aware data splitting; not as predictor"
    elif c in weights:
        role, use = "Sample-size metadata", "Optional weighting; review ada_count_consistency_status"
    elif c.startswith(audit_prefixes):
        role, use = "QC/audit", "Do not use as biological predictor"
    else:
        role, use = "Candidate predictor", "Evaluate missingness, encoding, and scientific relevance before modeling"
    feature_rows.append([c, role, use])

qc = [
    ["Input rows", input_rows, "INFO"],
    ["Redundant source-observation copies removed", len(excluded), "PASS"],
    ["Final modeling rows", len(model), "INFO"],
    ["Unique idc_row_id", int(model["idc_row_id"].nunique()), "PASS" if model["idc_row_id"].is_unique else "FAIL"],
    ["Duplicate idc_row_id rows", int(model["idc_row_id"].duplicated(False).sum()), "PASS" if model["idc_row_id"].is_unique else "FAIL"],
    ["Missing required values", int(model[required].isna().sum().sum()), "PASS"],
    ["ADA outside 0-100", int((~model["ada_frequency_percent"].between(0,100)).sum()), "PASS"],
    ["ada_high_10 inconsistencies", int((model["ada_high_10"] != (model["ada_frequency_percent"] >= 10).astype("Int64")).sum()), "PASS"],
    ["Bevacizumab-CD22 residual rows", int((model["molecule_inn_name"].eq("Bevacizumab") & model["target_clean"].eq("CD22")).sum()), "PASS"],
    ["Other/Missing target groups", int(model["target_group"].eq("Other target").sum()), "PASS"],
    ["Other/Missing MOA groups", int(model["moa_group"].isin(["Other/unclear","Missing"]).sum()), "PASS"],
    ["Count-vs-frequency review flags", int(model["ada_count_consistency_status"].eq("REVIEW_COUNT_MISMATCH").sum()), "CAUTION"],
    ["Rows eligible for binomial count modeling", int(model["binomial_count_model_eligible"].sum()), "INFO"],
    ["Overlapping/nested observations documented", int(model["record_dependency_note"].notna().sum()), "CAUTION"],
]

assert len(excluded) == 20
assert len(model) == 2611
assert model["idc_row_id"].is_unique
assert model[required].notna().all().all()
assert model["ada_frequency_percent"].between(0,100).all()
assert not (model["molecule_inn_name"].eq("Bevacizumab") & model["target_clean"].eq("CD22")).any()
assert not model["target_group"].eq("Other target").any()
assert not model["moa_group"].isin(["Other/unclear","Missing"]).any()
assert set(model.loc[model["molecule_inn_name"].eq("Reslizumab"), "moa_group"]) == {"Ligand neutralization"}

def clean_records(frame):
    return frame.replace({np.nan: None, pd.NA: None}).to_dict(orient="records")

payload = {
    "model_columns": list(model.columns),
    "model_rows": clean_records(model),
    "excluded_columns": list(excluded.columns),
    "excluded_rows": clean_records(excluded),
    "review_columns": ["review_id","issue_type","record_or_molecule","decision","rationale","source_url"],
    "review_rows": [dict(zip(["review_id","issue_type","record_or_molecule","decision","rationale","source_url"], r)) for r in review_log],
    "qc_columns": ["check","value","status"],
    "qc_rows": [dict(zip(["check","value","status"], r)) for r in qc],
    "feature_columns": ["column_name","model_role","recommended_use"],
    "feature_rows": [dict(zip(["column_name","model_role","recommended_use"], r)) for r in feature_rows],
}
Path(OUT_DIR / "final_payload.json").write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
print(json.dumps({"input_rows":input_rows,"removed":len(excluded),"final_rows":len(model),"columns":len(model.columns),"count_flags":int(model["ada_count_consistency_status"].eq("REVIEW_COUNT_MISMATCH").sum())},ensure_ascii=False))
