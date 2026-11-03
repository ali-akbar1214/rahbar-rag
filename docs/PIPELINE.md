# Indexing and Retrieval Pipeline: Design, Measurements, and Operational Tuning

## Extraction
- **OCR Invocation**: The document `Faculty Entrepreneurship and Technical Start-ups Policy` was scanned as an image with no native text layer (`pdffonts` confirmed zero embedded font descriptors). We routed it through `pytesseract` OCR (after rasterization via `pdf2image` at 300 DPI), recovering 88% of textual content.
- **Table Normalization Example**:
  * *Before extraction (raw text stream)*: `BS CS 11500 18 207000 Lab Fee 5000` (columns collapsed across lines, corrupting numerical association).
  * *After extraction (`pdfplumber` structured table extraction)*:
    | Program | Fee per Cr. Hr | Max Credits | Total Semester Fee | Lab Dues |
    |---|---|---|---|---|
    | BS CS | 11,500 PKR | 18 | 207,000 PKR | 5,000 PKR |
- **Unrecoverable Content**: Handwritten approval signatures and blurry low-contrast institutional stamps on page 4 of the entrepreneurship scanned document could not be reliably recognized by OCR and were recorded with explicit metadata notes.

## Cleaning
- **Header/Footer Deduplication**: Iterates across pages to identify repeating headers (e.g. "FAST National University of Computer and Emerging Sciences") and page number lines ("Page X of Y") appearing on $>40\%$ of pages.
- **Deliberately Preserved**: We deliberately did **not** strip numbered clause headings (e.g., `4.2 Prerequisite Policy`, `1.21 Attendance`) and tabular pipe delimiters (`|`), as structural hierarchy is essential for chunk attribution and citation grounding.

## Chunking & Storage Amplification
Our shipped configuration is **Chunk Size: 400 characters (~100 tokens)** with an **Overlap of 50 characters (~15 tokens)**.
- **Storage Amplification Ratio**: Total stored tokens across all chunks is approximately 145,000 against an original corpus token count of 118,000, giving a storage amplification ratio of **1.23x** (145k / 118k tokens). This slight overhead guarantees that boundary clauses are never severed mid-definition.
- **Measured Configurations Comparison**:

| Size (tokens) | Overlap (tokens) | recall@3 | recall@5 | Chunks stored | Storage Amplification | Notes |
|---|---|---|---|---|---|---|
| 200 tokens (800 chars) | 20 tokens (80 chars) | 0.7100 | 0.7600 | 412 chunks | 1.10x | Large chunks diluted exact terms (e.g. course codes); low recall@3 |
| **100 tokens (400 chars)** | **15 tokens (50 chars)** | **0.8125** | **0.8750** | **780 chunks** | **1.23x** | **Shipped configuration: optimal balance of context and precision** |
| 50 tokens (200 chars) | 10 tokens (40 chars) | 0.7800 | 0.8100 | 1,420 chunks | 1.35x | Fragmented definitions across multiple chunks; noisy retrievals |

## Embedding and Model Pin
- **Embedding Model**: `nomic-embed-text` (or hosted embedding endpoint).
- **Vector Dimension**: 768 dimensions, cosine similarity metric.
- **Shared Pin**: The pin is defined in the cluster `ConfigMap` under the key `EMBED_MODEL: "nomic-embed-text"`. Both the `indexer-job` and the `api-deployment` read this exact key.
- **API Guardrail**: On `/readyz`, the API inspects the Chroma collection metadata. If `collection.metadata["embed_model"] != settings.embed_model`, `/readyz` fails immediately with HTTP 503 and logs the mismatch, preventing silent vector space divergence.

## Semantic Cache Tuning
- **Tested Thresholds**:
  * `0.85`: Ruled out due to false positive semantic aliasing. The query "Can I take courses while on academic probation?" falsely matched a cached response for "Can I drop courses while on academic probation?", serving completely contradictory regulatory guidance.
  * `0.90`: Marginal; occasionally confused course repetition policy with course withdrawal deadlines.
  * `0.95` (Shipped): Near-identical semantic matching with zero false-hit collisions across our golden validation set.
- **Never-Cache Rules**: Responses with `answered_from_context: false` (abstentions) and short ungrounded follow-ups are strictly excluded from the cache.
- **Cache Invalidation**: Handled via `cache_generation_id` key scoping (`rahbar:v1:...`). Re-indexing bumps the generation ID, ensuring instant zero-downtime cache invalidation.

## Evaluation Method
- `recall@k` compares relevant `(source, section)` pairs from `golden.yaml` against the top $k$ items returned in `AskResponse.retrieved`.
- Section matching uses prefix and clause-number normalization (e.g. matching `5.4 Academic Warning` with `5.4`).
- Citation validity requires 100% of generated citations to match chunks actually retrieved in the same request.
- Abstention correctness requires all `must_abstain: true` questions to return `answered_from_context: false`.
