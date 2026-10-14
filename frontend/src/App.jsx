import { useCallback, useState } from 'react'
import UploadView from './components/UploadView.jsx'
import GraphView from './components/GraphView.jsx'
import { fetchGraph } from './api.js'

/**
 * Top level state machine:
 *   phase "upload"  -> the drag & drop landing screen
 *   phase "graph"   -> the full screen force-graph dashboard
 */
export default function App() {
  const [phase, setPhase] = useState('upload')
  const [graph, setGraph] = useState({ nodes: [], links: [] })
  const [summary, setSummary] = useState(null)

  // Called by UploadView once the backend finished scanning + persisting.
  const handleUploaded = useCallback(async (scanSummary) => {
    const data = await fetchGraph()
    setSummary(scanSummary)
    setGraph(data)
    setPhase('graph')
  }, [])

  const handleRescan = useCallback(() => {
    setPhase('upload')
  }, [])

  return (
    <div className="relative h-full w-full overflow-hidden bg-slate-50 text-slate-900">
      {phase === 'upload' ? (
        <UploadView onUploaded={handleUploaded} />
      ) : (
        <GraphView data={graph} summary={summary} onRescan={handleRescan} />
      )}
    </div>
  )
}
