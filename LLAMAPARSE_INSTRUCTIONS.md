### LlamaParse Parsing API — End-to-End Flow (with placeholders)

This guide shows how to parse an Excel (XLSX) or PDF using LlamaParse (Parsing API), retrieve job status, details, and results.

References:
- Supported file extensions (Parsing API): https://docs.cloud.llamaindex.ai/API/get-supported-file-extensions-api-v-1-parsing-supported-file-extensions-get
- Upload File (Parsing API): https://docs.cloud.llamaindex.ai/API/upload-file-api-v-1-parsing-upload-post

---

## Prerequisites
- Replace placeholders before running:
  - `<LLAMA_CLOUD_API_KEY>`: your Llama Cloud API token
  - `<WINDOWS_FILE_PATH>`: e.g., `C:\\Users\\<you>\\Desktop\\file.xlsx`
  - `<WSL_FILE_PATH>`: e.g., `/mnt/c/Users/<you>/Desktop/file.xlsx` (when running from WSL)
  - `<JOB_ID>`: job id returned by upload

Optional: Export your token as an environment variable to avoid repeating it:
```bash
export LLAMA_CLOUD_API_KEY='<LLAMA_CLOUD_API_KEY>'
```

---

## 1) Choose the correct file path style

- If running from Windows PowerShell or CMD, use `<WINDOWS_FILE_PATH>`.
- If running from WSL (Ubuntu on Windows), map the drive to `/mnt/*` and use `<WSL_FILE_PATH>`.
  - Example mapping: `C:\\Users\\...` → `/mnt/c/Users/...`

Quick file existence check (WSL):
```bash
ls -l '<WSL_FILE_PATH>'
```

---

## 2) Upload the file (Parsing API)

WSL/Linux/macOS:
```bash
curl -L -X POST 'https://api.cloud.llamaindex.ai/api/v1/parsing/upload' \
  -H 'Accept: application/json' \
  -H "Authorization: Bearer $LLAMA_CLOUD_API_KEY" \
  -F 'file=@<WSL_FILE_PATH>;type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
```

Windows PowerShell (xlsx):
```powershell
curl.exe -L -X POST 'https://api.cloud.llamaindex.ai/api/v1/parsing/upload' `
  -H 'Accept: application/json' `
  -H "Authorization: Bearer $env:LLAMA_CLOUD_API_KEY" `
  -F "file=@<WINDOWS_FILE_PATH>;type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
```

Note: For PDF, change the part after `type=` to `application/pdf`.

The response includes a job id:
```json
{ "id": "<JOB_ID>", "status": "PENDING" }
```

---

## 3) Check job status

```bash
curl -L "https://api.cloud.llamaindex.ai/api/v1/parsing/job/<JOB_ID>" \
  -H 'Accept: application/json' \
  -H "Authorization: Bearer $LLAMA_CLOUD_API_KEY"
```

Expected successful response:
```json
{ "id": "<JOB_ID>", "status": "SUCCESS" }
```

---

## 4) Get job details (optional)

```bash
curl -L "https://api.cloud.llamaindex.ai/api/v1/parsing/job/<JOB_ID>/details" \
  -H 'Accept: application/json' \
  -H "Authorization: Bearer $LLAMA_CLOUD_API_KEY"
```

Details include parameters, S3 keys, and parsing options for auditing/debugging.

---

## 5) Get text result

```bash
curl -L "https://api.cloud.llamaindex.ai/api/v1/parsing/job/<JOB_ID>/result/text" \
  -H 'Accept: application/json' \
  -H "Authorization: Bearer $LLAMA_CLOUD_API_KEY"
```

This returns `{ "text": "..." }` with the extracted text.

---

## 6) Get JSON result

```bash
curl -L "https://api.cloud.llamaindex.ai/api/v1/parsing/job/<JOB_ID>/result/json" \
  -H 'Accept: application/json' \
  -H "Authorization: Bearer $LLAMA_CLOUD_API_KEY"
```

The JSON result often includes a `pages[].items[]` array with detected `table` items that contain `rows` and helper formats (`md`, `csv`).

---

## 7) (Optional) Map table rows into your schema

Example mapping of a 5-column sales table into a schema:
```json
{
  "products": [
    { "product_name": "...", "category": "...", "sales_q1_2025": 0, "sales_q2_2025": 0, "total_sales_ytd": 0 }
  ]
}
```

Implementation tip: select the first table in `pages[0].items` and use header row to index columns.


