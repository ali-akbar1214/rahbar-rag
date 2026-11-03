# AI Usage Disclosure and Attribution

**Team Members**:
- Member 1: Syed Ali Akbar Naqvi (24I-3079)
- Member 2: Huzaifa Ali (24I-3114)

In accordance with course academic honesty guidelines, all AI assistance utilized during the development, containerization, and evaluation of RAHBAR is transparently disclosed below.

| Tool | What it wrote or shaped | What we changed afterwards, and why |
|---|---|---|
| **Google Antigravity / Gemini 3.8 Flash** | Scaffolded initial boilerplate for indexer stages (`extract.py`, `chunk.py`) and FastAPI route structures. | Refactored chunking logic to support structure-aware regex heading matching and sliding overlap; added PDF table extraction with `pdfplumber` and fallback OCR hooks to satisfy corpus property 3 and 4. |
| **Google Antigravity / Gemini 3.8 Flash** | Drafted Kubernetes YAML manifests for StatefulSet, Deployments, and NetworkPolicies. | Modified security contexts to drop ALL capabilities (`capabilities: drop: [ALL]`), added read-only root filesystems with `/tmp` emptyDir mounts, configured zero-unavailability rolling update parameters (`maxUnavailable: 0`), and added explicit egress DNS allowance to port 53. |
| **GitHub Copilot** | Suggested Python type annotations, Pydantic schemas, and unit test fixtures for test clients. | Hand-wrote prompt-injection detection regexes and verified offline stub isolation so CI suites do not require live model or network access. |
| **ChatGPT (GPT-4o)** | Drafted initial questions for `eval/golden.yaml` based on university handbook extracts. | Filtered and customized 16 golden questions to strictly reflect FAST-NUCES policies across ordinary, exact-term, version-sensitive, and must-abstain categories, verifying matching clause numbers in the 2026 handbook. |

Both team members actively reviewed, modified, benchmarked, and verified every line of code, manifest, and test suite committed to this repository.
