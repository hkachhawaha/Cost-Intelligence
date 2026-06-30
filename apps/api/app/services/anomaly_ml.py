"""IsolationForest anomaly service (§5.5, §8.2) — the Phase 9 ML upgrade over P7 stats.

sklearn is an OPTIONAL dependency: `train`/`score` lazy-import it and, when it is absent (or
no model has been fitted yet), fall back to the deterministic P7 Z-score detector so the
service is always offline-safe. No money math here — anomaly scores are advisory signals only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from app.services.anomaly_detection import Anomaly, detect_spend_spikes

logger = logging.getLogger("anomaly.ml")

# Canonical numeric features fed to the model (order is stable for reproducibility).
FEATURE_ORDER = ("amount", "month", "dow", "vendor_freq")


@dataclass
class TrainedModel:
    """In-memory handle to a fitted IsolationForest (persisted ref lives in model_calibration)."""

    estimator: object
    contamination: float
    n_samples: int


def _sklearn():
    """Lazy import; returns the IsolationForest class or None when sklearn isn't installed."""
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:  # offline / minimal install
        return None
    return IsolationForest


def featurize(row: dict) -> list[float]:
    """Project a spend row → the fixed numeric feature vector. Missing → 0.0."""
    return [float(row.get(f, 0) or 0) for f in FEATURE_ORDER]


class IsolationForestAnomalyService:
    """Fit per (tenant) and score spend rows. Falls back to Z-score when ML is unavailable."""

    def __init__(self, contamination: float = 0.02, random_state: int = 42):
        self.contamination = contamination
        self.random_state = random_state
        self._model: TrainedModel | None = None

    # ── training ──────────────────────────────────────────────────────────────
    def train(self, rows: list[dict]) -> TrainedModel | None:
        """Fit IsolationForest on featurized rows. Returns None (no model) if sklearn is
        missing or there's too little data — callers then use the Z-score fallback."""
        IsolationForest = _sklearn()
        if IsolationForest is None:
            logger.info("anomaly.ml.sklearn_absent — using zscore fallback")
            return None
        if len(rows) < 50:  # not enough signal for an unsupervised fit
            logger.info("anomaly.ml.too_few_samples n=%d — using zscore fallback", len(rows))
            return None
        X = [featurize(r) for r in rows]
        est = IsolationForest(
            contamination=self.contamination,
            random_state=self.random_state,
            n_estimators=100,
        )
        est.fit(X)
        self._model = TrainedModel(
            estimator=est, contamination=self.contamination, n_samples=len(rows)
        )
        return self._model

    # ── scoring ───────────────────────────────────────────────────────────────
    def score(self, rows: list[dict]) -> list[Anomaly]:
        """Score rows for anomalousness. Uses the fitted model if present; otherwise the
        deterministic P7 Z-score detector. Each row needs `spend_id` + `amount`."""
        if self._model is None:
            return self._zscore_fallback(rows)
        est = self._model.estimator
        X = [featurize(r) for r in rows]
        # predict: -1 = outlier, 1 = inlier; decision_function: higher = more normal.
        preds = est.predict(X)  # type: ignore[attr-defined]
        scores = est.decision_function(X)  # type: ignore[attr-defined]
        out: list[Anomaly] = []
        for row, pred, raw in zip(rows, preds, scores, strict=False):
            if pred == -1:
                out.append(
                    Anomaly(
                        anomaly_type="spend_spike",
                        subject_type="spend_record",
                        subject_id=str(row.get("spend_id", "")),
                        method="isolation_forest",
                        score=round(float(-raw), 4),  # invert so higher = more anomalous
                        detail={"amount": float(row.get("amount", 0) or 0),
                                "contamination": self.contamination},
                    )
                )
        return out

    @staticmethod
    def _zscore_fallback(rows: list[dict]) -> list[Anomaly]:
        """Deterministic P7 detector over (spend_id, amount). Always available offline."""
        series = [(str(r.get("spend_id", "")), Decimal(str(r.get("amount", 0) or 0))) for r in rows]
        found = detect_spend_spikes(series)
        for a in found:
            a.method = "zscore_fallback"
        return found
