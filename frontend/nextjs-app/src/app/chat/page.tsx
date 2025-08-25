"use client";
import { useState, useEffect } from "react";
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

  return (
    <main style={{ height: 'calc(100vh - 64px)', padding: 0, display: 'grid', gridTemplateRows: 'auto 1fr auto' }}>
      <div style={{ padding: 16, borderBottom: '1px solid #eee', display: 'flex', alignItems: 'center', gap: 12 }}>
        <strong style={{ fontSize: 18 }}>Chat</strong>
        <span style={{ color: '#666' }}>Mode: <strong>{mode}</strong></span>
      </div>
      <div style={{ overflow: 'auto', padding: 16 }}>
        {status && <p style={{ color: '#666' }}>{status}</p>}
        {result && (
          <section>
            <div style={{ marginBottom: 12 }}>
              <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{result.text}</pre>
            </div>
            {Array.isArray(result.sources) && result.sources.length > 0 && (
              <details open>
                <summary style={{ cursor: 'pointer' }}>Sources</summary>
                <ul style={{ marginTop: 8 }}>
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
              <details style={{ marginTop: 12 }}>
                <summary style={{ cursor: 'pointer' }}>Excerpt</summary>
                <pre style={{ whiteSpace: 'pre-wrap' }}>{result.report.content}</pre>
              </details>
            )}
          </section>
        )}
      </div>
      <form onSubmit={handleAsk} style={{ padding: 12, borderTop: '1px solid #eee', display: 'flex', alignItems: 'center', gap: 8 }}>
        <button type="button" title="Upload" onClick={() => window.location.href = '/upload'} style={{ border: '1px solid #ddd', borderRadius: 8, width: 36, height: 36 }}>+</button>
        <input
          value={documentIds}
          onChange={e => setDocumentIds(e.target.value)}
          placeholder="documentId(s) (optional)"
          style={{ width: 240, padding: '8px 10px', border: '1px solid #ddd', borderRadius: 8 }}
        />
        <textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          placeholder="Ask anything…"
          rows={1}
          style={{ flex: 1, resize: 'vertical', maxHeight: 180, padding: '10px 12px', border: '1px solid #ddd', borderRadius: 8 }}
        />
        <button type="submit" disabled={!prompt} style={{ padding: '10px 14px' }}>Send</button>
      </form>
    </main>
  );
}
