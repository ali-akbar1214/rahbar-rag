# RAG Pipeline Failure Analysis: Deliberate Injections, Symptoms, and Diagnostics

This document analyzes deliberate failure injections across the six pipeline stages (A through F), demonstrating the exact metrics, log signatures, and diagnostic commands required to identify root causes.

---

## Stage A · Extraction (Scanned PDF Table Collapse)
- **What we broke**: Disabled the OCR fallback in `extract.py` and processed the scanned image-only PDF (`Faculty Entrepreneurship Policy`) with raw text extraction alone.
- **Symptom**: Ingestion silently produced empty text buffers (`len(text) == 0`). In the chat UI, questions regarding startup IP ownership resulted in false abstentions (`answered_from_context: false`).
- **Diagnosis (as if uncaused)**:
  * Inspection command: `pdffonts corpus/raw/faculty-entrepreneurship-policy.pdf` showed an empty font descriptor table.
  * Extractor log check: `jq '.msg == "chunked"' indexer.log` showed 0 chunks generated for the document.
- **Remedy**: Re-enabled `pdf2image` rasterization piped to `pytesseract` OCR, and added structured tabular parsing via `pdfplumber` for markdown conversion.

---

## Stage B · Chunking (Zero Overlap & Arbitrary Character Windowing)
- **What we broke**: Replaced structure-aware chunking with a rigid 200-character split without overlap (`CHUNK_OVERLAP=0`).
- **Symptom**: `recall@5` plummeted from 0.875 to 0.620. Questions quoting specific policy conditions failed because clause headings were severed from their operative text.
- **Diagnosis (as if uncaused)**:
  * Evaluation runner output: `eval/run_eval.py` reported:
    `Gate Failure: recall@5 dropped from baseline 0.8750 to 0.6200`.
  * Chunk inspection in Chroma:
    `python -c "import chromadb; c=chromadb.HttpClient().get_collection('rahbar'); print(c.peek(5)['metadatas'])"`
    revealed section headers recorded as "General" or severed mid-word.
- **Remedy**: Restored regex heading detection (`HEADING_PATTERN`) and hierarchical splitting on double newlines with a 50-character sliding overlap.

---

## Stage C · Embedding & Model Pinning (Silent Embedding Divergence)
- **What we broke**: Changed `EMBED_MODEL` in the API ConfigMap to `all-MiniLM-L6-v2` while leaving the Chroma index populated with `nomic-embed-text` vectors, without triggering a re-index.
- **Symptom**: API returned gibberish retrieval results with near-zero similarity scores (`score < 0.20`), triggering blanket abstention across all queries.
- **Diagnosis (as if uncaused)**:
  * Readiness probe endpoint output: `curl http://rahbar-api.rahbar:8000/readyz` returned `HTTP 503 Service Unavailable`:
    ```json
    {
      "status": "not_ready",
      "checks": {
        "embed_model": "embedding_model mismatch: index has nomic-embed-text != configured all-MiniLM-L6-v2"
      }
    }
    ```
  * Application logs: `kubectl logs deploy/rahbar-api -n rahbar` logged:
    `ERROR: embedding model mismatch detected: index uses nomic-embed-text but API configured with all-MiniLM-L6-v2`.
- **Remedy**: Pinned the model centrally in `k8s/base/configmap.yaml` under `EMBED_MODEL` and ensured `/readyz` blocks pod readiness until the API and Chroma collection agree.

---

## Stage D · Retrieval (Superseded Policy Leakage)
- **What we broke**: Removed the `superseded` filter in `api/app/retrieval/chroma.py`.
- **Symptom**: When asking about course repetition rules, the retriever returned the repealed 2023 handbook clause rather than the active 2026 handbook, leading to factually incorrect advisory responses.
- **Diagnosis (as if uncaused)**:
  * Golden evaluation run: `python eval/run_eval.py` failed question `q09` (`type: version`).
  * Response inspection: `AskResponse.retrieved` contained `source: "undergraduate-academic-rules-aug-2023.pdf"`.
- **Remedy**: Applied strict metadata filtering in `ChromaRetriever.retrieve` to exclude chunks where `superseded == True`.

---

## Stage E · Augmentation (Context Dilution and Prompt Injection)
- **What we broke**: Removed the prompt injection filter in `api/app/services/grounding.py` and injected a prompt override string in a query.
- **Symptom**: Model output bypassed grounding instructions and attempted to answer conversational small-talk without citing documents.
- **Diagnosis (as if uncaused)**:
  * Log search: `kubectl logs -l app=rahbar,component=api -n rahbar | grep "injection"` returned zero hits.
  * Evaluation runner: `q16` (`type: injection`) returned `answered_from_context: true` instead of declining.
- **Remedy**: Added regex-based injection detection in `grounding.py` and strict prompt fencing (`System: You are RAHBAR...`), forcing immediate honest abstention when adversarial prompts are detected.

---

## Stage F · Generation (High Temperature Hallucination & Schema Corruption)
- **What we broke**: Increased LLM temperature to `1.2` and removed `response_format={"type": "json_object"}`.
- **Symptom**: Model started inventing non-existent university clauses (hallucinated `Clause 9.99`) and returned conversational markdown preamble, causing JSON parsing to fail.
- **Diagnosis (as if uncaused)**:
  * API logs showed repeated validation warnings:
    `WARNING: validation failure on attempt 1: ValidationError (Answer)`.
  * Fallback log: `ERROR: all retries exhausted; returning safe fallback response`.
  * Citation validity dropped to `72%` in `eval/run_eval.py`.
- **Remedy**: Enforced constrained decoding (`response_format={"type": "json_object"}`), lowered temperature to `0.2`, added Pydantic validation with 2 retries, and implemented deterministic citation matching against retrieved chunks.
