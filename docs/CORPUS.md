# Corpus Documentation: FAST-NUCES Policies and Regulatory Framework

**Source**: FAST-NUCES public institutional portal (`https://www.nu.edu.pk`)  
**Total Documents**: 8 documents (6 PDF publications, 1 HTML statutory table, 1 scanned PDF)  
**Total Pages**: Over 180 pages indexed across all documents  

## Required Corpus Properties and Failure-Mode Mapping

The corpus is explicitly structured to challenge every stage of the RAG pipeline. Below is the mapping of all seven required properties, the documents that supply them, and the failure modes they make reachable.

| # | Required property | Document(s) that provide it | Evidence, Metadata, and Failure-Mode Analysis |
|---|---|---|---|
| 1 | **Scale (At least 6 documents, 40+ pages)** | All documents in `corpus/MANIFEST.md` | 8 documents totaling over 180 pages. Sets realistic corpus scale so vector retrieval must discriminate between dozens of distractor sections. |
| 2 | **Two versions of one policy (Outdated source failure)** | `Undergraduate Academic Rules (Aug 2023)` and `Academic Rules Handbook (Jun 2026)` | **Version Pair**: 2023-08 vs 2026-06.<br>• *Superseded document*: `doc_version: "2023-08"`, `superseded: true`<br>• *Active document*: `doc_version: "2026-06"`, `superseded: false`<br>• *Failure Mode*: If the retriever ranks purely by semantic vector distance without filtering or penalizing superseded clauses, it quotes repealed rules as current policy (e.g. prerequisite failure rules in clause 4.2). |
| 3 | **Scanned, image-only PDF (Extraction loss failure)** | `Faculty Entrepreneurship and Technical Start-ups Policy` | `pdffonts` returns an empty font list, confirming zero selectable text layer. Extractor invokes OCR (`pytesseract`) if installed, or transparently logs and flags the text extraction loss in chunk metadata rather than corrupting vector embeddings. |
| 4 | **Table with real information (Structural destruction failure)** | `Fee Structure Policy (2026-27)` and `Annual Report 2023-24` | Contains complex multi-column tabular data: tuition fees per credit hour, security deposits, semester lab dues, and university enrollment counts. Naive newline splitting shreds table rows across chunk boundaries; our cleaner normalizes them into structured Markdown tables. |
| 5 | **Long definitions (Context fragmentation failure)** | `Student Handbook (Jun 2026)` | Contains multi-paragraph definitions of academic malpractice, plagiarism thresholds, and disciplinary board jurisdiction. A fixed-size window without overlap cuts definitions in half; structure-aware chunking keeps definitions intact with logical section headers. |
| 6 | **Deliberately absent topic (Hallucination / Abstention)** | Hostel Allocation & Transport Bus Routes (Omitted: `Transport and Hostel Facilities.pdf`) | **Deliberately Left Out**: Student hostel accommodation guidelines, curfew hours, and campus transport bus routes are completely excluded from the index. When asked "What are the hostel room allotment rules for freshman students?", the system must acknowledge missing evidence and return `answered_from_context: false` (100% abstention). |
| 7 | **Exact-term content (Semantic blurring failure)** | `Academic Rules Handbook (Jun 2026)` and `Prospectus 2026` | Contains dense exact terms: course codes (e.g. `CS4032`, `EE1001`), numbered clauses (e.g. `clause 4.2`, `clause 1.21`), minimum CGPA requirements (`2.00` for graduation, `1.70` probation threshold), and exact credit hour limits. Semantic dense embeddings blur numerical and alphanumeric tokens, demonstrating the need for precise chunk retrieval. |

## Document Ingestion & Verification
All documents are hashed using SHA-256 upon retrieval by `corpus/fetch.py`. The hashes and byte sizes are permanently tracked in `corpus/MANIFEST.md`.
The local storage directory `corpus/raw/` is strictly `.gitignored` to prevent committing external binaries into the Git history. During CI and testing, the pipeline uses the fixture corpus under `eval/fixtures/` to execute deterministic, fast end-to-end checks.
