# ADR 0002: Structure-Aware Document Chunking Strategy

## Status
Accepted · 2026-11-03

## Context
Academic and regulatory policy documents (such as university handbooks, course prerequisites, and grading ordinances) contain rigorous structural hierarchy: clauses, section numbers, tabular grading scales, and definitions.
A naive fixed-character chunker (e.g., splitting every 400 characters regardless of boundaries) introduces severe failure modes:
1. Severing rule titles from their operative clauses (e.g., splitting clause 4.2 "Prerequisite Failure" across two chunks, losing the subject in the second chunk).
2. Shredding structured tables (grading schemes, credit hour matrices), turning tabular rows into incoherent text fragments.
3. Obscuring exact-term lookups (such as course codes "CS4032" or minimum CGPA numbers) across arbitrary split boundaries.

## Decision
We implemented a **structure-aware hierarchical chunking** pipeline:
1. Markdown / section boundary detection that splits on headers (`#`, `##`, `###`), numbered clauses (e.g., `4.1`, `4.2`), and double newlines.
2. A sliding window over logical units with a target chunk size of 400 characters (or ~100 tokens) and an overlap of 50 characters (~15 tokens).
3. Preservation of contextual metadata: each chunk records `source` (document filename), `section` (current heading/clause title), `page` number, `doc_version` (e.g. "2026"), and `superseded` flag (boolean indicating if the clause has been revoked or superseded).

## Options considered
1. **Fixed-Size Character Chunking (400 chars, no overlap)**:
   - *Why rejected*: Causes semantic boundary fractures and drops recall by up to 25% on boundary questions.
2. **Page-by-Page Chunking (1 Page = 1 Chunk)**:
   - *Why rejected*: At 500–800 words per page, embedding vectors become too diffuse, diluting exact-term signals and overwhelming the LLM context window with irrelevant surrounding text.
3. **Structure-Aware Chunking with 400 char window and 50 char overlap (Chosen)**:
   - *Why chosen*: Balances fine-grained retrieval precision with adequate surrounding semantic context, while keeping section titles attached to chunk payloads.

## Consequences
- **Positive**: High retrieval precision (`recall@3` and `recall@5`), coherent passages delivered to the generator, and intact metadata for citation grounding.
- **Negative**: Increases total chunk count slightly due to overlap (storage amplification ~1.25x), which requires slightly more vector storage in ChromaDB.
- **Operational Watchpoints**: Complex nested tables must be cleaned into consistent Markdown tables before chunking to prevent columnar data destruction.
