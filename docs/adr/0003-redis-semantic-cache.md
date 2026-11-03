# ADR 0003: Redis Semantic Cache and Invalidation Strategy

## Status
Accepted · 2026-11-03

## Context
In a student-facing advisory system, frequent questions share identical semantic intent with varying surface wording (e.g., "What is the probation CGPA threshold?" vs "At what GPA do I get placed on academic probation?").
Executing full vector retrieval and hosted LLM inference for every repeated query introduces unnecessary latency (~1.5–3.0 seconds) and operational inference cost.
However, naive caching introduces severe hazards:
1. **Serving Stale Policy Answers**: When the corpus is updated or re-indexed, serving cached responses based on superseded documents leads to regulatory non-compliance.
2. **Caching Hallucinations / Abstentions**: Caching an answer that declined (`answered_from_context: false`) or a prompt injection attempt could poison future queries.

## Decision
We chose a **Semantic Cache backed by Redis** (with an in-memory fallback for local/unit testing):
1. **Cosine Similarity Thresholding**: Incoming queries are embedded using the pinned embedding model. Queries with cosine similarity $\ge 0.95$ against existing cache entries return the cached structured `AskResponse`.
2. **Cache Invalidation on Re-index**: A generation ID / collection version hash is embedded in the cache key prefix (`rahbar:v1:...`). Whenever a re-indexing Job finishes, it updates the generation ID, instantly invalidating stale cache entries.
3. **Never-Cache Guardrails**:
   - Queries where `answered_from_context == false` (abstentions) are **never cached**.
   - Queries marked with potential prompt injection or malformed input are **never cached**.
   - Context-dependent follow-up questions are bypassed.

## Options considered
1. **Second ChromaDB Collection (`rahbar_cache`)**:
   - *Why rejected*: Writing to ChromaDB from all 3 `rahbar-api` serving replicas violates our sole-writer architecture (ADR 0001), introduces multi-replica SQLite/HNSW write-lock contention on every cache miss, and lacks native per-key TTL (`EXPIRE`) and `allkeys-lru` memory eviction.
2. **Exact String Hash Caching (MD5 / SHA256 of question text)**:
   - *Why rejected*: Extremely low hit rate (< 5%) because minor punctuation, casing, or synonym differences miss the cache entirely.
3. **In-Memory Cache in API Pod Memory (LRU Cache)**:
   - *Why rejected*: With 3 API replicas, memory is fragmented across pods without cache sharing, and cache entries are lost on pod restart/rescheduling.
4. **Redis Centralized Semantic Cache with PVC (Chosen)**:
   - *Why chosen*: Shared state across all API replicas, persistent via `PersistentVolumeClaim` (`cache-data`), safe concurrent writes from 3–8 API replicas without touching ChromaDB's single-writer index, and built-in TTL + `allkeys-lru` eviction.

## Consequences
- **Positive**: Near-instantaneous response times (< 25ms) for recurring student queries, saving API quota and compute.
- **Negative**: Adds a dependency on the Redis service and requires a fast similarity check.
- **Operational Watchpoints**: Redis memory bounds must have `maxmemory-policy allkeys-lru` to prevent memory exhaustion.
