# ADR 0004: Pluggable Hosted LLM Provider, Constrained Decoding, and PII Protection

## Status
Accepted · 2026-11-03

## Context
Production RAG systems require strong guarantees on generation format, latency, and data privacy.
1. **Unconstrained Generation Failure**: If an LLM returns conversational prose or malformed JSON instead of the strict Pydantic `Answer` schema, the API will fail deserialization and crash with 500 errors.
2. **Hanging Calls & Resource Exhaustion**: Without hard timeouts on external inference endpoints, slow upstream API responses saturate ASGI worker threads, causing cascading request queuing and failure of liveness/readiness checks.
3. **Student Privacy (PII)**: Transmitting student queries containing student IDs, roll numbers, or personal identifiable information to third-party endpoints without validation poses privacy compliance risks.

## Decision
1. **Pluggable Architecture**: The system supports multiple LLM providers behind the `LLMProvider` abstract base class: `HostedProvider` (default), `OllamaProvider` (local cluster / host), and `StubProvider` (offline testing/CI).
2. **Constrained Decoding & Structured Outputs**: The provider enforces JSON mode (`response_format={"type": "json_object"}` or schema constraints) guaranteeing valid JSON output.
3. **Pydantic Validation, Retry, and Fallback**: The raw response is validated against the Pydantic `Answer` model. If parsing fails, the system retries up to 2 times with lowered temperature, and finally falls back to a deterministic safe abstention response rather than a 500 error.
4. **Hard Timeout**: Every external LLM HTTP call has a strict 15-second client timeout (`httpx.Timeout(15.0)`).
5. **PII Sanitization**: Prompt templates strip personal identifiers before generating queries.

## Options considered
1. **Relying on Prompt Engineering Alone for JSON**:
   - *Why rejected*: Highly nondeterministic; models occasionally include preamble (e.g. "Here is your JSON:") or omit trailing braces.
2. **Single Hardcoded Provider**:
   - *Why rejected*: Prevents offline CI evaluation, breaks when running on local clusters without internet, and limits provider flexibility.
3. **Pluggable Provider with Constrained Decoding & Fallback (Chosen)**:
   - *Why chosen*: Guaranteed contract conformance, resilient error recovery, and clean testability in offline CI pipelines.

## Consequences
- **Positive**: 100% schema compliance, zero 500 crashes from generation errors, fast fallback under upstream degradation.
- **Negative**: Hosted models require an API key securely passed via Kubernetes `Secret`.
- **Operational Watchpoints**: Keys must never be logged or committed to Git; logs must mask authorization headers.
