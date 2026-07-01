# Prompt & GenAI Guidelines

This document outlines the prompt engineering standards, gateway configurations, and safety constraints for integrating Large Language Models (LLMs) in the **Terzo Cost Intelligence** platform.

---

## 1. Gateway & Model Configuration

All AI interactions flow through a centralized **ModelGateway** (`app/core/model_gateway.py`), which enforces:
* **Model Version Pinning**: Ensures models like `gemini-2.5-pro` and `gemini-2.5-flash` are locked to specific versions to prevent silent behavior drift.
* **PII Redaction**: Redacts emails, phone numbers, and typical user identifiers before prompts leave the trust boundary.
* **Response Caching**: Fast classification and deterministic parsing prompts are cached in Redis to reduce billing costs and latency.
* **Telemetry**: Embeds token usage, latency, and cost attribution metrics under standard `terzo` tags.

---

## 2. Core Prompting Principles

### A. Groundedness Over Intelligence
The AI must never invent, calculate, or infer financial numbers.
* **Figure Grounding**: All dollar amounts, contract terms, or index percentages are supplied to the prompt as **read-only constants** calculated by deterministic Python modules.
* **Negative Constraints**: Prompts must explicitly instruct the LLM: *“Do not perform arithmetic. Use only the exact figures provided in the context.”*
* **Post-Processing Checks**: The system validates model rationales against the input figures using a groundedness guard. If the model includes an incorrect or altered figure, the response is rejected.

### B. Capped Confidence Layering
For critical classifications (e.g., matching spend items to contract line items):
1. **Prompt Instruction**: The prompt instructs the model to return a confidence score up to `0.80` even if fully certain.
2. **Code Guard**: The Python module caps the score via `min(confidence, 0.80)`.
3. **Database Validation**: The database table checks this constraint (`ai_confidence <= 0.80` CHECK constraint).

---

## 3. Production Prompts Reference

### AI-Inference (Spend-to-Contract Matching)
Used in the candidate matching pipeline:
* **Model**: `gemini-2.5-flash`
* **Task**: Maps a transactional spend record to potential contract line item candidates.
* **Injection Defense**: Explicit instructions to ignore text containing directives like "ignore previous instructions".

### Recommendation Rationale Writer
Used to draft renewal or cost saving advisories:
* **Model**: `gemini-2.5-pro`
* **Task**: Drafts natural language prose explaining recommended actions to a business user.
* **Constraint**: Forbidden from recalculating financial math or editing provided savings metrics.

---

## 4. Gateway Timeout & Latency Resilience

Since model endpoints (e.g. Gemini API, vector search DB) are invoked by containerized backends that may experience transient wake-up or connection latency:
- **Connection Deadlines**: Client requests hitting NirvanAI or model gateways must employ a generous connection deadline (~10 seconds connect timeout, 30 seconds read timeout) to absorb transient start-up latencies of underlying systems.
- **Graceful Timeouts**: In the event of a gateway or provider timeout, prompt clients must catch the error cleanly and return a structured fallback response rather than letting the web server crash.
- **Retry Mechanics**: Local API client wrappers should implement a maximum of 3 retries with jittered backoff for rate-limiting (429) or gateway (502/503/504) responses.

