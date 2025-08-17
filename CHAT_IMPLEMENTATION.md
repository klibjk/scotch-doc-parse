## Chat Implementation (Scotch Doc-Chat)

This document explains how the `/chat` experience at the deployed site works (`/chat`). It focuses on the asynchronous task flow that grounds answers on uploaded PDFs.

### High-level flow
- Frontend (Next.js) page `chat` collects a prompt and optional `documentId`.
- It POSTs to `POST /agent-task` to start an asynchronous task.
- A Step Functions state machine invokes backend logic to parse docs and generate an answer.
- The frontend polls `GET /agent-task?taskId=...` until the task is `COMPLETED`, then renders the result.

### Frontend
- File: `frontend/nextjs-app/src/app/chat/page.tsx`
  - Reads `API_BASE` from `frontend/nextjs-app/src/lib/config.ts` (defaults to the deployed API Gateway URL).
  - `startTask(prompt, documentIds)` → `POST ${API_BASE}/agent-task` body: `{ prompt, documentIds, userId }`.
  - `pollTask(taskId)` → `GET ${API_BASE}/agent-task?taskId=...` until `status === COMPLETED` (or `FAILED`).
  - Renders `result.text`, optional `result.sources`, and optional `result.report.content`.

### API Gateway endpoints
- `POST /agent-task` → Lambda: `lambda/start_task.py`
  - Validates input, writes an initial record into DynamoDB, and starts a Step Functions execution.
- `GET /agent-task?taskId=...` → Lambda: `lambda/get_result.py`
  - Returns the current task record with `status` and (when ready) `result`.
- `POST /upload-request` → Lambda: `lambda/get_presigned_upload.py`
  - Issues presigned S3 PUT for PDF uploads and returns a `documentId`.

### Step Functions (asynchronous task)
- Defined in `infrastructure/stacks/api_stack.py`:
  - Task `InvokeBedrockAgent` → Lambda `lambda/bedrock_agent.py` (timeout ~120s)
  - On success, `UpdateResult` writes the answer into DynamoDB.
  - On error, `HandleError` sets status `FAILED` with the error message.

### Backend Lambda: `lambda/bedrock_agent.py`
- Reads input: `{ prompt, documentIds[], userId, sessionId }` (payload provided via Step Functions).
- Loads PDFs from the uploads bucket using `userId/documentId.pdf`.
- Parses PDFs using `lambda/common/llama_parse.py` (LlamaParse integration via Secrets Manager key `LLAMAPARSE_SECRET_ID`).
- If parsed text is available, optionally calls Bedrock Runtime using the model in env `BEDROCK_MODEL_ID` to produce a concise answer grounded on excerpts; otherwise returns excerpts or a no-text message.
- Returns a standardized result:
  - `text`: answer string
  - `sources`: `{ documentId, pages[] }[]`
  - `report`: `{ format: markdown, content: ... }`
  - Plus `completedAt` and `sessionId` propagated back to Step Functions for storage.

### Storage and resources
- S3 Buckets (created in `ApiStack`):
  - `UploadsBucket`: user-uploaded PDFs (PUT via presigned URL).
  - `ReportsBucket`: reserved for generated reports.
- DynamoDB Table: `AgentTasks`
  - Partition key: `taskId`
  - Stores task `status`, `result` (stringified JSON), timestamps, `sessionId`.

### Configuration (CDK `ApiStack`)
- Common Lambda env:
  - `AGENT_TASKS_TABLE`: DynamoDB table name
  - `UPLOADS_BUCKET`, `REPORTS_BUCKET`
  - `LLAMAPARSE_SECRET_ID`: secret for LlamaParse API key
  - `BEDROCK_MODEL_ID`: foundation model for direct Bedrock Runtime calls (currently Sonnet 3.5)
- IAM permissions grant:
  - S3 read/write as needed
  - DynamoDB read/write for task lifecycle
  - Bedrock (InvokeModel/Converse) for `bedrock_agent.py`

### Related (separate) agent console
- `/agent` page is a simple console that POSTs to `POST /agent-chat` → `lambda/agent_chat.py`.
- That path uses Bedrock Agents Runtime (`invoke_agent`) with alias and session IDs. It is independent from the `/chat` async task flow described above.

### How to test `/chat` end-to-end
1) Upload a PDF via `/upload` (or call `POST /upload-request` and PUT to returned `uploadUrl`).
2) Start a task:
   - `POST ${API_BASE}/agent-task`
   - Body example: `{ "prompt": "Summarize the doc", "documentIds": ["doc_..."], "userId": "demo" }`
   - Response: `{ taskId }`
3) Poll result:
   - `GET ${API_BASE}/agent-task?taskId=...`
   - When `status === "COMPLETED"`, parse `result` JSON to get `text`, `sources`, `report`.

### Notes
- The `/chat` page is resilient by polling with increasing delay.
- The model used by `bedrock_agent.py` is controlled by `BEDROCK_MODEL_ID` (set in `ApiStack`). Changing this affects only the `/chat` flow, not the `/agent` (Bedrock Agent) console.
- Buckets have permissive CORS for PUT/GET to support browser uploads via presigned URLs.


