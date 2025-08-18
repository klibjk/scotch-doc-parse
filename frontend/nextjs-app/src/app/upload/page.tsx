"use client";
import { useState } from "react";
import { API_BASE } from "@/lib/config";

export default function UploadPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [status, setStatus] = useState<string>("");
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const [jumpUrl, setJumpUrl] = useState<string | null>(null);

  async function requestUpload(file: File) {
    setStatus("Requesting presigned URL…");
    const res = await fetch(`${API_BASE}/upload-request`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, contentType: file.type || "application/pdf", userId: "demo" }),
    });
    if (!res.ok) throw new Error("Failed to get presigned URL");
    return res.json();
  }

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!files.length) return;
    try {
      setStatus("Requesting presigned URLs…");
      const uploaded: string[] = [];
      // Upload in sequence to keep UI simple; could parallelize with Promise.allSettled
      for (const f of files) {
        const { uploadUrl, documentId, headers } = await requestUpload(f);
        setStatus(`Uploading ${f.name}…`);
        const put = await fetch(uploadUrl, { method: "PUT", headers: { "Content-Type": f.type || "application/pdf", ...(headers || {}) }, body: f });
        if (!put.ok) throw new Error(`Upload failed for ${f.name}`);
        uploaded.push(documentId);
      }
      setDocumentIds(uploaded);
      setJumpUrl(`/chat?docs=${encodeURIComponent(uploaded.join(","))}`);
      setStatus("Uploaded ✓ — Ready to chat.");
    } catch (err: any) {
      setStatus(err.message || "Error");
    }
  }

  return (
    <main style={{ padding: 24 }}>
      <h2>Upload Documents (PDF/XLSX)</h2>
      <form onSubmit={handleUpload} style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <input
          type="file"
          multiple
          accept="application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={(e) => setFiles(Array.from(e.target.files || []))}
        />
        <button type="submit" disabled={!files.length} style={{ padding: '8px 12px' }}>Upload Files</button>
      </form>
      <p>{status}</p>
      {documentIds.length > 0 && (
        <div>
          <p>documentIds:</p>
          <ul>
            {documentIds.map((id) => (<li key={id}><code>{id}</code></li>))}
          </ul>
          {jumpUrl && <a href={jumpUrl}><button style={{ padding: '8px 12px' }}>Go to Chat with these documents</button></a>}
        </div>
      )}
    </main>
  );
}
