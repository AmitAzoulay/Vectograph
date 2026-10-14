import { useCallback, useRef, useState } from 'react'
import { uploadCodebase } from '../api.js'

/**
 * Landing screen: a sleek drag & drop zone that accepts a single .zip.
 * While uploading/scanning it overlays an "Analyzing Architecture..." spinner.
 */
export default function UploadView({ onUploaded }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState(null)
  const [fileName, setFileName] = useState(null)

  const runScan = useCallback(
    async (file) => {
      if (!file) return
      if (!file.name.toLowerCase().endsWith('.zip')) {
        setError('Please provide a .zip archive of your codebase.')
        return
      }
      setError(null)
      setFileName(file.name)
      setBusy(true)
      setProgress(0)
      try {
        const summary = await uploadCodebase(file, setProgress)
        // Small pause so the user sees the "complete" state.
        setTimeout(() => onUploaded(summary), 350)
      } catch (err) {
        setError(err.message || 'Scan failed.')
        setBusy(false)
      }
    },
    [onUploaded],
  )

  const onDrop = useCallback(
    (e) => {
      e.preventDefault()
      setDragging(false)
      const file = e.dataTransfer.files?.[0]
      runScan(file)
    },
    [runScan],
  )

  return (
    <div className="relative flex h-full w-full items-center justify-center">
      {/* Background grid + soft bottom fade */}
      <div className="grid-overlay pointer-events-none absolute inset-0 opacity-60" />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-slate-100" />

      <div className="relative z-10 w-full max-w-2xl px-6 animate-fade-in">
        {/* Brand */}
        <div className="mb-10 text-center">
          <div className="mb-3 inline-flex items-center gap-3">
            <Logo />
            <h1 className="text-3xl font-bold tracking-tight text-slate-900">
              Vecto<span className="text-cyan-600">graph</span>
            </h1>
          </div>
          <p className="text-sm text-slate-500">
            Cybersecurity architecture mapping · upload a codebase, get an attack-surface graph.
          </p>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !busy && inputRef.current?.click()}
          className={[
            'group relative cursor-pointer rounded-2xl border-2 border-dashed p-12 text-center',
            'glass shadow-panel transition-all duration-300',
            dragging
              ? 'border-cyan-500 shadow-glow scale-[1.01]'
              : 'border-slate-300 hover:border-cyan-400 hover:shadow-glow',
          ].join(' ')}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={(e) => runScan(e.target.files?.[0])}
          />

          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-cyan-50 ring-1 ring-cyan-200 animate-float">
            <UploadIcon className="h-8 w-8 text-cyan-600" />
          </div>

          <p className="text-lg font-semibold text-slate-900">
            {dragging ? 'Drop to analyze' : 'Drag & drop your codebase'}
          </p>
          <p className="mt-1 text-sm text-slate-500">
            or <span className="text-cyan-600 underline-offset-4 group-hover:underline">browse</span> for a{' '}
            <span className="font-mono text-slate-700">.zip</span> file
          </p>

          {/* Supported stack hint */}
          <div className="mt-6 flex flex-wrap items-center justify-center gap-2 text-[11px] uppercase tracking-wider text-slate-500">
            {['JavaScript', 'TypeScript', 'Python', 'Express', 'FastAPI', 'Flask'].map((tag) => (
              <span key={tag} className="rounded-full border border-slate-200 bg-slate-100 px-2.5 py-1">
                {tag}
              </span>
            ))}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600 animate-fade-in">
            {error}
          </div>
        )}

        <p className="mt-6 text-center text-xs text-slate-500">
          Files are scanned in an isolated temp directory and never executed.
        </p>
      </div>

      {/* Busy overlay */}
      {busy && <BusyOverlay fileName={fileName} progress={progress} done={progress >= 100} />}
    </div>
  )
}

function BusyOverlay({ fileName, progress, done }) {
  return (
    <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-slate-50/90 backdrop-blur-md animate-fade-in">
      <div className="relative flex h-24 w-24 items-center justify-center">
        {/* Pulsing rings */}
        <span className="absolute inline-flex h-16 w-16 rounded-full bg-cyan-400/30 animate-pulse-ring" />
        <span className="absolute inline-flex h-16 w-16 rounded-full bg-cyan-300/30 animate-pulse-ring [animation-delay:0.6s]" />
        <div className="relative h-16 w-16 rounded-full border-2 border-cyan-200 border-t-cyan-500 animate-spin" />
      </div>

      <h2 className="mt-8 text-xl font-semibold text-slate-900">Analyzing Architecture…</h2>
      <p className="mt-2 max-w-sm truncate text-sm text-slate-500">{fileName}</p>

      {/* Progress bar reflects upload; scanning is near-instant after. */}
      <div className="mt-6 h-1.5 w-64 overflow-hidden rounded-full bg-slate-200">
        <div
          className="h-full rounded-full bg-gradient-to-r from-cyan-600 to-cyan-400 transition-all duration-300"
          style={{ width: `${done ? 100 : Math.max(progress, 8)}%` }}
        />
      </div>
      <p className="mt-3 font-mono text-xs text-slate-500">
        {done ? 'building graph…' : `${progress}% uploaded`}
      </p>
    </div>
  )
}

function Logo() {
  return (
    <svg width="34" height="34" viewBox="0 0 40 40" fill="none">
      <circle cx="20" cy="20" r="18" stroke="#22d3ee" strokeOpacity="0.4" strokeWidth="1.5" />
      <circle cx="20" cy="20" r="5" fill="#22d3ee" />
      <circle cx="8" cy="10" r="3" fill="#22c55e" />
      <circle cx="32" cy="12" r="3" fill="#ef4444" />
      <circle cx="30" cy="31" r="3" fill="#3b82f6" />
      <path d="M20 20 L8 10 M20 20 L32 12 M20 20 L30 31" stroke="#22d3ee" strokeOpacity="0.5" strokeWidth="1.2" />
    </svg>
  )
}

function UploadIcon({ className }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  )
}
