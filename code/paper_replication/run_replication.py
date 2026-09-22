from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy.stats import chi2

matplotlib.use("Agg")
import matplotlib.pyplot as plt


# This release keeps executable code under code/paper_replication while data,
# config, work, and outputs live at the repository root.
ROOT = Path(__file__).resolve().parents[2]
REPLICATION_DIR = ROOT
PROCESSED_DIR = REPLICATION_DIR / "data" / "processed"
MANUAL_FILE = REPLICATION_DIR / "data" / "manual" / "paper_derived_variables.csv"
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "outputs" / "paper_replication"
ARTIFACT_DIR = OUTPUT_DIR / "artifacts"
FIGURE_DIR = OUTPUT_DIR / "figures"

PAPER_URL = "https://www.frontiersin.org/journals/immunology/articles/10.3389/fimmu.2026.1816949/full"
GITHUB_URL = "https://github.com/Immunogenicity-Database-Collaborative/IDC-DB"
GITHUB_COMMIT = "049c8a5252396be64ac2a95a68a04384b57faa07"

TERM_ORDER = [
    ("T cell Epitope Content", "tcell"),
    ("Disease Indication", "C(disease)"),
    ("Therapeutic Immune MOA Type", "C(moa)"),
    ("Comedication Immune MOA Type", "C(comed)"),
    ("Dose Level", "dose"),
    ("Dose Interval", "dose_interval"),
    ("Year Trial was Completed", "trial_year"),
    ("Route of Administration", "C(route)"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Independent IDC Figure 6 / Table S6 paper-replication workflow."
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "proxy", "exact"),
        default="auto",
        help="auto runs exact when the author-derived file exists, otherwise a labeled proxy.",
    )
    parser.add_argument(
        "--allow-sample-mismatch",
        action="store_true",
        help="Allow exact mode to run when complete-case N is not the paper-inferred 1,216.",
    )
    return parser.parse_args()


def load_records(name: str) -> pd.DataFrame:
    path = PROCESSED_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run the artifact-tool extractor first: "
            "node paper_replication/extract_source_tables.mjs"
        )
    return pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def clean_string(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def excel_year(value: object) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        numeric = float(value)
        if 1900 <= numeric <= 2200:
            return float(int(numeric))
        if 10000 <= numeric <= 100000:
            return float((pd.Timestamp("1899-12-30") + pd.to_timedelta(numeric, unit="D")).year)
    parsed = pd.to_datetime(value, errors="coerce")
    return float(parsed.year) if not pd.isna(parsed) else np.nan


DOSE_PATTERN = re.compile(
    r"(?P<low>\d+(?:\.\d+)?)\s*"
    r"(?:(?:-|–|—|to)\s*(?P<high>\d+(?:\.\d+)?)\s*)?"
    r"(?P<unit>µg|μg|mcg|ug|mg|g)\b\s*"
    r"(?:/\s*(?P<denom>kg|m2|m\^2|m²))?",
    flags=re.IGNORECASE,
)


def parse_dose(text: object) -> tuple[float, str, str]:
    raw = clean_string(text).replace("_x000D_", " ")
    match = DOSE_PATTERN.search(raw)
    if not match:
        return np.nan, "", "no recognized mass dose"
    low = float(match.group("low"))
    high = float(match.group("high")) if match.group("high") else low
    value = (low + high) / 2.0
    unit = match.group("unit").lower()
    denom = (match.group("denom") or "").lower()
    if unit in {"µg", "μg", "mcg", "ug"}:
        value /= 1000.0
    elif unit == "g":
        value *= 1000.0
    assumption = "direct mass dose"
    if denom == "kg":
        value *= 70.0
        assumption = "proxy conversion: per-kg dose multiplied by 70 kg"
    elif denom in {"m2", "m^2", "m²"}:
        value *= 1.8
        assumption = "proxy conversion: per-m2 dose multiplied by 1.8 m2"
    return float(value), f"{unit}/{denom}" if denom else unit, assumption


def _median_positive_difference(numbers: list[float]) -> float:
    unique = sorted(set(numbers))
    differences = [b - a for a, b in zip(unique, unique[1:]) if b > a]
    return float(np.median(differences)) if differences else np.nan


def parse_interval_days(text: object) -> tuple[float, str]:
    raw = clean_string(text).lower().replace("_x000d_", " ")
    if not raw:
        return np.nan, "missing schedule"
    word_numbers = {
        "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
        "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
        "eleven": "11", "twelve": "12",
    }
    for word, number in word_numbers.items():
        raw = re.sub(rf"\b{word}\b", number, raw)
    compact = re.sub(r"\s+", "", raw)
    patterns = [
        (r"\bq\s*(\d+(?:\.\d+)?)\s*(?:w|wk|week)s?\b", 7.0, "qN weeks"),
        (r"\bq\s*(\d+(?:\.\d+)?)\s*d(?:ay)?s?\b", 1.0, "qN days"),
        (r"(?:once\s+)?every\s+(\d+(?:\.\d+)?)\s*week", 7.0, "every N weeks"),
        (r"(?:once\s+)?every\s+(\d+(?:\.\d+)?)\s*day", 1.0, "every N days"),
        (r"(?:once\s+)?every\s+(\d+(?:\.\d+)?)\s*month", 30.4375, "every N months"),
        (r"(?:once\s+)?every\s+(\d+(?:\.\d+)?)\s*w\b", 7.0, "every Nw"),
        (r"(?:once\s+)?every\s+(\d+(?:\.\d+)?)\s*d\b", 1.0, "every Nd"),
        (r"\b(\d+(?:\.\d+)?)\s*[- ]day\s+cycle\b", 1.0, "N-day cycle"),
    ]
    for pattern, multiplier, label in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            return float(match.group(1)) * multiplier, label
    compact_patterns = [
        (r"q(\d+(?:\.\d+)?)w", 7.0, "qNw compact"),
        (r"q(\d+(?:\.\d+)?)d", 1.0, "qNd compact"),
    ]
    for pattern, multiplier, label in compact_patterns:
        match = re.search(pattern, compact)
        if match:
            return float(match.group(1)) * multiplier, label
    keyword_rules = [
        (r"\b(eow|qow|every other week)\b", 14.0, "every other week"),
        (r"\b(qm|q1m)\b", 30.4375, "monthly compact"),
        (r"\b(biweekly|fortnightly)\b", 14.0, "biweekly"),
        (r"\b(weekly|once weekly|qw)\b", 7.0, "weekly"),
        (r"\b(twice weekly)\b", 3.5, "twice weekly"),
        (r"\b(monthly|once monthly)\b", 30.4375, "monthly"),
        (r"\b(daily|once daily|qd)\b", 1.0, "daily"),
        (r"\b(twice daily|bid)\b", 0.5, "twice daily"),
    ]
    for pattern, value, label in keyword_rules:
        if re.search(pattern, raw):
            return value, label
    every_list = re.search(
        r"every\s+((?:\d+(?:\.\d+)?\s*(?:,|or|and|;|\s)\s*)+\d+(?:\.\d+)?)\s*(day|week)s?",
        raw,
    )
    if every_list:
        values = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", every_list.group(1))]
        if values:
            multiplier = 7.0 if every_list.group(2) == "week" else 1.0
            return float(np.median(values)) * multiplier, "median of alternative every-N schedules"
    repeated_weeks = [float(value) for value in re.findall(r"\bweek\s*(\d+(?:\.\d+)?)", raw)]
    interval = _median_positive_difference(repeated_weeks)
    if not np.isnan(interval):
        return interval * 7.0, "median difference in repeated week labels"
    repeated_days = [float(value) for value in re.findall(r"\bday\s*(\d+(?:\.\d+)?)", raw)]
    interval = _median_positive_difference(repeated_days)
    if not np.isnan(interval):
        return interval, "median difference in repeated day labels"
    for unit_word, multiplier in (("week", 7.0), ("day", 1.0)):
        match = re.search(
            rf"{unit_word}s?\s+((?:\d+(?:\.\d+)?\s*(?:,|and|;|\s)\s*)+\d+(?:\.\d+)?)",
            raw,
        )
        if match:
            values = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", match.group(1))]
            interval = _median_positive_difference(values)
            if not np.isnan(interval):
                return interval * multiplier, f"median difference in listed {unit_word}s"
    return np.nan, "no deterministic cadence recognized"


def disease_group(category: object, description: object) -> str:
    category_text = clean_string(category)
    description_text = clean_string(description).lower()
    if category_text == "Inflammation and autoimmunity":
        return "Inflammation and autoimmunity"
    if category_text == "Infectious diseases":
        return "Infectious diseases"
    if category_text == "Cancer and neoplasms":
        hematology_terms = (
            "leuk", "lymphom", "myelom", "hematolog", "haematolog", "b-cell",
            "b cell", "t-cell", "t cell", "myelodys", "myelofib", "waldenstrom",
        )
        return (
            "Hematological malignancy"
            if any(term in description_text for term in hematology_terms)
            else "Solid tumor"
        )
    return "Other"


def moa_group(mechanism: object, target: object) -> str:
    text = f"{clean_string(mechanism)} {clean_string(target)}".lower()
    depletion_terms = (
        "deplet", "cd20", "cd19", "cd22", "cd52", "anti-b cell", "anti-t cell",
    )
    activation_terms = (
        "pd-1", "pd1", "pd-l1", "pdl1", "ctla-4", "ctla4", "checkpoint",
        "ox40", "cd137", "4-1bb", "agonist", "co-stimulat", "costimulat",
        "t cell activ", "t-cell activ", "b cell activ", "b-cell activ",
    )
    inflammation_terms = (
        "anti-inflamm", "tnf", "interleukin", "il-1", "il-4", "il-5", "il-6",
        "il-12", "il-13", "il-17", "il-23", "integrin", "jak", "complement",
        "allergic", "eosinoph", "inflammation", "autoimmun",
    )
    if any(term in text for term in depletion_terms):
        return "T/B cell depletor"
    if any(term in text for term in activation_terms):
        return "T/B cell activator"
    if any(term in text for term in inflammation_terms):
        return "Anti-inflammation"
    return "Other"


def comedication_group(value: object) -> str:
    text = clean_string(value).lower()
    if text in {"", "none", "na", "n/a", "not reported", "no co-medications"}:
        return "No co-medications"
    suppressive_terms = (
        "methotrexate", "corticosteroid", "prednisone", "prednisolone", "dexamethasone",
        "azathioprine", "mycophenolate", "cyclosporine", "tacrolimus", "leflunomide",
        "cyclophosphamide", "hydroxychloroquine", "immunosuppress", "steroid",
    )
    return (
        "Immune suppressors"
        if any(term in text for term in suppressive_terms)
        else "Non-immune suppressors"
    )


def route_group(value: object) -> str:
    text = clean_string(value).lower()
    if text == "intravenous":
        return "Intravenous"
    if text == "subcutaneous":
        return "Subcutaneous"
    if text == "ophthalmic":
        return "Ophthalmic"
    return "Other"


def sequence_length_by_therapeutic(therapeutic: pd.DataFrame, sequence: pd.DataFrame) -> pd.Series:
    sequence_lengths: dict[str, float] = {}
    for _, row in sequence.iterrows():
        identifier = clean_string(row.get("Sequence ID"))
        amino_acids = re.sub(r"[^A-Z]", "", clean_string(row.get("Amino Acid Sequence")).upper())
        multiplicity = pd.to_numeric(row.get("Chain Multiplicity"), errors="coerce")
        if identifier and amino_acids:
            sequence_lengths[identifier] = len(amino_acids) * (float(multiplicity) if pd.notna(multiplicity) else 1.0)

    output: dict[str, float] = {}
    for _, row in therapeutic.iterrows():
        therapeutic_id = clean_string(row.get("Therapeutic ID"))
        identifiers = [
            value.strip()
            for value in clean_string(row.get("Sequence IDC database Identifier(s)")).split(",")
            if value.strip()
        ]
        available = [sequence_lengths[value] for value in identifiers if value in sequence_lengths]
        output[therapeutic_id] = float(sum(available)) if available else np.nan
    return pd.Series(output, name="sequence_length_proxy")


def prepare_public_candidate(
    clinical: pd.DataFrame,
    therapeutic: pd.DataFrame,
    sequence: pd.DataFrame,
) -> pd.DataFrame:
    data = clinical.copy()
    data["source_excel_row"] = np.arange(2, len(data) + 2)
    data["ada_frequency_percent"] = pd.to_numeric(
        data["Frequency of ADA+ patients"], errors="coerce"
    )
    data = data.loc[
        data["Therapeutic Exposure Status"].astype(str).str.strip().eq("Therapeutic Exposed")
        & data["ada_frequency_percent"].notna()
    ].copy()
    data["high_ada"] = (data["ada_frequency_percent"] >= 10.0).astype(int)
    data["replication_row_key"] = (
        data["IDC Row identifier"].astype(str)
        + "__source_row_"
        + data["source_excel_row"].astype(str)
    )

    therapy_columns = [
        "Therapeutic ID",
        "Mechanism of Action",
        "Target(s) (Protein/Molecule)",
        "Sequence IDC database Identifier(s)",
    ]
    therapy_lookup = therapeutic[therapy_columns].drop_duplicates("Therapeutic ID")
    data = data.merge(
        therapy_lookup,
        left_on="Therapeutic Assessed for ADA ID",
        right_on="Therapeutic ID",
        how="left",
        validate="many_to_one",
    )
    sequence_proxy = sequence_length_by_therapeutic(therapeutic, sequence)
    data["sequence_length_proxy"] = data["Therapeutic Assessed for ADA ID"].map(sequence_proxy)

    dose_inputs = (
        data["Dosing Description"].fillna("").astype(str)
        + " | "
        + data["Therapeutic Dosing Schedule Description"].fillna("").astype(str)
    )
    dose_parsed = dose_inputs.map(parse_dose)
    data["dose_level_proxy"] = dose_parsed.map(lambda item: item[0])
    data["dose_unit_parsed"] = dose_parsed.map(lambda item: item[1])
    data["dose_proxy_assumption"] = dose_parsed.map(lambda item: item[2])

    interval_parsed = data["Therapeutic Dosing Schedule Description"].map(parse_interval_days)
    data["dose_interval_days_proxy"] = interval_parsed.map(lambda item: item[0])
    data["interval_parse_rule"] = interval_parsed.map(lambda item: item[1])
    data["trial_year_completed"] = data["Trial End Date"].map(excel_year)
    data["disease_indication_group_proxy"] = [
        disease_group(category, description)
        for category, description in zip(
            data["Disease Indication Category"], data["Disease Indication Description"]
        )
    ]
    data["therapeutic_moa_type_proxy"] = [
        moa_group(mechanism, target)
        for mechanism, target in zip(
            data["Mechanism of Action"], data["Target(s) (Protein/Molecule)"]
        )
    ]
    data["comedication_moa_type_proxy"] = data["Co-administered drugs"].map(
        comedication_group
    )
    data["route_group_proxy"] = data["Therapeutic Route of Administration"].map(route_group)
    return data


def zscore(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    standard_deviation = numeric.std(ddof=0)
    if pd.isna(standard_deviation) or standard_deviation == 0:
        return numeric
    return (numeric - numeric.mean()) / standard_deviation


def modeling_frame_from_proxy(candidate: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "row_id": candidate["IDC Row identifier"],
            "high_ada": candidate["high_ada"],
            "tcell": zscore(candidate["sequence_length_proxy"]),
            "disease": candidate["disease_indication_group_proxy"],
            "moa": candidate["therapeutic_moa_type_proxy"],
            "comed": candidate["comedication_moa_type_proxy"],
            "dose": zscore(candidate["dose_level_proxy"]),
            "dose_interval": zscore(candidate["dose_interval_days_proxy"]),
            "trial_year": zscore(candidate["trial_year_completed"]),
            "route": candidate["route_group_proxy"],
        }
    )
    return frame.dropna().copy()


def modeling_frame_from_exact(candidate: pd.DataFrame, manual_path: Path) -> pd.DataFrame:
    manual = pd.read_csv(manual_path)
    required = {
        "replication_row_key",
        "IDC Row identifier",
        "therapeutic_moa_type",
        "disease_indication_group",
        "t_cell_epitope_content",
        "dose_interval_days",
        "route_group",
        "comedication_moa_type",
        "dose_level",
        "trial_year_completed",
    }
    missing = sorted(required.difference(manual.columns))
    if missing:
        raise ValueError(f"Exact derived-variable file is missing columns: {missing}")
    if manual["replication_row_key"].duplicated().any():
        duplicates = manual.loc[
            manual["replication_row_key"].duplicated(keep=False), "replication_row_key"
        ].head(10).tolist()
        raise ValueError(f"Duplicate replication_row_key values in exact file: {duplicates}")
    merged = candidate[["replication_row_key", "IDC Row identifier", "high_ada"]].merge(
        manual,
        on="replication_row_key",
        how="left",
        validate="one_to_one",
        suffixes=("_public", "_manual"),
    )
    return pd.DataFrame(
        {
            "row_id": merged["replication_row_key"],
            "high_ada": merged["high_ada"],
            "tcell": zscore(merged["t_cell_epitope_content"]),
            "disease": merged["disease_indication_group"],
            "moa": merged["therapeutic_moa_type"],
            "comed": merged["comedication_moa_type"],
            "dose": zscore(merged["dose_level"]),
            "dose_interval": zscore(merged["dose_interval_days"]),
            "trial_year": zscore(merged["trial_year_completed"]),
            "route": merged["route_group"],
        }
    ).dropna()


def sequential_deviance(
    frame: pd.DataFrame,
    analysis_type: str,
    term_order: list[tuple[str, str]] | None = None,
) -> pd.DataFrame:
    if len(frame) < 50:
        raise ValueError(f"Only {len(frame)} complete rows; model was not fitted.")
    required_levels = {"disease": 2, "moa": 2, "comed": 2, "route": 2}
    for column, minimum in required_levels.items():
        if frame[column].nunique(dropna=True) < minimum:
            raise ValueError(f"{column} has fewer than {minimum} observed levels.")

    active_order = TERM_ORDER if term_order is None else term_order
    formula_terms: list[str] = []
    previous = smf.glm(
        formula="high_ada ~ 1",
        data=frame,
        family=sm.families.Binomial(),
    ).fit(maxiter=300, disp=0)
    rows: list[dict[str, object]] = []
    for model_order, (label, term) in enumerate(active_order, start=1):
        formula_terms.append(term)
        current = smf.glm(
            formula=f"high_ada ~ {' + '.join(formula_terms)}",
            data=frame,
            family=sm.families.Binomial(),
        ).fit(maxiter=300, disp=0)
        degrees_of_freedom = int(round(previous.df_resid - current.df_resid))
        deviance_reduction = float(previous.deviance - current.deviance)
        rows.append(
            {
                "analysis_type": analysis_type,
                "model_order": model_order,
                "variable": label,
                "df": degrees_of_freedom,
                "deviance": deviance_reduction,
                "residual_df": int(round(current.df_resid)),
                "residual_deviance": float(current.deviance),
                "p_value": float(chi2.sf(deviance_reduction, degrees_of_freedom)),
                "n_complete": int(len(frame)),
                "formula_through_term": f"high_ada ~ {' + '.join(formula_terms)}",
            }
        )
        previous = current
    return pd.DataFrame(rows)


def order_sensitivity(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run deterministic first/last placements for each term on one fixed cohort."""
    scenarios: list[tuple[str, list[tuple[str, str]]]] = [("paper_inferred", TERM_ORDER)]
    for focus in TERM_ORDER:
        remaining = [term for term in TERM_ORDER if term != focus]
        scenarios.append((f"first__{focus[1]}", [focus, *remaining]))
        scenarios.append((f"last__{focus[1]}", [*remaining, focus]))

    seen: set[tuple[str, ...]] = set()
    detail_frames: list[pd.DataFrame] = []
    for scenario_id, scenario_order in scenarios:
        signature = tuple(term for _, term in scenario_order)
        if signature in seen:
            continue
        seen.add(signature)
        result = sequential_deviance(
            frame,
            analysis_type="proxy_order_sensitivity",
            term_order=scenario_order,
        )
        result.insert(0, "scenario_id", scenario_id)
        result.insert(1, "scenario_order", " -> ".join(label for label, _ in scenario_order))
        detail_frames.append(result)

    details = pd.concat(detail_frames, ignore_index=True)
    paper_values = details.loc[
        details["scenario_id"].eq("paper_inferred"), ["variable", "deviance"]
    ].rename(columns={"deviance": "proxy_paper_order_deviance"})
    extrema = details.groupby("variable", as_index=False).agg(
        minimum_deviance=("deviance", "min"),
        median_deviance=("deviance", "median"),
        maximum_deviance=("deviance", "max"),
        n_order_scenarios=("scenario_id", "nunique"),
    )
    minimum_orders = details.loc[details.groupby("variable")["deviance"].idxmin(), [
        "variable", "scenario_id"
    ]].rename(columns={"scenario_id": "minimum_scenario"})
    maximum_orders = details.loc[details.groupby("variable")["deviance"].idxmax(), [
        "variable", "scenario_id"
    ]].rename(columns={"scenario_id": "maximum_scenario"})
    summary = (
        paper_values.merge(extrema, on="variable", validate="one_to_one")
        .merge(minimum_orders, on="variable", validate="one_to_one")
        .merge(maximum_orders, on="variable", validate="one_to_one")
    )
    summary["deviance_range"] = summary["maximum_deviance"] - summary["minimum_deviance"]
    summary["range_to_paper_order_ratio"] = np.where(
        summary["proxy_paper_order_deviance"].abs() > 1e-12,
        summary["deviance_range"] / summary["proxy_paper_order_deviance"].abs(),
        np.nan,
    )
    display_order = {label: index for index, (label, _) in enumerate(TERM_ORDER, start=1)}
    summary.insert(0, "paper_model_order", summary["variable"].map(display_order))
    return summary.sort_values("paper_model_order"), details


def drop_one_likelihood_ratio(frame: pd.DataFrame) -> pd.DataFrame:
    """Conditional contribution of each term after all other terms are included."""
    all_terms = [term for _, term in TERM_ORDER]
    full_formula = f"high_ada ~ {' + '.join(all_terms)}"
    full = smf.glm(
        formula=full_formula,
        data=frame,
        family=sm.families.Binomial(),
    ).fit(maxiter=300, disp=0)
    rows: list[dict[str, object]] = []
    for paper_order, (label, term) in enumerate(TERM_ORDER, start=1):
        reduced_terms = [candidate for candidate in all_terms if candidate != term]
        reduced = smf.glm(
            formula=f"high_ada ~ {' + '.join(reduced_terms)}",
            data=frame,
            family=sm.families.Binomial(),
        ).fit(maxiter=300, disp=0)
        degrees_of_freedom = int(round(reduced.df_resid - full.df_resid))
        deviance_if_removed = float(reduced.deviance - full.deviance)
        rows.append(
            {
                "paper_model_order": paper_order,
                "variable": label,
                "df": degrees_of_freedom,
                "conditional_deviance": deviance_if_removed,
                "p_value": float(chi2.sf(deviance_if_removed, degrees_of_freedom)),
                "full_model_residual_df": int(round(full.df_resid)),
                "full_model_residual_deviance": float(full.deviance),
                "n_complete": int(len(frame)),
                "interpretation": "Drop-one likelihood-ratio test on the fixed proxy cohort; order-independent but still proxy-based.",
            }
        )
    return pd.DataFrame(rows)


def proxy_missingness(candidate: pd.DataFrame, proxy_frame: pd.DataFrame) -> pd.DataFrame:
    fields = [
        ("ADA binary outcome", "high_ada"),
        ("T cell Epitope Content proxy", "sequence_length_proxy"),
        ("Disease Indication proxy", "disease_indication_group_proxy"),
        ("Therapeutic Immune MOA Type proxy", "therapeutic_moa_type_proxy"),
        ("Comedication Immune MOA Type proxy", "comedication_moa_type_proxy"),
        ("Dose Level proxy", "dose_level_proxy"),
        ("Dose Interval proxy", "dose_interval_days_proxy"),
        ("Year Trial was Completed", "trial_year_completed"),
        ("Route of Administration proxy", "route_group_proxy"),
    ]
    rows = []
    for variable, column in fields:
        missing = int(candidate[column].isna().sum())
        rows.append(
            {
                "variable": variable,
                "candidate_rows": int(len(candidate)),
                "available_rows": int(len(candidate) - missing),
                "missing_rows": missing,
                "missing_percent": missing / len(candidate),
                "proxy_field": column,
            }
        )
    rows.append(
        {
            "variable": "Any required proxy-model field",
            "candidate_rows": int(len(candidate)),
            "available_rows": int(len(proxy_frame)),
            "missing_rows": int(len(candidate) - len(proxy_frame)),
            "missing_percent": (len(candidate) - len(proxy_frame)) / len(candidate),
            "proxy_field": "complete-case intersection",
        }
    )
    return pd.DataFrame(rows)


def outcome_balance(candidate: pd.DataFrame, proxy_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for stage, values in [
        ("Exposed + outcome candidate", candidate["high_ada"]),
        ("Complete public-data proxy model", proxy_frame["high_ada"]),
    ]:
        for outcome_value, label in [(0, "Low ADA (<10%)"), (1, "High ADA (>=10%)")]:
            count = int(values.eq(outcome_value).sum())
            rows.append(
                {
                    "stage": stage,
                    "outcome": label,
                    "rows": count,
                    "stage_rows": int(len(values)),
                    "percent_of_stage": count / len(values),
                }
            )
    return pd.DataFrame(rows)


def source_manifest() -> pd.DataFrame:
    sources = [
        (
            REPLICATION_DIR / "data" / "raw" / "User_IDC_DB_V1_All_Tables.xlsx",
            "User-provided original IDC DB V1 all-tables workbook (frozen copy)",
            "D:/DownLoads/IDC_DB_V1_All_Tables.xlsx",
        ),
        (
            REPLICATION_DIR / "data" / "raw" / "Frontiers_Data_Sheet_1.pdf",
            "Frontiers supplementary methods and Table S6",
            "https://public-pages-files-2025.frontiersin.org/articles/1816949/file/Data_Sheet_1.pdf/1816949_data-sheet_1/1",
        ),
        (
            REPLICATION_DIR / "data" / "raw" / "Frontiers_Table_1.xlsx",
            "Frontiers aggregated ADA values (Table 1)",
            "https://public-pages-files-2025.frontiersin.org/articles/1816949/file/Table_1.xlsx/1816949_table_1/1",
        ),
        (
            REPLICATION_DIR / "data" / "raw" / "Frontiers_Table_2.xlsx",
            "Frontiers IDC DS V1 all tables (Table 2)",
            "https://public-pages-files-2025.frontiersin.org/articles/1816949/file/Table_2.xlsx/1816949_table_2/1",
        ),
        (
            REPLICATION_DIR
            / "data"
            / "raw"
            / "IDC-DB"
            / "releases"
            / "V1.00"
            / "IDC_DB_V1_Aggregated_ADA_Values.xlsx",
            "Author GitHub V1.00 aggregated ADA workbook",
            GITHUB_URL,
        ),
        (
            REPLICATION_DIR
            / "data"
            / "raw"
            / "IDC-DB"
            / "releases"
            / "V1.00"
            / "IDC_DB_V1_All_Tables.xlsx",
            "Author GitHub V1.00 all-tables workbook",
            GITHUB_URL,
        ),
        (
            Path("C:/Users/BulrushMarry/Desktop/2025.12.08.692993v1.full.pdf"),
            "User-provided bioRxiv preprint",
            "https://doi.org/10.64898/2025.12.08.692993",
        ),
    ]
    rows = []
    for path, role, url in sources:
        rows.append(
            {
                "source_role": role,
                "path": str(path),
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else np.nan,
                "sha256": sha256(path) if path.exists() else "",
                "origin_url": url,
                "github_commit_if_applicable": GITHUB_COMMIT if GITHUB_URL in url else "",
            }
        )
    return pd.DataFrame(rows)


def availability_audit() -> pd.DataFrame:
    rows = [
        ("ADA binary outcome", "Frequency of ADA+ patients + Therapeutic Exposure Status", True, "Direct", "None"),
        ("Therapeutic Immune MOA Type", "Free-text Mechanism of Action", False, "Keyword proxy", "Author row-level 4-class mapping"),
        ("Disease Indication", "Category + free-text description", False, "Deterministic 5-group proxy", "Author cancer subtype/grouping rules"),
        ("T cell Epitope Content", "Sequences are public; derived predictions are not", False, "Total sequence length proxy", "Author NetMHCIIpan-4.3 EL + OAS/human-proteome filtered counts"),
        ("Dose Interval", "Free-text dosing schedule", False, "Regex cadence proxy", "Author parser/manual derived numeric interval"),
        ("Route of Administration", "Controlled raw route", False, "4-level proxy", "Author exact inclusion/grouping in complete cases"),
        ("Comedication Immune MOA Type", "Free-text co-administered drugs", False, "Drug-name keyword proxy", "Author row-level 3-class mapping"),
        ("Dose Level", "Free-text dosing description", False, "Mass extraction; 70 kg/1.8 m2 assumptions", "Author dose harmonization and unit conversion rules"),
        ("Year Trial was Completed", "Trial End Date", True, "Excel date to year", "None, subject to author's missing-date handling"),
        ("Model formula/order", "Methods + Table S6 residual-df sequence", False, "Type-I order inferred from residual df", "Author analysis code or explicit formula"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "field_or_component",
            "public_source",
            "exact_publicly_available",
            "implemented_public_proxy",
            "strict_replication_requirement",
        ],
    )


def sample_funnel(clinical: pd.DataFrame, candidate: pd.DataFrame, proxy_frame: pd.DataFrame) -> pd.DataFrame:
    exposed = clinical["Therapeutic Exposure Status"].astype(str).str.strip().eq("Therapeutic Exposed")
    frequency = pd.to_numeric(clinical["Frequency of ADA+ patients"], errors="coerce")
    sequence_available = candidate["sequence_length_proxy"].notna()
    dose_available = candidate["dose_level_proxy"].notna()
    interval_available = candidate["dose_interval_days_proxy"].notna()
    year_available = candidate["trial_year_completed"].notna()
    return pd.DataFrame(
        [
            (1, "Raw ADA-frequency rows", len(clinical), "User original IDC DB V1 / Clinical Trial"),
            (2, "Therapeutic Exposed", int(exposed.sum()), "Paper population rule"),
            (3, "Exposed with non-missing ADA frequency", int((exposed & frequency.notna()).sum()), "Binary outcome available"),
            (4, "Sequence-length proxy available", int(sequence_available.sum()), "Not the paper epitope count"),
            (5, "Dose proxy parsed", int(dose_available.sum()), "Regex + stated body-size assumptions"),
            (6, "Dose-interval proxy parsed", int(interval_available.sum()), "Regex/list cadence parser"),
            (7, "Trial completion year available", int(year_available.sum()), "Trial End Date"),
            (8, "Complete public-data proxy model", len(proxy_frame), "All eight proxy fields complete"),
            (9, "Paper-inferred exact complete cases", 1216, "Inferred from Table S6 residual df"),
        ],
        columns=["step", "criterion", "rows", "note"],
    )


def manual_review_template(candidate: pd.DataFrame) -> pd.DataFrame:
    columns = {
        "replication_row_key": candidate["replication_row_key"],
        "IDC Row identifier": candidate["IDC Row identifier"],
        "therapeutic_moa_type": candidate["therapeutic_moa_type_proxy"],
        "disease_indication_group": candidate["disease_indication_group_proxy"],
        "t_cell_epitope_content": np.nan,
        "dose_interval_days": candidate["dose_interval_days_proxy"],
        "route_group": candidate["route_group_proxy"],
        "comedication_moa_type": candidate["comedication_moa_type_proxy"],
        "dose_level": candidate["dose_level_proxy"],
        "trial_year_completed": candidate["trial_year_completed"],
        "review_status": "UNREVIEWED_PROXY_ONLY",
        "mapping_source": "public-data deterministic proxy; replace with author-derived values",
        "reviewer": "",
        "Therapeutic Assessed for ADA ID": candidate["Therapeutic Assessed for ADA ID"],
        "Molecule Assessed for ADA INN Name": candidate["Molecule Assessed for ADA INN Name"],
        "Mechanism of Action": candidate["Mechanism of Action"],
        "Target(s) (Protein/Molecule)": candidate["Target(s) (Protein/Molecule)"],
        "Disease Indication Category": candidate["Disease Indication Category"],
        "Disease Indication Description": candidate["Disease Indication Description"],
        "Co-administered drugs": candidate["Co-administered drugs"],
        "Dosing Description": candidate["Dosing Description"],
        "Therapeutic Dosing Schedule Description": candidate["Therapeutic Dosing Schedule Description"],
        "dose_unit_parsed": candidate["dose_unit_parsed"],
        "dose_proxy_assumption": candidate["dose_proxy_assumption"],
        "interval_parse_rule": candidate["interval_parse_rule"],
    }
    return pd.DataFrame(columns)


def duplicate_id_audit(candidate: pd.DataFrame) -> pd.DataFrame:
    """Expose repeated public source identifiers without silently dropping rows."""
    columns = [
        "replication_row_key",
        "source_excel_row",
        "IDC Row identifier",
        "Trial ID",
        "External Source Identifier",
        "Molecule Assessed for ADA INN Name",
        "Therapeutic Assessed for ADA ID",
        "ada_frequency_percent",
        "Disease Indication Description",
        "Dosing Description",
        "Therapeutic Dosing Schedule Description",
        "Therapeutic Route of Administration",
    ]
    duplicated = candidate["IDC Row identifier"].duplicated(keep=False)
    return candidate.loc[duplicated, columns].sort_values(
        ["IDC Row identifier", "source_excel_row"], kind="stable"
    )


def comparison_table(paper: pd.DataFrame, reproduced: pd.DataFrame, label: str) -> pd.DataFrame:
    right = reproduced.rename(
        columns={
            "df": f"{label}_df",
            "deviance": f"{label}_deviance",
            "residual_df": f"{label}_residual_df",
            "residual_deviance": f"{label}_residual_deviance",
            "p_value": f"{label}_p_value",
            "n_complete": f"{label}_n_complete",
        }
    )
    keep = [
        "variable",
        f"{label}_df",
        f"{label}_deviance",
        f"{label}_residual_df",
        f"{label}_residual_deviance",
        f"{label}_p_value",
        f"{label}_n_complete",
    ]
    merged = paper.merge(right[keep], on="variable", how="left", validate="one_to_one")
    merged[f"{label}_minus_paper_deviance"] = merged[f"{label}_deviance"] - merged["deviance"]
    merged["interpretation"] = (
        "Proxy comparison only; mismatch is expected because author-derived fields and code are unavailable."
        if label == "proxy"
        else "Strict result; investigate any non-zero difference."
    )
    return merged


def category_counts(candidate: pd.DataFrame, proxy_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    mappings = [
        ("Therapeutic Immune MOA Type", "therapeutic_moa_type_proxy", "moa"),
        ("Disease Indication", "disease_indication_group_proxy", "disease"),
        ("Comedication Immune MOA Type", "comedication_moa_type_proxy", "comed"),
        ("Route of Administration", "route_group_proxy", "route"),
    ]
    for variable, candidate_column, model_column in mappings:
        candidate_counts = candidate[candidate_column].value_counts(dropna=False)
        complete_counts = proxy_frame[model_column].value_counts(dropna=False)
        levels = sorted(set(candidate_counts.index.astype(str)).union(complete_counts.index.astype(str)))
        for level in levels:
            rows.append(
                {
                    "variable": variable,
                    "level": level,
                    "candidate_rows": int(candidate_counts.get(level, 0)),
                    "proxy_complete_case_rows": int(complete_counts.get(level, 0)),
                }
            )
    return pd.DataFrame(rows)


def make_figure(paper: pd.DataFrame, proxy: pd.DataFrame | None, target: Path) -> None:
    ordered = paper.sort_values("display_rank", ascending=False).copy()
    labels = ordered["variable"].tolist()
    y = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(10.8, 6.2))
    if proxy is not None and not proxy.empty:
        proxy_values = ordered["variable"].map(proxy.set_index("variable")["deviance"])
        ax.barh(y - 0.18, ordered["deviance"], height=0.34, color="#17365D", label="Published Table S6")
        ax.barh(y + 0.18, proxy_values, height=0.34, color="#D97706", label="Public-data proxy")
        ax.legend(frameon=False, loc="lower right")
    else:
        ax.barh(y, ordered["deviance"], height=0.55, color="#17365D")
    ax.set_yticks(y, labels)
    ax.set_xlabel("Sequential reduction in model deviance")
    ax.set_title("IDC Figure 6 replication audit")
    ax.grid(axis="x", alpha=0.25)
    ax.spines[["top", "right", "left"]].set_visible(False)
    fig.text(
        0.01,
        0.01,
        "The orange series is an explicitly non-exact proxy; it substitutes sequence length and deterministic text mappings for unpublished author-derived variables.",
        fontsize=8.5,
        color="#6B7280",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(target, dpi=300, bbox_inches="tight")
    plt.close(fig)


def dataframe_to_markdown(frame: pd.DataFrame, float_digits: int = 6) -> str:
    def render(value: object) -> str:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return ""
        if isinstance(value, (float, np.floating)):
            return f"{float(value):.{float_digits}g}"
        return str(value).replace("|", "\\|").replace("\n", " ")

    headers = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend(
        "| " + " | ".join(render(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    )
    return "\n".join(lines)


def write_report(
    manifest: pd.DataFrame,
    funnel: pd.DataFrame,
    proxy_results: pd.DataFrame,
    exact_results: pd.DataFrame | None,
    exact_status: str,
    proxy_frame: pd.DataFrame,
) -> None:
    proxy_rank = proxy_results.sort_values("deviance", ascending=False)[
        ["variable", "deviance", "p_value"]
    ]
    top_proxy = proxy_rank.iloc[0]
    exact_message = (
        f"严格复现已运行，完整案例数为 {int(exact_results['n_complete'].iloc[0]):,}。"
        if exact_results is not None
        else "严格复现未运行：公开材料缺少作者生成的逐行派生变量与分析代码。"
    )
    report = f"""# IDC 论文复现报告：Figure 6 / Table S6

生成时间：{datetime.now(timezone.utc).isoformat()}

## 结论

已建立与现有随机森林、TabPFN 完全分离的 `paper_replication` 流程。{exact_message}

- 严格复现状态：`{exact_status}`
- 公开数据代理运行：完成，完整案例 {len(proxy_frame):,} 行；论文由残差自由度反推为 1,216 行。
- 代理模型中 deviance 最大的变量是 `{top_proxy['variable']}`（{top_proxy['deviance']:.3f}）。该排序不能作为论文结论的复现，因为 T-cell epitope、MOA、合并用药、剂量和间隔均使用了公开数据代理。
- 论文 Table S6 的残差自由度序列支持 Type-I（顺序）deviance；论文图按 deviance 大小展示，但模型加入顺序是：T-cell epitope → disease → therapeutic MOA → comedication → dose → interval → year → route。

## 为什么不能直接得到论文相同数值

作者公开了 IDC DS V1 原始表和聚合表，但没有公开 Figure 6 的分析代码，也没有公开以下逐行派生变量：NetMHCIIpan-4.3/OAS 过滤后的 T-cell epitope 数、四类 therapeutic immune MOA、五类疾病、三类合并用药、统一剂量、统一给药间隔。论文方法描述足以定义科学意图，但不足以唯一重建 1,216 行设计矩阵。

当前流程因此设置了严格闸门：只有把作者派生变量放入 `paper_replication/data/manual/paper_derived_variables.csv`，`--mode exact` 才会运行；缺字段、重复主键或样本数不符时会明确失败，而不会把代理结果伪装成精确复现。

## 公开数据代理实现

- 仅保留 `Therapeutic Exposed` 且 ADA frequency 非缺失的行，按 `<10%` / `>=10%` 构造二分类结局。
- 疾病映射为论文 Figure 4 的五组；肿瘤依据疾病描述中的血液系统关键词分为 hematological malignancy 与 solid tumor。
- therapeutic MOA 与 comedication 用透明关键词规则映射，供定位差异，不视为作者标签。
- 剂量从自由文本提取质量单位；`mg/kg` 采用 70 kg、`mg/m2` 采用 1.8 m2 的代理换算，均在逐行表中保留假设说明。
- 给药间隔从 `q2w`、`every N weeks`、weekly、给药日/周列表等表达式解析。
- 未公开的 T-cell epitope 数不被臆造；代理模型明确使用总序列长度，严格模式必须替换为作者方法的 epitope count。
- 使用 logistic GLM，并按 Table S6 残差自由度反推顺序计算逐项 deviance reduction 与卡方 p 值。

## 样本漏斗

{dataframe_to_markdown(funnel)}

## 代理结果（不可当作精确复现）

{dataframe_to_markdown(proxy_rank)}

## 来源与版本

- 最终论文与方法：[Frontiers 文章]({PAPER_URL})
- 作者数据仓库：[IDC-DB GitHub]({GITHUB_URL})，冻结提交 `{GITHUB_COMMIT}`
- Frontiers 的 Data Sheet 1 与 Table 1/2 已保存到 `paper_replication/data/raw/`，哈希见结果工作簿 `Source_Manifest`。
- 用户提供的 bioRxiv PDF 也已纳入哈希审计；Table S6 数值与最终 Frontiers 补充材料一致。

## 下一步获得严格复现所需材料

1. 优先向作者索取 Figure 6 的逐行分析表或脚本，尤其是 epitope count 与三类人工分组列。
2. 将逐行值填入生成的 `outputs/paper_replication/artifacts/manual_review_template.csv`，完成后保存为 `paper_replication/data/manual/paper_derived_variables.csv`。使用 `replication_row_key` 作为唯一键；公开表中的 `IDC Row identifier` 存在重复，保留作来源审计。
3. 运行 `.venv\\Scripts\\python.exe paper_replication\\run_replication.py --mode exact`。
4. 核对完整案例 N=1,216、最终 residual df=1,199，以及每项 df/deviance/p 值；若不同，先检查模型顺序和缺失值口径，不调整结果来迎合论文。
"""
    (OUTPUT_DIR / "IDC_paper_replication_report.md").write_text(report, encoding="utf-8")

    log = f"""# IDC paper_replication 工作日志

## {datetime.now(timezone.utc).isoformat()} — 建立独立复现流程

1. 冻结来源：Frontiers Data Sheet 1、Table 1、Table 2；作者 GitHub V1.00 commit `{GITHUB_COMMIT}`；用户提供 bioRxiv PDF。
2. 验证数据规模：218 therapeutics、222 sequence rows、3,334 ADA-frequency rows；公开数据与论文 Figure 1 数量口径一致。
3. 锁定方法：ADA `<10%` / `>=10%`；8 个因素；Table S6 残差自由度反推 1,216 完整案例及 Type-I 公式顺序。
4. 识别复现阻断：作者未公开逐行 epitope count、MOA/疾病/合并用药映射、剂量/间隔派生规则及分析代码。
5. 实现严格闸门：`{MANUAL_FILE.relative_to(ROOT)}` 不存在或不合格时，严格复现不运行。
6. 实现公开数据代理：所有替代变量均带 proxy 标识与逐行解析说明；代理结果不覆盖、不替代论文结果。
7. 完成顺序 deviance logistic GLM；代理完整案例数 {len(proxy_frame):,}，严格状态 `{exact_status}`。
8. 生成样本漏斗、来源哈希、字段可用性、逐行审核模板、Table S6 对照和 Figure 6 审计图。

## 关键分析点

- Figure 6 的“重要性”是顺序 deviance contribution，不是随机森林/TabPFN 的 feature importance，两者不能直接比较。
- 顺序 deviance 依赖公式顺序；交换 disease 与 MOA 等项会改变数值。
- 论文图按 deviance 排序，Table S6 的 residual df 才暴露实际加入顺序。
- 精确复现的首要瓶颈是作者派生设计矩阵，不是更换模型或继续调参。
- 公开 Clinical Trial 表在本分析候选中有重复 `IDC Row identifier`；流程不静默删除，而是使用来源行号构造唯一 `replication_row_key`，由作者分析行表决定最终保留口径。
"""
    (OUTPUT_DIR / "IDC_paper_replication_work_log.md").write_text(log, encoding="utf-8")


def append_robustness_sections(
    order_summary: pd.DataFrame,
    drop_one: pd.DataFrame,
    missingness: pd.DataFrame,
    balance: pd.DataFrame,
) -> None:
    report_addition = f"""

## 复现差异定位与稳健性诊断

本节仅评估公开数据代理结果的稳定性，不改变严格复现状态，也不把代理分析解释为论文结果。

### 顺序敏感性

对每个变量分别执行“最先进入”和“最后进入”模型的确定性场景，并保留论文残差自由度所推断的原始顺序。Type-I deviance 的变化范围如下：

{dataframe_to_markdown(order_summary[["variable", "proxy_paper_order_deviance", "minimum_deviance", "median_deviance", "maximum_deviance", "deviance_range", "range_to_paper_order_ratio"]])}

### 完整模型逐项删减检验

下表是在固定 1,443 行代理完整案例上，从完整模型中逐项删除变量所得的 likelihood-ratio deviance。它不依赖进入顺序，但仍依赖公开代理变量定义。

{dataframe_to_markdown(drop_one[["variable", "df", "conditional_deviance", "p_value", "n_complete"]])}

### 代理字段完整性

{dataframe_to_markdown(missingness)}

### ADA 结局分布

{dataframe_to_markdown(balance)}
"""
    report_path = OUTPUT_DIR / "IDC_paper_replication_report.md"
    report_path.write_text(
        report_path.read_text(encoding="utf-8") + report_addition,
        encoding="utf-8",
    )

    log_addition = f"""

## 复现差异定位阶段

9. 在固定代理完整案例 N={int(drop_one['n_complete'].iloc[0]):,} 上运行确定性顺序敏感性分析：每个变量分别置于首位和末位，并保留论文推断顺序。
10. 运行完整模型逐项删减 likelihood-ratio 检验，提供不受变量进入顺序影响的条件贡献；该结果仍明确标记为公开数据代理。
11. 生成逐字段缺失率与 ADA 高低组分布，量化候选集到完整案例集的选择差异。
12. 新增 `order_sensitivity_summary.csv`、`order_sensitivity_runs.csv`、`drop_one_lrt.csv`、`proxy_missingness.csv`、`outcome_balance.csv` 和 `robustness_comparison.csv`，并纳入结果工作簿。
"""
    log_path = OUTPUT_DIR / "IDC_paper_replication_work_log.md"
    log_path.write_text(
        log_path.read_text(encoding="utf-8") + log_addition,
        encoding="utf-8",
    )


def append_user_source_validation(source_comparison: pd.DataFrame) -> None:
    compact = source_comparison[[
        "comparator_id",
        "binary_identical_to_user",
        "all_sheet_values_identical_to_user",
        "sheet",
        "user_rows",
        "comparator_rows",
        "user_columns",
        "comparator_columns",
        "exact_cell_values",
        "differing_cells",
    ]]
    report_addition = f"""

## 用户提供原始数据集验证

已将用户提供的 `IDC_DB_V1_All_Tables.xlsx` 冻结复制到 `paper_replication/data/raw/User_IDC_DB_V1_All_Tables.xlsx`，并改为 all-tables 数据提取的主输入。

- 用户文件与作者 GitHub V1.00 文件大小、二进制 SHA-256 完全一致。
- Frontiers Table 2 的 Excel 容器哈希不同，但六张工作表的维度和全部单元格值均与用户文件一致，差异单元格数为 0。
- 因此切换到用户原始文件不会改变治疗药物、序列或临床试验记录；它只强化了来源链和本地可迁移性。

{dataframe_to_markdown(compact)}
"""
    report_path = OUTPUT_DIR / "IDC_paper_replication_report.md"
    report_path.write_text(
        report_path.read_text(encoding="utf-8") + report_addition,
        encoding="utf-8",
    )

    log_path = OUTPUT_DIR / "IDC_paper_replication_work_log.md"
    log_addition = """

## 用户原始数据集接入

13. 接收用户提供的 `D:/DownLoads/IDC_DB_V1_All_Tables.xlsx`，复制为项目冻结源文件，不修改原始文件。
14. 二进制验证：用户文件与作者 GitHub V1.00 all-tables 文件大小和 SHA-256 完全一致。
15. 工作表级验证：Frontiers Table 2 虽容器哈希不同，但 Licensing、Therapeutic、Sequence、Clinical Trial、Variables Explained、Controlled Language 六表维度与全部单元格值一致，差异单元格数均为 0。
16. 将 all-tables 提取主输入切换为用户冻结副本；聚合表仍使用已冻结的 Frontiers Table 1。
"""
    log_path.write_text(
        log_path.read_text(encoding="utf-8") + log_addition,
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    (REPLICATION_DIR / "data" / "manual").mkdir(parents=True, exist_ok=True)

    clinical = load_records("clinical_trial")
    therapeutic = load_records("therapeutic")
    sequence = load_records("sequence")
    candidate = prepare_public_candidate(clinical, therapeutic, sequence)
    proxy_frame = modeling_frame_from_proxy(candidate)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        proxy_results = sequential_deviance(proxy_frame, "public_data_proxy")
        order_summary, order_details = order_sensitivity(proxy_frame)
        drop_one = drop_one_likelihood_ratio(proxy_frame)

    missingness = proxy_missingness(candidate, proxy_frame)
    balance = outcome_balance(candidate, proxy_frame)

    paper = pd.read_csv(CONFIG_DIR / "paper_table_s6.csv")
    proxy_comparison = comparison_table(paper, proxy_results, "proxy")
    robustness_comparison = (
        paper[["variable", "deviance"]]
        .rename(columns={"deviance": "published_sequential_deviance"})
        .merge(
            proxy_results[["variable", "deviance"]].rename(
                columns={"deviance": "proxy_sequential_deviance"}
            ),
            on="variable",
            validate="one_to_one",
        )
        .merge(
            drop_one[["variable", "conditional_deviance"]].rename(
                columns={"conditional_deviance": "proxy_conditional_deviance"}
            ),
            on="variable",
            validate="one_to_one",
        )
        .merge(
            order_summary[[
                "variable",
                "minimum_deviance",
                "maximum_deviance",
                "deviance_range",
                "range_to_paper_order_ratio",
            ]],
            on="variable",
            validate="one_to_one",
        )
    )
    exact_results: pd.DataFrame | None = None
    exact_status = "BLOCKED_EXACT_SOURCE_FIELDS"

    should_run_exact = args.mode == "exact" or (args.mode == "auto" and MANUAL_FILE.exists())
    if should_run_exact:
        if not MANUAL_FILE.exists():
            raise FileNotFoundError(
                f"Exact mode requires {MANUAL_FILE}. Use the generated manual-review template."
            )
        exact_frame = modeling_frame_from_exact(candidate, MANUAL_FILE)
        if len(exact_frame) != 1216 and not args.allow_sample_mismatch:
            raise ValueError(
                f"Exact complete-case N is {len(exact_frame)}, expected 1216 from Table S6. "
                "Resolve the row-selection/derived-variable mismatch or rerun with "
                "--allow-sample-mismatch for diagnosis only."
            )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            exact_results = sequential_deviance(exact_frame, "strict_exact_candidate")
        exact_results.to_csv(ARTIFACT_DIR / "exact_table_s6.csv", index=False)
        comparison_table(paper, exact_results, "exact").to_csv(
            ARTIFACT_DIR / "exact_table_s6_comparison.csv", index=False
        )
        exact_status = "COMPLETED_STRICT_CANDIDATE"

    manifest = source_manifest()
    source_comparison_path = ARTIFACT_DIR / "source_workbook_value_comparison.csv"
    frozen_source_comparison = PROCESSED_DIR / "source_workbook_value_comparison.csv"
    # The original audit was performed with the workbook rendering runtime.
    # A frozen machine-readable result is bundled so the statistical workflow
    # remains portable when that optional runtime is unavailable.
    if not source_comparison_path.exists() and frozen_source_comparison.exists():
        source_comparison_path = frozen_source_comparison
    if not source_comparison_path.exists():
        raise FileNotFoundError(
            "Missing the source workbook value comparison. Run the artifact-tool "
            "source workbook audit or restore data/processed/"
            "source_workbook_value_comparison.csv."
        )
    source_comparison = pd.read_csv(source_comparison_path)
    availability = availability_audit()
    funnel = sample_funnel(clinical, candidate, proxy_frame)
    categories = category_counts(candidate, proxy_frame)
    review_template = manual_review_template(candidate)
    duplicate_audit = duplicate_id_audit(candidate)

    manifest.to_csv(ARTIFACT_DIR / "source_manifest.csv", index=False)
    source_comparison.to_csv(ARTIFACT_DIR / "source_workbook_value_comparison.csv", index=False)
    availability.to_csv(ARTIFACT_DIR / "source_availability.csv", index=False)
    funnel.to_csv(ARTIFACT_DIR / "sample_funnel.csv", index=False)
    paper.to_csv(ARTIFACT_DIR / "paper_table_s6.csv", index=False)
    proxy_results.to_csv(ARTIFACT_DIR / "proxy_table_s6.csv", index=False)
    proxy_comparison.to_csv(ARTIFACT_DIR / "table_s6_comparison.csv", index=False)
    categories.to_csv(ARTIFACT_DIR / "category_levels.csv", index=False)
    review_template.to_csv(ARTIFACT_DIR / "manual_review_template.csv", index=False)
    duplicate_audit.to_csv(ARTIFACT_DIR / "duplicate_idc_row_identifiers.csv", index=False)
    order_summary.to_csv(ARTIFACT_DIR / "order_sensitivity_summary.csv", index=False)
    order_details.to_csv(ARTIFACT_DIR / "order_sensitivity_runs.csv", index=False)
    drop_one.to_csv(ARTIFACT_DIR / "drop_one_lrt.csv", index=False)
    missingness.to_csv(ARTIFACT_DIR / "proxy_missingness.csv", index=False)
    balance.to_csv(ARTIFACT_DIR / "outcome_balance.csv", index=False)
    robustness_comparison.to_csv(ARTIFACT_DIR / "robustness_comparison.csv", index=False)

    candidate_export_columns = [
        "replication_row_key",
        "source_excel_row",
        "IDC Row identifier",
        "Trial ID",
        "External Source Identifier",
        "Molecule Assessed for ADA INN Name",
        "Therapeutic Assessed for ADA ID",
        "ada_frequency_percent",
        "high_ada",
        "therapeutic_moa_type_proxy",
        "disease_indication_group_proxy",
        "sequence_length_proxy",
        "dose_interval_days_proxy",
        "route_group_proxy",
        "comedication_moa_type_proxy",
        "dose_level_proxy",
        "trial_year_completed",
        "dose_unit_parsed",
        "dose_proxy_assumption",
        "interval_parse_rule",
    ]
    candidate[candidate_export_columns].to_csv(
        ARTIFACT_DIR / "analytic_candidate_proxy.csv", index=False
    )

    make_figure(paper, proxy_results, FIGURE_DIR / "figure6_published_vs_proxy.png")
    write_report(manifest, funnel, proxy_results, exact_results, exact_status, proxy_frame)
    append_robustness_sections(order_summary, drop_one, missingness, balance)
    append_user_source_validation(source_comparison)

    metadata = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "mode_requested": args.mode,
        "exact_status": exact_status,
        "proxy_status": "COMPLETED_PUBLIC_DATA_PROXY",
        "paper_expected_complete_cases": 1216,
        "proxy_complete_cases": int(len(proxy_frame)),
        "raw_clinical_rows": int(len(clinical)),
        "candidate_rows": int(len(candidate)),
        "candidate_duplicate_idc_row_identifier_rows": int(
            candidate["IDC Row identifier"].duplicated(keep=False).sum()
        ),
        "order_sensitivity_scenarios": int(order_details["scenario_id"].nunique()),
        "drop_one_full_model_residual_df": int(drop_one["full_model_residual_df"].iloc[0]),
        "user_source_binary_matches_author_github": bool(
            source_comparison.loc[
                source_comparison["comparator_id"].eq("author_github_v1_00"),
                "binary_identical_to_user",
            ].all()
        ),
        "user_source_values_match_frontiers": bool(
            source_comparison.loc[
                source_comparison["comparator_id"].eq("frontiers_table_2"),
                "exact_cell_values",
            ].all()
        ),
        "paper_url": PAPER_URL,
        "github_url": GITHUB_URL,
        "github_commit": GITHUB_COMMIT,
        "paper_table_s6_unchanged_between_user_preprint_and_frontiers_supplement": True,
    }
    (ARTIFACT_DIR / "replication_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    payload = {
        "metadata": metadata,
        "tables": {
            "Source_Manifest": manifest.replace({np.nan: None}).to_dict(orient="records"),
            "Source_Comparison": source_comparison.replace({np.nan: None}).to_dict(orient="records"),
            "Source_Availability": availability.replace({np.nan: None}).to_dict(orient="records"),
            "Sample_Funnel": funnel.replace({np.nan: None}).to_dict(orient="records"),
            "Paper_Table_S6": paper.replace({np.nan: None}).to_dict(orient="records"),
            "Proxy_Table_S6": proxy_results.replace({np.nan: None}).to_dict(orient="records"),
            "S6_Comparison": proxy_comparison.replace({np.nan: None}).to_dict(orient="records"),
            "Category_Levels": categories.replace({np.nan: None}).to_dict(orient="records"),
            "Duplicate_ID_Audit": duplicate_audit.replace({np.nan: None}).to_dict(orient="records"),
            "Robustness_Comparison": robustness_comparison.replace({np.nan: None}).to_dict(orient="records"),
            "Order_Sensitivity": order_summary.replace({np.nan: None}).to_dict(orient="records"),
            "Order_Scenarios": order_details.replace({np.nan: None}).to_dict(orient="records"),
            "Drop_One_LRT": drop_one.replace({np.nan: None}).to_dict(orient="records"),
            "Proxy_Missingness": missingness.replace({np.nan: None}).to_dict(orient="records"),
            "Outcome_Balance": balance.replace({np.nan: None}).to_dict(orient="records"),
            "Manual_Review": review_template.replace({np.nan: None}).to_dict(orient="records"),
            "Analytic_Candidate": candidate[candidate_export_columns]
            .replace({np.nan: None})
            .to_dict(orient="records"),
        },
    }
    (ARTIFACT_DIR / "workbook_payload.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
