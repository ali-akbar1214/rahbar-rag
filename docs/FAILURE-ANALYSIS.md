# RAG Pipeline Failure Analysis: Breaking One Stage at a Time

Following Section 5.5, we deliberately broke all six stages of the pipeline one at a time on isolated runs and recorded the user-visible symptom, how we would diagnose it blind from our Prometheus `/metrics` and JSON stdout logs, the responsible stage, and the code remedy. Remember the lecture rule: **only Stage F is the model's fault—always check A through E first.**

---

## Stage A · Extraction — Index the Scanned PDF Without OCR
- **How we broke it**: Disabled the `pytesseract` / `pdf2image` branch in `indexer/pipeline/extract.py` and indexed `faculty-entrepreneurship-and-technical-start-ups-policy.pdf` with native PDF text extraction only.
- **Symptom**: Every question about faculty spin-out equity or IP ownership returned an abstention (`answered_from_context: false`), while handbook questions continued working normally.
- **Blind Diagnosis (Metrics & Logs)**:
  - `rahbar_abstentions_total` spiked on entrepreneurship queries, and the API per-request JSON log (`msg: "answered"`) showed `scores: [0.11, 0.09]` (none from `faculty-entrepreneurship-*.pdf`).
  - Checking the indexer Job logs (`kubectl logs job/rahbar-indexer-job -n rahbar`) showed `{"msg": "chunked", "source": "faculty-entrepreneurship-and-technical-start-ups-policy.pdf", "chunks": 0}`.
  - Running `pdffonts` on the raw PDF confirmed an empty font table (scanned image-only PDF).
- **Remedy**: Enabled page-level `< 30` char detection in `extract.py` with `pdf2image` rasterization + `pytesseract` OCR (`poppler-utils` and `tesseract-ocr` baked into `indexer/Dockerfile`).

---

## Stage B · Chunking — Fixed-Size 100-Token Chunks With Zero Overlap
- **How we broke it**: Replaced structure-aware splitting in `indexer/pipeline/chunk.py` with a naive fixed 400-character (~100-token) slice and `CHUNK_OVERLAP=0`.
- **Symptom**: Answers to multi-condition clauses (e.g., `q04` suspension of registration, `q06` plagiarism penalties) became incomplete or missed exact thresholds, and `eval/run_eval.py` failed the CI gate (`recall@5` dropped from `0.9333` to `0.6200`).
- **Blind Diagnosis (Metrics & Logs)**:
  - API JSON request logs showed chunks retrieved from the right `source`, but `section` was `"General Overview"` because clause headers had been sliced into the tail of the preceding chunk with zero overlap.
  - `eval/results.json` showed `recall@5` dropping > 25 points while `rahbar_fallbacks_total` stayed `0` (proving generation was healthy and Stage B/C was at fault).
- **Remedy**: Restored hierarchical heading → paragraph → sentence chunking with `CHUNK_SIZE=400` and `CHUNK_OVERLAP=50`, attaching detected clause headings to every emitted chunk's `section` metadata.

---

## Stage C · Retrieval — Change `EMBED_MODEL` on the API Only
- **How we broke it**: Patched `EMBED_MODEL: "all-minilm"` in `ConfigMap/rahbar-config` and restarted `Deployment/rahbar-api` without running a re-index Job.
- **Symptom**: Newly created API pod stayed at `0/1 READY` (with the guardrail enabled). When tested *without* the guardrail locally, retrieval returned nonsensical chunks with similarity scores `< 0.15`, causing 100% false abstentions.
- **Blind Diagnosis (Metrics & Logs)**:
  - `kubectl get pods -n rahbar` showed the replacement pod held at `0/1 READY`, and `/readyz` returned HTTP `503`.
  - `kubectl logs` printed the exact JSON error: `"embedding model mismatch detected: index uses nomic-embed-text (dim=768) but API configured with all-minilm"`.
  - Without the guardrail, `rahbar_abstentions_total` jumped to 100% of requests while `scores` in the `"answered"` log line collapsed near zero across every query.
- **Remedy**: Enforced the shared `EMBED_MODEL` pin in `ConfigMap/rahbar-config`, recorded `embed_model` and `dimension` in Chroma collection metadata (`indexer/pipeline/store.py`), and verified parity in `verify_embedding_pin` + `/readyz` (`api/app/routes/health.py`).

---

## Stage D · Prompt — Remove the "Use Only Supplied Context" Instruction
- **How we broke it**: Removed the grounding constraint (*"answer strictly using the supplied `<untrusted_document_data>` excerpts"*) from `HostedProvider._build_prompt` in `api/app/providers/llm/hosted.py`.
- **Symptom**: On must-abstain hostel and bus shuttle questions (`q14`, `q15`) when `RELEVANCE_FLOOR` was lowered, the LLM confidently invented generic university hostel curfews and fabricated non-existent section names, failing `abstention_correctness` (`< 1.0`) and `citation_validity` (`< 0.95`).
- **Blind Diagnosis (Metrics & Logs)**:
  - In `msg: "answered"` logs, `scores` were low (`0.16–0.22`) and `chunk_ids` pointed to unrelated fee pages, yet `answered_from_context` was `true`.
  - `eval/run_eval.py` reported `Gate Failure: Abstention correctness 50.0% is below required 100.0%` and `citation_validity` dropped below `0.95`.
- **Remedy**: Restored strict grounding instructions + `<untrusted_document_data>` XML delimiters, enforced `RELEVANCE_FLOOR=0.15` pre-generation abstention in `answer.py`, and validated every `(source, section)` citation in `grounding.validate_citations`.

---

## Stage E · Source — Remove the `superseded` Filter on Version-Sensitive Questions
- **How we broke it**: Disabled the `where={"superseded": False}` filter in `ChromaRetriever.retrieve` (`api/app/retrieval/chroma.py`) and asked `q09` (*"Under current 2026 rules, can a student repeat a course if they obtained a grade of C?"*).
- **Symptom**: The API confidently quoted the repealed `2023-08` handbook (`undergraduate-academic-rules-aug-2023.pdf`) instead of the active `2026-06` handbook, giving outdated academic advice.
- **Blind Diagnosis (Metrics & Logs)**:
  - `rahbar_retrieval_latency_seconds` and `scores` (`0.88`) looked completely normal!
  - Inspecting `chunk_ids` in the per-request JSON log (`"chunk_ids": ["undergraduate-academic-rules-aug-2023.pdf-p14-0031"]`) immediately revealed a `superseded: true` source entering top-$k$ retrieval, and `eval/run_eval.py` failed `type_recall5["version"]`.
- **Remedy**: Restored `where={"superseded": False}` metadata filtering in `ChromaRetriever.retrieve`, bypassed only when `asks_for_older_version(question)` detects an explicit historical query (such as `q10` asking specifically about 2023 rules).

---

## Stage F · Generation — Raise `TEMPERATURE` to `1.2`
- **How we broke it**: Raised `TEMPERATURE` from `"0.2"` to `"1.2"` in `ConfigMap/rahbar-config`.
- **Symptom**: Occasional malformed JSON / schema drift triggered retries and safe fallback responses, while answers paraphrased numerical thresholds loosely and invented non-retrieved sub-clauses.
- **Blind Diagnosis (Metrics & Logs)**:
  - `rahbar_fallbacks_total` became non-zero in `/metrics`, `rahbar_generation_latency_seconds` doubled on requests that hit retry attempt 2, and `rahbar.llm.hosted` logged `WARNING: validation failure on attempt 1`.
  - Unlike Stages A–E, `chunk_ids` and `scores` in the request log were completely accurate—confirming retrieval succeeded and isolating the fault to Stage F.
- **Remedy**: Pinned `TEMPERATURE: "0.2"` in `k8s/base/configmap.yaml`, enforced JSON schema / `json_object` constrained decoding, kept 1 validation retry at reduced temperature (`temperature - 0.1`), and stripped any unverified citations in `validate_citations`.
