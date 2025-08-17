export const metadata = {
  title: 'Scotch Doc-Chat',
  description: 'Upload PDFs and chat with AI',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'system-ui' }}>
        <header style={{
          display: 'flex', alignItems: 'center', gap: 16,
          padding: '12px 16px', borderBottom: '1px solid #eee', position: 'sticky', top: 0, background: '#fff'
        }}>
          <strong>Scotch Doc-Chat</strong>
          <nav style={{ display: 'flex', gap: 12 }}>
            <a href="/" style={{ textDecoration: 'none' }}>Home</a>
            <a href="/upload" style={{ textDecoration: 'none' }}>Upload</a>
            <a href="/chat" style={{ textDecoration: 'none' }}>Chat</a>
          </nav>
        </header>
        <div style={{ maxWidth: 900, margin: '0 auto' }}>
          {children}
        </div>
      </body>
    </html>
  );
}
