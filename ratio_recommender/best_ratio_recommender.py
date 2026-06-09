from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from predictor.accuracy_predictor import AccuracyPredictorModel


DEFAULT_MIN_RATIO = 0.10
DEFAULT_MAX_RATIO = 0.90
DEFAULT_SEARCH_TOLERANCE = 1e-4
DEFAULT_TABLE_SAMPLES = 33
DEFAULT_RATIO_PENALTY = 0.25


@dataclass
class CompressionRatioRecommender:
    predictor_model: AccuracyPredictorModel
    min_ratio: float = DEFAULT_MIN_RATIO
    max_ratio: float = DEFAULT_MAX_RATIO
    min_accuracy_threshold: float = 0.80
    ratio_penalty: float = DEFAULT_RATIO_PENALTY
    search_tolerance: float = DEFAULT_SEARCH_TOLERANCE
    table_samples: int = DEFAULT_TABLE_SAMPLES

    @classmethod
    def load(
        cls,
        model_path,
        min_ratio: float = DEFAULT_MIN_RATIO,
        max_ratio: float = DEFAULT_MAX_RATIO,
        min_accuracy_threshold: float = 0.80,
        ratio_penalty: float = DEFAULT_RATIO_PENALTY,
        search_tolerance: float = DEFAULT_SEARCH_TOLERANCE,
        table_samples: int = DEFAULT_TABLE_SAMPLES,
    ) -> "CompressionRatioRecommender":
        model = AccuracyPredictorModel.load(model_path)
        return cls(
            predictor_model=model,
            min_ratio=float(min_ratio),
            max_ratio=float(max_ratio),
            min_accuracy_threshold=float(min_accuracy_threshold),
            ratio_penalty=float(ratio_penalty),
            search_tolerance=float(search_tolerance),
            table_samples=int(table_samples),
        )

    def __post_init__(self) -> None:
        self.min_ratio = float(self.min_ratio)
        self.max_ratio = float(self.max_ratio)
        self.min_accuracy_threshold = float(self.min_accuracy_threshold)
        self.ratio_penalty = float(self.ratio_penalty)
        self.search_tolerance = float(self.search_tolerance)
        self.table_samples = int(self.table_samples)

        if not (0.0 < self.min_ratio < self.max_ratio <= 1.0):
            raise ValueError("Expected 0 < min_ratio < max_ratio <= 1.")
        if self.ratio_penalty < 0.0:
            raise ValueError("ratio_penalty must be non-negative.")
        if self.search_tolerance <= 0.0:
            raise ValueError("search_tolerance must be positive.")
        if self.table_samples < 3:
            raise ValueError("table_samples must be at least 3.")

    def _predict_probe_mean_accuracy(self, probe_feature_df: pd.DataFrame, ratio: float) -> float:
        pred = self.predictor_model.predict_probe_accuracy(probe_feature_df, ratio=float(ratio))
        return float(pred["predicted_probe_accuracy_mean"])

    def _penalized_score(self, predicted_probe_accuracy_mean: float, ratio: float) -> float:
        return float(predicted_probe_accuracy_mean) - float(self.ratio_penalty) * float(ratio)

    def _evaluate_ratio_point(self, probe_feature_df: pd.DataFrame, ratio: float) -> Dict[str, float]:
        pred_mean = self._predict_probe_mean_accuracy(probe_feature_df, float(ratio))
        return {
            "ratio": float(ratio),
            "predicted_probe_accuracy_mean": float(pred_mean),
            "penalized_score": self._penalized_score(pred_mean, float(ratio)),
        }

    def _golden_section_maximize(self, probe_feature_df: pd.DataFrame, left: float, right: float) -> Dict[str, float]:
        phi = (1.0 + np.sqrt(5.0)) / 2.0
        inv_phi = 1.0 / phi

        a = float(left)
        b = float(right)
        c = b - (b - a) * inv_phi
        d = a + (b - a) * inv_phi
        fc = self._evaluate_ratio_point(probe_feature_df, c)
        fd = self._evaluate_ratio_point(probe_feature_df, d)

        while (b - a) > self.search_tolerance:
            if float(fc["penalized_score"]) <= float(fd["penalized_score"]):
                a = c
                c = d
                fc = fd
                d = a + (b - a) * inv_phi
                fd = self._evaluate_ratio_point(probe_feature_df, d)
            else:
                b = d
                d = c
                fd = fc
                c = b - (b - a) * inv_phi
                fc = self._evaluate_ratio_point(probe_feature_df, c)

        candidates = [
            self._evaluate_ratio_point(probe_feature_df, float(left)),
            self._evaluate_ratio_point(probe_feature_df, float(right)),
            fc,
            fd,
            self._evaluate_ratio_point(probe_feature_df, (a + b) / 2.0),
        ]
        return max(
            candidates,
            key=lambda item: (float(item["penalized_score"]), float(item["ratio"])),
        )

    def _sample_curve(self, probe_feature_df: pd.DataFrame, num_samples: Optional[int] = None) -> pd.DataFrame:
        n = int(num_samples or self.table_samples)
        ratios = np.linspace(self.min_ratio, self.max_ratio, n)
        rows: List[Dict[str, float]] = []
        for ratio in ratios:
            point = self._evaluate_ratio_point(probe_feature_df, float(ratio))
            rows.append(
                {
                    "compression_ratio": float(point["ratio"]),
                    "predicted_probe_accuracy_mean": float(point["predicted_probe_accuracy_mean"]),
                    "penalized_score": float(point["penalized_score"]),
                }
            )
        return pd.DataFrame(rows).sort_values("compression_ratio").reset_index(drop=True)

    def evaluate_probe_ratio_curve(self, probe_feature_df: pd.DataFrame, num_samples: Optional[int] = None) -> pd.DataFrame:
        return self._sample_curve(probe_feature_df, num_samples=num_samples)

    def _find_best_threshold_feasible_point(
        self,
        probe_feature_df: pd.DataFrame,
        sampled_curve: pd.DataFrame,
    ) -> Optional[Dict[str, float]]:
        threshold = float(self.min_accuracy_threshold)
        feasible_df = sampled_curve[sampled_curve["predicted_probe_accuracy_mean"] >= threshold].copy()
        if feasible_df.empty:
            return None

        ratios = feasible_df["compression_ratio"].to_numpy(dtype=np.float64)
        scores = feasible_df["penalized_score"].to_numpy(dtype=np.float64)
        accs = feasible_df["predicted_probe_accuracy_mean"].to_numpy(dtype=np.float64)
        best_idx = max(range(len(ratios)), key=lambda idx: (float(scores[idx]), float(ratios[idx])))
        best_ratio = float(ratios[best_idx])
        best_acc = float(accs[best_idx])
        best_score = float(scores[best_idx])

        return {
            "ratio": best_ratio,
            "predicted_probe_accuracy_mean": best_acc,
            "penalized_score": best_score,
        }

    def select_best_ratio(self, probe_feature_df: pd.DataFrame) -> Dict[str, object]:
        sampled_curve = self._sample_curve(probe_feature_df)
        threshold_solution = self._find_best_threshold_feasible_point(probe_feature_df, sampled_curve)
        if threshold_solution is not None:
            return {
                "best_ratio": float(threshold_solution["ratio"]),
                "best_predicted_probe_accuracy_mean": float(threshold_solution["predicted_probe_accuracy_mean"]),
                "best_penalized_score": float(threshold_solution["penalized_score"]),
                "selection_rule": "best_penalized_score_meeting_threshold",
                "min_accuracy_threshold": float(self.min_accuracy_threshold),
                "ratio_penalty": float(self.ratio_penalty),
                "search_interval": (float(self.min_ratio), float(self.max_ratio)),
                "search_tolerance": float(self.search_tolerance),
                "ratio_evaluation_table": sampled_curve,
            }

        ratios = sampled_curve["compression_ratio"].to_numpy(dtype=np.float64)
        scores = sampled_curve["penalized_score"].to_numpy(dtype=np.float64)
        peak_idx = int(np.argmax(scores))
        left_idx = max(0, peak_idx - 1)
        right_idx = min(len(ratios) - 1, peak_idx + 1)

        optimum = self._golden_section_maximize(
            probe_feature_df,
            left=float(ratios[left_idx]),
            right=float(ratios[right_idx]),
        )
        return {
            "best_ratio": float(optimum["ratio"]),
            "best_predicted_probe_accuracy_mean": float(optimum["predicted_probe_accuracy_mean"]),
            "best_penalized_score": float(optimum["penalized_score"]),
            "selection_rule": "continuous_max_penalized_score_fallback",
            "min_accuracy_threshold": float(self.min_accuracy_threshold),
            "ratio_penalty": float(self.ratio_penalty),
            "search_interval": (float(self.min_ratio), float(self.max_ratio)),
            "search_tolerance": float(self.search_tolerance),
            "ratio_evaluation_table": sampled_curve,
        }

    def recommend_probe_ratio(self, probe_feature_df: pd.DataFrame) -> Dict[str, object]:
        selected = self.select_best_ratio(probe_feature_df)
        best_prediction = self.predictor_model.predict_probe_accuracy(
            probe_feature_df,
            ratio=float(selected["best_ratio"]),
        )
        return {
            **selected,
            "best_ratio_prediction": best_prediction,
            "probe_feature_df": probe_feature_df.copy(),
        }

    def recommend_probe_ratio_from_files(
        self,
        templates_path,
        spike_times_path,
        spike_clusters_path,
        ops_path,
        probe_name: Optional[str] = None,
    ) -> Dict[str, object]:
        probe_name = probe_name or Path(templates_path).parent.name
        probe_feature_df = self.predictor_model.predict_probe_accuracy_from_files(
            templates_path=templates_path,
            spike_times_path=spike_times_path,
            spike_clusters_path=spike_clusters_path,
            ops_path=ops_path,
            ratio=float(self.min_ratio),
        )["probe_feature_df"]

        result = self.recommend_probe_ratio(probe_feature_df)
        result["probe_name"] = probe_name
        result["input_files"] = {
            "templates_path": str(Path(templates_path)),
            "spike_times_path": str(Path(spike_times_path)),
            "spike_clusters_path": str(Path(spike_clusters_path)),
            "ops_path": str(Path(ops_path)),
        }
        return result

    def recommend_many_from_files(self, probe_specs: Iterable[Dict[str, object]]) -> Dict[str, object]:
        recommendation_rows: List[Dict[str, object]] = []
        detailed_results: List[Dict[str, object]] = []

        for i, spec in enumerate(probe_specs):
            result = self.recommend_probe_ratio_from_files(
                templates_path=spec["templates_path"],
                spike_times_path=spec["spike_times_path"],
                spike_clusters_path=spec["spike_clusters_path"],
                ops_path=spec["ops_path"],
                probe_name=spec.get("probe_name") or f"probe_{i}",
            )
            recommendation_rows.append(
                {
                    "probe_name": result["probe_name"],
                    "best_ratio": result["best_ratio"],
                    "best_predicted_probe_accuracy_mean": result["best_predicted_probe_accuracy_mean"],
                    "best_penalized_score": result["best_penalized_score"],
                    "selection_rule": result["selection_rule"],
                    "min_accuracy_threshold": result["min_accuracy_threshold"],
                    "ratio_penalty": result["ratio_penalty"],
                }
            )
            detailed_results.append(result)

        return {
            "recommendation_table": pd.DataFrame(recommendation_rows),
            "detailed_results": detailed_results,
        }
