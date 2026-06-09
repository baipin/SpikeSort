from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


DEFAULT_RATIOS: Tuple[float, ...] = (0.10, 0.20, 0.30, 0.50, 0.70)
DEFAULT_FEATURE_COLUMNS: Tuple[str, ...] = (
    "compression_ratio",
    "compression_ratio_sq",
    "baseline_spikes",
    "firing_rate_hz",
    "template_ptp_mean",
    "template_ptp_max",
    "template_energy",
    "dominant_channel",
    "template_width_samples",
)


def infer_src_n_chan_from_bin(bin_path, dtype=np.float32, candidates=(383, 385)):
    size = Path(bin_path).stat().st_size
    item = np.dtype(dtype).itemsize
    ok = []
    for ch in candidates:
        if size % (ch * item) == 0:
            ok.append(ch)
    if not ok:
        raise ValueError(f"Cannot infer channel count for {bin_path} from size={size}.")
    return 383 if 383 in ok else ok[0]


def per_neuron_binned_accuracy(st_ref, clu_ref, st_test, clu_test, bin_size_samples, n_units=None):
    st_ref = np.asarray(st_ref, dtype=np.int64)
    clu_ref = np.asarray(clu_ref, dtype=np.int64)
    st_test = np.asarray(st_test, dtype=np.int64)
    clu_test = np.asarray(clu_test, dtype=np.int64)

    if n_units is None:
        max_ref = int(clu_ref.max()) if clu_ref.size else -1
        max_test = int(clu_test.max()) if clu_test.size else -1
        n_units = max(max_ref, max_test) + 1

    max_time = 0
    if st_ref.size:
        max_time = max(max_time, int(st_ref.max()))
    if st_test.size:
        max_time = max(max_time, int(st_test.max()))
    n_bins = max(1, max_time // int(bin_size_samples) + 1)

    ref_bins = st_ref // int(bin_size_samples) if st_ref.size else np.empty((0,), dtype=np.int64)
    test_bins = st_test // int(bin_size_samples) if st_test.size else np.empty((0,), dtype=np.int64)
    ref_lin = clu_ref * n_bins + ref_bins if st_ref.size else np.empty((0,), dtype=np.int64)
    test_lin = clu_test * n_bins + test_bins if st_test.size else np.empty((0,), dtype=np.int64)

    ref_counts = np.bincount(ref_lin, minlength=n_units * n_bins).reshape(n_units, n_bins)
    test_counts = np.bincount(test_lin, minlength=n_units * n_bins).reshape(n_units, n_bins)
    matched_counts = np.maximum(ref_counts - np.abs(test_counts - ref_counts), 0)

    ref_totals = ref_counts.sum(axis=1)
    test_totals = test_counts.sum(axis=1)
    matched_totals = matched_counts.sum(axis=1)
    acc = np.full(n_units, np.nan, dtype=np.float64)
    valid = ref_totals > 0
    acc[valid] = matched_totals[valid] / ref_totals[valid]

    return pd.DataFrame(
        {
            "neuron_id": np.arange(n_units, dtype=np.int64),
            "baseline_spikes": ref_totals.astype(np.int64),
            "compressed_spikes": test_totals.astype(np.int64),
            "matched_spikes_after_binning": matched_totals.astype(np.int64),
            "binned_count_accuracy": acc,
            "sensitivity": 1.0 - acc,
        }
    )


def _compute_template_width_samples(template_waveform: np.ndarray) -> int:
    trough = int(np.argmin(template_waveform))
    peak = int(np.argmax(template_waveform))
    return int(abs(peak - trough))


def extract_baseline_neuron_features(
    templates: np.ndarray,
    st_base: np.ndarray,
    clu_base: np.ndarray,
    sample_rate: float,
) -> pd.DataFrame:
    templates = np.asarray(templates, dtype=np.float32)
    st_base = np.asarray(st_base, dtype=np.int64).reshape(-1)
    clu_base = np.asarray(clu_base, dtype=np.int64).reshape(-1)

    n_units = templates.shape[0]
    duration_seconds = float(st_base.max() + 1) / float(sample_rate) if st_base.size else 1.0
    spike_counts = np.bincount(clu_base, minlength=n_units).astype(np.int64)

    rows = []
    for neuron_id in range(n_units):
        tpl = templates[neuron_id]
        channel_ptp = np.ptp(tpl, axis=0)
        dominant_channel = int(np.argmax(channel_ptp))
        dominant_waveform = tpl[:, dominant_channel]
        rows.append(
            {
                "neuron_id": int(neuron_id),
                "baseline_spikes": int(spike_counts[neuron_id]),
                "firing_rate_hz": float(spike_counts[neuron_id] / max(duration_seconds, 1e-12)),
                "template_ptp_mean": float(channel_ptp.mean()),
                "template_ptp_max": float(channel_ptp.max()),
                "template_energy": float(np.mean(np.square(tpl))),
                "dominant_channel": int(dominant_channel),
                "template_width_samples": int(_compute_template_width_samples(dominant_waveform)),
            }
        )

    return pd.DataFrame(rows)


def load_probe_data(
    templates_path,
    spike_times_path,
    spike_clusters_path,
    ops_path,
):
    templates = np.load(Path(templates_path))
    st_base = np.load(Path(spike_times_path)).squeeze().astype(np.int64)
    clu_base = np.load(Path(spike_clusters_path)).squeeze().astype(np.int64)
    ops_base = np.load(Path(ops_path), allow_pickle=True).item()
    sample_rate = float(ops_base["fs"])
    return {
        "templates": templates,
        "spike_times": st_base,
        "spike_clusters": clu_base,
        "ops": ops_base,
        "sample_rate": sample_rate,
    }


def build_probe_feature_frame_from_files(
    templates_path,
    spike_times_path,
    spike_clusters_path,
    ops_path,
) -> pd.DataFrame:
    probe = load_probe_data(
        templates_path=templates_path,
        spike_times_path=spike_times_path,
        spike_clusters_path=spike_clusters_path,
        ops_path=ops_path,
    )
    return extract_baseline_neuron_features(
        probe["templates"],
        probe["spike_times"],
        probe["spike_clusters"],
        sample_rate=probe["sample_rate"],
    )


def build_ratio_feature_frame(
    base_feature_df: pd.DataFrame,
    ratio: float,
    target_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    frame = base_feature_df.copy()
    frame["compression_ratio"] = float(ratio)
    frame["compression_ratio_sq"] = float(ratio) ** 2
    if target_df is not None:
        merged = frame.merge(
            target_df[["neuron_id", "binned_count_accuracy", "sensitivity", "compressed_spikes"]],
            on="neuron_id",
            how="left",
        )
        return merged
    return frame


def standardize_features(
    frame: pd.DataFrame,
    feature_columns: Sequence[str],
    means: Optional[np.ndarray] = None,
    scales: Optional[np.ndarray] = None,
):
    X = frame.loc[:, feature_columns].to_numpy(dtype=np.float64)
    if means is None:
        means = X.mean(axis=0)
    if scales is None:
        scales = X.std(axis=0)
    scales = np.where(scales < 1e-12, 1.0, scales)
    X_scaled = (X - means) / scales
    return X_scaled, np.asarray(means, dtype=np.float64), np.asarray(scales, dtype=np.float64)


def regression_metrics(y_true, y_pred) -> Dict[str, float]:
    y_true = np.asarray(y_true, dtype=np.float64)
    y_pred = np.asarray(y_pred, dtype=np.float64)
    err = y_pred - y_true
    mse = float(np.mean(np.square(err)))
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(mse))
    denom = float(np.sum(np.square(y_true - y_true.mean())))
    r2 = float(1.0 - np.sum(np.square(err)) / denom) if denom > 0 else 0.0
    return {"mae": mae, "rmse": rmse, "r2": r2}


def leave_one_ratio_out_cv(
    frame: pd.DataFrame,
    feature_columns: Sequence[str],
    target_column: str,
    alpha: float = 1.0,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    ratios = sorted(float(v) for v in frame["compression_ratio"].unique())
    fold_rows = []
    pred_parts = []

    for held_out_ratio in ratios:
        train_df = frame[frame["compression_ratio"] != held_out_ratio].copy()
        test_df = frame[frame["compression_ratio"] == held_out_ratio].copy()
        model = AccuracyPredictorModel.train(
            train_df,
            feature_columns=feature_columns,
            target_column=target_column,
            alpha=alpha,
        )
        pred = model.predict_dataframe(test_df)
        pred["held_out_ratio"] = float(held_out_ratio)
        metrics = regression_metrics(pred[target_column], pred["predicted_accuracy"])
        fold_rows.append({"held_out_ratio": float(held_out_ratio), **metrics})
        pred_parts.append(pred)

    all_pred = pd.concat(pred_parts, ignore_index=True)
    summary = regression_metrics(all_pred[target_column], all_pred["predicted_accuracy"])
    return pd.DataFrame(fold_rows), summary


@dataclass
class AccuracyPredictorModel:
    feature_columns: Tuple[str, ...]
    target_column: str
    alpha: float
    intercept_: float
    coefficients_: np.ndarray
    feature_means_: np.ndarray
    feature_scales_: np.ndarray
    training_metrics_: Dict[str, float]

    @classmethod
    def train(
        cls,
        frame: pd.DataFrame,
        feature_columns: Sequence[str] = DEFAULT_FEATURE_COLUMNS,
        target_column: str = "binned_count_accuracy",
        alpha: float = 1.0,
    ) -> "AccuracyPredictorModel":
        clean = frame.dropna(subset=list(feature_columns) + [target_column]).copy()
        X_scaled, means, scales = standardize_features(clean, feature_columns)
        y = clean[target_column].to_numpy(dtype=np.float64)

        X_aug = np.column_stack([np.ones(X_scaled.shape[0], dtype=np.float64), X_scaled])
        reg = np.eye(X_aug.shape[1], dtype=np.float64) * float(alpha)
        reg[0, 0] = 0.0
        beta = np.linalg.solve(X_aug.T @ X_aug + reg, X_aug.T @ y)

        intercept = float(beta[0])
        coef = beta[1:].astype(np.float64)
        y_hat = X_aug @ beta
        metrics = regression_metrics(y, y_hat)

        return cls(
            feature_columns=tuple(feature_columns),
            target_column=target_column,
            alpha=float(alpha),
            intercept_=intercept,
            coefficients_=coef,
            feature_means_=means,
            feature_scales_=scales,
            training_metrics_=metrics,
        )

    def _transform(self, frame: pd.DataFrame) -> np.ndarray:
        X = frame.loc[:, self.feature_columns].to_numpy(dtype=np.float64)
        return (X - self.feature_means_) / self.feature_scales_

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        X_scaled = self._transform(frame)
        y = self.intercept_ + X_scaled @ self.coefficients_
        return np.clip(y, 0.0, 1.0)

    def predict_dataframe(self, frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        out["predicted_accuracy"] = self.predict(frame)
        return out

    def predict_probe_accuracy(self, probe_feature_df: pd.DataFrame, ratio: float) -> Dict[str, object]:
        frame = build_ratio_feature_frame(probe_feature_df, ratio=float(ratio))
        pred = self.predict_dataframe(frame)
        return {
            "ratio": float(ratio),
            "predicted_probe_accuracy_mean": float(pred["predicted_accuracy"].mean()),
            "predicted_neuron_accuracy_table": pred,
        }

    def predict_probe_accuracy_from_files(
        self,
        templates_path,
        spike_times_path,
        spike_clusters_path,
        ops_path,
        ratio: float,
    ) -> Dict[str, object]:
        probe_feature_df = build_probe_feature_frame_from_files(
            templates_path=templates_path,
            spike_times_path=spike_times_path,
            spike_clusters_path=spike_clusters_path,
            ops_path=ops_path,
        )
        result = self.predict_probe_accuracy(probe_feature_df, ratio=ratio)
        result["probe_feature_df"] = probe_feature_df
        result["input_files"] = {
            "templates_path": str(Path(templates_path)),
            "spike_times_path": str(Path(spike_times_path)),
            "spike_clusters_path": str(Path(spike_clusters_path)),
            "ops_path": str(Path(ops_path)),
        }
        return result

    def to_payload(self) -> Dict[str, object]:
        return {
            "feature_columns": list(self.feature_columns),
            "target_column": self.target_column,
            "alpha": float(self.alpha),
            "intercept": float(self.intercept_),
            "coefficients": self.coefficients_.tolist(),
            "feature_means": self.feature_means_.tolist(),
            "feature_scales": self.feature_scales_.tolist(),
            "training_metrics": dict(self.training_metrics_),
        }

    @classmethod
    def from_payload(cls, payload: Dict[str, object]) -> "AccuracyPredictorModel":
        return cls(
            feature_columns=tuple(payload["feature_columns"]),
            target_column=str(payload["target_column"]),
            alpha=float(payload["alpha"]),
            intercept_=float(payload["intercept"]),
            coefficients_=np.asarray(payload["coefficients"], dtype=np.float64),
            feature_means_=np.asarray(payload["feature_means"], dtype=np.float64),
            feature_scales_=np.asarray(payload["feature_scales"], dtype=np.float64),
            training_metrics_=dict(payload.get("training_metrics", {})),
        )

    def save(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, self.to_payload(), allow_pickle=True)

    @classmethod
    def load(cls, path) -> "AccuracyPredictorModel":
        payload = np.load(Path(path), allow_pickle=True).item()
        return cls.from_payload(payload)
