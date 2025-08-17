"use client";
import { useState } from "react";
import { API_BASE } from "@/lib/config";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string>("");
  const [documentId, setDocumentId] = useState<string | null>(null);
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
    if (!file) return;
    try {
      const { uploadUrl, documentId } = await requestUpload(file);
      setStatus("Uploading to S3…");
      const put = await fetch(uploadUrl, { method: "PUT", headers: { "Content-Type": file.type || "application/pdf" }, body: file });
      if (!put.ok) throw new Error("Upload failed");
      setDocumentId(documentId);
      setJumpUrl(`/chat?doc=${encodeURIComponent(documentId)}`);
      setStatus("Uploaded ✓ — Ready to chat.");
    } catch (err: any) {
      setStatus(err.message || "Error");
    }
  }

  return (
    <main style={{ padding: 24 }}>
      <h2>Upload PDF</h2>
      <form onSubmit={handleUpload} style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        <button type="submit" disabled={!file} style={{ padding: '8px 12px' }}>Upload</button>
      </form>
      <p>{status}</p>
      {documentId && (
        <div>
          <p>documentId: <code>{documentId}</code></p>
          {jumpUrl && <a href={jumpUrl}><button style={{ padding: '8px 12px' }}>Go to Chat with this document</button></a>}
        </div>
      )}
    </main>
  );
}
