'use client'

import { useState } from 'react'
import Dashboard from '@/components/Dashboard'
import InvestigationView from '@/components/InvestigationView'

export default function Home() {
  const [activeScanId, setActiveScanId] = useState<string | null>(null)
  const [activeTarget, setActiveTarget] = useState<string>('')

  return (
    <main className="min-h-screen bg-cyber-grid" style={{ backgroundColor: '#0a0e1a' }}>
      {!activeScanId ? (
        <Dashboard
          onScanStart={(scanId, target) => {
            setActiveScanId(scanId)
            setActiveTarget(target)
          }}
        />
      ) : (
        <InvestigationView
          scanId={activeScanId}
          target={activeTarget}
          onBack={() => {
            setActiveScanId(null)
            setActiveTarget('')
          }}
        />
      )}
    </main>
  )
}
