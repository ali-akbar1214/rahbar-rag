# Evidence: GitHub Branch Protection Configuration
Date: 2026-11-03
Repository: rahbar-grounded-rag

Branch protection rules applied on `main`:
- Require a pull request before merging: ENABLED
  - Required approvals: 1
  - Dismiss stale pull request approvals when new commits are pushed: ENABLED
  - Require review from Code Owners: ENABLED
- Require status checks to pass before merging: ENABLED
  - Required check: `lint`
  - Required check: `test` (coverage >= 60%)
  - Required check: `manifests` (kubeconform validation)
  - Required check: `e2e-eval` (evaluation regression gate)
- Do not allow bypassing the above settings: ENABLED
- Restrict who can push to matching branches: ENABLED (No direct pushes to main)
