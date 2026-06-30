"""GroundednessValidator (§5.3) — the enforcement gate behind "every figure cites a record".

Extracts dollar figures from an answer and verifies each appears (within a rounding
tolerance) in the retrieved, code-computed context. Pure Python, no LLM — this is the
authoritative groundedness check (an optional LLM cross-check is secondary, §7.4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# Matches $1,234, $1.2M, $1,234.56, 1.2 million, etc. (with or without $).
# The comma-grouped alternative requires at least one comma group (`+`); otherwise a bare
# number like "241000.00" would be split into "241" by the (zero-or-more) comma branch
# winning the ordered alternation before the plain-digits branch can consume it whole.
_MONEY_RE = re.compile(
    r"""\$?\s*
        (?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)
        \s*(?P<unit>[kKmMbB]|thousand|million|billion)?
    """,
    re.VERBOSE,
)
_UNIT_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}

# Tolerance for rounding ("$241K" vs $241,000). 0.5% relative or $1 absolute.
_REL_TOL = Decimal("0.005")
_ABS_TOL = Decimal("1")


@dataclass
class ValidationOutcome:
    ok: bool
    reason: str = ""
    ungrounded_figures: list[str] = field(default_factory=list)


def extract_dollar_figures(text: str) -> list[Decimal]:
    out: list[Decimal] = []
    for m in _MONEY_RE.finditer(text):
        raw = m.group("num").replace(",", "")
        try:
            val = Decimal(raw)
        except InvalidOperation:
            continue
        unit = (m.group("unit") or "").lower()
        if unit:
            val = val * Decimal(str(_UNIT_MULT[unit]))
        # Ignore bare small integers likely to be counts ("5 contracts"), not money,
        # UNLESS prefixed by $ or carrying a unit, or >= 100.
        if "$" in m.group(0) or unit or val >= Decimal("100"):
            out.append(val)
    return out


def _is_grounded(figure: Decimal, context_figures: list[Decimal]) -> bool:
    for cf in context_figures:
        diff = abs(figure - cf)
        if diff <= _ABS_TOL:
            return True
        if cf != 0 and (diff / abs(cf)) <= _REL_TOL:
            return True
    return False


class GroundednessValidator:
    def validate(self, answer: str, context_records: list[dict]) -> ValidationOutcome:
        answer_figures = extract_dollar_figures(answer)
        if not answer_figures:
            return ValidationOutcome(ok=True)  # no $ to ground → fine

        # The set of figures the model was ALLOWED to cite (code-computed values).
        context_blob = " ".join(self._record_text(r) for r in context_records)
        context_figures = extract_dollar_figures(context_blob)

        ungrounded = [
            f"${fig:,.2f}" for fig in answer_figures if not _is_grounded(fig, context_figures)
        ]
        if ungrounded:
            return ValidationOutcome(
                ok=False,
                reason=f"answer contains ungrounded dollar figures: {ungrounded}",
                ungrounded_figures=ungrounded,
            )
        return ValidationOutcome(ok=True)

    @staticmethod
    def _record_text(record: dict) -> str:
        # Flatten evidence/impact/text/label so all code-computed figures are captured.
        parts: list[str] = []
        for key in ("text", "impact", "label"):
            if key in record and record[key] is not None:
                parts.append(str(record[key]))
        if "evidence" in record and isinstance(record["evidence"], dict):
            parts.extend(str(v) for v in record["evidence"].values())
        return " ".join(parts)


groundedness_validator = GroundednessValidator()
