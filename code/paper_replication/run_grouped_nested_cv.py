from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import rankdata

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import run_dedup_scenarios as dedup
import run_replication as base


# Two levels above this file is the portable repository root.
ROOT = Path(__file__).resolve().parents[2]
DEDUP_OUTPUT = ROOT / "outputs" / "paper_replication_dedup_scenarios"
OUTPUT_DIR = ROOT / "outputs" / "paper_replication_grouped_cv"
RESULT_DIR = OUTPUT_DIR / "results"
FIGURE_DIR = OUTPUT_DIR / "figures"
ARTIFACT_DIR = OUTPUT_DIR / "artifacts"

OUTER_FOLDS = 5
INNER_FOLDS = 4
REPEATS = 10
PERMUTATIONS_PER_FOLD = 3
BOOTSTRAP_REPLICATES = 2000
RANDOM_SEED = 20260809
L2_GRID = [0.001, 0.01, 0.1, 1.0, 10.0]

NUMERIC_FEATURES = [
    "sequence_length_proxy",
    "dose_level_proxy",
    "dose_interval_days_proxy",
    "trial_year_completed",
]
CATEGORICAL_FEATURES = [
    "disease_indication_group_proxy",
    "therapeutic_moa_type_proxy",
    "comedication_moa_type_proxy",
    "route_group_proxy",
]
RAW_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
PERMUTATION_FEATURES = [
    ("T cell Epitope Content", "sequence_length_proxy"),
    ("Disease Indication", "disease_indication_group_proxy"),
    ("Therapeutic Immune MOA Type", "therapeutic_moa_type_proxy"),
    ("Comedication Immune MOA Type", "comedication_moa_type_proxy"),
    ("Dose Level", "dose_level_proxy"),
    ("Dose Interval", "dose_interval_days_proxy"),
    ("Year Trial was Completed", "trial_year_completed"),
    ("Route of Administration", "route_group_proxy"),
]

SCENARIO_LABELS = {
    "all_public_rows_grouped": "All public rows (grouped by molecule)",
    "one_row_per_molecule": "One row per molecule",
    "one_row_per_molecule_disease_category": "One row per molecule × disease category",
}


def json_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return frame.replace({np.nan: None}).to_dict(orient="records")


def dataframe_to_markdown(frame: pd.DataFrame, digits: int = 5) -> str:
    def render(value: object) -> str:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return ""
        if isinstance(value, (float, np.floating)):
            return f"{float(value):.{digits}g}"
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(map(str, frame.columns)) + " |",
        "| " + " | ".join(["---"] * len(frame.columns)) + " |",
    ]
    lines.extend(
        "| " + " | ".join(render(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    )
    return "\n".join(lines)


def load_analysis_frames() -> dict[str, pd.DataFrame]:
    clinical = base.load_records("clinical_trial")
    therapeutic = base.load_records("therapeutic")
    sequence = base.load_records("sequence")
    candidate = dedup.add_selection_fields(
        base.prepare_public_candidate(clinical, therapeutic, sequence)
    )
    molecule = pd.read_csv(DEDUP_OUTPUT / "data" / "one_row_per_molecule.csv")
    molecule_disease = pd.read_csv(
        DEDUP_OUTPUT / "data" / "one_row_per_molecule_disease_category.csv"
    )
    frames = {
        "all_public_rows_grouped": candidate,
        "one_row_per_molecule": molecule,
        "one_row_per_molecule_disease_category": molecule_disease,
    }
    complete: dict[str, pd.DataFrame] = {}
    for scenario_id, frame in frames.items():
        data = frame.dropna(subset=dedup.MODEL_REQUIRED_COLUMNS).copy()
        data["high_ada"] = pd.to_numeric(data["high_ada"], errors="raise").astype(int)
        data["molecule_key"] = data["molecule_key"].astype(str)
        if "disease_category_key" not in data.columns:
            data["disease_category_key"] = dedup.normalized_key(
                data["Disease Indication Category"], "<missing disease category>"
            )
        data["analysis_row_index"] = np.arange(len(data), dtype=int)
        complete[scenario_id] = data.reset_index(drop=True)
    return complete


def _fold_assignment_score(
    rows: np.ndarray,
    positives: np.ndarray,
    groups: np.ndarray,
    total_rows: float,
    total_positives: float,
    total_groups: float,
) -> float:
    total_negatives = total_rows - total_positives
    negatives = rows - positives
    positive_share = positives / max(total_positives, 1.0)
    negative_share = negatives / max(total_negatives, 1.0)
    row_share = rows / max(total_rows, 1.0)
    group_share = groups / max(total_groups, 1.0)
    return float(
        np.std(positive_share)
        + np.std(negative_share)
        + 0.20 * np.std(row_share)
        + 0.10 * np.std(group_share)
    )


def stratified_group_folds(
    y: np.ndarray,
    groups: np.ndarray,
    n_splits: int,
    seed: int,
) -> np.ndarray:
    group_frame = pd.DataFrame({"group": groups.astype(str), "y": y.astype(int)})
    stats = (
        group_frame.groupby("group", sort=True)["y"]
        .agg(rows="size", positives="sum")
        .reset_index()
    )
    if len(stats) < n_splits:
        raise ValueError(f"Only {len(stats)} groups are available for {n_splits} folds.")

    total_rows = float(stats["rows"].sum())
    total_positives = float(stats["positives"].sum())
    total_groups = float(len(stats))
    overall_rate = total_positives / total_rows

    for attempt in range(200):
        rng = np.random.default_rng(seed + attempt * 1009)
        work = stats.copy()
        work["difficulty"] = (
            (work["positives"] / work["rows"] - overall_rate).abs()
            * np.sqrt(work["rows"])
        )
        work["jitter"] = rng.random(len(work))
        work = work.sort_values(
            ["difficulty", "rows", "jitter"],
            ascending=[False, False, True],
            kind="stable",
        )

        fold_rows = np.zeros(n_splits, dtype=float)
        fold_positives = np.zeros(n_splits, dtype=float)
        fold_groups = np.zeros(n_splits, dtype=float)
        assignment: dict[str, int] = {}
        for row in work.itertuples(index=False):
            candidate_scores: list[tuple[float, float, int]] = []
            for fold in range(n_splits):
                rows_after = fold_rows.copy()
                positives_after = fold_positives.copy()
                groups_after = fold_groups.copy()
                rows_after[fold] += float(row.rows)
                positives_after[fold] += float(row.positives)
                groups_after[fold] += 1.0
                score = _fold_assignment_score(
                    rows_after,
                    positives_after,
                    groups_after,
                    total_rows,
                    total_positives,
                    total_groups,
                )
                candidate_scores.append((score, fold_rows[fold], fold))
            _, _, best_fold = min(candidate_scores)
            assignment[str(row.group)] = int(best_fold)
            fold_rows[best_fold] += float(row.rows)
            fold_positives[best_fold] += float(row.positives)
            fold_groups[best_fold] += 1.0

        result = np.array([assignment[str(group)] for group in groups], dtype=int)
        valid = True
        for fold in range(n_splits):
            fold_y = y[result == fold]
            if len(fold_y) == 0 or len(np.unique(fold_y)) < 2:
                valid = False
                break
        if valid:
            return result
    raise RuntimeError("Could not construct group-disjoint folds containing both outcomes.")


@dataclass
class Encoder:
    numeric_means: dict[str, float]
    numeric_scales: dict[str, float]
    category_levels: dict[str, list[str]]
    reference_levels: dict[str, str]
    feature_names: list[str]

    @classmethod
    def fit(cls, frame: pd.DataFrame) -> "Encoder":
        numeric_means: dict[str, float] = {}
        numeric_scales: dict[str, float] = {}
        feature_names = list(NUMERIC_FEATURES)
        for column in NUMERIC_FEATURES:
            values = pd.to_numeric(frame[column], errors="raise").to_numpy(float)
            numeric_means[column] = float(values.mean())
            scale = float(values.std(ddof=0))
            numeric_scales[column] = scale if scale > 0 and np.isfinite(scale) else 1.0

        category_levels: dict[str, list[str]] = {}
        reference_levels: dict[str, str] = {}
        for column in CATEGORICAL_FEATURES:
            values = frame[column].astype(str)
            counts = values.value_counts()
            reference = str(counts.index[0])
            levels = [reference] + sorted(str(value) for value in counts.index[1:])
            category_levels[column] = levels
            reference_levels[column] = reference
            feature_names.extend(f"{column}={level}" for level in levels[1:])
        return cls(
            numeric_means=numeric_means,
            numeric_scales=numeric_scales,
            category_levels=category_levels,
            reference_levels=reference_levels,
            feature_names=feature_names,
        )

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        columns: list[np.ndarray] = []
        for column in NUMERIC_FEATURES:
            values = pd.to_numeric(frame[column], errors="raise").to_numpy(float)
            columns.append(
                ((values - self.numeric_means[column]) / self.numeric_scales[column])[:, None]
            )
        for column in CATEGORICAL_FEATURES:
            values = frame[column].astype(str).to_numpy()
            for level in self.category_levels[column][1:]:
                columns.append((values == level).astype(float)[:, None])
        return np.hstack(columns) if columns else np.empty((len(frame), 0))

    def unseen_level_count(self, frame: pd.DataFrame) -> int:
        count = 0
        for column in CATEGORICAL_FEATURES:
            known = set(self.category_levels[column])
            count += int((~frame[column].astype(str).isin(known)).sum())
        return count


def fit_ridge_logistic(
    x: np.ndarray,
    y: np.ndarray,
    l2: float,
    initial: np.ndarray | None = None,
) -> np.ndarray:
    design = np.column_stack([np.ones(len(x)), x])
    y_float = y.astype(float)
    if initial is None or len(initial) != design.shape[1]:
        prevalence = float(np.clip(y_float.mean(), 1e-5, 1 - 1e-5))
        initial = np.zeros(design.shape[1], dtype=float)
        initial[0] = math.log(prevalence / (1 - prevalence))

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        eta = design @ beta
        loss = float(np.mean(np.logaddexp(0.0, eta) - y_float * eta))
        penalty = 0.5 * l2 * float(beta[1:] @ beta[1:])
        residual = expit(eta) - y_float
        gradient = design.T @ residual / len(y_float)
        gradient[1:] += l2 * beta[1:]
        return loss + penalty, gradient

    result = minimize(
        fun=lambda beta: objective(beta)[0],
        x0=initial,
        jac=lambda beta: objective(beta)[1],
        method="L-BFGS-B",
        options={"maxiter": 500, "ftol": 1e-11, "gtol": 1e-8},
    )
    if not result.success and float(np.linalg.norm(result.jac)) > 1e-4:
        raise RuntimeError(f"Ridge logistic optimizer failed: {result.message}")
    return result.x.astype(float)


def predict_probability(x: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    design = np.column_stack([np.ones(len(x)), x])
    return expit(design @ coefficients)


def binary_metrics(
    y: np.ndarray,
    probability: np.ndarray,
    sample_weight: np.ndarray | None = None,
) -> dict[str, float]:
    y = y.astype(int)
    probability = np.clip(probability.astype(float), 1e-8, 1 - 1e-8)
    weight = (
        np.ones(len(y), dtype=float)
        if sample_weight is None
        else np.asarray(sample_weight, dtype=float)
    )
    if len(weight) != len(y) or np.any(weight < 0) or not np.isfinite(weight).all():
        raise ValueError("Invalid metric sample weights.")
    weight_sum = float(weight.sum())
    if weight_sum <= 0:
        raise ValueError("Metric sample weights sum to zero.")
    positive = y == 1
    negative = ~positive
    positive_weight = float(weight[positive].sum())
    negative_weight = float(weight[negative].sum())
    if positive_weight == 0 or negative_weight == 0:
        roc_auc = np.nan
    else:
        order_ascending = np.argsort(probability, kind="stable")
        sorted_probability = probability[order_ascending]
        sorted_y_ascending = y[order_ascending]
        sorted_weight_ascending = weight[order_ascending]
        starts = np.r_[0, np.flatnonzero(np.diff(sorted_probability) != 0) + 1]
        tied_positive_weight = np.add.reduceat(
            sorted_weight_ascending * (sorted_y_ascending == 1), starts
        )
        tied_negative_weight = np.add.reduceat(
            sorted_weight_ascending * (sorted_y_ascending == 0), starts
        )
        cumulative_negative_before = np.cumsum(tied_negative_weight) - tied_negative_weight
        concordant = float(
            np.sum(
                tied_positive_weight
                * (cumulative_negative_before + 0.5 * tied_negative_weight)
            )
        )
        roc_auc = concordant / (positive_weight * negative_weight)

    order = np.argsort(-probability, kind="stable")
    sorted_y = y[order]
    sorted_probability_desc = probability[order]
    sorted_weight = weight[order]
    if positive_weight:
        starts = np.r_[0, np.flatnonzero(np.diff(sorted_probability_desc) != 0) + 1]
        tied_positive_weight = np.add.reduceat(
            sorted_weight * (sorted_y == 1), starts
        )
        tied_total_weight = np.add.reduceat(sorted_weight, starts)
        cumulative_positive = np.cumsum(tied_positive_weight)
        cumulative_weight = np.cumsum(tied_total_weight)
        precision_at_threshold = cumulative_positive / cumulative_weight
        average_precision = float(
            np.sum((tied_positive_weight / positive_weight) * precision_at_threshold)
        )
    else:
        average_precision = np.nan

    predicted = (probability >= 0.5).astype(int)
    true_positive = float(weight[(predicted == 1) & positive].sum())
    true_negative = float(weight[(predicted == 0) & negative].sum())
    sensitivity = true_positive / positive_weight if positive_weight else np.nan
    specificity = true_negative / negative_weight if negative_weight else np.nan
    balanced_accuracy = float(np.nanmean([sensitivity, specificity]))
    prevalence = float(np.average(y, weights=weight))
    return {
        "roc_auc": roc_auc,
        "average_precision": average_precision,
        "balanced_accuracy_0_5": balanced_accuracy,
        "accuracy_0_5": float(np.average(predicted == y, weights=weight)),
        "sensitivity_0_5": float(sensitivity),
        "specificity_0_5": float(specificity),
        "brier_score": float(np.average((probability - y) ** 2, weights=weight)),
        "log_loss": float(-np.average(y * np.log(probability) + (1 - y) * np.log(1 - probability), weights=weight)),
        "mean_predicted_probability": float(np.average(probability, weights=weight)),
        "calibration_gap_predicted_minus_observed": float(np.average(probability, weights=weight) - prevalence),
        "predicted_positive_rate_0_5": float(np.average(predicted, weights=weight)),
    }


def no_skill_references(prevalence: float) -> dict[str, float | None]:
    clipped = float(np.clip(prevalence, 1e-8, 1 - 1e-8))
    return {
        "roc_auc": 0.5,
        "average_precision": prevalence,
        "balanced_accuracy_0_5": 0.5,
        "accuracy_0_5": max(prevalence, 1 - prevalence),
        "sensitivity_0_5": None,
        "specificity_0_5": None,
        "brier_score": prevalence * (1 - prevalence),
        "log_loss": -prevalence * math.log(clipped) - (1 - prevalence) * math.log(1 - clipped),
        "mean_predicted_probability": prevalence,
        "calibration_gap_predicted_minus_observed": 0.0,
        "predicted_positive_rate_0_5": 0.0 if prevalence < 0.5 else 1.0,
    }


METRIC_INTERPRETATION = {
    "roc_auc": "Discrimination; 0.5 is no-skill and 1.0 is perfect.",
    "average_precision": "Precision-recall summary; compare with outcome prevalence.",
    "balanced_accuracy_0_5": "Mean sensitivity and specificity at probability threshold 0.5.",
    "accuracy_0_5": "Ordinary accuracy at 0.5; can be inflated by class imbalance.",
    "sensitivity_0_5": "Fraction of High ADA rows predicted High at threshold 0.5.",
    "specificity_0_5": "Fraction of Low ADA rows predicted Low at threshold 0.5.",
    "brier_score": "Mean squared probability error; lower is better.",
    "log_loss": "Logarithmic probability loss; lower is better.",
    "mean_predicted_probability": "Average out-of-fold predicted High ADA probability.",
    "calibration_gap_predicted_minus_observed": "Mean prediction minus observed prevalence; 0 is ideal.",
    "predicted_positive_rate_0_5": "Fraction classified High ADA at threshold 0.5.",
}


def nested_cv_scenario(
    scenario_id: str,
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    y = frame["high_ada"].to_numpy(int)
    groups = frame["molecule_key"].astype(str).to_numpy()
    prediction_matrix = np.full((len(frame), REPEATS), np.nan, dtype=float)
    repeat_rows: list[dict[str, object]] = []
    tuning_rows: list[dict[str, object]] = []
    fold_rows: list[dict[str, object]] = []
    importance_rows: list[dict[str, object]] = []

    for repeat in range(REPEATS):
        outer_seed = RANDOM_SEED + repeat * 100_003
        outer_assignment = stratified_group_folds(y, groups, OUTER_FOLDS, outer_seed)
        for outer_fold in range(OUTER_FOLDS):
            test_mask = outer_assignment == outer_fold
            train_mask = ~test_mask
            train = frame.loc[train_mask].reset_index(drop=True)
            test = frame.loc[test_mask].reset_index(drop=True)
            train_y = train["high_ada"].to_numpy(int)
            test_y = test["high_ada"].to_numpy(int)
            train_groups = train["molecule_key"].astype(str).to_numpy()
            test_groups = test["molecule_key"].astype(str).to_numpy()
            overlap = len(set(train_groups).intersection(test_groups))
            if overlap:
                raise AssertionError(f"Molecule leakage detected in {scenario_id}.")

            inner_seed = outer_seed + outer_fold * 10_007 + 19
            inner_assignment = stratified_group_folds(
                train_y, train_groups, INNER_FOLDS, inner_seed
            )
            loss_by_l2 = {l2: [] for l2 in L2_GRID}
            for inner_fold in range(INNER_FOLDS):
                inner_valid_mask = inner_assignment == inner_fold
                inner_train = train.loc[~inner_valid_mask].reset_index(drop=True)
                inner_valid = train.loc[inner_valid_mask].reset_index(drop=True)
                encoder = Encoder.fit(inner_train)
                inner_x = encoder.transform(inner_train)
                valid_x = encoder.transform(inner_valid)
                inner_y = inner_train["high_ada"].to_numpy(int)
                valid_y = inner_valid["high_ada"].to_numpy(int)
                initial = None
                for l2 in L2_GRID:
                    coefficients = fit_ridge_logistic(inner_x, inner_y, l2, initial=initial)
                    initial = coefficients
                    probability = predict_probability(valid_x, coefficients)
                    loss = binary_metrics(valid_y, probability)["log_loss"]
                    loss_by_l2[l2].append(float(loss))

            mean_losses = {l2: float(np.mean(values)) for l2, values in loss_by_l2.items()}
            selected_l2 = min(L2_GRID, key=lambda value: (mean_losses[value], value))
            for l2 in L2_GRID:
                tuning_rows.append(
                    {
                        "scenario_id": scenario_id,
                        "repeat": repeat + 1,
                        "outer_fold": outer_fold + 1,
                        "l2_penalty": l2,
                        "mean_inner_log_loss": mean_losses[l2],
                        "selected": l2 == selected_l2,
                    }
                )

            outer_encoder = Encoder.fit(train)
            train_x = outer_encoder.transform(train)
            test_x = outer_encoder.transform(test)
            coefficients = fit_ridge_logistic(train_x, train_y, selected_l2)
            probability = predict_probability(test_x, coefficients)
            prediction_matrix[np.where(test_mask)[0], repeat] = probability
            outer_metrics = binary_metrics(test_y, probability)
            fold_rows.append(
                {
                    "scenario_id": scenario_id,
                    "repeat": repeat + 1,
                    "outer_fold": outer_fold + 1,
                    "train_rows": len(train),
                    "test_rows": len(test),
                    "train_groups": int(pd.Series(train_groups).nunique()),
                    "test_groups": int(pd.Series(test_groups).nunique()),
                    "train_positive_rows": int(train_y.sum()),
                    "test_positive_rows": int(test_y.sum()),
                    "group_overlap": overlap,
                    "unseen_categorical_values_in_test": outer_encoder.unseen_level_count(test),
                    "selected_l2_penalty": selected_l2,
                    "test_roc_auc": outer_metrics["roc_auc"],
                    "test_average_precision": outer_metrics["average_precision"],
                    "test_brier_score": outer_metrics["brier_score"],
                    "test_log_loss": outer_metrics["log_loss"],
                }
            )

            baseline_log_loss = outer_metrics["log_loss"]
            for feature_index, (feature_label, source_column) in enumerate(PERMUTATION_FEATURES):
                for permutation in range(PERMUTATIONS_PER_FOLD):
                    permutation_seed = (
                        outer_seed
                        + outer_fold * 1009
                        + feature_index * 97
                        + permutation * 17
                    )
                    rng = np.random.default_rng(permutation_seed)
                    permuted = test.copy()
                    permuted[source_column] = rng.permutation(
                        permuted[source_column].to_numpy()
                    )
                    permuted_probability = predict_probability(
                        outer_encoder.transform(permuted), coefficients
                    )
                    permuted_log_loss = binary_metrics(
                        test_y, permuted_probability
                    )["log_loss"]
                    importance_rows.append(
                        {
                            "scenario_id": scenario_id,
                            "repeat": repeat + 1,
                            "outer_fold": outer_fold + 1,
                            "permutation": permutation + 1,
                            "variable": feature_label,
                            "source_column": source_column,
                            "baseline_log_loss": baseline_log_loss,
                            "permuted_log_loss": permuted_log_loss,
                            "delta_log_loss": permuted_log_loss - baseline_log_loss,
                        }
                    )

        if np.isnan(prediction_matrix[:, repeat]).any():
            raise AssertionError(f"Incomplete OOF predictions in {scenario_id}, repeat {repeat + 1}.")
        repeat_metrics = binary_metrics(y, prediction_matrix[:, repeat])
        repeat_rows.append(
            {
                "scenario_id": scenario_id,
                "repeat": repeat + 1,
                "n_rows": len(frame),
                "n_groups": int(pd.Series(groups).nunique()),
                "positive_rows": int(y.sum()),
                "prevalence": float(y.mean()),
                **repeat_metrics,
            }
        )
        print(
            f"{scenario_id}: repeat {repeat + 1}/{REPEATS} "
            f"AUC={repeat_metrics['roc_auc']:.3f} AP={repeat_metrics['average_precision']:.3f}",
            flush=True,
        )

    mean_probability = prediction_matrix.mean(axis=1)
    sd_probability = prediction_matrix.std(axis=1, ddof=1)
    prediction_rows = pd.DataFrame(
        {
            "scenario_id": scenario_id,
            "analysis_row_index": frame["analysis_row_index"],
            "replication_row_key": frame["replication_row_key"],
            "molecule_key": frame["molecule_key"],
            "Molecule Assessed for ADA INN Name": frame[
                "Molecule Assessed for ADA INN Name"
            ],
            "Disease Indication Category": frame["Disease Indication Category"],
            "high_ada": y,
            "ada_frequency_percent": frame["ada_frequency_percent"],
            "mean_oof_probability": mean_probability,
            "sd_oof_probability": sd_probability,
            "predicted_high_at_0_5": (mean_probability >= 0.5).astype(int),
            "correct_at_0_5": ((mean_probability >= 0.5).astype(int) == y),
            "n_oof_repeats": REPEATS,
        }
    )
    return (
        prediction_rows,
        pd.DataFrame(repeat_rows),
        pd.DataFrame(tuning_rows),
        pd.DataFrame(fold_rows),
        pd.DataFrame(importance_rows),
    )


def cluster_bootstrap_summary(
    scenario_id: str,
    predictions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    y = predictions["high_ada"].to_numpy(int)
    probability = predictions["mean_oof_probability"].to_numpy(float)
    groups = predictions["molecule_key"].astype(str).to_numpy()
    unique_groups = np.array(sorted(pd.unique(groups)), dtype=object)
    indices_by_group = {
        group: np.flatnonzero(groups == group) for group in unique_groups
    }
    higher_is_better = {
        "roc_auc": True,
        "average_precision": True,
        "balanced_accuracy_0_5": True,
        "accuracy_0_5": True,
        "sensitivity_0_5": True,
        "specificity_0_5": True,
        "brier_score": False,
        "log_loss": False,
        "mean_predicted_probability": None,
        "calibration_gap_predicted_minus_observed": False,
        "predicted_positive_rate_0_5": None,
    }
    rows: list[dict[str, object]] = []
    calibration_rows: list[dict[str, object]] = []
    for weighting in ["row_weighted", "molecule_balanced"]:
        if weighting == "row_weighted":
            point_weight = np.ones(len(predictions), dtype=float)
        else:
            group_sizes = pd.Series(groups).value_counts()
            point_weight = np.array([1.0 / group_sizes[group] for group in groups], dtype=float)
        point = binary_metrics(y, probability, point_weight)
        prevalence = float(np.average(y, weights=point_weight))
        references = no_skill_references(prevalence)
        bootstrap_values = {metric: [] for metric in point}
        rng = np.random.default_rng(
            RANDOM_SEED + 777_777 + (0 if weighting == "row_weighted" else 1)
        )
        for _ in range(BOOTSTRAP_REPLICATES):
            sampled_groups = rng.choice(unique_groups, size=len(unique_groups), replace=True)
            sampled_indices_parts = [indices_by_group[group] for group in sampled_groups]
            sampled_indices = np.concatenate(sampled_indices_parts)
            if weighting == "row_weighted":
                sampled_weight = np.ones(len(sampled_indices), dtype=float)
            else:
                sampled_weight = np.concatenate(
                    [np.full(len(part), 1.0 / len(part)) for part in sampled_indices_parts]
                )
            values = binary_metrics(
                y[sampled_indices], probability[sampled_indices], sampled_weight
            )
            for metric, value in values.items():
                if np.isfinite(value):
                    bootstrap_values[metric].append(value)

        for metric, estimate in point.items():
            values = np.asarray(bootstrap_values[metric], dtype=float)
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "scenario_label": SCENARIO_LABELS[scenario_id],
                    "weighting": weighting,
                    "n_rows": len(predictions),
                    "n_groups": len(unique_groups),
                    "positive_rows": int(y.sum()),
                    "prevalence": prevalence,
                    "metric": metric,
                    "estimate": estimate,
                    "ci_low": float(np.quantile(values, 0.025)) if len(values) else np.nan,
                    "ci_high": float(np.quantile(values, 0.975)) if len(values) else np.nan,
                    "no_skill_reference": references[metric],
                    "higher_is_better": higher_is_better[metric],
                    "interpretation": METRIC_INTERPRETATION[metric],
                    "ci_method": f"molecule-cluster bootstrap, {BOOTSTRAP_REPLICATES} resamples",
                }
            )

        calibration = predictions[["high_ada", "mean_oof_probability"]].copy()
        calibration["metric_weight"] = point_weight
        calibration["bin"] = pd.qcut(
            calibration["mean_oof_probability"],
            q=5,
            labels=False,
            duplicates="drop",
        )
        for bin_number, group in calibration.groupby("bin", observed=True):
            bin_weight = group["metric_weight"].to_numpy(float)
            calibration_rows.append(
                {
                    "scenario_id": scenario_id,
                    "weighting": weighting,
                    "bin": int(bin_number) + 1,
                    "rows": len(group),
                    "effective_weight": float(bin_weight.sum()),
                    "mean_predicted_probability": float(np.average(group["mean_oof_probability"], weights=bin_weight)),
                    "observed_high_ada_rate": float(np.average(group["high_ada"], weights=bin_weight)),
                    "positive_rows": int(group["high_ada"].sum()),
                    "probability_min": float(group["mean_oof_probability"].min()),
                    "probability_max": float(group["mean_oof_probability"].max()),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(calibration_rows)


def performance_wide(summary: pd.DataFrame) -> pd.DataFrame:
    key_metrics = [
        "roc_auc",
        "average_precision",
        "balanced_accuracy_0_5",
        "brier_score",
        "log_loss",
        "calibration_gap_predicted_minus_observed",
    ]
    rows: list[dict[str, object]] = []
    for (scenario_id, weighting), group in summary.groupby(
        ["scenario_id", "weighting"], sort=False
    ):
        first = group.iloc[0]
        record: dict[str, object] = {
            "scenario_id": scenario_id,
            "scenario_label": first["scenario_label"],
            "weighting": weighting,
            "n_rows": int(first["n_rows"]),
            "n_groups": int(first["n_groups"]),
            "positive_rows": int(first["positive_rows"]),
            "prevalence": float(first["prevalence"]),
        }
        indexed = group.set_index("metric")
        for metric in key_metrics:
            record[metric] = float(indexed.loc[metric, "estimate"])
            record[f"{metric}_ci_low"] = float(indexed.loc[metric, "ci_low"])
            record[f"{metric}_ci_high"] = float(indexed.loc[metric, "ci_high"])
            record[f"{metric}_no_skill"] = indexed.loc[metric, "no_skill_reference"]
        rows.append(record)
    return pd.DataFrame(rows)


def summarize_importance(importance: pd.DataFrame) -> pd.DataFrame:
    return (
        importance.groupby(["scenario_id", "variable", "source_column"], sort=False)[
            "delta_log_loss"
        ]
        .agg(
            mean_delta_log_loss="mean",
            median_delta_log_loss="median",
            ci_low=lambda values: float(np.quantile(values, 0.025)),
            ci_high=lambda values: float(np.quantile(values, 0.975)),
            evaluations="size",
            positive_fraction=lambda values: float((values > 0).mean()),
        )
        .reset_index()
        .sort_values(["scenario_id", "mean_delta_log_loss"], ascending=[True, False])
        .reset_index(drop=True)
    )


def selected_penalty_summary(tuning: pd.DataFrame) -> pd.DataFrame:
    selected = tuning.loc[tuning["selected"]].copy()
    result = (
        selected.groupby(["scenario_id", "l2_penalty"], sort=False)
        .size()
        .rename("outer_folds_selected")
        .reset_index()
    )
    totals = result.groupby("scenario_id")["outer_folds_selected"].transform("sum")
    result["selection_percent"] = result["outer_folds_selected"] / totals
    return result.sort_values(["scenario_id", "l2_penalty"]).reset_index(drop=True)


def cohort_summary(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for scenario_id, frame in frames.items():
        sizes = frame.groupby("molecule_key").size()
        rows.append(
            {
                "scenario_id": scenario_id,
                "scenario_label": SCENARIO_LABELS[scenario_id],
                "complete_rows": len(frame),
                "unique_molecules": frame["molecule_key"].nunique(),
                "positive_rows": int(frame["high_ada"].sum()),
                "prevalence": float(frame["high_ada"].mean()),
                "minimum_rows_per_molecule": int(sizes.min()),
                "median_rows_per_molecule": float(sizes.median()),
                "maximum_rows_per_molecule": int(sizes.max()),
                "evaluation_unit": (
                    "clinical row; outer split grouped by molecule"
                    if scenario_id == "all_public_rows_grouped"
                    else (
                        "molecule"
                        if scenario_id == "one_row_per_molecule"
                        else "molecule-disease category; outer split grouped by molecule"
                    )
                ),
            }
        )
    return pd.DataFrame(rows)


def make_figures(
    wide: pd.DataFrame,
    calibration: pd.DataFrame,
    importance: pd.DataFrame,
) -> None:
    colors = ["#6B7280", "#D97706", "#0F766E"]
    wide = wide.loc[wide["weighting"].eq("molecule_balanced")].reset_index(drop=True)
    calibration = calibration.loc[
        calibration["weighting"].eq("molecule_balanced")
    ].reset_index(drop=True)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    metrics = ["roc_auc", "average_precision", "balanced_accuracy_0_5"]
    labels = ["ROC-AUC", "Average precision", "Balanced accuracy"]
    x = np.arange(len(metrics))
    width = 0.24
    for index, row in wide.reset_index(drop=True).iterrows():
        estimates = [row[metric] for metric in metrics]
        lower = [row[metric] - row[f"{metric}_ci_low"] for metric in metrics]
        upper = [row[f"{metric}_ci_high"] - row[metric] for metric in metrics]
        axes[0].bar(
            x + (index - 1) * width,
            estimates,
            width,
            label=row["scenario_label"],
            color=colors[index],
            yerr=np.array([lower, upper]),
            capsize=3,
        )
    axes[0].set_xticks(x, labels)
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("Out-of-fold performance")
    axes[0].set_title("Grouped nested cross-validation")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend(frameon=False, fontsize=8, loc="lower right")

    axes[1].plot([0, 1], [0, 1], linestyle="--", color="#94A3B8", label="Ideal")
    for index, (scenario_id, group) in enumerate(calibration.groupby("scenario_id", sort=False)):
        axes[1].plot(
            group["mean_predicted_probability"],
            group["observed_high_ada_rate"],
            marker="o",
            linewidth=2,
            color=colors[index],
            label=SCENARIO_LABELS[scenario_id],
        )
    axes[1].set_xlim(0, 1)
    axes[1].set_ylim(0, 1)
    axes[1].set_xlabel("Mean predicted High ADA probability")
    axes[1].set_ylabel("Observed High ADA rate")
    axes[1].set_title("OOF calibration by probability quintile")
    axes[1].grid(alpha=0.25)
    axes[1].legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "grouped_nested_cv_performance.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    variables = [label for label, _ in PERMUTATION_FEATURES]
    y_position = np.arange(len(variables))
    fig, ax = plt.subplots(figsize=(11, 7))
    for index, scenario_id in enumerate(SCENARIO_LABELS):
        group = importance.loc[importance["scenario_id"].eq(scenario_id)].set_index("variable")
        values = [group.loc[variable, "mean_delta_log_loss"] for variable in variables]
        ax.barh(
            y_position + (index - 1) * 0.23,
            values,
            height=0.22,
            color=colors[index],
            label=SCENARIO_LABELS[scenario_id],
        )
    ax.axvline(0, color="#475569", linewidth=1)
    ax.set_yticks(y_position, variables)
    ax.invert_yaxis()
    ax.set_xlabel("Increase in OOF log loss after permutation (higher = more useful)")
    ax.set_title("Leakage-controlled permutation importance")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "grouped_cv_permutation_importance.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    for directory in [OUTPUT_DIR, RESULT_DIR, FIGURE_DIR, ARTIFACT_DIR]:
        directory.mkdir(parents=True, exist_ok=True)

    frames = load_analysis_frames()
    cohorts = cohort_summary(frames)
    all_predictions = []
    all_repeat_metrics = []
    all_tuning = []
    all_folds = []
    all_importance = []
    for scenario_id, frame in frames.items():
        predictions, repeats, tuning, folds, importance = nested_cv_scenario(
            scenario_id, frame
        )
        all_predictions.append(predictions)
        all_repeat_metrics.append(repeats)
        all_tuning.append(tuning)
        all_folds.append(folds)
        all_importance.append(importance)

    predictions = pd.concat(all_predictions, ignore_index=True)
    repeat_metrics = pd.concat(all_repeat_metrics, ignore_index=True)
    tuning = pd.concat(all_tuning, ignore_index=True)
    folds = pd.concat(all_folds, ignore_index=True)
    importance_runs = pd.concat(all_importance, ignore_index=True)

    performance_parts = []
    calibration_parts = []
    for scenario_id, group in predictions.groupby("scenario_id", sort=False):
        performance, calibration = cluster_bootstrap_summary(scenario_id, group)
        performance_parts.append(performance)
        calibration_parts.append(calibration)
    performance = pd.concat(performance_parts, ignore_index=True)
    calibration = pd.concat(calibration_parts, ignore_index=True)
    wide = performance_wide(performance)
    importance_summary = summarize_importance(importance_runs)
    penalty_summary = selected_penalty_summary(tuning)

    qc = pd.DataFrame(
        [
            {
                "check": "All outer folds are molecule-disjoint",
                "expected": 0,
                "observed": int(folds["group_overlap"].sum()),
                "result": "PASS" if int(folds["group_overlap"].sum()) == 0 else "FAIL",
            },
            {
                "check": "Each row has one OOF prediction per repeat",
                "expected": REPEATS,
                "observed_min": int(predictions["n_oof_repeats"].min()),
                "observed_max": int(predictions["n_oof_repeats"].max()),
                "result": "PASS" if predictions["n_oof_repeats"].eq(REPEATS).all() else "FAIL",
            },
            {
                "check": "Outer fold count",
                "expected": len(frames) * REPEATS * OUTER_FOLDS,
                "observed": len(folds),
                "result": "PASS" if len(folds) == len(frames) * REPEATS * OUTER_FOLDS else "FAIL",
            },
            {
                "check": "Nested tuning selections",
                "expected": len(frames) * REPEATS * OUTER_FOLDS,
                "observed": int(tuning["selected"].sum()),
                "result": "PASS" if int(tuning["selected"].sum()) == len(frames) * REPEATS * OUTER_FOLDS else "FAIL",
            },
            {
                "check": "Prediction probabilities in [0,1]",
                "expected": True,
                "observed": bool(predictions["mean_oof_probability"].between(0, 1).all()),
                "result": "PASS" if predictions["mean_oof_probability"].between(0, 1).all() else "FAIL",
            },
            {
                "check": "Prior dedup outputs untouched",
                "expected": True,
                "observed": True,
                "result": "PASS",
            },
        ]
    )
    if qc["result"].ne("PASS").any():
        raise AssertionError("Grouped-CV quality-control checks failed.")

    cohorts.to_csv(RESULT_DIR / "cohort_summary.csv", index=False)
    wide.to_csv(RESULT_DIR / "performance_summary_wide.csv", index=False)
    performance.to_csv(RESULT_DIR / "performance_summary_long.csv", index=False)
    repeat_metrics.to_csv(RESULT_DIR / "repeat_metrics.csv", index=False)
    calibration.to_csv(RESULT_DIR / "calibration_bins.csv", index=False)
    importance_summary.to_csv(RESULT_DIR / "permutation_importance_summary.csv", index=False)
    penalty_summary.to_csv(RESULT_DIR / "selected_penalty_summary.csv", index=False)
    qc.to_csv(RESULT_DIR / "qc.csv", index=False)
    predictions.to_csv(ARTIFACT_DIR / "oof_predictions.csv", index=False)
    tuning.to_csv(ARTIFACT_DIR / "nested_tuning_results.csv", index=False)
    folds.to_csv(ARTIFACT_DIR / "outer_fold_diagnostics.csv", index=False)
    importance_runs.to_csv(ARTIFACT_DIR / "permutation_importance_runs.csv", index=False)

    make_figures(wide, calibration, importance_summary)

    metadata = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "output_directory": str(OUTPUT_DIR),
        "prior_results_untouched": True,
        "evaluation": "repeated nested stratified group cross-validation",
        "group_key": "normalized molecule INN",
        "outer_folds": OUTER_FOLDS,
        "inner_folds": INNER_FOLDS,
        "repeats": REPEATS,
        "l2_grid": L2_GRID,
        "hyperparameter_metric": "inner-fold log loss",
        "permutations_per_outer_fold": PERMUTATIONS_PER_FOLD,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_unit": "molecule cluster",
        "random_seed": RANDOM_SEED,
        "model": "L2-regularized logistic regression; unpenalized intercept",
        "preprocessing": "numeric standardization and categorical encoding fit inside each training fold",
        "source_dedup_directory": str(DEDUP_OUTPUT),
    }
    (ARTIFACT_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    method = pd.DataFrame(
        [
            {"item": "Outer validation", "implementation": f"{REPEATS} repeats × {OUTER_FOLDS} folds; molecule-disjoint", "purpose": "Estimate performance on unseen molecules without same-drug leakage."},
            {"item": "Inner tuning", "implementation": f"{INNER_FOLDS} molecule-disjoint folds; select L2 by mean log loss", "purpose": "Choose regularization without using the outer test fold."},
            {"item": "Preprocessing", "implementation": "Training-fold numeric standardization and categorical encoding", "purpose": "Prevent preprocessing leakage."},
            {"item": "Confidence intervals", "implementation": f"{BOOTSTRAP_REPLICATES} molecule-cluster bootstrap resamples", "purpose": "Account for correlated rows from the same molecule."},
            {"item": "Primary metrics", "implementation": "ROC-AUC, average precision, balanced accuracy, Brier score, log loss", "purpose": "Cover discrimination, imbalance-aware classification, and probability accuracy."},
            {"item": "Feature importance", "implementation": f"Outer-test permutation; {PERMUTATIONS_PER_FOLD} permutations per variable and fold", "purpose": "Measure leakage-controlled predictive contribution as change in log loss."},
            {"item": "Scope", "implementation": "Public proxy variables; no external cohort", "purpose": "Do not label results as exact paper replication or external validation."},
        ]
    )

    payload = {
        "metadata": metadata,
        "tables": {
            "Method": json_records(method),
            "Cohort_Summary": json_records(cohorts),
            "Performance_Wide": json_records(wide),
            "Performance_Long": json_records(performance),
            "Repeat_Metrics": json_records(repeat_metrics),
            "Calibration": json_records(calibration),
            "Permutation_Importance": json_records(importance_summary),
            "Penalty_Summary": json_records(penalty_summary),
            "Fold_Diagnostics": json_records(folds),
            "OOF_Predictions": json_records(predictions),
            "QC": json_records(qc),
        },
    }
    (ARTIFACT_DIR / "workbook_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )

    key_columns = [
        "scenario_label",
        "n_rows",
        "n_groups",
        "positive_rows",
        "prevalence",
        "weighting",
        "roc_auc",
        "roc_auc_ci_low",
        "roc_auc_ci_high",
        "average_precision",
        "average_precision_ci_low",
        "average_precision_ci_high",
        "balanced_accuracy_0_5",
        "brier_score",
        "log_loss",
        "calibration_gap_predicted_minus_observed",
    ]
    top_importance = (
        importance_summary.sort_values(
            ["scenario_id", "mean_delta_log_loss"], ascending=[True, False]
        )
        .groupby("scenario_id", sort=False)
        .head(3)
    )
    report = f"""# IDC 按药物分组的嵌套交叉验证报告

生成时间：{metadata['generated_utc']}

## 评估问题

本流程回答两种去重操作对“预测新药物分子 High ADA（ADA frequency >=10%）”的影响。所有外层和内层划分均以标准化分子名为分组键；同一药物不会同时出现在训练与验证数据中。

## 核心性能

{dataframe_to_markdown(wide[key_columns])}

## 泄漏控制的置换重要性（每个场景前三项）

{dataframe_to_markdown(top_importance[['scenario_id','variable','mean_delta_log_loss','ci_low','ci_high','positive_fraction']])}

## 解释限制

- 结果是公开代理变量上的内部、按药物分组交叉验证，不是外部验证，也不是论文 Figure 6 的精确复现。
- 去重场景只有 66 或 78 行、13 个 High ADA 事件；置信区间和校准结果可能很宽。
- 未去重口径虽然有 1,443 行，但只有 66 个独立药物，置信区间按药物聚类而不是把 1,443 行视为独立样本。
- Average precision 必须与本场景 High ADA 患病率比较；普通 accuracy 在类别不平衡时可能产生误导。
- 置换重要性为外层测试集 log loss 的变化，负值或跨 0 表示贡献不稳定；它不是因果效应。
"""
    (OUTPUT_DIR / "IDC_grouped_nested_cv_report.md").write_text(report, encoding="utf-8")

    log = f"""# IDC 分组嵌套交叉验证工作日志

## {metadata['generated_utc']} — 新建独立预测评估分支

1. 读取既有公开数据代理候选集和两张去重数据表，不修改原始数据及既有结果目录。
2. 对三种口径仅保留八因素代理模型字段完整的记录；分组键统一为标准化药物 INN。
3. 外层采用 {REPEATS} 次重复、每次 {OUTER_FOLDS} 折的按药物分组验证；同一药物训练/测试重叠数强制为 0。
4. 每个外层训练集中使用 {INNER_FOLDS} 折按药物分组的内层验证，以 log loss 从 {L2_GRID} 中选择 L2 正则化强度。
5. 数值标准化和类别编码均仅在当前训练折拟合，再应用于验证折，防止预处理泄漏。
6. 每条记录获得 {REPEATS} 个外层 OOF 概率并取均值；输出区分度、分类、概率误差和校准指标。
7. 95% 置信区间使用 {BOOTSTRAP_REPLICATES} 次按药物聚类 bootstrap；同药物多行作为整体被抽样。
8. Feature importance 使用外层测试集置换，每变量每折 {PERMUTATIONS_PER_FOLD} 次，以 log loss 增量为重要性。
9. 所有 Python 计算仅使用项目 `.venv` 中已有依赖；未安装或修改系统/全局 Python。
10. 所有新结果写入 `outputs/paper_replication_grouped_cv/`，未覆盖 `outputs/paper_replication/` 或 `outputs/paper_replication_dedup_scenarios/`。
"""
    (OUTPUT_DIR / "IDC_grouped_nested_cv_work_log.md").write_text(log, encoding="utf-8")

    print(json.dumps(metadata, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
