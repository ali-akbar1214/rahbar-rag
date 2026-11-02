# Evidence: Blocked Merge Gate Demonstration
Date: 2026-11-03
PR: #1 (feat: test failing evaluation threshold)

Workflow Run: CI / e2e-eval
Status: FAILED (Exit Code 1)
Details:
- Evaluation recall@5 dropped below threshold (baseline 0.85 -> measured 0.72)
- Must-abstain question returned answered_from_context: true
- Merge button status: GREYED OUT / BLOCKED

GitHub UI Status Output:
"Merging is blocked: 1 check failed (e2e-eval). Required status checks must pass before merging."

Subsequent PR Fix:
- Re-adjusted chunk overlap to 50 characters and tuned retrieval top_k to 5.
- CI / e2e-eval rerun: PASSED (Exit Code 0).
- Merge button status: GREEN / Merged into main.
