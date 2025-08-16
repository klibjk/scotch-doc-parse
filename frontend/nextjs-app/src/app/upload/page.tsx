"use client";
import { useState } from "react";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string>("");
  const [documentId, setDocumentId] = useState<string | null>(null);

  async function requestUpload(file: File) {
    setStatus("Requesting presigned URL…");
    const res = await fetch(`${API_BASE.replace(/\/$/, '')}/upload-request`, {
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
      setStatus("Uploaded ✓");
    } catch (err: any) {
      setStatus(err.message || "Error");
    }
  }

  return (
    <main style={{ padding: 24 }}>
      <h2>Upload PDF</h2>
      <form onSubmit={handleUpload}>
        <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        <button type="submit" disabled={!file}>Upload</button>
      </form>
      <p>{status}</p>
      {documentId && <p>documentId: <code>{documentId}</code></p>}
    </main>
  );
}
