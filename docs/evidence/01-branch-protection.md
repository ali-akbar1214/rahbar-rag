# Evidence: GitHub Branch Protection Configuration

- **Date**: 2026-11-03
- **Repository**: https://github.com/ali-akbar1214/rahbar-rag
- **Protected Branch**: `main`

## Enforced Protection Rules (`GET /repos/ali-akbar1214/rahbar-rag/branches/main/protection`)

- **Require a pull request before merging**: `ENABLED`
  - Required approving reviews: `1` (`required_approving_review_count: 1`)
  - Dismiss stale pull request approvals when new commits are pushed: `ENABLED` (`dismiss_stale_reviews: true`)
- **Require status checks to pass before merging**: `ENABLED` (`strict: true`)
  - `Lint & Style Check`
  - `Unit Tests & Code Coverage`
  - `Kubeconform Manifest Validation`
  - `Build & Trivy Vulnerability Scan`
  - `Ephemeral Kind Cluster & E2E Eval Gate`
- **Do not allow bypassing the above settings (`enforce_admins`)**: `ENABLED` (`enforce_admins.enabled: true`)
- **Allow force pushes / deletions**: `DISABLED` (`allow_force_pushes: false`, `allow_deletions: false`)
