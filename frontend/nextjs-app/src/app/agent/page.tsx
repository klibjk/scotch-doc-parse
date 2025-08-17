"use client";
import { useState } from "react";
import { API_BASE } from "@/lib/config";

export default function AgentConsolePage() {
  const [prompt, setPrompt] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [status, setStatus] = useState("");
  const [answer, setAnswer] = useState("");

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    setStatus("Asking agent…");
    setAnswer("");
    try {
      const res = await fetch(`${API_BASE}/agent-chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, sessionId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || "Agent error");
      setSessionId(data.sessionId || "");
      setAnswer(data.text || "");
      setStatus("Done");
    } catch (err: any) {
      setStatus(err.message || "Error");
    }
  }

  return (
    <main style={{ padding: 24 }}>
      <h2>Bedrock Agent Console</h2>
      <form onSubmit={handleAsk}>
        <textarea value={prompt} onChange={e=>setPrompt(e.target.value)} rows={5} cols={80} placeholder="Ask the agent…" />
        <br />
        <input value={sessionId} onChange={e=>setSessionId(e.target.value)} placeholder="sessionId (optional)" />
        <br />
        <button type="submit" disabled={!prompt}>Send</button>
      </form>
      <p>{status}</p>
      {answer && (
        <section>
          <h3>Answer</h3>
          <pre style={{whiteSpace:'pre-wrap'}}>{answer}</pre>
        </section>
      )}
    </main>
  );
}
