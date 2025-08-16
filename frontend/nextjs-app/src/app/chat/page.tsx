"use client";
import { useState } from "react";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

async function startTask(prompt: string, documentIds: string[]) {
  const res = await fetch(`${API_BASE.replace(/\/$/, '')}/agent-task`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, documentIds, userId: "demo" })
  });
  if (!res.ok) throw new Error("Failed to start task");
  return res.json();
}

async function pollTask(taskId: string) {
  const res = await fetch(`${API_BASE.replace(/\/$/, '')}/agent-task?taskId=${encodeURIComponent(taskId)}`);
  if (!res.ok) throw new Error("Failed to get task");
  return res.json();
}

export default function ChatPage() {
  const [prompt, setPrompt] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [status, setStatus] = useState("");
  const [result, setResult] = useState<any>(null);

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    setStatus("Starting task…");
    setResult(null);
    try {
      const { taskId } = await startTask(prompt, documentId ? [documentId] : []);
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
        <input value={documentId} onChange={e=>setDocumentId(e.target.value)} placeholder="documentId (optional)" />
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
        </section>
      )}
    </main>
  );
}
