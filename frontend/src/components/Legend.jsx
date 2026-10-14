import { NODE_META, REL_COLORS, colorForType } from '../graph/config.js'
import { useMemo } from 'react'

/**
 * Bottom-left legend. Shows node colour coding (with live counts) and the
 * relationship colours so the graph is instantly readable.
 */
export default function Legend({ nodes, links }) {
  // Count nodes per architectural type.
  const counts = useMemo(() => {
    const c = {}
    for (const n of nodes) c[n.type] = (c[n.type] || 0) + 1
    return c
  }, [nodes])

  const relTypes = useMemo(() => {
    const set = new Set(links.map((l) => l.type))
    return Object.keys(REL_COLORS).filter((t) => set.has(t))
  }, [links])

  return (
    <div className="absolute bottom-4 left-4 glass rounded-xl p-4 shadow-panel animate-fade-in">
      <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        Legend
      </p>

      <div className="space-y-2">
        {Object.entries(NODE_META)
          .filter(([type]) => counts[type])
          .map(([type, meta]) => (
            <div key={type} className="flex items-center gap-2.5">
              <span
                className="h-3 w-3 shrink-0 rounded-full ring-1 ring-slate-300"
                style={{ backgroundColor: colorForType(type) }}
              />
              <span className="text-xs text-slate-700">{meta.label}</span>
              <span className="ml-auto pl-3 font-mono text-[11px] text-slate-400">
                {counts[type]}
              </span>
            </div>
          ))}
      </div>

      {relTypes.length > 0 && (
        <>
          <p className="mb-2 mt-4 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
            Relationships
          </p>
          <div className="space-y-1.5">
            {relTypes.map((type) => (
              <div key={type} className="flex items-center gap-2.5">
                <span
                  className="h-0.5 w-4 rounded-full"
                  style={{ backgroundColor: REL_COLORS[type] }}
                />
                <span className="text-[11px] text-slate-600">{type}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
