"""Single chokepoint for ALL LLM calls (blueprint §5.5, §6.2).

Responsibilities: routing (alias → pinned model), version pinning, response caching,
cost/rate control, PII redaction, per-tenant cost attribution.

NO other module may import `google.genai` directly — everything goes through here.
The Gemini client is created lazily so the gateway (and its pure helpers: routing,
pricing, redaction, budget) stay importable and unit-testable without a key. Redis is
opened per call via `get_redis()` to stay event-loop-safe across Celery/test loops.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from decimal import Decimal

from opentelemetry import trace

from app.core.config import settings
from app.core.redis import get_redis
from app.services.usage import record_model_usage

logger = logging.getLogger("nirvana.model_gateway")
tracer = trace.get_tracer("nirvana.model_gateway")


# ── Version pinning (blueprint §12.3). The ONLY place model IDs are written. ──
MODEL_ALIASES: dict[str, str] = {
    "complex": "gemini-2.5-pro",  # generation, drafting, conversation
    "fast": "gemini-2.5-flash",  # intent routing, classification
}

# Price table ($ per 1M tokens) — used for code-side cost attribution, never the model.
MODEL_PRICING: dict[str, dict[str, Decimal]] = {
    "gemini-2.5-pro": {
        "input": Decimal("1.25"),
        "output": Decimal("10.00"),
        "cache_read": Decimal("0.31"),
    },
    "gemini-2.5-flash": {
        "input": Decimal("0.30"),
        "output": Decimal("2.50"),
        "cache_read": Decimal("0.075"),
    },
}

# PII patterns redacted before ANY prompt leaves the process. Business figures
# (ACV, amounts) are NOT PII and are intentionally left intact so answers can be grounded.
_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("[EMAIL]", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("[PHONE]", re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("[SSN]", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
]


@dataclass
class CompletionResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_hit: bool
    latency_ms: int


class RateLimitExceeded(Exception):
    """Raised when a tenant exceeds its per-window token budget (circuit breaker)."""


class ModelGateway:
    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not settings.gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY not configured")
            from google import genai

            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    # ── public API ────────────────────────────────────────────────────────
    async def complete(
        self,
        model: str,
        prompt: str,
        *,
        tenant_id: str,
        purpose: str,
        system: str | None = None,
        max_tokens: int = 4096,
        run_id: str | None = None,
        cache_ttl_s: int | None = None,
    ) -> CompletionResult:
        """Text completion. `model` is an alias ('complex'|'fast') or a pinned id."""
        return await self._invoke(
            model=model,
            prompt=prompt,
            tenant_id=tenant_id,
            purpose=purpose,
            system=system,
            max_tokens=max_tokens,
            run_id=run_id,
            cache_ttl_s=cache_ttl_s or settings.model_cache_ttl_s,
            want_json=False,
        )

    async def complete_json(
        self,
        model: str,
        prompt: str,
        *,
        tenant_id: str,
        purpose: str,
        system: str | None = None,
        max_tokens: int = 2048,
        run_id: str | None = None,
    ) -> dict:
        """JSON completion: appends a strict-JSON instruction, parses, returns dict."""
        json_prompt = (
            f"{prompt}\n\nRespond with ONLY valid minified JSON. No prose, no markdown fences."
        )
        result = await self._invoke(
            model=model,
            prompt=json_prompt,
            tenant_id=tenant_id,
            purpose=purpose,
            system=system,
            max_tokens=max_tokens,
            run_id=run_id,
            cache_ttl_s=settings.model_cache_ttl_s,
            want_json=True,
        )
        return self._safe_json(result.text)

    # ── internals ─────────────────────────────────────────────────────────
    async def _invoke(
        self,
        *,
        model: str,
        prompt: str,
        tenant_id: str,
        purpose: str,
        system: str | None,
        max_tokens: int,
        run_id: str | None,
        cache_ttl_s: int,
        want_json: bool,
    ) -> CompletionResult:
        from google.genai import errors as genai_errors
        from google.genai import types

        pinned = MODEL_ALIASES.get(model, model)  # routing + version pinning
        with tracer.start_as_current_span("model_gateway.complete") as span:
            span.set_attribute("nirvana.model", pinned)
            span.set_attribute("nirvana.purpose", purpose)
            span.set_attribute("nirvana.tenant_id", tenant_id)

            # 1) PII redaction BEFORE anything leaves the process
            redacted = self._redact_pii(prompt)
            redacted_system = self._redact_pii(system) if system else None

            # 2) Rate / cost control (circuit breaker per tenant)
            await self._enforce_budget(tenant_id)

            redis = get_redis()
            try:
                # 3) Response cache (keyed on pinned model + redacted prompt + format)
                cache_key = self._cache_key(pinned, redacted, redacted_system, want_json)
                cached = await redis.get(cache_key)
                if cached is not None:
                    span.set_attribute("nirvana.cache_hit", True)
                    await record_model_usage(
                        tenant_id=tenant_id,
                        model=pinned,
                        purpose=purpose,
                        input_tokens=0,
                        output_tokens=0,
                        cache_read_tokens=0,
                        cost_usd=Decimal("0"),
                        cache_hit=True,
                        run_id=run_id,
                    )
                    return CompletionResult(
                        text=cached.decode() if isinstance(cached, bytes) else cached,
                        model=pinned,
                        input_tokens=0,
                        output_tokens=0,
                        cache_read_tokens=0,
                        cache_hit=True,
                        latency_ms=0,
                    )

                # 4) The actual model call (the ONLY google.genai call site)
                t0 = time.perf_counter()
                gen_config = types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    system_instruction=redacted_system or None,
                    response_mime_type="application/json" if want_json else None,
                )
                try:
                    resp = await self._get_client().aio.models.generate_content(
                        model=pinned,
                        contents=redacted,
                        config=gen_config,
                    )
                except genai_errors.ClientError as e:
                    if getattr(e, "code", None) == 429:
                        span.set_attribute("nirvana.provider_rate_limited", True)
                        raise RateLimitExceeded("provider rate limited") from e
                    raise
                latency_ms = int((time.perf_counter() - t0) * 1000)

                text = resp.text or ""
                usage = resp.usage_metadata
                input_tokens = (usage.prompt_token_count or 0) if usage else 0
                output_tokens = (usage.candidates_token_count or 0) if usage else 0
                cache_read = (usage.cached_content_token_count or 0) if usage else 0

                # 5) Per-tenant cost attribution (computed in CODE)
                cost = self._compute_cost(pinned, input_tokens, output_tokens, cache_read)
                await record_model_usage(
                    tenant_id=tenant_id,
                    model=pinned,
                    purpose=purpose,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=cache_read,
                    cost_usd=cost,
                    cache_hit=False,
                    run_id=run_id,
                )
                await self._increment_budget(tenant_id, input_tokens + output_tokens)

                # 6) Cache the completion
                await redis.set(cache_key, text, ex=cache_ttl_s)

                span.set_attribute("nirvana.input_tokens", input_tokens)
                span.set_attribute("nirvana.output_tokens", output_tokens)
                span.set_attribute("nirvana.cost_usd", float(cost))
                return CompletionResult(
                    text=text,
                    model=pinned,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=cache_read,
                    cache_hit=False,
                    latency_ms=latency_ms,
                )
            finally:
                await redis.aclose()

    def _redact_pii(self, text: str) -> str:
        for replacement, pattern in _PII_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def _cache_key(self, model: str, prompt: str, system: str | None, want_json: bool) -> str:
        h = hashlib.sha256()
        h.update(model.encode())
        h.update(b"\x00")
        h.update((system or "").encode())
        h.update(b"\x00")
        h.update(prompt.encode())
        h.update(b"\x00")
        h.update(b"json" if want_json else b"text")
        return f"mg:cache:{h.hexdigest()}"

    def _compute_cost(self, model: str, in_tok: int, out_tok: int, cache_tok: int) -> Decimal:
        p = MODEL_PRICING[model]
        m = Decimal(1_000_000)
        return (
            Decimal(in_tok) / m * p["input"]
            + Decimal(out_tok) / m * p["output"]
            + Decimal(cache_tok) / m * p["cache_read"]
        )

    async def _enforce_budget(self, tenant_id: str) -> None:
        window_key = f"mg:budget:{tenant_id}:{int(time.time() // 60)}"  # per-minute window
        redis = get_redis()
        try:
            used = int(await redis.get(window_key) or 0)
        finally:
            await redis.aclose()
        if used >= settings.model_tokens_per_minute_per_tenant:
            logger.warning("tenant %s tripped model rate limit (%d tok/min)", tenant_id, used)
            raise RateLimitExceeded("tenant token budget exceeded for this minute")

    async def _increment_budget(self, tenant_id: str, tokens: int) -> None:
        window_key = f"mg:budget:{tenant_id}:{int(time.time() // 60)}"
        redis = get_redis()
        try:
            await redis.incrby(window_key, tokens)
            await redis.expire(window_key, 120)
        finally:
            await redis.aclose()

    @staticmethod
    def _safe_json(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`").lstrip("json").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1:
                return json.loads(text[start : end + 1])
            raise


model_gateway = ModelGateway()  # module-level singleton
