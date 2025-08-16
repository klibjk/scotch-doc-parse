### Scotch Doc-Chat App — Development Plan

Build a web app where users upload PDFs, chat with an AI about document contents, and export reports. Backend is serverless on AWS with an asynchronous API to avoid timeouts. Parsing is powered by LlamaParse; reasoning is via AWS Bedrock Agent using Claude 3.5 Sonnet.

---

## Objectives
- Deliver a chatbot UI that can answer questions grounded in uploaded PDFs.
- Support PDF ingestion via presigned uploads; parse with LlamaParse.
- Use a Bedrock Agent with an Action Group to call Python functions (LlamaParse, retrieval, report export).
- Provide asynchronous task API to prevent timeouts for long-running agent calls.
- Store conversations and task results in DynamoDB; artifacts in S3.
- Offer report export (Markdown → HTML/PDF later) generated from the agent’s structured outputs.

## Non-Goals (v1)
- Non-PDF formats (DOCX, PPTX) — out of scope.
- Realtime streaming responses — initial v1 will be poll-based.
- Multi-tenant org features beyond a basic `userId` scoping.

---

## Tech Stack
- Languages: Python 3.11 (Lambdas, CDK), JavaScript/TypeScript (Next.js frontend)
- Frontend: Next.js, static export to S3 + CloudFront on custom domain
- Backend (Serverless): API Gateway, Lambda, Step Functions, DynamoDB, S3, Bedrock Agent (Claude 3.5 Sonnet)
- Parsing: LlamaParse (PDF only in v1)

### Key Environment Variables / Parameters
- `BEDROCK_AGENT_ID` (SSM Parameter)
- `BEDROCK_AGENT_ALIAS_ID` (SSM Parameter)
- `BEDROCK_MODEL_ID` = `anthropic.claude-3-5-sonnet-20240620` (Parameter)
- `LLAMAPARSE_API_KEY` (AWS Secrets Manager)
- `UPLOADS_BUCKET`, `REPORTS_BUCKET`, `LOGS_BUCKET` (CDK Outputs/SSM)
- `CF_DISTRIBUTION_DOMAIN` (CDK Output)

---

## High-Level Architecture

```mermaid
flowchart TD
  U[User (Browser)] -->|1. Get presigned URL| APIG[API Gateway]
  APIG -->|Lambda| PreSig[GetPresignedUploadLambda]
  U -->|2. PUT PDF| S3Uploads[(S3 Uploads Bucket)]
  U -->|3. Start chat task (prompt + doc refs)| APIG
  APIG -->|Lambda| StartTaskLambda
  StartTaskLambda -->|StartExecution| SFN[(Step Functions)]
  SFN --> DDBInit[(DynamoDB AgentTasks)]
  SFN --> Agent[BedrockAgentLambda]
  Agent --> Bedrock[Bedrock Agent (Claude 3.5 Sonnet)]
  Bedrock -->|Action Group: parse/report| Llama[LlamaParse API]
  SFN -->|Update result| DDBRes[(DynamoDB AgentTasks)]
  U -->|Poll task status| APIG --> GetResultLambda --> DDBRes
  Agent-.-> DDBChat[(DynamoDB ChatSessions/Messages)]
  Agent-.-> S3Reports[(S3 Reports Bucket)]
  classDef store fill:#eef,stroke:#99f;
  class S3Uploads,S3Reports,DDBInit,DDBRes,DDBChat store;
```

---

## Core Components

### Frontend (Next.js)
- Pages: `Upload`, `Chat`, `Reports`.
- Upload flow: request presigned URL → PUT file to S3 → receive `documentId`.
- Chat flow: post `prompt` + `documentId[]` to `POST /agent-task` → receive `taskId` → poll `GET /agent-task?taskId=...` until `COMPLETED`.
- Report export: trigger report generation via agent tool; download from `S3 Reports` after task completion.

### API Gateway
- `POST /agent-task`: starts asynchronous task; returns `{ taskId }`.
- `GET /agent-task?taskId=...`: returns task status/result.
- `POST /upload-request`: returns `{ uploadUrl, documentId }` for presigned S3 PUT.

### Lambda Functions (Python 3.11)
- `StartTaskLambda`: validates input, writes initial task record, starts a Step Functions execution, returns `taskId`.
- `GetResultLambda`: retrieves task record by `taskId` from DynamoDB.
- `BedrockAgentLambda`: invokes Bedrock Agent with conversation context, tool results, and document references.
- `GetPresignedUploadLambda`: returns presigned S3 URL and a `documentId`.
- (Optional v1.1) `GenerateReportLambda`: converts agent-produced Markdown to HTML/PDF.

### Step Functions State Machine
States:
- `StartExecution`: PutItem `RUNNING` task (taskId, prompt, createdAt).
- `InvokeBedrockAgent`: Invoke `BedrockAgentLambda`.
- `UpdateResult`: UpdateItem with `COMPLETED`, `result`, `completedAt`, `sessionId`.
- `HandleError`: UpdateItem with `FAILED`, `error`.

Retry/timeout policies configured around agent invocation to avoid indefinite waits.

### DynamoDB
- Table `AgentTasks` (PK: `taskId`)
  - `status`: `RUNNING|COMPLETED|FAILED`
  - `prompt`: original prompt
  - `result`: agent response object (JSON + text)
  - `error`: error details (if failed)
  - `createdAt`, `completedAt`
  - `sessionId`: Bedrock session id
  - `ttl`: Time to live (for cleanup)
  - `userId`: partitioning/scope

- Table `ChatSessions` (PK: `sessionId`, SK: `messageId`)
  - `role`: `user|assistant|tool`
  - `content`: text/JSON
  - `docRefs`: list of `documentId`
  - `createdAt`
  - GSI: `byUser` (PK: `userId`, SK: `createdAt` desc)

### S3 Buckets
- `uploads` bucket: source PDFs; private. Prefix by `userId/` and `documentId.pdf`.
- `reports` bucket: exported reports (Markdown, HTML, optional PDF); private; downloadable via signed URLs.
- `logs` bucket: optional long-term logs/trace exports.

### Bedrock Agent (Claude 3.5 Sonnet)
- Model: `anthropic.claude-3-5-sonnet-20240620`.
- Orchestrates task reasoning; keeps session state.
- Action Group exposing tools implemented via Lambda-backed functions:
  - `parse_pdf(document_id)`: fetch from S3, call LlamaParse, return structured JSON + plain text.
  - `search_chunks(query, top_k)`: (v1.1) if chunk store is added.
  - `generate_report(request)`: produce Markdown summary from parsed content and Q&A session context.

System prompt (draft):
```
You are a document analysis assistant. Always ground answers in the provided parsed content.
When citations exist, include a short Sources section with documentId and page numbers.
Prefer concise responses with clear bullet points.
If a question is outside the document scope, ask for clarification.
```

### LlamaParse Integration
- Use LlamaParse REST API with API key from Secrets Manager. Do NOT embed secrets in code.
- Supported in v1: PDFs only.
- Typical flow in `parse_pdf` tool:
  1) Download object from `uploads` bucket by `documentId`.
  2) Call LlamaParse (upload + parse or direct parse if supported) using `LLAMAPARSE_API_KEY`.
  3) Normalize output into: `{ text, pages:[{pageNumber, text}], tables:[...], metadata:{title, author?} }`.
  4) Return snippet(s) and references for agent grounding.

---

## API Design

### POST /agent-task
Request
```json
{
  "prompt": "Summarize section 2 and list key risks",
  "documentIds": ["doc_123"],
  "userId": "user_abc",
  "sessionId": "sess_456"  
}
```

Response
```json
{ "taskId": "task_789" }
```

### GET /agent-task?taskId=...
Response (RUNNING)
```json
{
  "taskId": "task_789",
  "status": "RUNNING"
}
```

Response (COMPLETED)
```json
{
  "taskId": "task_789",
  "status": "COMPLETED",
  "result": {
    "text": "Here are the key risks...",
    "sources": [{"documentId": "doc_123", "pages": [2,3]}],
    "report": {"format": "markdown", "content": "# Report..."}
  },
  "completedAt": "2025-01-01T12:00:00Z"
}
```

Response (FAILED)
```json
{
  "taskId": "task_789",
  "status": "FAILED",
  "error": {"message": "Timeout invoking agent"}
}
```

### POST /upload-request
Request
```json
{ "filename": "contract.pdf", "contentType": "application/pdf", "userId": "user_abc" }
```

Response
```json
{
  "uploadUrl": "https://s3...",
  "documentId": "doc_123",
  "expiresIn": 900
}
```

---

## Step Functions — State Definition (ASL Sketch)
```json
{
  "Comment": "Agent async orchestration",
  "StartAt": "StartExecution",
  "States": {
    "StartExecution": {
      "Type": "Task",
      "Resource": "arn:aws:states:::dynamodb:putItem",
      "Parameters": {
        "TableName.$": "$.env.AgentTasksTable",
        "Item": {
          "taskId": {"S.$": "$.taskId"},
          "status": {"S": "RUNNING"},
          "prompt": {"S.$": "$.prompt"},
          "createdAt": {"S.$": "$.createdAt"},
          "userId": {"S.$": "$.userId"}
        }
      },
      "Next": "InvokeBedrockAgent"
    },
    "InvokeBedrockAgent": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:REGION:ACCOUNT:function:BedrockAgentLambda",
      "TimeoutSeconds": 120,
      "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "HandleError"}],
      "Next": "UpdateResult"
    },
    "UpdateResult": {
      "Type": "Task",
      "Resource": "arn:aws:states:::dynamodb:updateItem",
      "Parameters": {
        "TableName.$": "$.env.AgentTasksTable",
        "Key": {"taskId": {"S.$": "$.taskId"}},
        "UpdateExpression": "SET #status=:c, #result=:r, #completedAt=:t, #sessionId=:s",
        "ExpressionAttributeNames": {"#status": "status", "#result": "result", "#completedAt": "completedAt", "#sessionId": "sessionId"},
        "ExpressionAttributeValues": {
          ":c": {"S": "COMPLETED"},
          ":r": {"S.$": "$.agentResult"},
          ":t": {"S.$": "$.completedAt"},
          ":s": {"S.$": "$.sessionId"}
        }
      },
      "End": true
    },
    "HandleError": {
      "Type": "Task",
      "Resource": "arn:aws:states:::dynamodb:updateItem",
      "Parameters": {
        "TableName.$": "$.env.AgentTasksTable",
        "Key": {"taskId": {"S.$": "$.taskId"}},
        "UpdateExpression": "SET #status=:f, #error=:e",
        "ExpressionAttributeNames": {"#status": "status", "#error": "error"},
        "ExpressionAttributeValues": {
          ":f": {"S": "FAILED"},
          ":e": {"S.$": "$.errorMessage"}
        }
      },
      "End": true
    }
  }
}
```

---

## Data Model Details

### AgentTasks (DynamoDB)
- PK: `taskId` (string)
- Attributes: `status`, `prompt`, `result` (JSON string), `error` (JSON string), `createdAt`, `completedAt`, `sessionId`, `userId`, `ttl`.
- TTL recommended: 3–7 days for ephemeral status; long-term summaries stored separately if needed.

### ChatSessions (DynamoDB)
- PK: `sessionId`, SK: `messageId` (ULID)
- Attributes: `role`, `content`, `docRefs`, `createdAt`, `userId`.
- GSI `byUser`: `{ PK: userId, SK: createdAt }` to list sessions.

### S3 Object Layout
- Uploads: `s3://<uploads-bucket>/<userId>/<documentId>.pdf`
- Reports: `s3://<reports-bucket>/<userId>/<reportId>.md` (and `.html`, optional `.pdf` later)

---

## Security & IAM
- Principle of least privilege: distinct roles for each Lambda and for Step Functions.
- Secrets: store `LLAMAPARSE_API_KEY` in Secrets Manager; fetch at cold start and cache.
- Validations: size/type checks for uploads; only `application/pdf` allowed in v1.
- AuthN/AuthZ: pluggable — start with simple API key or Cognito in front of API Gateway; scope resources by `userId`.
- CloudFront: OAC between CloudFront and S3 for frontend; enforce HTTPS.

### Resource Tagging (Mandatory)
- All AWS resources created for this project must be tagged:
  - key `project_name`, value `scotch-doc-parser`
  - key `developer_name`, value `andresp`
- Apply tags at the CDK App level so all stacks/resources inherit them.
- Example:
```python
# infrastructure/app.py
from aws_cdk import App, Tags

app = App()
Tags.of(app).add("project_name", "scotch-doc-parser")
Tags.of(app).add("developer_name", "andresp")
```
- CDK propagates tags to most resources (S3, Lambda, Step Functions, DynamoDB, API Gateway, CloudFront). For any constructs that do not support tags, add explicit tagging where supported.

---

## CDK Project Structure (Python)
```
infrastructure/
  app.py
  stacks/
    api_stack.py            # API Gateway, Lambdas, Step Functions, DynamoDB, S3
    frontend_stack.py       # S3 static site + CloudFront + domain
lambda/
  start_task.py
  get_result.py
  bedrock_agent.py
  get_presigned_upload.py
  common/
    aws.py                 # clients, helpers
    llama_parse.py         # LlamaParse client wrappers
    models.py              # pydantic/dataclasses for payloads
frontend/
  nextjs-app/              # Next.js app
```

---

## Frontend Notes
- Use a minimalist chat UI with message bubbles, file badges, and a status pill.
- Polling interval: 1–2s backoff to 3–5s on longer runs.
- Show citations under messages when provided by agent tools.
- Provide a "Generate report" CTA that submits a follow-up task for a report.

---

## Observability
- CloudWatch Logs for each Lambda with JSON structured logs.
- X-Ray tracing enabled on API Gateway, Lambdas, Step Functions.
- Emit metrics: task durations, failures, agent tokens, LlamaParse latency.

---

## Testing Strategy
- Unit tests: tool functions (LlamaParse client, S3 helpers, Dynamo access).
- Integration tests: Step Functions execution with mocked Bedrock/LlamaParse.
- E2E smoke: deploy to sandbox; upload → ask → poll → result.

---

## Deployment
### AWS credentials and region
- Use the default AWS CLI profile (`[default]`) and default region from your `~/.aws/config`.
- CDK, API Gateway, Lambda, Step Functions, and boto3 clients will use the default profile/region unless explicitly overridden.
- Quick checklist:
  1) Run `aws configure` and set Access Key ID, Secret Access Key, Default region name (e.g., `us-east-1`), and Default output.
  2) Verify identity: `aws sts get-caller-identity`.
  3) Ensure `~/.aws/config` has a default region and `~/.aws/credentials` has `[default]`.
- Example config files:
```ini
# ~/.aws/config
[default]
region = us-east-1
output = json

# ~/.aws/credentials
[default]
aws_access_key_id = <YOUR_ACCESS_KEY_ID>
aws_secret_access_key = <YOUR_SECRET_ACCESS_KEY>
```
- Optional: for CI/local shells you may export `AWS_PROFILE=default` and `AWS_DEFAULT_REGION=us-east-1`, but this is not required if defaults are set.
- Ensure Secrets Manager (for `LLAMAPARSE_API_KEY`) and Bedrock Agent resources reside in the same default region used by CDK deploys.
1) Bootstrap CDK (`cdk bootstrap`) if first-time account/region.
2) `cdk deploy FrontendStack ApiStack` (two stacks or one, as implemented).
3) Store `LLAMAPARSE_API_KEY` in Secrets Manager before first run.
4) Configure domain for CloudFront distribution (ACM cert in us-east-1).

---

## Milestones
- M0: Project scaffolding (CDK, Lambdas, Next.js skeleton, buckets/tables)
- M1: Upload + parse tool wired; basic Q&A via agent; async API end-to-end
- M2: Report generation (Markdown), download
- M3: Observability + basic auth; polish UX; docs and runbooks

---

## Risks & Mitigations
- Agent latency/timeouts → Async SFN with retries, generous Lambda timeouts.
- Parsing variability → Normalize LlamaParse output, add guardrails in system prompt.
- Cost control → TTL on tasks, size limits, log retention, sampling.

---

## Knowledge Management — Graphiti MCP
- Capture project requirements, architecture decisions, and task-specific patterns as Knowledge Graph entries.
- During implementation: document tool schemas, Step Functions transitions, and error signatures.
- Troubleshooting: record recurring failure modes (timeouts, parse errors) and fixes.
- After features land: note best practices and gotchas (e.g., pagination of large results).
- Entries should be structured with clear titles, detailed bodies, and links to code files, CDK resources, and runbooks for future reuse.

---

## Notes
- Keep the Bedrock Agent system prompt updated as UX issues emerge.
- Consider a chunk store/RAG index in v1.1 if needed for large documents.
- Ensure all secrets (including LlamaParse) are never committed; use Secrets Manager.


