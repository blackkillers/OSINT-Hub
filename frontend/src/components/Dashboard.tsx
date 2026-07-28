'use client'

import { useState } from 'react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const TARGET_TYPES = [
  { value: 'email', label: 'Email', icon: '📧', placeholder: 'target@example.com', color: '#00d4ff' },
  { value: 'username', label: 'Username', icon: '👤', placeholder: 'john_doe', color: '#a78bfa' },
  { value: 'phone', label: 'Phone', icon: '📞', placeholder: '+33612345678', color: '#34d399' },
  { value: 'ip', label: 'IP Address', icon: '🌐', placeholder: '8.8.8.8', color: '#ef4444' },
  { value: 'domain', label: 'Domain', icon: '🔗', placeholder: 'example.com', color: '#f59e0b' },
]

const RECENT_SCANS = [
  { id: '1', target: 'john.doe@example.com', type: 'email', status: 'success', time: '2 min ago', nodes: 14 },
  { id: '2', target: 'johndoe92', type: 'username', status: 'success', time: '1h ago', nodes: 27 },
  { id: '3', target: '8.8.8.8', type: 'ip', status: 'success', time: '3h ago', nodes: 8 },
]

const STATS = [
  { label: 'Total Scans', value: '247', icon: '🔍', color: '#00d4ff' },
  { label: 'Nodes Mapped', value: '4,821', icon: '🔮', color: '#a78bfa' },
  { label: 'Active Modules', value: '14', icon: '⚡', color: '#00ff88' },
  { label: 'Tor Circuits', value: '3', icon: '🧅', color: '#f59e0b' },
]

interface DashboardProps {
  onScanStart: (scanId: string, target: string) => void
}

export default function Dashboard({ onScanStart }: DashboardProps) {
  const [target, setTarget] = useState('')
  const [targetType, setTargetType] = useState('email')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const selectedType = TARGET_TYPES.find(t => t.value === targetType)!

  const handleScan = async () => {
    if (!target.trim()) return
    setIsLoading(true)
    setError('')

    try {
      const res = await fetch(`${API_URL}/api/v1/scans`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target: target.trim(),
          target_type: targetType,
          selected_modules: ['all'],
        }),
      })

      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'API request failed')
      }

      const data = await res.json()
      onScanStart(data.scan_id, target.trim())
    } catch (err: any) {
      setError(err.message || 'Failed to connect to OSINT-Hub API. Ensure the backend is running.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Navbar */}
      <nav className="border-b border-brand-border bg-brand-surface bg-opacity-80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #00d4ff, #00ff88)' }}>
              <span className="text-black font-black text-sm">O</span>
            </div>
            <span className="font-black text-xl tracking-tight" style={{ background: 'linear-gradient(90deg, #00d4ff, #00ff88)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              OSINT-Hub
            </span>
            <span className="terminal-text opacity-60 text-xs hidden md:block">// Sovereign Intelligence Platform</span>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-green-400 status-running"></div>
              <span className="text-xs text-brand-muted font-mono">System Online</span>
            </div>
            <a
              href="https://buymeacoffee.com/studioengine"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs px-3 py-1.5 rounded-lg border border-yellow-500 border-opacity-50 text-yellow-400 hover:bg-yellow-500 hover:bg-opacity-10 transition-all font-medium"
            >
              ☕ Support
            </a>
          </div>
        </div>
      </nav>

      <div className="flex-1 max-w-7xl mx-auto px-6 py-12 w-full">
        {/* Hero */}
        <div className="text-center mb-16">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full border mb-6 text-xs font-mono" style={{ borderColor: '#00d4ff33', background: '#00d4ff0a', color: '#00d4ff' }}>
            <span className="w-2 h-2 rounded-full bg-cyan-400 status-running inline-block"></span>
            Zero Trust · 100% Local AI · Tor Anonymization Active
          </div>
          <h1 className="text-5xl md:text-6xl font-black mb-4 leading-tight">
            <span style={{ background: 'linear-gradient(135deg, #00d4ff 0%, #00ff88 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              OSINT Investigation
            </span>
            <br />
            <span className="text-white">Platform</span>
          </h1>
          <p className="text-brand-muted text-lg max-w-2xl mx-auto">
            Sovereign intelligence gathering across email, username, phone, IP & domain targets.
            Powered by 15+ CLI tools, AI correlation, and interactive graph visualization.
          </p>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-12">
          {STATS.map((stat) => (
            <div key={stat.label} className="module-card rounded-xl p-4" style={{ background: '#0f1629' }}>
              <div className="text-2xl mb-1">{stat.icon}</div>
              <div className="text-2xl font-black" style={{ color: stat.color }}>{stat.value}</div>
              <div className="text-xs text-brand-muted mt-1">{stat.label}</div>
            </div>
          ))}
        </div>

        {/* Main Scan Form */}
        <div className="max-w-3xl mx-auto mb-12">
          <div className="rounded-2xl p-8 border" style={{ background: '#0f1629', borderColor: '#1e2d4a' }}>
            <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
              <span style={{ color: '#00d4ff' }}>⬡</span>
              New Investigation
            </h2>

            {/* Target Type Selector */}
            <div className="flex flex-wrap gap-2 mb-6">
              {TARGET_TYPES.map((type) => (
                <button
                  key={type.value}
                  onClick={() => setTargetType(type.value)}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all border"
                  style={{
                    borderColor: targetType === type.value ? type.color : '#1e2d4a',
                    background: targetType === type.value ? `${type.color}15` : 'transparent',
                    color: targetType === type.value ? type.color : '#8892a4',
                  }}
                >
                  <span>{type.icon}</span>
                  {type.label}
                </button>
              ))}
            </div>

            {/* Input */}
            <div className="flex gap-3">
              <div className="flex-1 relative">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-lg">{selectedType.icon}</span>
                <input
                  type="text"
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleScan()}
                  placeholder={selectedType.placeholder}
                  className="w-full pl-12 pr-4 py-4 rounded-xl border text-white placeholder-brand-muted font-mono text-sm outline-none transition-all focus:border-cyan-500"
                  style={{ background: '#060a14', borderColor: '#1e2d4a' }}
                />
              </div>
              <button
                onClick={handleScan}
                disabled={isLoading || !target.trim()}
                className="px-8 py-4 rounded-xl font-bold text-black transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                style={{
                  background: isLoading ? '#1e2d4a' : 'linear-gradient(135deg, #00d4ff, #00ff88)',
                  color: isLoading ? '#8892a4' : '#0a0e1a',
                }}
              >
                {isLoading ? (
                  <>
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Scanning...
                  </>
                ) : (
                  <>🔍 Investigate</>
                )}
              </button>
            </div>

            {error && (
              <div className="mt-4 p-4 rounded-lg border border-red-500 border-opacity-30 bg-red-500 bg-opacity-10 text-red-400 text-sm font-mono">
                ⚠ {error}
              </div>
            )}
          </div>
        </div>

        {/* Recent Scans */}
        <div className="max-w-3xl mx-auto">
          <h3 className="text-sm font-semibold text-brand-muted uppercase tracking-wider mb-4 font-mono">Recent Investigations</h3>
          <div className="space-y-3">
            {RECENT_SCANS.map((scan) => (
              <div key={scan.id} className="module-card rounded-xl p-4 flex items-center justify-between cursor-pointer" style={{ background: '#0f1629' }}>
                <div className="flex items-center gap-3">
                  <span>{TARGET_TYPES.find(t => t.value === scan.type)?.icon}</span>
                  <div>
                    <div className="font-mono text-sm text-white">{scan.target}</div>
                    <div className="text-xs text-brand-muted">{scan.time}</div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono" style={{ color: '#00ff88' }}>{scan.nodes} nodes</span>
                  <span className="w-2 h-2 rounded-full bg-green-400"></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-brand-border py-6 mt-12">
        <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="text-xs text-brand-muted font-mono">
            OSINT-Hub v1.0.0 · MIT License · Zero Trust · All data stays on your server
          </div>
          <a
            href="https://buymeacoffee.com/studioengine"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-yellow-400 hover:text-yellow-300 transition-colors font-medium"
          >
            ☕ Buy Me a Coffee · Support Open Source OSINT
          </a>
        </div>
      </footer>
    </div>
  )
}
