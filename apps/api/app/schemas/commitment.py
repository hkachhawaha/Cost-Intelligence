"""Commitment Check contracts (§4.3, §8.6). `ProposedDeal` is a deal NOT YET signed;
`CommitmentVerdict` is the deterministic stress-test result. The verdict is ALWAYS advisory —
the human signs. The index move is a first-party assumption, never an external feed.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ProposedDeal(BaseModel):
    """Input to Commitment Check. Describes a deal NOT YET signed."""

    entity_id: str | None = None
    vendor_name: str | None = None
    acv: Decimal = Field(gt=0)
    tcv: Decimal | None = None
    term_months: int | None = Field(default=None, gt=0)
    indexed_share: Decimal = Field(ge=0, le=1)  # fraction index-linked
    assumed_index_pct: Decimal = Field(ge=0)  # FIRST-PARTY assumption, e.g. 0.03
    margin_tolerance: Decimal = Field(gt=0)  # $ exposure the entity can absorb

    @field_validator("indexed_share")
    @classmethod
    def share_is_fraction(cls, v: Decimal) -> Decimal:
        if not (0 <= v <= 1):
            raise ValueError("indexed_share must be in [0,1]")
        return v


class StressScenario(BaseModel):
    move_pct: int  # 5 | 10 | 15
    exposure: Decimal  # indexed exposure under this adverse move
    over_tolerance: bool  # exposure − tolerance > 0


class CommitmentVerdict(BaseModel):
    indexed_exposure: Decimal
    scenarios: list[StressScenario]
    verdict: Literal["approve", "condition", "block"]
    conditions: list[str] = []
    rationale: str | None = None
    advisory: bool = True  # ALWAYS true — the human signs


class SignDecision(BaseModel):
    decision: Literal["accepted", "declined", "modified"]
    note: str | None = None
