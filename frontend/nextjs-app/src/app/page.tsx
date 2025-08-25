export default function HomePage() {
  return (
    <main className="py-10">
      <h1 className="text-3xl font-semibold">Scotch Doc-Chat</h1>
      <p className="text-neutral-600 mt-2">Upload PDFs and chat with an AI.</p>
      <div className="flex gap-3 mt-6">
        <a href="/upload" className="px-4 py-2 rounded-xl border border-neutral-300 hover:bg-white/60">Go to Upload</a>
        <a href="/chat" className="px-4 py-2 rounded-xl border border-neutral-300 hover:bg-white/60">Go to Chat</a>
        <a href="/agent" className="px-4 py-2 rounded-xl border border-neutral-300 hover:bg-white/60">Agent Console</a>
      </div>
    </main>
  );
}
