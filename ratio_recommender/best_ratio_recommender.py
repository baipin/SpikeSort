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


@dataclass
class CompressionRatioRecommender:
    predictor_model: AccuracyPredictorModel
    min_ratio: float = DEFAULT_MIN_RATIO
    max_ratio: float = DEFAULT_MAX_RATIO
    min_accuracy_threshold: float = 0.80
    search_tolerance: float = DEFAULT_SEARCH_TOLERANCE
    table_samples: int = DEFAULT_TABLE_SAMPLES

    @classmethod
    def load(
        cls,
        model_path,
        min_ratio: float = DEFAULT_MIN_RATIO,
        max_ratio: float = DEFAULT_MAX_RATIO,
        min_accuracy_threshold: float = 0.80,
        search_tolerance: float = DEFAULT_SEARCH_TOLERANCE,
        table_samples: int = DEFAULT_TABLE_SAMPLES,
    ) -> "CompressionRatioRecommender":
        model = AccuracyPredictorModel.load(model_path)
        return cls(
            predictor_model=model,
            min_ratio=float(min_ratio),
            max_ratio=float(max_ratio),
            min_accuracy_threshold=float(min_accuracy_threshold),
            search_tolerance=float(search_tolerance),
            table_samples=int(table_samples),
        )

    def __post_init__(self) -> None:
        self.min_ratio = float(self.min_ratio)
        self.max_ratio = float(self.max_ratio)
        self.min_accuracy_threshold = float(self.min_accuracy_threshold)
        self.search_tolerance = float(self.search_tolerance)
        self.table_samples = int(self.table_samples)

        if not (0.0 < self.min_ratio < self.max_ratio <= 1.0):
            raise ValueError("Expected 0 < min_ratio < max_ratio <= 1.")
        if self.search_tolerance <= 0.0:
            raise ValueError("search_tolerance must be positive.")
        if self.table_samples < 3:
            raise ValueError("table_samples must be at least 3.")

    def _predict_probe_mean_accuracy(self, probe_feature_df: pd.DataFrame, ratio: float) -> float:
        pred = self.predictor_model.predict_probe_accuracy(probe_feature_df, ratio=float(ratio))
        return float(pred["predicted_probe_accuracy_mean"])

    def _evaluate_ratio_point(self, probe_feature_df: pd.DataFrame, ratio: float) -> Dict[str, float]:
        pred_mean = self._predict_probe_mean_accuracy(probe_feature_df, float(ratio))
        return {
            "ratio": float(ratio),
            "predicted_probe_accuracy_mean": float(pred_mean),
            "meets_min_accuracy_threshold": float(pred_mean) >= float(self.min_accuracy_threshold),
        }

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
                    "meets_min_accuracy_threshold": bool(point["meets_min_accuracy_threshold"]),
                }
            )
        return pd.DataFrame(rows).sort_values("compression_ratio").reset_index(drop=True)

    def evaluate_probe_ratio_curve(self, probe_feature_df: pd.DataFrame, num_samples: Optional[int] = None) -> pd.DataFrame:
        return self._sample_curve(probe_feature_df, num_samples=num_samples)

    def _find_minimum_feasible_ratio(
        self,
        sampled_curve: pd.DataFrame,
    ) -> Optional[Dict[str, float]]:
        threshold = float(self.min_accuracy_threshold)
        feasible_df = sampled_curve[sampled_curve["predicted_probe_accuracy_mean"] >= threshold].copy()
        if feasible_df.empty:
            return None

        ratios = feasible_df["compression_ratio"].to_numpy(dtype=np.float64)
        accs = feasible_df["predicted_probe_accuracy_mean"].to_numpy(dtype=np.float64)
        best_idx = int(np.argmin(ratios))
        best_ratio = float(ratios[best_idx])
        best_acc = float(accs[best_idx])

        return {
            "ratio": best_ratio,
            "predicted_probe_accuracy_mean": best_acc,
            "meets_min_accuracy_threshold": True,
        }

    def select_best_ratio(self, probe_feature_df: pd.DataFrame) -> Dict[str, object]:
        sampled_curve = self._sample_curve(probe_feature_df)
        threshold_solution = self._find_minimum_feasible_ratio(sampled_curve)
        if threshold_solution is not None:
            return {
                "recommended_keep_ratio": float(threshold_solution["ratio"]),
                "recommended_predicted_probe_accuracy_mean": float(threshold_solution["predicted_probe_accuracy_mean"]),
                "selection_rule": "minimum_keep_ratio_meeting_threshold",
                "threshold_feasible": True,
                "min_accuracy_threshold": float(self.min_accuracy_threshold),
                "search_interval": (float(self.min_ratio), float(self.max_ratio)),
                "search_tolerance": float(self.search_tolerance),
                "ratio_evaluation_table": sampled_curve,
            }

        best_fallback_idx = int(np.argmax(sampled_curve["predicted_probe_accuracy_mean"].to_numpy(dtype=np.float64)))
        fallback_row = sampled_curve.iloc[best_fallback_idx]
        return {
            "recommended_keep_ratio": float(fallback_row["compression_ratio"]),
            "recommended_predicted_probe_accuracy_mean": float(fallback_row["predicted_probe_accuracy_mean"]),
            "selection_rule": "no_ratio_meets_threshold_use_max_predicted_accuracy",
            "threshold_feasible": False,
            "min_accuracy_threshold": float(self.min_accuracy_threshold),
            "search_interval": (float(self.min_ratio), float(self.max_ratio)),
            "search_tolerance": float(self.search_tolerance),
            "ratio_evaluation_table": sampled_curve,
        }

    def recommend_probe_ratio(self, probe_feature_df: pd.DataFrame) -> Dict[str, object]:
        selected = self.select_best_ratio(probe_feature_df)
        best_prediction = self.predictor_model.predict_probe_accuracy(
            probe_feature_df,
            ratio=float(selected["recommended_keep_ratio"]),
        )
        return {
            **selected,
            "recommended_ratio_prediction": best_prediction,
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
                    "recommended_keep_ratio": result["recommended_keep_ratio"],
                    "recommended_predicted_probe_accuracy_mean": result["recommended_predicted_probe_accuracy_mean"],
                    "selection_rule": result["selection_rule"],
                    "threshold_feasible": result["threshold_feasible"],
                    "min_accuracy_threshold": result["min_accuracy_threshold"],
                }
            )
            detailed_results.append(result)

        return {
            "keep_ratio_vector_table": pd.DataFrame(recommendation_rows),
            "recommendation_table": pd.DataFrame(recommendation_rows),
            "detailed_results": detailed_results,
        }
