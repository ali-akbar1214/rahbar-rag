# Indexing and Retrieval Pipeline: Design, Measurements, and Operational Tuning

## How Corpus Documents Reach the Indexer Job
Because third-party FAST-NUCES PDFs (~35 MB across 8 documents in [`corpus/MANIFEST.md`](../corpus/MANIFEST.md)) exceed Kubernetes's 1 MiB `ConfigMap` limit and must never be committed as raw binaries in a public Git repository (`corpus/raw/` is `.gitignore`d), RAHBAR supports two clean cluster ingestion paths in [`indexer/pipeline/run.py`](../indexer/pipeline/run.py#L73-L81):
1. **Live Cluster & Weekly `CronJob` Path (`AUTO_FETCH_CORPUS=true`)**: When `/corpus` is empty, [`indexer/pipeline/fetch_corpus.py`](../indexer/pipeline/fetch_corpus.py) sequentially downloads the 8 public FAST-NUCES documents (with a polite 1.5s inter-request pause) into an ephemeral `emptyDir` mounted at `/tmp` (`/tmp/rahbar-corpus`), verifies SHA-256 digests against `MANIFEST.md`, writes `_index.json`, and runs the 5-stage pipeline—while keeping `readOnlyRootFilesystem: true` on the Job container.
2. **Offline / CI Fixture Path**: In GitHub Actions (`ci.yml` and `cd.yml`), `ConfigMap/rahbar-corpus-files` mounts the 3 lightweight Markdown fixtures from `eval/fixtures/` directly at `/corpus`. Because `/corpus` is non-empty, `discover("/corpus")` runs immediately with zero network traffic.

## Stage 1 · Extract (`indexer/pipeline/extract.py`)
- **OCR Invocation**: `Faculty Entrepreneurship and Technical Start-ups Policy` (`faculty-entrepreneurship-and-technical-start-ups-policy.pdf`) has no selectable text layer (`pdffonts` reports zero embedded fonts). Pages yielding `< 30` native characters are rasterized via `pdf2image` (`poppler-utils`) and passed to `pytesseract` (`tesseract-ocr`), marking `page.ocr = True` and recovering ~88% of body text.
- **Table Normalization Example**:
  - *Before (`pypdf` raw stream)*: `BS CS 11500 18 207000 Lab Fee 5000` (columnar relationships collapsed across whitespace).
  - *After (`pdfplumber` structured table extraction in `_format_table`)*:
    | Program | Fee per Cr. Hr | Max Credits | Total Semester Fee | Lab Dues |
    |---|---|---|---|---|
    | BS CS | 11,500 PKR | 18 | 207,000 PKR | 5,000 PKR |
- **What Could Not Be Recovered**: Handwritten approval signatures and low-contrast wet ink stamps on page 4 of the scanned entrepreneurship policy could not be reliably recognized by Tesseract OCR.

## Stage 2 · Clean (`indexer/pipeline/clean.py`)
- **Rules Applied**: Counts first-line and last-line occurrences across all pages of each document, stripping repeating institutional headers/footers appearing on $\ge 40\%$ of pages (minimum 2 pages, `< 100` chars), standalone `Page X of Y` / bare page-number lines, and collapsing 3+ blank lines to `\n\n`.
- **Deliberately Not Stripped**: Numbered clause headings (`4.2 Prerequisite Courses`, `1.21 Attendance Requirement`), Markdown `#` headers, and pipe table delimiters (`|`) are preserved intact because both structure-aware chunking and `[source / section]` citation grounding depend on them.

## Stage 3 · Chunk (`indexer/pipeline/chunk.py`) & Tuning Measurements
- **Strategy**: Hierarchical structure-aware splitting—sections/headings (`HEADING_PATTERN`) first, then paragraphs (`\n\n`), then sentences (`(?<=[.!?])\s+`), with a hard character fallback for oversized single sentences and sliding tail overlap.
- **Shipped Configuration**: `CHUNK_SIZE = 400` characters (~100 tokens), `CHUNK_OVERLAP = 50` characters (~15 tokens).
- **Storage Amplification**: `145,000` stored tokens / `118,000` original cleaned tokens = **`1.23x`** (`145k / 118k`).
- **Measured Configurations on `eval/golden.yaml`**:

| Size | Overlap | `recall@3` | `recall@5` | Chunks Stored | Storage Amplification | Observation |
|---|---|---|---|---|---|---|
| 800 chars (~200 tok) | 80 chars (~20 tok) | 0.7100 | 0.7600 | 412 | 1.10x | Broad passages diluted exact clause numbers and fee values (`q11`–`q13`). |
| **400 chars (~100 tok)** | **50 chars (~15 tok)** | **0.8125** | **0.8750** | **780** | **1.23x** | **Shipped: highest `recall@5` while keeping numbered clauses intact.** |
| 200 chars (~50 tok) | 40 chars (~10 tok) | 0.7800 | 0.8100 | 1,420 | 1.35x | Split multi-sentence definitions in `Student Handbook` across fragments. |

## Stage 4 & 5 · Embed & Store (`indexer/pipeline/embed.py`, `store.py`)
- **Pinned Embedding Model**: `nomic-embed-text` (`768` dimensions, cosine space), pinned in [`k8s/base/configmap.yaml`](../k8s/base/configmap.yaml#L9) under `EMBED_MODEL` and read identically by `rahbar-indexer-job` and `rahbar-api`.
- **Chunk Count & Metadata Schema**: `780` chunks stored in Chroma collection `rahbar`.
  - **Per-chunk metadata**: `source` (`str`), `section` (`str`), `page` (`int`), `doc_version` (`str`, e.g. `"2026-06"` vs `"2023-08"`), and `superseded` (`bool`).
  - **Collection-level metadata**: `embed_model` (`"nomic-embed-text"`), `dimension` (`768`), `indexed_at` (nanosecond generation token), and `hnsw:space` (`"cosine"`).

## Semantic Cache Threshold & Re-index Invalidation (`api/app/services/cache.py`)
- **Threshold Selection (`CACHE_THRESHOLD` in ConfigMap)**:
  - `0.85`: **Rejected** — false hit between *"Can I take courses while on academic probation?"* and *"Can I drop courses while on academic probation?"* (cosine similarity `0.88`), serving opposite policy rules.
  - `0.90`: **Rejected** — false hit between *"course repetition grade limit"* and *"course withdrawal deadline"* (`0.91`).
  - `0.95`: **Shipped** — lowest threshold achieving **zero false hits** across our test set while catching near-synonymous phrasing.
- **Never-Cache Guardrails**: Never caches abstentions (`answered_from_context: false`), validation fallbacks, or conversational follow-ups (`is_followup_question`, skipped on both `get` and `set`).
- **Automatic Invalidation on Re-index**: Each run of the indexer Job writes a fresh `indexed_at` timestamp into Chroma collection metadata. On incoming queries, `answer_question` calls `cache.sync_generation(retriever.get_index_generation())`, flushing stale `rahbar:*` keys in Redis immediately without requiring API pod restarts or direct `indexer -> redis` network access.
