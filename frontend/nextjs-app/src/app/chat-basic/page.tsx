export default function ChatBasicPage() {
  return (
    <main style={{ padding: 24 }}>
      <h2>Chat (Baseline)</h2>
      <p>Use the main Chat for retrieval; this page bypasses vector DB and uses normalized parsing only.</p>
      <iframe src="/chat?mode=baseline" style={{ width: '100%', height: 600, border: '1px solid #ddd' }} />
    </main>
  );
}
