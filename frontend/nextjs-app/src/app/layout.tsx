export const metadata = {
  title: 'Scotch Doc-Chat',
  description: 'Upload PDFs and chat with AI',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0 }}>{children}</body>
    </html>
  );
}
