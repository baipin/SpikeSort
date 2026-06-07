from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from predictor.accuracy_predictor import AccuracyPredictorModel, DEFAULT_RATIOS


@dataclass
class CompressionRatioRecommender:
    predictor_model: AccuracyPredictorModel
    candidate_ratios: Sequence[float] = DEFAULT_RATIOS
    min_accuracy_threshold: float = 0.80

    @classmethod
    def load(
        cls,
        model_path,
        candidate_ratios: Sequence[float] = DEFAULT_RATIOS,
        min_accuracy_threshold: float = 0.80,
    ) -> "CompressionRatioRecommender":
        model = AccuracyPredictorModel.load(model_path)
        return cls(
            predictor_model=model,
            candidate_ratios=tuple(float(r) for r in candidate_ratios),
            min_accuracy_threshold=float(min_accuracy_threshold),
        )

    def evaluate_probe_ratios(self, probe_feature_df: pd.DataFrame) -> pd.DataFrame:
        rows: List[Dict[str, float]] = []
        for ratio in self.candidate_ratios:
            pred = self.predictor_model.predict_probe_accuracy(probe_feature_df, ratio=float(ratio))
            rows.append(
                {
                    "compression_ratio": float(ratio),
                    "predicted_probe_accuracy_mean": float(pred["predicted_probe_accuracy_mean"]),
                }
            )
        return pd.DataFrame(rows).sort_values("compression_ratio").reset_index(drop=True)

    def select_best_ratio(self, ratio_eval_df: pd.DataFrame) -> Dict[str, object]:
        eval_df = ratio_eval_df.sort_values("compression_ratio").reset_index(drop=True)
        eligible = eval_df[eval_df["predicted_probe_accuracy_mean"] >= float(self.min_accuracy_threshold)].copy()

        if not eligible.empty:
            best_row = eligible.sort_values(
                ["compression_ratio", "predicted_probe_accuracy_mean"],
                ascending=[False, False],
            ).iloc[0]
            selection_rule = "highest_ratio_meeting_threshold"
        else:
            best_row = eval_df.sort_values(
                ["predicted_probe_accuracy_mean", "compression_ratio"],
                ascending=[False, False],
            ).iloc[0]
            selection_rule = "highest_predicted_accuracy_fallback"

        return {
            "best_ratio": float(best_row["compression_ratio"]),
            "best_predicted_probe_accuracy_mean": float(best_row["predicted_probe_accuracy_mean"]),
            "selection_rule": selection_rule,
            "min_accuracy_threshold": float(self.min_accuracy_threshold),
        }

    def recommend_probe_ratio(self, probe_feature_df: pd.DataFrame) -> Dict[str, object]:
        ratio_eval_df = self.evaluate_probe_ratios(probe_feature_df)
        selected = self.select_best_ratio(ratio_eval_df)
        return {
            **selected,
            "ratio_evaluation_table": ratio_eval_df,
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
        ratio_eval_df = []
        probe_name = probe_name or Path(templates_path).parent.name
        probe_feature_df = self.predictor_model.predict_probe_accuracy_from_files(
            templates_path=templates_path,
            spike_times_path=spike_times_path,
            spike_clusters_path=spike_clusters_path,
            ops_path=ops_path,
            ratio=float(self.candidate_ratios[0]),
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
                    "selection_rule": result["selection_rule"],
                    "min_accuracy_threshold": result["min_accuracy_threshold"],
                }
            )
            detailed_results.append(result)

        return {
            "recommendation_table": pd.DataFrame(recommendation_rows),
            "detailed_results": detailed_results,
        }
