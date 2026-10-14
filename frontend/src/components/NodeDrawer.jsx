import { NODE_META, colorForType } from '../graph/config.js'

/**
 * Right-hand details drawer. Slides in when a node is clicked and shows the
 * node's type, name, the exact file path it was found in and the source
 * snippet that triggered its creation.
 */
export default function NodeDrawer({
  node,
  connectionCount,
  canDrillDown = false,
  onDrillDown,
  onClose,
}) {
  const open = Boolean(node)
  const type = node?.type
  const color = colorForType(type)
  const meta = node?.meta || {}

  return (
    <>
      {/* Backdrop (click to close). Only intercepts clicks while open. */}
      <div
        onClick={onClose}
        className={[
          'absolute inset-0 z-20 transition-opacity duration-300',
          open ? 'bg-slate-900/20 opacity-100' : 'pointer-events-none opacity-0',
        ].join(' ')}
      />

      <aside
        className={[
          'absolute right-0 top-0 z-30 flex h-full w-full max-w-md flex-col',
          'glass shadow-panel transition-transform duration-300 ease-out',
          open ? 'translate-x-0' : 'translate-x-full',
        ].join(' ')}
        aria-hidden={!open}
      >
        {node && (
          <>
            {/* Header */}
            <header className="flex items-start justify-between gap-4 border-b border-slate-200 p-5">
              <div className="min-w-0">
                <span
                  className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest"
                  style={{
                    color,
                    backgroundColor: hexToRgba(color, 0.12),
                    boxShadow: `inset 0 0 0 1px ${hexToRgba(color, 0.35)}`,
                  }}
                >
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
                  {NODE_META[type]?.label || type}
                </span>
                <h2 className="mt-3 break-words text-lg font-semibold leading-snug text-slate-900">
                  {node.name}
                </h2>
              </div>
              <button
                onClick={onClose}
                className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-900"
                aria-label="Close details"
              >
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </header>

            {/* Body */}
            <div className="flex-1 space-y-5 overflow-y-auto p-5">
              {canDrillDown && (
                <button
                  onClick={() => onDrillDown?.(node.id)}
                  className="btn-primary w-full justify-center"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polygon points="12 2 2 7 12 12 22 7 12 2" />
                    <polyline points="2 17 12 22 22 17" />
                    <polyline points="2 12 12 17 22 12" />
                  </svg>
                  Drill into components
                </button>
              )}

              <Detail label="File path">
                <code className="break-all font-mono text-xs text-cyan-700">
                  {node.filePath || '—'}
                  {node.line ? <span className="text-slate-400">{`:${node.line}`}</span> : null}
                </code>
              </Detail>

              {/* Type specific metadata */}
              <MetaGrid meta={meta} />

              <Detail label={`Connections · ${connectionCount}`}>
                <p className="text-xs text-slate-500">
                  {connectionCount === 0
                    ? 'No relationships detected for this node.'
                    : `Linked to ${connectionCount} other node${connectionCount === 1 ? '' : 's'} in the architecture graph.`}
                </p>
              </Detail>

              {node.snippet && (
                <Detail label="Source snippet">
                  <pre className="overflow-x-auto rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-700">
                    <code>{node.snippet}</code>
                  </pre>
                </Detail>
              )}
            </div>

            <footer className="border-t border-slate-200 p-4">
              <p className="text-center text-[10px] uppercase tracking-widest text-slate-500">
                Detected by deterministic static analysis
              </p>
            </footer>
          </>
        )}
      </aside>
    </>
  )
}

function Detail({ label, children }) {
  return (
    <div>
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        {label}
      </p>
      {children}
    </div>
  )
}

// Renders the arbitrary `meta` object the scanner attached to a node,
// skipping empty values.
function MetaGrid({ meta }) {
  const entries = Object.entries(meta).filter(([, v]) => v !== null && v !== undefined && v !== '')
  if (entries.length === 0) return null

  return (
    <Detail label="Details">
      <dl className="divide-y divide-slate-100 overflow-hidden rounded-lg border border-slate-200">
        {entries.map(([key, value]) => (
          <div key={key} className="flex items-start justify-between gap-4 bg-slate-50/60 px-3 py-2">
            <dt className="text-xs capitalize text-slate-500">{key.replace(/([A-Z])/g, ' $1')}</dt>
            <dd className="max-w-[60%] break-all text-right font-mono text-xs text-slate-800">
              {String(value)}
            </dd>
          </div>
        ))}
      </dl>
    </Detail>
  )
}

function hexToRgba(hex, alpha) {
  const clean = hex.replace('#', '')
  const r = parseInt(clean.substring(0, 2), 16)
  const g = parseInt(clean.substring(2, 4), 16)
  const b = parseInt(clean.substring(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
