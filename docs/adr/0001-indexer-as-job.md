# ADR 0001: Decoupling Document Indexing into a Kubernetes Job

## Status
Accepted · 2026-11-03

## Context
In early prototypes or naive RAG architectures, document ingestion and vector indexing are frequently run inside the application startup lifecycle (e.g., in a FastAPI `lifespan` handler). 
In a production Kubernetes deployment running 3 replicas of the API service connected to a persistent vector store (ChromaDB), embedding and indexing on startup creates critical failure modes:
1. **Concurrent Write Collisions & Corruption**: ChromaDB on SQLite/DuckDB backing does not safely support multi-writer concurrency. When 3 API replicas boot simultaneously, concurrent writes to the same PVC cause lock contention, database deadlocks, or index corruption.
2. **Startup Probe Failures**: Embedding a large PDF corpus (dozens of documents, hundreds of chunks) takes minutes and spikes CPU/memory. This causes `startupProbe` and `readinessProbe` to exceed timeout thresholds, triggering continuous container kill-restart crashloops (`CrashLoopBackOff`).
3. **Severe Resource Bloat**: Embedding requires high transient CPU/memory allocations. Tying this requirement to the API Deployment forces artificially high memory limits across all 3 replicas, severely limiting horizontal pod autoscaling (HPA) efficiency.

## Decision
We chose to strictly isolate the ingestion pipeline into a standalone Kubernetes `Job` (`indexer-job`) for one-off and deployment-time runs, complemented by a `CronJob` (`reindex-cronjob`) for scheduled periodic re-indexing.
The API service acts solely as a **read-only consumer** of the Chroma collection. The indexer is the **sole writer**.

## Options considered
1. **Indexing in FastAPI Lifespan Handler**:
   - *Why rejected*: Causes race conditions across the 3 replicas, blows startup probe windows, and risks Chroma database write locks.
2. **Indexing in a Kubernetes InitContainer in the API Pod**:
   - *Why rejected*: Although it finishes before the API container starts, each replica still runs its own init container against the shared PVC, repeating the duplicate write and lock contention issue across replicas.
3. **Dedicated Kubernetes Job (Chosen)**:
   - *Why chosen*: Guaranteed single-execution semantics (`parallelism: 1`, `completions: 1`), isolated ephemeral resource limits, clean exit upon completion (`restartPolicy: OnFailure`), and decoupling of ingestion failures from serving availability.

## Consequences
- **Positive**: The API boots in under 2 seconds and can safely scale from 3 to 8 replicas via HPA without touching Chroma write locks. The indexer Job can run with dedicated high memory limits (e.g., 2Gi) without wasting cluster resources once completed.
- **Negative**: Document updates are asynchronous; new documents are not available until the Indexer Job finishes successfully.
- **Operational Watchpoints**: API `/readyz` probe must verify Chroma is reachable and the collection is non-empty before receiving user traffic, preventing requests from being routed to an unindexed deployment.
