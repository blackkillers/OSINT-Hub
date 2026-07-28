import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'OSINT-Hub | Sovereign Intelligence Platform',
  description: 'Sovereign, self-hosted OSINT investigation platform with AI-powered graph visualization',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="bg-brand-darker min-h-screen antialiased">
        {children}
      </body>
    </html>
  )
}
