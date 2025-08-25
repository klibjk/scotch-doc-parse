## Plan: Vector Database for Scalable Retrieval (PDF/XLSX)

### Goal
Retrieve only the most relevant passages/rows per question to improve accuracy, reduce tokens, and scale to many files.

### Architecture
- Chunking
  - PDF: chunk by headings/pages (500–1000 tokens) with overlap.
  - XLSX: chunk by rows or small row-groups per sheet; include headers.
- Metadata per chunk
  - `documentId`, `filename`, `docType`, `page|sheet`, `rowStart|rowEnd`, `userId`, timestamp.
- Embeddings + store
  - Use a vector store (pgvector/FAISS) to store embeddings and metadata.
- Query time
  - Encode question, retrieve top-k (3–8) chunks with a score threshold.
  - Compose prompt context: concise `text` plus a small JSON/table snippet and citations.

### Changes
1) ETL job (Lambda or Step Functions)
   - After LlamaParse, produce chunks and write embeddings to the vector store.
2) `/chat` path
   - Replace full-document excerpts with top-k retrieved chunks.
   - Include citations (`documentId`, page/sheet, row range).
3) Optional: Bedrock Agent tool
   - Add a retrieval tool for agents to call with the user’s question.

### Testing
- Index `sample_docs` and fixtures.
- Ask the minimal Healthy Drinks questions; verify results cite correct rows/pages.
- Load test with many files; observe stable tokens/latency.

### Ops
- Backfill job for existing docs.
- TTL/retention policy for stale chunks.
- Quota review for embeddings/model calls.
