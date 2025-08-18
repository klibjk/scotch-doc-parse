"use client";
import { useState, useEffect } from "react";
import { API_BASE } from "@/lib/config";

async function startTask(prompt: string, documentIds: string[]) {
  const res = await fetch(`${API_BASE}/agent-task`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, documentIds, userId: "demo" })
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

  // Support /chat?doc=... to prefill the documentId
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const docs = params.get('docs') || params.get('doc');
    if (docs) setDocumentIds(docs);
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
      const { taskId } = await startTask(prompt, ids);
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
    <main style={{ padding: 24 }}>
      <h2>Chat</h2>
      <form onSubmit={handleAsk}>
        <input value={documentIds} onChange={e=>setDocumentIds(e.target.value)} placeholder="documentId(s) comma-separated (optional)" />
        <br />
        <textarea value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="Ask something about your document…" rows={4} cols={60} />
        <br />
        <button type="submit" disabled={!prompt}>Ask</button>
      </form>
      <p>{status}</p>
      {result && (
        <section>
          <h3>Answer</h3>
          <pre style={{whiteSpace:'pre-wrap'}}>{result.text}</pre>
          {Array.isArray(result.sources) && result.sources.length > 0 && (
            <div>
              <h4>Sources</h4>
              <ul>
                {result.sources.map((s:any, i:number) => (
                  <li key={i}>doc {s.documentId}, pages: {Array.isArray(s.pages) ? s.pages.join(',') : ''}</li>
                ))}
              </ul>
            </div>
          )}
          {result.report?.content && (
            <div>
              <h4>Report (Markdown)</h4>
              <pre style={{whiteSpace:'pre-wrap'}}>{result.report.content}</pre>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
