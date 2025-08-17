export default function HomePage() {
  return (
    <main style={{ padding: 24 }}>
      <h1>Scotch Doc-Chat</h1>
      <p>Upload PDFs and chat with an AI.</p>
      <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
        <a href="/upload"><button style={{ padding: '8px 12px' }}>Go to Upload</button></a>
        <a href="/chat"><button style={{ padding: '8px 12px' }}>Go to Chat</button></a>
        <a href="/agent"><button style={{ padding: '8px 12px' }}>Agent Console</button></a>
      </div>
    </main>
  );
}
