## Plan: Add .pdf and .xlsx support with verifiable parsing for Q&A

### Goals
- Support uploading one or more `.pdf` and `.xlsx` files (batch or single) to S3.
- Parse and normalize both formats so the LLM can answer questions grounded in those files.
- Provide a minimal, automatable test set aligned to the “Healthy Drinks” questions.

### Current state (summary)
- Uploads: Presigned S3 PUT via `POST /upload-request` with `contentType`.
- Chat flow: `POST /agent-task` → Step Functions → `lambda/bedrock_agent.py` parses PDFs via LlamaParse, composes excerpts, and (optionally) calls Bedrock model (Sonnet 3.5) to answer.
- Agent console (`/agent`) is separate and uses Bedrock Agents runtime.

### Proposed changes
1) Content-type aware uploads
   - Keep original extension instead of forcing `.pdf` keys. Store as `${userId}/${documentId}.${ext}`.
   - Update `lambda/get_presigned_upload.py` to:
     - Map `contentType` to extension: `application/pdf`→`pdf`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`→`xlsx`.
     - Return `{ documentId, extension }` so downstream knows file type (or infer later via S3 `HeadObject.ContentType`).

2) Unified parsing layer
   - Create `lambda/common/parse_document.py` with:
     - `parse_pdf(bytes)`: use existing LlamaParse wrapper (existing `llama_parse.parse_pdf_bytes`).
     - `parse_xlsx(bytes)`: use `pandas` (`openpyxl` engine) to extract sheets as rows; also produce a flattened text summary per sheet for LLM context.
     - Normalize to a common structure:
       ```json
       {
         "docType": "pdf"|"xlsx",
         "text": "...",              // joined narrative text
         "tables": [ { "name":"Sheet1", "rows":[{...}] } ],
         "metadata": { "title": "...", "sheetNames": ["..."] }
       }
       ```
   - Update `lambda/bedrock_agent.py` to branch by extension and call the appropriate parser; preserve a `sources` array as before.

3) Grounding format for LLM
   - For PDFs: keep current excerpt strategy (first N kB) plus metadata title.
   - For XLSX: build a compact textual summary per table (first M rows + inferred headers) AND include a JSON snippet with the most relevant rows if under size budget.
   - Compose a single context blob:
     - `Question`
     - `PDF excerpts` (if any)
     - `XLSX summaries + key rows`
   - Keep output schema the same: `{ text, sources, report }`.

4) Frontend updates
   - Upload page: allow multi-file selection; request presigned URLs for each file; upload in parallel; display collected `documentId`s.
   - Chat page: let user paste or select multiple `documentId`s (already supported by array param) and submit.

5) Testing strategy (Healthy Drinks minimal set)
   - Fixtures (checked into `tests/fixtures/`):
     - `products.xlsx`: columns e.g. `product`, `flavor`, `size_oz`, `price`, `tags` (energy/relaxation/detox), `promo_code`.
     - `orders.xlsx`: columns e.g. `order_id`, `status`, `eta`, `address`, `can_cancel` (Y/N).
     - `catalog.pdf` (optional): a brochure with ingredient lists.
   - Unit tests (parsers):
     - `tests/test_parse_xlsx.py`: verify `parse_xlsx` returns expected sheets/rows and a non-empty `text` summary.
     - `tests/test_parse_pdf.py`: verify LlamaParse result shape and non-empty `text` for the fixture brochure.
   - Integration tests (end-to-end):
     - Script: upload fixtures via `POST /upload-request` + PUT; collect `documentId`s.
     - Start chat task with relevant `documentId`s and ask:
       - Order-related (1–5): expect matching substrings from `orders.xlsx` (status, ETA, cancel policy, address change policy, reorder acknowledgement).
       - Product-related (6–10): expect ingredients from PDF or `products.xlsx`, flavors/sizes from `products.xlsx`, price, promo presence, and “best for X” derived from `tags`.
     - Assert: answers contain expected values (e.g., order `123` status `Shipped`, ETA date; `Berry Boost` price `$3.99`; promo `SPRING10`).

6) Operational concerns
   - Size budgets: cap XLSX extracted rows per sheet (e.g., first 50) and prefer summarization; consider dynamic selection based on the question in future.
   - Error handling: if parsing fails for a doc, include a source entry with an error message and continue with others.
   - Security: maintain S3 CORS (already permissive) and block public reads; validate `contentType` on presign.

7) Optional next steps (v2)
   - Indexing for retrieval: push parsed text/rows into a vector index (e.g., OpenSearch Serverless) for semantic retrieval instead of static excerpts.
   - Tool-based agent: expose a tool that can run filtered table lookups against parsed XLSX content.
   - Report generation: export filtered tables and answers into a downloadable report in `ReportsBucket`.

### Work items (incremental)
1. Update presign to preserve extension and return it.
2. Add `parse_document.py` and `parse_xlsx(bytes)` with `pandas[openpyxl]` dependency.
3. Modify `bedrock_agent.py` to parse by extension and compose unified context.
4. Frontend: multi-file upload + document list UI.
5. Add fixtures and tests (unit + integration scripts).
6. Quotas: ensure model/agent quotas meet expected test throughput.

### Dependencies
- Python: `pandas`, `openpyxl` (add to `requirements.txt`).
- Existing: LlamaParse secret in Secrets Manager.


