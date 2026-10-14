import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import Legend from './Legend.jsx'
import NodeDrawer from './NodeDrawer.jsx'
import {
  PHYSICS,
  colorForType,
  isArchitectureType,
  radiusForType,
  relColor,
  withAlpha,
} from '../graph/config.js'

/**
 * Full-screen interactive architecture graph (light theme).
 *
 * Two viewing states:
 *   - "architecture" (default): only the high-level network map — Application,
 *     Client, Database and ExternalAPI nodes and the flows between them.
 *   - "internal": the file / route structure of a single Application, entered
 *     by double-clicking its node or using the drawer's "Drill down" button.
 *
 * Edges are drawn manually via `linkCanvasObject` so that:
 *   - the shaft stops exactly at the base of the arrowhead (no piercing),
 *   - the arrowhead is filled on a per-link colour,
 *   - the relationship type (CALLS, QUERIES, REQUESTS, …) is rendered on the
 *     line, rotated to follow it and never upside-down.
 */
export default function GraphView({ data, summary, onRescan }) {
  const containerRef = useRef(null)
  const fgRef = useRef(null)
  const fittedRef = useRef(false)
  // Tracks the previous click so we can detect a double-click ourselves
  // (force-graph dispatches raw pointer events, whose `detail` is unreliable).
  const lastClickRef = useRef({ id: null, time: 0 })

  const [size, setSize] = useState({ width: 0, height: 0 })
  const [hoverNode, setHoverNode] = useState(null)
  const [selectedNode, setSelectedNode] = useState(null)

  // Which abstraction level is on screen, and (for internal) which app.
  const [viewState, setViewState] = useState({ level: 'architecture', appId: null })

  // --- responsive canvas ----------------------------------------------------
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setSize({ width, height })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // A fresh payload (new scan) always starts back at the architecture view.
  useEffect(() => {
    setViewState({ level: 'architecture', appId: null })
  }, [data])

  // Every logical application in the scan (used for breadcrumbs / drill-down).
  const applications = useMemo(
    () => (data.nodes || []).filter((n) => n.type === 'Application'),
    [data],
  )

  const activeApp = useMemo(
    () => applications.find((a) => a.id === viewState.appId) || null,
    [applications, viewState.appId],
  )

  // The slice of the full graph that corresponds to the current view state.
  const view = useMemo(() => buildView(data, viewState), [data, viewState])

  // --- prepare graph data ---------------------------------------------------
  // We clone the payload because react-force-graph MUTATES nodes/links
  // (it injects x/y/vx/vy and swaps link source/target to node objects).
  // The adjacency + node index are built here, while ids are still plain
  // strings, and are used for hover highlighting and manual link painting.
  const prepared = useMemo(() => {
    const nodes = view.nodes.map((n) => ({ ...n }))
    const links = view.links.map((l) => ({ ...l }))

    const adjacency = new Map()
    const ensure = (id) => {
      if (!adjacency.has(id)) adjacency.set(id, new Set())
      return adjacency.get(id)
    }
    for (const link of links) {
      const s = typeof link.source === 'object' ? link.source.id : link.source
      const t = typeof link.target === 'object' ? link.target.id : link.target
      ensure(s).add(t)
      ensure(t).add(s)
    }

    const nodeIndex = new Map(nodes.map((n) => [n.id, n]))
    return { nodes, links, adjacency, nodeIndex }
  }, [view])

  // A fresh dataset should forget any previous selection / fitted state.
  useEffect(() => {
    setSelectedNode(null)
    setHoverNode(null)
    fittedRef.current = false
  }, [prepared])

  // --- physics tuning -------------------------------------------------------
  useEffect(() => {
    const fg = fgRef.current
    if (!fg) return
    const charge = fg.d3Force('charge')
    if (charge) charge.strength(PHYSICS.chargeStrength)
    const link = fg.d3Force('link')
    if (link) link.distance(PHYSICS.linkDistance).strength(PHYSICS.linkStrength)
    // Reheat so the new constants take effect.
    fg.d3ReheatSimulation?.()
  }, [prepared])

  const nodeCount = prepared.nodes.length
  // Only label every node when the graph is small enough to stay readable.
  const labelAll = nodeCount <= 120

  // --- helpers --------------------------------------------------------------
  const isNeighbour = useCallback(
    (id) => {
      if (!hoverNode) return false
      return prepared.adjacency.get(hoverNode.id)?.has(id) || hoverNode.id === id
    },
    [hoverNode, prepared],
  )

  const linkEnds = useCallback((link) => {
    const s = typeof link.source === 'object' ? link.source.id : link.source
    const t = typeof link.target === 'object' ? link.target.id : link.target
    return [s, t]
  }, [])

  const linkActive = useCallback(
    (link) => {
      if (!hoverNode) return null // no active focus
      const [s, t] = linkEnds(link)
      return s === hoverNode.id || t === hoverNode.id
    },
    [hoverNode, linkEnds],
  )

  // Resolve a link endpoint (an id or a resolved node object) to its node.
  const resolveEnd = useCallback(
    (end) => (end && typeof end === 'object' ? end : prepared.nodeIndex.get(end) || null),
    [prepared],
  )

  // Node radius, enlarged while the node is focused (mirrors paintNode).
  const nodeRadius = useCallback(
    (node) => {
      const focused = hoverNode?.id === node.id || selectedNode?.id === node.id
      return radiusForType(node.type) * (focused ? 1.5 : 1)
    },
    [hoverNode, selectedNode],
  )

  // Opacity of a link given the current focus (hover > selection > idle).
  const linkOpacity = useCallback(
    (link) => {
      if (hoverNode) return linkActive(link) ? 1 : 0.06
      if (selectedNode) {
        const [s, t] = linkEnds(link)
        return s === selectedNode.id || t === selectedNode.id ? 1 : 0.12
      }
      return 0.75
    },
    [hoverNode, selectedNode, linkActive, linkEnds],
  )

  // --- view navigation ------------------------------------------------------
  const drillInto = useCallback((appId) => {
    if (!appId) return
    setSelectedNode(null)
    setHoverNode(null)
    setViewState({ level: 'internal', appId })
  }, [])

  const goBack = useCallback(() => {
    setSelectedNode(null)
    setHoverNode(null)
    setViewState({ level: 'architecture', appId: null })
  }, [])

  // --- node painting --------------------------------------------------------
  const paintNode = useCallback(
    (node, ctx, globalScale) => {
      const active = hoverNode ? isNeighbour(node.id) : true
      const isHover = hoverNode?.id === node.id
      const isSelected = selectedNode?.id === node.id
      const focused = isHover || isSelected
      const base = colorForType(node.type)
      const r = radiusForType(node.type) * (focused ? 1.5 : 1)
      const alpha = active ? 1 : 0.15

      // Soft halo behind the focused node.
      if (focused) {
        ctx.beginPath()
        ctx.arc(node.x, node.y, r + 5, 0, 2 * Math.PI)
        ctx.fillStyle = withAlpha(base, 0.2)
        ctx.fill()
      }

      // Body.
      ctx.beginPath()
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
      ctx.fillStyle = withAlpha(base, alpha)
      ctx.fill()

      // Ring: dark and crisp on the light canvas.
      ctx.lineWidth = (focused ? 2 : 1) / globalScale
      ctx.strokeStyle = focused
        ? '#0f172a'
        : withAlpha('#0f172a', active ? 0.35 : 0.06)
      ctx.stroke()

      // Label under the node, drawn in screen-constant size, dark on light.
      const showLabel = focused || (active && labelAll)
      if (showLabel) {
        const fontSize = 11 / globalScale
        ctx.font = `${focused ? '600' : '500'} ${fontSize}px Inter, system-ui, sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        ctx.fillStyle = focused
          ? '#020617'
          : withAlpha('#334155', active ? 0.9 : 0.2)
        const label = truncate(node.name, 24)
        ctx.fillText(label, node.x, node.y + r + 2)
      }
    },
    [hoverNode, selectedNode, isNeighbour, labelAll],
  )

  // Invisible, slightly larger hit area for easier pointer targeting.
  const paintPointerArea = useCallback((node, color, ctx) => {
    const r = radiusForType(node.type) + 3
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
    ctx.fill()
  }, [])

  // --- custom edge painting -------------------------------------------------
  // Draws the shaft, a filled arrowhead and a rotated type label. The shaft
  // terminates at the arrowhead base so it can never pierce the arrow.
  const paintLink = useCallback(
    (link, ctx, globalScale) => {
      const start = resolveEnd(link.source)
      const end = resolveEnd(link.target)
      if (!start || !end || start.x == null || end.x == null) return

      const dx = end.x - start.x
      const dy = end.y - start.y
      const dist = Math.hypot(dx, dy)
      if (dist < 1) return
      const ux = dx / dist
      const uy = dy / dist

      const color = relColor(link.type)
      const opacity = linkOpacity(link)
      const emphasized = hoverNode ? linkActive(link) : true

      // Keep the arrowhead a constant size on screen regardless of zoom.
      const arrowLen = 9 / globalScale
      const arrowHalf = 4 / globalScale

      // Stop the shaft at the node boundary plus a small gap.
      const startPad = nodeRadius(start) + 1.5
      const endPad = nodeRadius(end) + 1.5

      const x1 = start.x + ux * startPad
      const y1 = start.y + uy * startPad
      const tipX = end.x - ux * endPad
      const tipY = end.y - uy * endPad
      const baseX = tipX - ux * arrowLen
      const baseY = tipY - uy * arrowLen

      ctx.save()
      ctx.globalAlpha = opacity

      // Shaft — drawn up to the arrowhead base, never through it.
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(baseX, baseY)
      ctx.strokeStyle = color
      ctx.lineCap = 'round'
      ctx.lineWidth =
        (emphasized && (hoverNode || selectedNode) ? 2.6 : 1.8) / globalScale
      ctx.stroke()

      // Filled arrowhead at the target node.
      const nx = -uy
      const ny = ux
      ctx.beginPath()
      ctx.moveTo(tipX, tipY)
      ctx.lineTo(baseX + nx * arrowHalf, baseY + ny * arrowHalf)
      ctx.lineTo(baseX - nx * arrowHalf, baseY - ny * arrowHalf)
      ctx.closePath()
      ctx.fillStyle = color
      ctx.fill()

      ctx.restore()

      // Relationship label, centred on the shaft and parallel to the line.
      const longEnough = dist * globalScale > 30
      if (globalScale >= 0.32 && longEnough && opacity > 0.25) {
        let angle = Math.atan2(dy, dx)
        // Never render the text upside-down.
        if (angle > Math.PI / 2 || angle < -Math.PI / 2) angle += Math.PI

        const midX = (x1 + baseX) / 2
        const midY = (y1 + baseY) / 2
        const fontSize = 11 / globalScale
        const text = link.type

        ctx.save()
        ctx.translate(midX, midY)
        ctx.rotate(angle)
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.font = `600 ${fontSize}px Inter, system-ui, sans-serif`

        const padX = 4 / globalScale
        const padY = 2.5 / globalScale
        const w = ctx.measureText(text).width + padX * 2
        const h = fontSize + padY * 2

        // Light "pill" so the label reads clearly over the canvas + line.
        ctx.globalAlpha = Math.min(1, opacity + 0.15)
        ctx.fillStyle = 'rgba(255, 255, 255, 0.94)'
        roundRect(ctx, -w / 2, -h / 2, w, h, 4 / globalScale)
        ctx.fill()
        ctx.strokeStyle = withAlpha(color, 0.45)
        ctx.lineWidth = 1 / globalScale
        ctx.stroke()

        // Type text uses the link colour for a clear visual association.
        ctx.globalAlpha = Math.max(opacity, 0.85)
        ctx.fillStyle = color
        ctx.fillText(text, 0, 0)
        ctx.restore()
      }
    },
    [resolveEnd, nodeRadius, linkOpacity, linkActive, hoverNode, selectedNode],
  )

  // Frame the whole graph the first time the simulation settles.
  const handleEngineStop = useCallback(() => {
    if (!fittedRef.current) {
      fgRef.current?.zoomToFit(600, 70)
      fittedRef.current = true
    }
  }, [])

  const handleNodeClick = useCallback(
    (node) => {
      const now = Date.now()
      const last = lastClickRef.current
      const isDoubleClick = last.id === node.id && now - last.time < 320
      lastClickRef.current = { id: node.id, time: now }

      // Double-clicking an Application drills into its internal components.
      if (isDoubleClick && node.type === 'Application') {
        drillInto(node.id)
        return
      }
      setSelectedNode(node)
    },
    [drillInto],
  )

  const handleBackgroundClick = useCallback(() => setSelectedNode(null), [])

  const inInternalView = viewState.level === 'internal'

  return (
    <div ref={containerRef} className="relative h-full w-full bg-slate-50">
      {/* The canvas itself */}
      <ForceGraph2D
        ref={fgRef}
        graphData={prepared}
        width={size.width}
        height={size.height}
        backgroundColor="#f8fafc"
        // physics
        d3AlphaDecay={PHYSICS.d3AlphaDecay}
        d3VelocityDecay={PHYSICS.d3VelocityDecay}
        warmupTicks={PHYSICS.warmupTicks}
        cooldownTicks={PHYSICS.cooldownTicks}
        onEngineStop={handleEngineStop}
        // painting
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={paintPointerArea}
        linkCanvasObject={paintLink}
        linkCanvasObjectMode="replace"
        // interaction
        onNodeHover={setHoverNode}
        onNodeClick={handleNodeClick}
        onBackgroundClick={handleBackgroundClick}
        enableNodeDrag
        enableZoomInteraction
        enablePanInteraction
      />

      {/* Grid texture sits under the glass UI but over the canvas edge. */}
      <div className="grid-overlay pointer-events-none absolute inset-0 opacity-40" />

      <Toolbar
        summary={summary}
        nodeCount={nodeCount}
        linkCount={prepared.links.length}
        onRescan={onRescan}
      />

      {inInternalView && (
        <Breadcrumb appName={activeApp?.name || 'Application'} onBack={goBack} />
      )}

      <Legend nodes={prepared.nodes} links={prepared.links} />

      {/* Zoom / interaction hint */}
      <div className="pointer-events-none absolute bottom-4 right-4 glass rounded-lg px-3 py-2 text-[11px] text-slate-500">
        <span className="font-medium text-slate-700">Scroll</span> zoom ·{' '}
        <span className="font-medium text-slate-700">Drag</span> pan ·{' '}
        <span className="font-medium text-slate-700">Click</span> details
        {!inInternalView && applications.length > 0 && (
          <>
            {' · '}
            <span className="font-medium text-slate-700">Double-click</span> an
            app to drill in
          </>
        )}
      </div>

      <NodeDrawer
        node={selectedNode}
        connectionCount={
          selectedNode ? prepared.adjacency.get(selectedNode.id)?.size ?? 0 : 0
        }
        canDrillDown={selectedNode?.type === 'Application' && !inInternalView}
        onDrillDown={drillInto}
        onClose={() => setSelectedNode(null)}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Derive the visible subgraph for the current abstraction level.
// ---------------------------------------------------------------------------
const endId = (end) => (typeof end === 'object' ? end.id : end)

function buildView(data, viewState) {
  const nodes = data.nodes || []
  const links = data.links || []

  // --- architecture level: top-level network map only ----------------------
  if (viewState?.level !== 'internal' || !viewState.appId) {
    const allowed = new Set(
      nodes.filter((n) => isArchitectureType(n.type)).map((n) => n.id),
    )
    return {
      nodes: nodes.filter((n) => allowed.has(n.id)),
      links: links.filter(
        (l) => allowed.has(endId(l.source)) && allowed.has(endId(l.target)),
      ),
    }
  }

  // --- internal level: one application's components ------------------------
  const appId = viewState.appId
  const byId = new Map(nodes.map((n) => [n.id, n]))

  // Direct children declared via HAS_COMPONENT (the app's files/modules).
  const children = new Set()
  for (const link of links) {
    if (link.type === 'HAS_COMPONENT' && endId(link.source) === appId) {
      children.add(endId(link.target))
    }
  }

  const keep = new Set([appId, ...children])
  const keptLinks = []

  for (const link of links) {
    const s = endId(link.source)
    const t = endId(link.target)

    if (link.type === 'HAS_COMPONENT') {
      if (s === appId && children.has(t)) keptLinks.push(link)
      continue
    }

    // Only follow edges that originate from this app's own components.
    if (!children.has(s)) continue

    const target = byId.get(t)
    if (!target) continue

    if (target.type === 'Service') {
      // Include sibling modules (CALLS) but never foreign applications.
      if (children.has(t)) {
        keep.add(t)
        keptLinks.push(link)
      }
    } else {
      // Endpoints, databases and external services are always relevant.
      keep.add(t)
      keptLinks.push(link)
    }
  }

  return { nodes: nodes.filter((n) => keep.has(n.id)), links: keptLinks }
}

// ---------------------------------------------------------------------------
// Top toolbar: brand, scan summary, rescan action.
// ---------------------------------------------------------------------------
function Toolbar({ summary, nodeCount, linkCount, onRescan }) {
  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-4 p-4">
      <div className="pointer-events-auto glass rounded-xl px-4 py-3 shadow-panel animate-fade-in">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-cyan-500 shadow-glow" />
          <span className="text-sm font-semibold tracking-tight text-slate-900">
            Vecto<span className="text-cyan-600">graph</span>
          </span>
          <span className="ml-1 rounded-md border border-slate-200 bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-slate-500">
            architecture map
          </span>
        </div>
        <div className="mt-2 flex items-center gap-4 text-[11px] text-slate-500">
          <Stat label="Nodes" value={nodeCount} />
          <Stat label="Edges" value={linkCount} />
          {summary?.filesScanned != null && (
            <Stat label="Files" value={summary.filesScanned} />
          )}
        </div>
      </div>

      <div className="pointer-events-auto flex items-center gap-2">
        <button className="btn-ghost shadow-panel" onClick={onRescan}>
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          New scan
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Floating breadcrumb shown while drilled into an application.
// ---------------------------------------------------------------------------
function Breadcrumb({ appName, onBack }) {
  return (
    <div className="pointer-events-auto absolute left-1/2 top-4 z-10 -translate-x-1/2 animate-fade-in">
      <div className="glass flex items-center gap-1 rounded-full p-1 pl-1 pr-2.5 shadow-panel">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-100"
        >
          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 18l-6-6 6-6" />
          </svg>
          Back to Architecture
        </button>
        <span className="text-slate-300">/</span>
        <span className="flex items-center gap-1.5 rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-semibold text-cyan-700 ring-1 ring-inset ring-cyan-200">
          <span className="h-1.5 w-1.5 rounded-full bg-cyan-500" />
          {appName}
        </span>
      </div>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="font-mono text-sm font-semibold text-slate-800">{value}</span>
      <span>{label}</span>
    </span>
  )
}

// Rounded-rectangle path (ctx.roundRect is not available in every browser).
function roundRect(ctx, x, y, w, h, r) {
  const radius = Math.max(0, Math.min(r, w / 2, h / 2))
  ctx.beginPath()
  ctx.moveTo(x + radius, y)
  ctx.arcTo(x + w, y, x + w, y + h, radius)
  ctx.arcTo(x + w, y + h, x, y + h, radius)
  ctx.arcTo(x, y + h, x, y, radius)
  ctx.arcTo(x, y, x + w, y, radius)
  ctx.closePath()
}

function truncate(text, max) {
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}
