export const metadata = {
  title: 'Scotch Doc-Chat',
  description: 'Upload PDFs and chat with AI',
};

import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head />
      <body className="bg-surface text-ink font-ui">
        <header className="sticky top-0 z-40 bg-surface/95 backdrop-blur border-b border-neutral-200">
          <div className="mx-auto max-w-5xl px-4 py-3 flex items-center gap-6">
            <strong className="text-lg">Scotch Doc-Chat</strong>
            <nav className="flex items-center gap-4 text-sm">
              <a className="hover:underline" href="/">Home</a>
              <a className="hover:underline" href="/upload">Upload</a>
              <a className="hover:underline" href="/chat">Chat</a>
              <a className="hover:underline" href="/chat-basic">Chat (Baseline)</a>
            </nav>
          </div>
        </header>
        <div className="mx-auto max-w-5xl px-4">
          {children}
        </div>
      </body>
    </html>
  );
}
