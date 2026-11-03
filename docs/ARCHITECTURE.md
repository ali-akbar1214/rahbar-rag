# RAHBAR Architecture Notes

## 1. Two-Path Separation: Sole-Writer Batch Job vs. Read-Only Serving Replicas
RAHBAR strictly separates **indexing** (runs once on demand or weekly via `CronJob`) from **querying** (runs on every HTTP request across 3–8 stateless `rahbar-api` pods):
- **Writer Path**: `Job/rahbar-indexer-job` (`indexer/pipeline/run.py`) executes the 5-stage pipeline (`extract` -> `clean` -> `chunk` -> `embed` -> `store`), writes chunk metadata (`source`, `section`, `page`, `doc_version`, `superseded`) plus collection-level `embed_model` and `dimension` pins, and exits `0`.
- **Reader Path**: `Deployment/rahbar-api` (`api/app/main.py`) never writes to ChromaDB. Its `/readyz` probe verifies Chroma reachability, non-empty collection count, and `EMBED_MODEL` parity before Kubernetes adds the pod to `Endpoints/rahbar-api`.

## 2. Why ChromaDB Uses a `StatefulSet` Instead of a `Deployment`
A Kubernetes `Deployment` assumes interchangeable, stateless pods and defaults to `RollingUpdate`, which briefly runs old and new pods simultaneously while sharing or racing on a single `PersistentVolumeClaim`. ChromaDB stores its catalog in SQLite alongside HNSW binary index segments under `/data`; two pods mounting or writing the same volume corrupt the WAL/segment state or deadlock on `ReadWriteOnce` volume attachment.

Deploying `rahbar-chroma` as a 1-replica **`StatefulSet`** with `volumeClaimTemplates` (`chroma-data`, `2Gi`, `ReadWriteOnce`) guarantees:
1. **Ordered, At-Most-One Pod Lifecycle**: `rahbar-chroma-0` terminates cleanly before a replacement pod mounts `chroma-data-rahbar-chroma-0`.
2. **Stable Storage Binding**: Even across pod deletion or node drain, the exact PVC rebinds to `rahbar-chroma-0`, preserving the indexed embeddings without re-running the indexer `Job`.

## 3. Defense-in-Depth Cluster Security
- **Workload Identity**: Every component (`api`, `ui`, `chroma`, `redis`, `indexer`) runs under its own dedicated `ServiceAccount` (`k8s/base/serviceaccounts.yaml`) with `automountServiceAccountToken: false`.
- **Container Hardening**: Non-root UIDs (`1000` / `101` / `999`), `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`, and `readOnlyRootFilesystem: true` on serving tiers (`api`, `ui`, `redis`).
- **Zero-Trust Network Segmentation**: `default-deny-all` blocks all pod ingress and egress in `rahbar`, followed by explicit `NetworkPolicy` allowlists (`ui` cannot reach `chroma` or `redis`; only `api` and `indexer` can reach `chroma:8000`; only `api` can reach `redis:6379`; `kube-dns` allowed on UDP/TCP `53`).
