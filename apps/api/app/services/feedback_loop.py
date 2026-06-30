"""LearningFeedbackService (§9) — capture human-feedback signals and recalibrate.

Three signal sources (confirmed matches, corrected taxonomy, opportunity outcomes), three
targets (fuzzy weights, detection thresholds, anomaly model). Learned params are versioned
in `model_calibration`; activation is atomic and guarded by non-regression. PO-exact
confidence (1.0) is NEVER learnable. All math here is deterministic (no external feed).
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.automation import LearningLabel, ModelCalibration

logger = logging.getLogger("learning")

# The signals whose weights may be learned; PO-exact is excluded (always 1.0).
LEARNABLE_FUZZY_SIGNALS = ("vendor", "amount", "date", "cost_center")
PO_EXACT_CONFIDENCE = 1.0  # platform invariant — never learned away


class LearningFeedbackService:
    def __init__(self, session: AsyncSession, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    # ── signal capture ──────────────────────────────────────────────────────
    async def _label(
        self, signal_type, subject_id, features, label, actor_id=None
    ) -> LearningLabel:
        row = LearningLabel(
            id=uuid4(),
            tenant_id=UUID(self.tenant_id),
            signal_type=signal_type,
            subject_id=UUID(str(subject_id)),
            features=features,
            label=label,
            actor_id=UUID(actor_id) if actor_id else None,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def on_match_confirmed(
        self, match_result_id, features: dict, correct_contract_id, actor_id=None
    ):
        return await self._label(
            "match_confirmed",
            match_result_id,
            features,
            {"contract_id": str(correct_contract_id)},
            actor_id,
        )

    async def on_taxonomy_corrected(
        self, spend_id, features: dict, correct_l1, correct_l2, actor_id=None
    ):
        return await self._label(
            "taxonomy_corrected", spend_id, features, {"l1": correct_l1, "l2": correct_l2}, actor_id
        )

    async def on_opportunity_outcome(self, opp_id, features: dict, confirmed: bool, actor_id=None):
        return await self._label(
            "opp_confirmed" if confirmed else "opp_dismissed",
            opp_id,
            features,
            {"confirmed": confirmed},
            actor_id,
        )

    # ── recalibration ─────────────────────────────────────────────────────────
    async def recalibrate_all(self) -> dict:
        return {
            "fuzzy_weights": await self._recalibrate_fuzzy_weights(),
            "detection_thresholds": await self._recalibrate_detection_thresholds(),
        }

    async def _recalibrate_fuzzy_weights(self) -> ModelCalibration | None:
        labels = await self._labels(["match_confirmed", "match_reassigned"])
        if len(labels) < settings.learning_min_examples_fuzzy:
            return None
        weights = self._fit_weights(labels)  # learnable signals only; never PO-exact
        precision = self._eval_weights(labels, weights)
        return await self._publish("fuzzy_weights", weights, {"precision": precision})

    async def _recalibrate_detection_thresholds(self) -> ModelCalibration | None:
        labels = await self._labels(["opp_confirmed", "opp_dismissed"])
        if len(labels) < settings.learning_min_examples_thresholds:
            return None
        thresholds, precision = self._optimize_thresholds(labels)
        return await self._publish("detection_thresholds", thresholds, {"precision": precision})

    # ── learned-parameter math (deterministic) ────────────────────────────────
    @staticmethod
    def _fit_weights(labels: list[LearningLabel]) -> dict:
        """Weight each signal by its mean value among CORRECT matches, normalized to sum 1.0.
        PO-exact is not in the learnable set (it stays a constant 1.0)."""
        correct = [lbl.features for lbl in labels if lbl.features.get("correct")]
        if not correct:
            return {s: 1.0 / len(LEARNABLE_FUZZY_SIGNALS) for s in LEARNABLE_FUZZY_SIGNALS}
        raw = {
            s: sum(float(f.get(s, 0)) for f in correct) / len(correct)
            for s in LEARNABLE_FUZZY_SIGNALS
        }
        total = sum(raw.values()) or 1.0
        return {s: round(v / total, 4) for s, v in raw.items()}

    @staticmethod
    def _eval_weights(labels: list[LearningLabel], weights: dict) -> float:
        """Precision proxy: fraction of correct examples whose weighted score ≥ 0.5."""
        scored = [
            (
                sum(weights[s] * float(lbl.features.get(s, 0)) for s in LEARNABLE_FUZZY_SIGNALS),
                bool(lbl.features.get("correct")),
            )
            for lbl in labels
        ]
        passed = [c for score, c in scored if score >= 0.5]
        return round(sum(1 for c in passed if c) / len(passed), 4) if passed else 0.0

    def _optimize_thresholds(self, labels: list[LearningLabel]) -> tuple[dict, float]:
        """Pick a min-impact threshold that admits confirmed opps; clamp to config bounds."""
        confirmed = [
            float(lbl.features.get("impact", 0)) for lbl in labels if lbl.label.get("confirmed")
        ]
        chosen = min(confirmed) if confirmed else settings.detection_threshold_min
        clamped = max(
            settings.detection_threshold_min, min(chosen, settings.detection_threshold_max)
        )
        # Precision proxy: confirmed at/above threshold / all at/above threshold.
        above = [lbl for lbl in labels if float(lbl.features.get("impact", 0)) >= clamped]
        precision = (
            round(sum(1 for lbl in above if lbl.label.get("confirmed")) / len(above), 4)
            if above
            else 0.0
        )
        return {"min_impact": clamped}, precision

    # ── persistence / versioning ──────────────────────────────────────────────
    async def _labels(self, signal_types: list[str]) -> list[LearningLabel]:
        rows = await self.session.scalars(
            select(LearningLabel).where(LearningLabel.signal_type.in_(signal_types))
        )
        return list(rows.all())

    async def _active(self, kind: str) -> ModelCalibration | None:
        return await self.session.scalar(
            select(ModelCalibration)
            .where(ModelCalibration.model_kind == kind)
            .where(ModelCalibration.active.is_(True))
        )

    async def _publish(self, kind: str, params: dict, metrics: dict) -> ModelCalibration:
        """Version + atomically activate, but ONLY if metrics don't regress; keep prior for
        rollback. Returns the new calibration (active flag reflects the regression guard)."""
        prev = await self._active(kind)
        next_version = (
            (
                await self.session.scalar(
                    select(func.coalesce(func.max(ModelCalibration.version), 0)).where(
                        ModelCalibration.model_kind == kind
                    )
                )
            )
            or 0
        ) + 1
        improves = prev is None or metrics.get("precision", 0) >= prev.metrics.get("precision", 0)
        cal = ModelCalibration(
            id=uuid4(),
            tenant_id=UUID(self.tenant_id),
            model_kind=kind,
            version=next_version,
            params=params,
            metrics=metrics,
            active=improves,
        )
        if improves and prev is not None:
            prev.active = False
        self.session.add(cal)
        await self.session.flush()
        return cal
