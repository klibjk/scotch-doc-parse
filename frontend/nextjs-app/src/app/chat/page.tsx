"use client";
import { useState, useEffect, useRef } from "react";
import { API_BASE } from "@/lib/config";

async function startTask(prompt: string, documentIds: string[], mode: 'retrieval' | 'baseline') {
  const res = await fetch(`${API_BASE}/agent-task`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, documentIds, userId: "demo", mode })
  });
  if (!res.ok) throw new Error("Failed to start task");
  return res.json();
}

async function pollTask(taskId: string) {
  const res = await fetch(`${API_BASE}/agent-task?taskId=${encodeURIComponent(taskId)}`);
  if (!res.ok) throw new Error("Failed to get task");
  return res.json();
}

export default function ChatPage() {
  const [prompt, setPrompt] = useState("");
  const [documentIds, setDocumentIds] = useState<string>("");
  const [status, setStatus] = useState("");
  const [result, setResult] = useState<any>(null);
  const [mode, setMode] = useState<'retrieval' | 'baseline'>('retrieval');
  const textRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Support /chat?doc=... and /chat?mode=baseline
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const docs = params.get('docs') || params.get('doc');
    if (docs) setDocumentIds(docs);
    const m = (params.get('mode') || '').toLowerCase();
    if (m === 'baseline') setMode('baseline');
  }, []);

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    setStatus("Starting task…");
    setResult(null);
    try {
      const ids = documentIds
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const { taskId } = await startTask(prompt, ids, mode);
      setStatus("Polling…");
      let tries = 0;
      while (tries < 60) {
        const data = await pollTask(taskId);
        if (data.status === "COMPLETED") {
          setResult(data.result ? JSON.parse(data.result) : null);
          setStatus("Done");
          break;
        }
        if (data.status === "FAILED") {
          setStatus("Failed");
          break;
        }
        await new Promise(r => setTimeout(r, Math.min(1000 + tries * 250, 5000)));
        tries += 1;
      }
    } catch (e: any) {
      setStatus(e.message || "Error");
    }
  }

  // Auto-resize the textarea up to a max height, then allow scrolling
  function autoResizeTextArea(el: HTMLTextAreaElement) {
    const max = 220; // px
    el.style.height = 'auto';
    const next = Math.min(max, el.scrollHeight);
    el.style.height = `${next}px`;
  }

  // Upload helpers (mirror /upload page behavior)
  async function requestUpload(file: File) {
    const res = await fetch(`${API_BASE}/upload-request`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, contentType: file.type || "application/pdf", userId: "demo" }),
    });
    if (!res.ok) throw new Error("Failed to get presigned URL");
    return res.json();
  }

  async function handleChooseFilesClick() {
    fileInputRef.current?.click();
  }

  async function handleFilesSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    try {
      setStatus("Uploading…");
      const uploaded: string[] = [];
      for (const f of files) {
        const { uploadUrl, documentId, headers } = await requestUpload(f);
        const put = await fetch(uploadUrl, {
          method: "PUT",
          headers: { "Content-Type": f.type || "application/pdf", ...(headers || {}) },
          body: f,
        });
        if (!put.ok) throw new Error(`Upload failed for ${f.name}`);
        uploaded.push(documentId);
      }
      // Merge new IDs with any existing ones in the field
      const existing = documentIds
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const merged = [...existing, ...uploaded];
      setDocumentIds(merged.join(','));
      setStatus("Uploaded ✓");
    } catch (err: any) {
      setStatus(err.message || "Upload error");
    } finally {
      // reset input so selecting the same file again still triggers change
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  return (
    <main className="h-[calc(100vh-64px)] grid grid-rows-[auto,1fr,auto]">
      <div className="px-4 py-3 border-b border-neutral-200 flex items-center gap-3">
        <strong className="text-lg">Chat</strong>
        <span className="text-neutral-600">Mode: <strong>{mode}</strong></span>
      </div>
      <div className="overflow-auto p-4">
        {status && <p className="text-neutral-600">{status}</p>}
        {result && (
          <section>
            <div className="mb-3">
              <pre className="whitespace-pre-wrap m-0">{result.text}</pre>
            </div>
            {Array.isArray(result.sources) && result.sources.length > 0 && (
              <details open>
                <summary className="cursor-pointer">Sources</summary>
                <ul className="mt-2 list-disc pl-5">
                  {result.sources.map((s: any, i: number) => (
                    <li key={i}>
                      {s.filename || `doc ${s.documentId}`}
                      {Array.isArray(s.sheets) && s.sheets.length ? ` · sheets: ${s.sheets.join(',')}` : ''}
                      {Array.isArray(s.rows) && s.rows.length ? ` · rows: ${s.rows.join(',')}` : ''}
                      {Array.isArray(s.pages) && s.pages.length ? ` · pages: ${s.pages.join(',')}` : ''}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            {result.report?.content && (
              <details className="mt-3">
                <summary className="cursor-pointer">Excerpt</summary>
                <pre className="whitespace-pre-wrap">{result.report.content}</pre>
              </details>
            )}
          </section>
        )}
      </div>
      <form onSubmit={handleAsk} className="p-3 border-t border-neutral-200 flex items-end gap-2 bg-surface">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          accept="application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={handleFilesSelected}
        />
        <button type="button" title="Upload" onClick={handleChooseFilesClick} className="w-9 h-9 rounded-xl border border-neutral-300 hover:bg-white/60">+</button>
        <input
          value={documentIds}
          onChange={e => setDocumentIds(e.target.value)}
          placeholder="documentId(s) (optional)"
          className="w-60 px-2.5 py-2 rounded-xl border border-neutral-300"
        />
        <textarea
          value={prompt}
          ref={textRef}
          onChange={e => {
            setPrompt(e.target.value);
            autoResizeTextArea(e.target);
          }}
          placeholder="Ask anything…"
          rows={1}
          className="flex-1 resize-none max-h-56 overflow-y-auto px-3 py-2 rounded-xl border border-neutral-300"
        />
        <button type="submit" disabled={!prompt} className="px-3 py-2 rounded-xl border border-neutral-300 hover:bg-white/60 disabled:opacity-50">Send</button>
      </form>
    </main>
  );
}
