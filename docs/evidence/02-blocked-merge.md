# Evidence: Evaluation Regression Gate Blocking Merge on Pull Request #1

- **Date**: 2026-11-03
- **Pull Request**: https://github.com/ali-akbar1214/rahbar-rag/pull/1 (`dev` -> `main`)

## 1. Intentional Evaluation Gate Failure (Blocked Merge)

- **Commit**: `6c0c197` (`k8s/base/configmap.yaml` configured with overly strict `RELEVANCE_FLOOR: "0.45"`)
- **Workflow Run**: https://github.com/ali-akbar1214/rahbar-rag/actions/runs/41690682297
- **Job Breakdown**:
  - `Lint & Style Check`: **SUCCESS**
  - `Unit Tests & Code Coverage`: **SUCCESS**
  - `Kubeconform Manifest Validation`: **SUCCESS**
  - `Build & Trivy Vulnerability Scan`: **SUCCESS**
  - `Ephemeral Kind Cluster & E2E Eval Gate`: **FAILURE** (Exit Code `1`)
- **Gate Output (`eval/run_eval.py`)**:
  ```text
  FAIL: Gate Failure: recall@5 dropped from baseline 0.8750 to 0.4000 (exceeding max allowable drop of 0.05)
  ```
- **GitHub PR Merge State (`gh pr view 1 --json mergeStateStatus`)**:
  - `mergeStateStatus`: **`BLOCKED`**
  - Screenshots: [`02-blocked-merge-failed.png`](./02-blocked-merge-failed.png), [`02-pr1-checks-failed.png`](./02-pr1-checks-failed.png)

## 2. Threshold Fix and Green CI Reruns

- **Fix**: Restored `RELEVANCE_FLOOR: "0.15"` in `k8s/base/configmap.yaml` so valid grounded chunks pass similarity filtering while unanswerable queries still abstain at `100%`.
- **Verification**: All 5 required CI checks (`Lint & Style Check`, `Unit Tests & Code Coverage`, `Kubeconform Manifest Validation`, `Build & Trivy Vulnerability Scan`, and `Ephemeral Kind Cluster & E2E Eval Gate`) pass with exit code `0` (`recall@5: 1.0000`, `citation_validity: 1.0000`, `abstention_correctness: 1.0000`).
- **Passing Screenshot**: [`02-blocked-merge-passed.png`](./02-blocked-merge-passed.png)
