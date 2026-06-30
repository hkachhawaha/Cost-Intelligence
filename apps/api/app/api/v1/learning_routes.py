"""Continuous-learning calibration (§9). Read the active learned parameters and trigger a
deterministic recalibration. Recalibration is sparse-safe (skips below the configured example
floor) and non-regressing (a worse candidate never activates)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_current_principal
from app.core.database import get_session
from app.core.rbac import require_permission
from app.models.automation import ModelCalibration
from app.services.feedback_loop import LearningFeedbackService

router = APIRouter(tags=["learning"])


@router.get("/learning/calibration", dependencies=[Depends(require_permission("learning:read"))])
async def list_calibration(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.scalars(
            select(ModelCalibration)
            .where(ModelCalibration.active.is_(True))
            .order_by(ModelCalibration.model_kind)
        )
    ).all()
    return {
        "active": [
            {
                "model_kind": c.model_kind,
                "version": c.version,
                "params": c.params,
                "metrics": c.metrics,
            }
            for c in rows
        ]
    }


@router.post(
    "/learning/recalibrate",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("learning:write"))],
)
async def recalibrate(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    svc = LearningFeedbackService(session, principal.tenant_id)
    result = await svc.recalibrate_all()
    await session.commit()
    return {
        "fuzzy_weights": _summ(result["fuzzy_weights"]),
        "detection_thresholds": _summ(result["detection_thresholds"]),
    }


def _summ(cal: ModelCalibration | None) -> dict | None:
    if cal is None:
        return None  # too few examples → skipped (sparse-safe)
    return {
        "version": cal.version,
        "active": cal.active,
        "params": cal.params,
        "metrics": cal.metrics,
    }
