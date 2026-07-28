'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  ConnectionMode,
  Node,
  Edge,
} from 'reactflow'
import 'reactflow/dist/style.css'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const WS_URL = (process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000').replace(/^http/, 'ws')

const NODE_COLORS: Record<string, string> = {
  email: '#00d4ff',
  person: '#00ff88',
  social_account: '#a78bfa',
  phone: '#34d399',
  domain: '#f59e0b',
  ip: '#ef4444',
  leak: '#f97316',
  location: '#ec4899',
  other: '#8892a4',
}

function buildFlowNode(n: any, index: number): Node {
  const color = NODE_COLORS[n.type] || '#8892a4'
  return {
    id: n.id,
    type: 'default',
    position: {
      x: 400 + Math.cos((index / 10) * 2 * Math.PI) * (150 + index * 30),
      y: 300 + Math.sin((index / 10) * 2 * Math.PI) * (150 + index * 30),
    },
    data: { label: n.label, nodeType: n.type },
    style: {
      background: `${color}15`,
      border: `1.5px solid ${color}`,
      borderRadius: '10px',
      color: color,
      fontSize: '11px',
      fontFamily: 'JetBrains Mono, monospace',
      fontWeight: '600',
      padding: '8px 14px',
      minWidth: '100px',
      textAlign: 'center',
      boxShadow: `0 0 10px ${color}33`,
    },
  }
}

function buildFlowEdge(e: any): Edge {
  return {
    id: `${e.source}-${e.target}-${e.relation}`,
    source: e.source,
    target: e.target,
    label: e.relation,
    labelStyle: { fill: '#8892a4', fontSize: 9, fontFamily: 'JetBrains Mono, monospace' },
    style: { stroke: '#1e2d4a', strokeWidth: 1.5 },
    animated: true,
  }
}

interface ScanResult {
  module_name: string
  status: string
  execution_time_ms: number
  nodes: any[]
  edges: any[]
  error?: string
}

interface InvestigationViewProps {
  scanId: string
  target: string
  onBack: () => void
}

export default function InvestigationView({ scanId, target, onBack }: InvestigationViewProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [moduleResults, setModuleResults] = useState<ScanResult[]>([])
  const [overallStatus, setOverallStatus] = useState('running')
  const [aiSummary, setAiSummary] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<any>(null)
  const [activeTab, setActiveTab] = useState<'graph' | 'modules' | 'ai'>('graph')
  const wsRef = useRef<WebSocket | null>(null)
  const pollRef = useRef<any>(null)

  const fetchResults = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/scans/${scanId}`)
      if (!res.ok) return
      const data = await res.json()

      setOverallStatus(data.overall_status)
      setModuleResults(data.module_results || [])
      if (data.ai_summary) setAiSummary(data.ai_summary)

      // Build flow nodes from all module results
      const allNodes: any[] = data.nodes || []
      const allEdges: any[] = data.edges || []

      const flowNodes = allNodes.map((n: any, i: number) => buildFlowNode(n, i))
      const flowEdges = allEdges.map((e: any) => buildFlowEdge(e))

      setNodes(flowNodes)
      setEdges(flowEdges)

      if (data.overall_status !== 'running' && data.overall_status !== 'pending') {
        clearInterval(pollRef.current)
      }
    } catch (_) {}
  }, [scanId, setNodes, setEdges])

  useEffect(() => {
    // Initial fetch
    fetchResults()

    // Poll every 3 seconds
    pollRef.current = setInterval(fetchResults, 3000)

    // WebSocket for real-time updates
    try {
      const wsUrl = `${WS_URL}/api/v1/ws/scans/${scanId}`
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws
      ws.onmessage = () => fetchResults()
      ws.onerror = () => {} // Silent fallback to polling
    } catch (_) {}

    return () => {
      clearInterval(pollRef.current)
      wsRef.current?.close()
    }
  }, [fetchResults])

  const onConnect = useCallback((params: any) => {
    setEdges((eds) => addEdge(params, eds))
  }, [setEdges])

  const statusConfig: Record<string, { color: string; label: string; pulse: boolean }> = {
    running: { color: '#00d4ff', label: '⟳ Scanning...', pulse: true },
    pending: { color: '#f59e0b', label: '⏳ Pending', pulse: true },
    success: { color: '#00ff88', label: '✓ Complete', pulse: false },
    failed: { color: '#ef4444', label: '✗ Failed', pulse: false },
    partial: { color: '#f59e0b', label: '⚠ Partial', pulse: false },
  }

  const status = statusConfig[overallStatus] || statusConfig.pending
  const completedModules = moduleResults.filter(m => m.status !== 'running' && m.status !== 'pending').length
  const totalNodes = nodes.length

  return (
    <div className="h-screen flex flex-col" style={{ background: '#0a0e1a' }}>
      {/* Header */}
      <nav className="border-b border-brand-border px-6 py-3 flex items-center justify-between" style={{ background: '#0f1629' }}>
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="text-brand-muted hover:text-white transition-colors text-sm flex items-center gap-2">
            ← Back
          </button>
          <div className="h-4 w-px bg-brand-border"></div>
          <div>
            <span className="font-mono text-sm text-white">{target}</span>
            <span className="text-xs text-brand-muted ml-2">· {scanId.slice(0, 8)}...</span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs font-mono" style={{ color: '#00d4ff' }}>{totalNodes} nodes</span>
          <div className="flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono" style={{ background: `${status.color}15`, color: status.color }}>
            <span className={`w-2 h-2 rounded-full inline-block`} style={{ background: status.color, animation: status.pulse ? 'status-pulse 1.5s ease-in-out infinite' : 'none' }}></span>
            {status.label}
          </div>
        </div>
      </nav>

      {/* Tab Bar */}
      <div className="flex border-b border-brand-border px-6" style={{ background: '#0f1629' }}>
        {(['graph', 'modules', 'ai'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="px-4 py-3 text-sm font-medium transition-all border-b-2 capitalize"
            style={{
              borderBottomColor: activeTab === tab ? '#00d4ff' : 'transparent',
              color: activeTab === tab ? '#00d4ff' : '#8892a4',
            }}
          >
            {tab === 'graph' && '🔮 '}
            {tab === 'modules' && '⚡ '}
            {tab === 'ai' && '🤖 '}
            {tab === 'graph' ? 'Investigation Graph' : tab === 'modules' ? `Modules (${completedModules}/${moduleResults.length || '?'})` : 'AI Analysis'}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {/* GRAPH TAB */}
        {activeTab === 'graph' && (
          <div className="h-full relative">
            {nodes.length === 0 ? (
              <div className="h-full flex items-center justify-center">
                <div className="text-center">
                  <div className="text-4xl mb-4">🔍</div>
                  <div className="text-brand-muted font-mono text-sm">Scanning target... Building investigation graph</div>
                  <div className="flex justify-center mt-4 gap-1">
                    {[...Array(3)].map((_, i) => (
                      <div key={i} className="w-2 h-2 rounded-full bg-cyan-400 status-running" style={{ animationDelay: `${i * 0.3}s` }}></div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeClick={(_, node) => setSelectedNode(node)}
                connectionMode={ConnectionMode.Loose}
                fitView
                style={{ background: '#0a0e1a' }}
              >
                <Background color="#1e2d4a" gap={40} size={1} />
                <Controls style={{ background: '#0f1629', border: '1px solid #1e2d4a', borderRadius: '8px' }} />
                <MiniMap
                  style={{ background: '#060a14', border: '1px solid #1e2d4a', borderRadius: '8px' }}
                  nodeColor={(n) => NODE_COLORS[(n.data as any).nodeType] || '#8892a4'}
                  maskColor="#0a0e1a99"
                />
              </ReactFlow>
            )}

            {/* Node Inspector Panel */}
            {selectedNode && (
              <div className="absolute top-4 right-4 w-72 rounded-xl border p-4 shadow-xl" style={{ background: '#0f1629', borderColor: '#1e2d4a' }}>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-semibold uppercase tracking-wider text-brand-muted">Node Inspector</span>
                  <button onClick={() => setSelectedNode(null)} className="text-brand-muted hover:text-white text-sm">✕</button>
                </div>
                <div className="space-y-2">
                  <div>
                    <div className="text-xs text-brand-muted">Label</div>
                    <div className="font-mono text-sm text-white">{selectedNode.data.label}</div>
                  </div>
                  <div>
                    <div className="text-xs text-brand-muted">Type</div>
                    <div className="font-mono text-xs" style={{ color: NODE_COLORS[selectedNode.data.nodeType] || '#8892a4' }}>
                      {selectedNode.data.nodeType}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-brand-muted">ID</div>
                    <div className="font-mono text-xs text-brand-muted break-all">{selectedNode.id}</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* MODULES TAB */}
        {activeTab === 'modules' && (
          <div className="p-6 overflow-y-auto h-full">
            {moduleResults.length === 0 ? (
              <div className="text-center text-brand-muted text-sm py-20 font-mono">Waiting for module results...</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-5xl mx-auto">
                {moduleResults.map((mod) => {
                  const statusColors: Record<string, string> = {
                    success: '#00ff88', failed: '#ef4444', timeout: '#f59e0b', partial: '#f97316', running: '#00d4ff', pending: '#8892a4',
                  }
                  const c = statusColors[mod.status] || '#8892a4'
                  return (
                    <div key={mod.module_name} className="module-card rounded-xl p-5" style={{ background: '#0f1629' }}>
                      <div className="flex items-center justify-between mb-3">
                        <span className="font-mono text-sm text-white">{mod.module_name.replace(/_/g, ' ')}</span>
                        <span className="text-xs px-2 py-1 rounded-full font-mono" style={{ background: `${c}15`, color: c }}>
                          {mod.status}
                        </span>
                      </div>
                      <div className="flex items-center gap-4 text-xs text-brand-muted font-mono">
                        <span>⏱ {mod.execution_time_ms}ms</span>
                        <span>📌 {mod.nodes?.length || 0} nodes</span>
                        <span>🔗 {mod.edges?.length || 0} edges</span>
                      </div>
                      {mod.error && (
                        <div className="mt-3 text-xs text-red-400 font-mono bg-red-500 bg-opacity-5 rounded-lg p-2 border border-red-500 border-opacity-20">
                          {mod.error}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* AI TAB */}
        {activeTab === 'ai' && (
          <div className="p-6 overflow-y-auto h-full">
            <div className="max-w-3xl mx-auto">
              {!aiSummary ? (
                <div className="text-center py-20">
                  <div className="text-4xl mb-4">🤖</div>
                  <div className="text-brand-muted text-sm font-mono">
                    {overallStatus === 'running' || overallStatus === 'pending'
                      ? 'AI analysis will run once modules complete...'
                      : 'No AI analysis available for this scan.'}
                  </div>
                </div>
              ) : (
                <div className="rounded-xl border p-6" style={{ background: '#0f1629', borderColor: '#1e2d4a' }}>
                  <div className="flex items-center gap-2 mb-4">
                    <span style={{ color: '#a78bfa' }}>🤖</span>
                    <span className="font-semibold text-white">AI Intelligence Report</span>
                    <span className="text-xs text-brand-muted font-mono ml-auto">Powered by Ollama (Local)</span>
                  </div>
                  <div className="prose prose-invert text-sm text-slate-300 leading-relaxed whitespace-pre-wrap font-mono">
                    {aiSummary}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
