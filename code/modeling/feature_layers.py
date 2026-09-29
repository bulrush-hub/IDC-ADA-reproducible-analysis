"""Three-layer feature taxonomy for IDC ADA prediction.

The locked baseline still uses the same 29 predictors and the same column order.
This module adds a research-oriented interpretation layer without silently
changing the already evaluated model.  New candidate fields are listed
separately and must be evaluated on development data before promotion.
"""

from __future__ import annotations

from collections.abc import Iterable


# Layer 1: properties of the biologic itself.  These are the starting point for
# future sequence-based or structure-aware ADA prediction.
MOLECULAR_CATEGORICAL_FEATURES = [
    "protein_modality",
    "species",
    "antibody_backbone_clean",
    "light_chain_clean",
    "conjugate_modification_clean",
    "target_group",
    "moa_group",
    "labelled_as_biosimilar",
    "sequence_verified",
]
MOLECULAR_NUMERIC_FEATURES = [
    "log_total_sequence_length",
    "n_sequence_chains",
    "n_unique_sequences",
    "max_chain_length",
]
MOLECULAR_BINARY_FEATURES = ["sequence_available"]
BASELINE_MOLECULAR_FEATURES = (
    MOLECULAR_CATEGORICAL_FEATURES
    + MOLECULAR_NUMERIC_FEATURES
    + MOLECULAR_BINARY_FEATURES
)


# Layer 2: treatment and patient context.  These variables address when the
# same biologic is more likely to be observed with ADA in clinical use.
CLINICAL_CATEGORICAL_FEATURES = [
    "disease_category_clean",
    "route_clean",
]
CLINICAL_NUMERIC_FEATURES = ["log_dose_mg_extracted"]
CLINICAL_BINARY_FEATURES = [
    "has_coadministered_drugs",
    "comedication_missing",
    "dose_mg_missing",
]
BASELINE_CLINICAL_FEATURES = (
    CLINICAL_CATEGORICAL_FEATURES
    + CLINICAL_NUMERIC_FEATURES
    + CLINICAL_BINARY_FEATURES
)


# Layer 3: study design and measurement opportunity.  These variables address
# how likely a study is to detect or report ADA, rather than molecular biology.
MEASUREMENT_CATEGORICAL_FEATURES = [
    "ada_assay_platform",
    "prospective_or_retrospective",
    "randomized_or_not",
    "trial_blinding",
    "therapeutic_comparator",
]
MEASUREMENT_NUMERIC_FEATURES = [
    "log_n_ada_assessed",
    "log_assessment_days",
]
MEASUREMENT_BINARY_FEATURES = [
    "ada_assay_missing",
    "ada_assay_sensitivity_missing",
]
BASELINE_MEASUREMENT_FEATURES = (
    MEASUREMENT_CATEGORICAL_FEATURES
    + MEASUREMENT_NUMERIC_FEATURES
    + MEASUREMENT_BINARY_FEATURES
)


# Preserve the historical baseline order exactly.  Random-forest and TabPFN
# results can depend on column order, so layer labels must not silently reorder
# the locked 29-feature benchmark.
PRIMARY_CATEGORICAL_FEATURES = [
    "disease_category_clean",
    "route_clean",
    "protein_modality",
    "species",
    "antibody_backbone_clean",
    "light_chain_clean",
    "conjugate_modification_clean",
    "target_group",
    "moa_group",
    "ada_assay_platform",
    "prospective_or_retrospective",
    "randomized_or_not",
    "trial_blinding",
    "therapeutic_comparator",
    "labelled_as_biosimilar",
    "sequence_verified",
]
PRIMARY_BINARY_FEATURES = [
    "has_coadministered_drugs",
    "comedication_missing",
    "dose_mg_missing",
    "sequence_available",
    "ada_assay_missing",
    "ada_assay_sensitivity_missing",
]
PRIMARY_NUMERIC_FEATURES = [
    "log_n_ada_assessed",
    "log_assessment_days",
    "log_dose_mg_extracted",
    "log_total_sequence_length",
    "n_sequence_chains",
    "n_unique_sequences",
    "max_chain_length",
]
PRIMARY_FEATURES = (
    PRIMARY_CATEGORICAL_FEATURES
    + PRIMARY_NUMERIC_FEATURES
    + PRIMARY_BINARY_FEATURES
)


FEATURE_LAYER_QUESTIONS = {
    "molecular": (
        "Which properties of the biologic are associated with ADA risk, and "
        "which sequence-derived signals may transfer to unseen molecules?"
    ),
    "clinical": (
        "For the same biologic, in which treatment and patient context is ADA "
        "more likely to be observed?"
    ),
    "measurement": (
        "How likely is this study design and assay process to detect or report ADA?"
    ),
}

# Available columns that are scientifically useful but not part of the locked
# baseline.  They need normalization/derivation and development-only validation
# before being promoted into a new model version.
FUTURE_MOLECULAR_FIELDS = [
    "fc_modifications_clean",
    "expression_system",
    "target_clean",
    "mechanism_of_action_reviewed",
    "heavy_chain_sequence",
    "light_chain_sequence",
    "full_protein_sequence",
]
FUTURE_CLINICAL_FIELDS = [
    "patient_population",
    "dosing_description",
    "dosing_schedule_description",
    "coadministered_drugs",
]
FUTURE_MEASUREMENT_FIELDS = [
    "ada_assay_sensitivity",
    "ada_assay",
]


# Public layer lists include both the locked baseline inputs and the available
# development candidates requested for the next model generation.  Training
# scripts continue to consume PRIMARY_* until a new model version is explicitly
# approved and validated.
MOLECULAR_FEATURES = BASELINE_MOLECULAR_FEATURES + FUTURE_MOLECULAR_FIELDS
CLINICAL_FEATURES = BASELINE_CLINICAL_FEATURES + FUTURE_CLINICAL_FIELDS
MEASUREMENT_FEATURES = BASELINE_MEASUREMENT_FEATURES + FUTURE_MEASUREMENT_FIELDS

FEATURE_LAYER_BY_FEATURE = {
    **{feature: "molecular" for feature in MOLECULAR_FEATURES},
    **{feature: "clinical" for feature in CLINICAL_FEATURES},
    **{feature: "measurement" for feature in MEASUREMENT_FEATURES},
}


_SOURCE_COLUMN = {
    "log_n_ada_assessed": "n_ada_assessed",
    "log_assessment_days": "assessment_days",
    "log_dose_mg_extracted": "dose_mg_extracted",
    "log_total_sequence_length": "total_sequence_length",
}


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicated: set[str] = set()
    for value in values:
        if value in seen:
            duplicated.add(value)
        seen.add(value)
    return sorted(duplicated)


def validate_feature_layers() -> None:
    """Fail early if a feature is missing, duplicated, or assigned twice."""

    all_layered = MOLECULAR_FEATURES + CLINICAL_FEATURES + MEASUREMENT_FEATURES
    all_duplicates = _duplicates(all_layered)
    if all_duplicates:
        raise ValueError(f"Fields assigned to more than one layer: {all_duplicates}")
    layered = (
        BASELINE_MOLECULAR_FEATURES
        + BASELINE_CLINICAL_FEATURES
        + BASELINE_MEASUREMENT_FEATURES
    )
    duplicate_layer_members = _duplicates(layered)
    if duplicate_layer_members:
        raise ValueError(
            f"Features assigned to more than one layer: {duplicate_layer_members}"
        )
    if set(layered) != set(PRIMARY_FEATURES):
        missing = sorted(set(PRIMARY_FEATURES) - set(layered))
        unexpected = sorted(set(layered) - set(PRIMARY_FEATURES))
        raise ValueError(
            f"Layer coverage mismatch; missing={missing}, unexpected={unexpected}"
        )
    if len(PRIMARY_FEATURES) != 29:
        raise ValueError(f"Expected 29 locked baseline features, got {len(PRIMARY_FEATURES)}")


def build_feature_layer_manifest() -> list[dict[str, object]]:
    """Return auditable rows for active inputs and development candidates."""

    feature_type = {
        **{feature: "categorical" for feature in PRIMARY_CATEGORICAL_FEATURES},
        **{feature: "numeric" for feature in PRIMARY_NUMERIC_FEATURES},
        **{feature: "binary_indicator" for feature in PRIMARY_BINARY_FEATURES},
    }
    rows = [
        {
            "feature": feature,
            "source_column": _SOURCE_COLUMN.get(feature, feature),
            "feature_layer": FEATURE_LAYER_BY_FEATURE[feature],
            "feature_type": feature_type[feature],
            "model_status": "locked_baseline_active",
            "research_question": FEATURE_LAYER_QUESTIONS[
                FEATURE_LAYER_BY_FEATURE[feature]
            ],
        }
        for feature in PRIMARY_FEATURES
    ]
    future_by_layer = {
        "molecular": FUTURE_MOLECULAR_FIELDS,
        "clinical": FUTURE_CLINICAL_FIELDS,
        "measurement": FUTURE_MEASUREMENT_FIELDS,
    }
    for layer, features in future_by_layer.items():
        rows.extend(
            {
                "feature": feature,
                "source_column": feature,
                "feature_layer": layer,
                "feature_type": "candidate_raw_or_text",
                "model_status": "development_candidate_not_in_locked_baseline",
                "research_question": FEATURE_LAYER_QUESTIONS[layer],
            }
            for feature in features
        )
    return rows


validate_feature_layers()
