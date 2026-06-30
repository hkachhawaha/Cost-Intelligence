"""Statistical anomaly detection for v1 (§5.5, §8.2). All math in Python — no LLM.

Detectors: spend spike (Z-score), off-pattern GL (IQR per GL), new vendor (set diff),
duplicate payment (same vendor+amount within a window). ML models are deferred to Phase 9.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal


@dataclass
class Anomaly:
    anomaly_type: str
    subject_type: str
    subject_id: str
    method: str
    score: float
    detail: dict


def detect_spend_spikes(
    series: list[tuple[str, Decimal]], z_threshold: float = 3.0
) -> list[Anomaly]:
    """series = [(spend_id, amount)] for one vendor/category. Flags |z| > threshold."""
    amounts = [float(a) for _, a in series]
    if len(amounts) < 4:
        return []
    mean = statistics.mean(amounts)
    std = statistics.pstdev(amounts)
    if std == 0:
        return []
    out: list[Anomaly] = []
    for (spend_id, amount), x in zip(series, amounts, strict=False):
        z = (x - mean) / std
        if abs(z) > z_threshold:
            out.append(
                Anomaly(
                    anomaly_type="spend_spike",
                    subject_type="spend_record",
                    subject_id=str(spend_id),
                    method="zscore",
                    score=round(z, 3),
                    detail={
                        "mean": round(mean, 2),
                        "std": round(std, 2),
                        "value": float(amount),
                        "z_threshold": z_threshold,
                    },
                )
            )
    return out


def detect_off_pattern_gl(
    by_gl: dict[str, list[tuple[str, Decimal]]], iqr_mult: float = 1.5
) -> list[Anomaly]:
    """Per GL code, flag amounts beyond Q3 + iqr_mult*IQR (or below Q1 - iqr_mult*IQR)."""
    out: list[Anomaly] = []
    for gl, rows in by_gl.items():
        amounts = sorted(float(a) for _, a in rows)
        if len(amounts) < 4:
            continue
        q1 = _percentile(amounts, 25)
        q3 = _percentile(amounts, 75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        hi = q3 + iqr_mult * iqr
        lo = q1 - iqr_mult * iqr
        for spend_id, amount in rows:
            v = float(amount)
            if v > hi or v < lo:
                out.append(
                    Anomaly(
                        anomaly_type="off_pattern_gl",
                        subject_type="spend_record",
                        subject_id=str(spend_id),
                        method="iqr",
                        score=round((v - q3) / iqr if v > hi else (q1 - v) / iqr, 3),
                        detail={
                            "gl_code": gl,
                            "q1": q1,
                            "q3": q3,
                            "iqr": iqr,
                            "upper": hi,
                            "lower": lo,
                            "value": v,
                        },
                    )
                )
    return out


def detect_new_vendors(
    current_vendor_ids: set[str], historical_vendor_ids: set[str]
) -> list[Anomaly]:
    """Vendors appearing this period that were never seen before."""
    return [
        Anomaly(
            anomaly_type="new_vendor",
            subject_type="vendor",
            subject_id=str(vid),
            method="rule",
            score=1.0,
            detail={"first_seen": True},
        )
        for vid in (current_vendor_ids - historical_vendor_ids)
    ]


def detect_duplicate_payments(records: list[dict], window_days: int = 7) -> list[Anomaly]:
    """Same vendor + amount within `window_days` → likely duplicate-payment signature."""
    from collections import defaultdict

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        groups[(r["vendor_id"], r["amount"])].append(r)
    out: list[Anomaly] = []
    for (vendor_id, amount), rows in groups.items():
        rows.sort(key=lambda x: x["spend_date"])
        for i in range(1, len(rows)):
            gap = rows[i]["spend_date"] - rows[i - 1]["spend_date"]
            if gap <= timedelta(days=window_days):
                out.append(
                    Anomaly(
                        anomaly_type="duplicate_payment",
                        subject_type="spend_record",
                        subject_id=str(rows[i]["spend_id"]),
                        method="rule",
                        score=1.0,
                        detail={
                            "vendor_id": str(vendor_id),
                            "amount": str(amount),
                            "prior_spend_id": str(rows[i - 1]["spend_id"]),
                            "days_apart": gap.days,
                        },
                    )
                )
    return out


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)
