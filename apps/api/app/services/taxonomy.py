"""TaxonomyService (§5.4) — L1/L2 classification for the Enrichment agent.

Deterministic-first: a keyword map handles the unambiguous majority for free (no model
call, high confidence). The LLM (gemini-2.5-flash via the gateway) is the FALLBACK only
for the long tail; its output is validated against the registry (unknown → Other).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.model_gateway import model_gateway

# Canonical 2-level taxonomy (configurable per tenant). L1 = category, L2 = sub-category.
TAXONOMY: dict[str, list[str]] = {
    "IT & Software": ["SaaS", "Cloud Infrastructure", "Hardware", "Telecom"],
    "Professional Services": ["Consulting", "Legal", "Audit", "Staffing"],
    "Facilities": ["Rent", "Utilities", "Maintenance", "Security"],
    "Marketing": ["Advertising", "Events", "Agency", "Content"],
    "Logistics": ["Freight", "Warehousing", "Last-Mile"],
    "Other": ["Uncategorized"],
}

# Deterministic keyword → (L1, L2) map for the unambiguous majority.
_KEYWORD_MAP: list[tuple[tuple[str, str], list[str]]] = [
    (("IT & Software", "SaaS"), ["saas", "subscription", "license", "seat"]),
    (("IT & Software", "Cloud Infrastructure"), ["aws", "azure", "gcp", "cloud", "compute", "s3"]),
    (("Professional Services", "Consulting"), ["consult", "advisory", "engagement"]),
    (("Professional Services", "Legal"), ["legal", "law firm", "counsel"]),
    (("Facilities", "Rent"), ["lease", "rent", "premises"]),
    (("Logistics", "Freight"), ["freight", "shipping", "carrier"]),
]


@dataclass
class TaxonomyResult:
    l1: str
    l2: str
    confidence: float
    method: str  # 'rules' | 'llm'


class TaxonomyService:
    def classify_rules(
        self, vendor_name: str, gl_code: str | None, description: str | None
    ) -> TaxonomyResult | None:
        blob = " ".join(filter(None, [vendor_name, gl_code, description])).lower()
        for (l1, l2), keywords in _KEYWORD_MAP:
            if any(kw in blob for kw in keywords):
                return TaxonomyResult(l1=l1, l2=l2, confidence=0.95, method="rules")
        return None

    async def classify(
        self,
        *,
        tenant_id: str,
        vendor_name: str,
        gl_code: str | None,
        description: str | None,
        run_id: str | None = None,
    ) -> TaxonomyResult:
        # 1) Deterministic first (free, high-confidence).
        if (r := self.classify_rules(vendor_name, gl_code, description)) is not None:
            return r
        # 2) LLM fallback (haiku) for the long tail.
        from app.agents.prompts import TAXONOMY_CLASSIFICATION_PROMPT

        prompt = TAXONOMY_CLASSIFICATION_PROMPT.format(
            taxonomy="\n".join(f"- {l1}: {', '.join(l2s)}" for l1, l2s in TAXONOMY.items()),
            vendor_name=vendor_name,
            gl_code=gl_code or "unknown",
            description=description or "none",
        )
        result = await model_gateway.complete_json(
            "fast", prompt, tenant_id=tenant_id, purpose="taxonomy_classify", run_id=run_id
        )
        l1 = result.get("l1", "Other")
        l2 = result.get("l2", "Uncategorized")
        # Validate against the registry; unknown → Other/Uncategorized.
        if l1 not in TAXONOMY or l2 not in TAXONOMY.get(l1, []):
            l1, l2 = "Other", "Uncategorized"
        return TaxonomyResult(
            l1=l1, l2=l2, confidence=float(result.get("confidence", 0.6)), method="llm"
        )


taxonomy_service = TaxonomyService()
