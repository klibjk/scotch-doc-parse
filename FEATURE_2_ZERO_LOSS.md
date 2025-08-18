## Plan: Zero-loss Preservation of Parsed Outputs (PDF/XLSX)

### Goal
Store and expose complete LlamaParse outputs without dropping structure, while still providing compact excerpts for prompts.

### Approach
- Persist raw LlamaParse JSON for each document to S3: `parsed/{userId}/{documentId}.json`.
- Extend normalized object to optionally include a pointer to the raw JSON location: `metadata.rawS3Uri`.
- For PDFs, pass through `pages`, `tables` in normalized results (do not discard structure).
- For XLSX, keep complete `tables` as returned by LlamaParse.
- Keep prompt-sized excerpts for `/chat` to control tokens.

### Changes
1) `lambda/common/parse_document.py`
   - Add `pages` passthrough for PDF, keep `tables` if present.
   - Ensure XLSX tables are kept fully.
2) `lambda/bedrock_agent.py`
   - After parsing, write raw result to S3 `parsed/...` and set `metadata.rawS3Uri`.
   - Continue building excerpts from `text` only for the prompt.
3) Buckets & IAM
   - Use existing `ReportsBucket` or add a dedicated `ParsedBucket` (if preferred) for raw JSON.
   - Grant write permissions to the Lambda.

### Testing
- Upload sample PDF/XLSX; verify `parsed/...json` is created.
- Confirm normalized object includes `rawS3Uri` and `pages/tables` fields.
- `/chat` still responds within token limits.

### Risks
- Larger storage footprint; mitigate with TTL policies if needed.
- Ensure no PII leak to public; buckets stay private.
