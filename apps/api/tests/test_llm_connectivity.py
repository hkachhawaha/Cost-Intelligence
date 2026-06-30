"""Live Gemini connectivity checks (manual / opt-in).

These hit the real Google Gemini API, so they only run when GEMINI_API_KEY is set
(skipped in offline CI). They verify, bottom-up:
  1. raw SDK generation        — is the key valid + network reachable?
  2. raw SDK embeddings        — does gemini-embedding-001 return a 1536-dim vector?
  3. ModelGateway.complete     — does the app's chokepoint return text + token usage?
  4. ModelGateway.complete_json— does JSON mode parse into a dict?

Run: GEMINI_API_KEY=… uv run pytest apps/api/tests/test_llm_connectivity.py -v -s
"""

from __future__ import annotations

import pytest

from app.core.config import settings

pytestmark = pytest.mark.skipif(
    not settings.gemini_api_key, reason="no GEMINI_API_KEY configured"
)

_GEN_MODEL = "gemini-2.5-flash"  # cheap/fast for a smoke test
_EMBED_MODEL = "gemini-embedding-001"


@pytest.fixture(autouse=True)
def _fresh_gateway_client():
    """pytest-asyncio gives each test its own event loop; the gateway caches one
    genai client whose httpx pool binds to the loop that created it. Reset it per
    test so each builds a client on its own loop (a no-op in the long-lived app loop)."""
    from app.core.model_gateway import model_gateway

    model_gateway._client = None
    yield
    model_gateway._client = None


async def test_gemini_generation_direct():
    """Raw SDK call — proves the key works and the model responds."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    resp = await client.aio.models.generate_content(
        model=_GEN_MODEL,
        contents="Reply with exactly one word: PONG",
        config=types.GenerateContentConfig(max_output_tokens=2000),
    )
    text = (resp.text or "").strip()
    print(f"\n[direct generate] -> {text!r}")
    assert text, "Gemini returned empty text"
    assert "PONG" in text.upper()


async def test_gemini_embeddings_direct():
    """Raw SDK embeddings — proves gemini-embedding-001 returns a 1536-dim vector."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    resp = await client.aio.models.embed_content(
        model=_EMBED_MODEL,
        contents=["Acme Cloud renews on 2026-08-15 at $240,000 ACV."],
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT", output_dimensionality=settings.embedding_dim
        ),
    )
    vec = resp.embeddings[0].values
    print(f"\n[direct embed] dim={len(vec)} first3={vec[:3]}")
    assert len(vec) == settings.embedding_dim == 1536
    assert all(isinstance(x, float) for x in vec[:5])


async def test_gateway_complete_live():
    """The app's ModelGateway end-to-end — routing alias → text + token usage.

    A unique nonce in the prompt busts the gateway's Redis response cache so this is a
    fresh call (token accounting exercised), not a cache hit (which reports 0 tokens)."""
    from uuid import uuid4

    from app.core.model_gateway import model_gateway

    res = await model_gateway.complete(
        "fast",
        f"(ref {uuid4()}) Reply with exactly one word: PONG",
        tenant_id="00000000-0000-0000-0000-000000000000",
        purpose="connectivity_check",
        max_tokens=2000,
    )
    print(f"\n[gateway complete] model={res.model} in={res.input_tokens} "
          f"out={res.output_tokens} cache_hit={res.cache_hit} text={res.text.strip()!r}")
    assert res.model == "gemini-2.5-flash"  # alias 'fast' resolved + version-pinned
    assert "PONG" in res.text.upper()
    assert res.input_tokens > 0  # fresh call → real token accounting


async def test_gateway_complete_json_live():
    """JSON mode (used by intent classification) parses into a dict."""
    from app.core.model_gateway import model_gateway

    out = await model_gateway.complete_json(
        "fast",
        'Return this exact JSON object and nothing else: {"intent": "qa"}',
        tenant_id="00000000-0000-0000-0000-000000000000",
        purpose="connectivity_check_json",
    )
    print(f"\n[gateway complete_json] -> {out!r}")
    assert isinstance(out, dict)
    assert out.get("intent") == "qa"
