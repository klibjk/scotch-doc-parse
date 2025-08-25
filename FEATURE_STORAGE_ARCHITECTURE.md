## Feature: Storage Architecture — On-Demand and Preemptive Retrieval

### Summary
Store user uploads durably in S3; retrieve into Lambda memory on demand to parse and build LLM context. Optionally preemptively parse+cache after upload to reduce query latency. Support multi-file queries and graceful partial failure.

### Goals
- Durable storage via S3: `s3://<uploads>/<userId>/<documentId>.<ext>`.
- On-demand retrieval in `bedrock_agent.py`: fetch bytes → parse → build excerpts/retrieval context.
- Memoization: reuse previously parsed JSON (S3 pointer) or in-memory LRU per warm Lambda.
- Preemptive path: `index_etl.py` parses and writes `parsed/<userId>/<documentId>.json` alongside embeddings JSONL.
- Multi-file support: accept `documentIds[]`, merge ranked excerpts, enforce token budgets.

### Current State (as of this branch)
- Uploads: `POST /upload-request` returns presigned PUT; keys keep original extension.
- Agent: `bedrock_agent.py` downloads from S3 and parses via `parse_document.py` → `llama_parse.py`.
- Zero-loss: agent writes normalized parsed JSON to `s3://<reports>/parsed/<user>/<doc>.json` and attaches `metadata.rawS3Uri`.
- Index ETL: `index_etl.py` chunks+embeds to `embeddings/<user>/<doc>.jsonl` (triggered by S3 ObjectCreated).

### Changes in this feature
1) Agent memoization
   - Reuse S3 `parsed/<user>/<doc>.json` when present (same-or-new ETag) to skip re-parsing.
   - Add shallow in-memory LRU (key: uploads ETag) per warm Lambda to avoid redundant S3 reads within the same container.

2) Preemptive parsed JSON
   - Extend `index_etl.py` to write normalized parsed output to `parsed/<user>/<doc>.json` in addition to embeddings JSONL.

3) Multi-file ranking tighten
   - Keep existing vector retrieval; optionally apply simple keyword TF-IDF weighting before truncation.

### API/Contract
- Unchanged request/response. Agent may respond faster when caches hit.
- `metadata.rawS3Uri` always points to the latest normalized parsed JSON if available.

### Risks & Mitigations
- Latency spikes: on-demand fetch/parse → mitigated by preemptive parse and memoization.
- Consistency: use S3 `ETag`/`versionId` in cache key; enable versioning in bucket (out of scope for code change).
- Cost: preemptive parse can be gated by size/type; apply TTL/LRU on in-memory cache and allow skip for large files.
- Partial failures: per-doc try/except; include `metadata.error` and continue.

### Deployment Notes
- No infra changes required beyond existing buckets and permissions.
- Ensure `REPORTS_BUCKET` has write permission for `parsed/...` objects (already granted).


