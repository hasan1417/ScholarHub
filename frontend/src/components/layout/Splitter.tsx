import React, { useCallback, useEffect, useRef, useState } from 'react'
import { logEvent } from '../../utils/metrics'

export type SplitterProps = {
  left: React.ReactNode
  right: React.ReactNode
  minLeftPx?: number // default 220
  minRightPx?: number // default 320
  initialPct?: number // default 0.5
  storageKey?: string // default 'latex.split.width'
  onChangePct?: (pct: number) => void
  onCommitPct?: (pct: number) => void
  onDragStart?: () => void
  onDragEnd?: () => void
}

const DEFAULT_KEY = 'latex.split.width'

function clampPct(p: number, min = 0.15, max = 0.85) {
  return Math.min(max, Math.max(min, p))
}

function readPct(storageKey: string, fallback: number) {
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return fallback
    const n = parseFloat(raw)
    return isNaN(n) ? fallback : clampPct(n)
  } catch { return fallback }
}

const Splitter: React.FC<SplitterProps> = ({
  left,
  right,
  minLeftPx = 220,
  minRightPx = 320,
  initialPct = 0.5,
  storageKey = DEFAULT_KEY,
  onChangePct,
  onCommitPct,
  onDragStart,
  onDragEnd,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const gutterRef = useRef<HTMLDivElement | null>(null)
  const overlayRef = useRef<HTMLDivElement | null>(null)
  const [pct, setPct] = useState(readPct(storageKey, initialPct))
  const draggingRef = useRef(false)
  const pointerIdRef = useRef<number | null>(null)
  const startXRef = useRef(0)
  const startPctRef = useRef(pct)
  const rafRef = useRef<number | null>(null)

  const applyPct = (nextPct: number, commit = false) => {
    const val = clampPct(nextPct)
    setPct(val)
    if (!commit) {
      // Use setTimeout to avoid setState during render
      setTimeout(() => onChangePct?.(val), 0)
    }
  }

  const addOverlay = () => {
    if (overlayRef.current) return
    const o = document.createElement('div')
    o.style.position = 'fixed'
    o.style.inset = '0'
    o.style.cursor = 'col-resize'
    o.style.background = 'transparent'
    o.style.zIndex = '2147483647'
    o.setAttribute('aria-hidden', 'true')
    document.body.appendChild(o)
    overlayRef.current = o
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
  }

  const removeOverlay = () => {
    if (overlayRef.current) {
      try { document.body.removeChild(overlayRef.current) } catch {}
      overlayRef.current = null
    }
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
  }

  const endDrag = useCallback((commit = true) => {
    if (!draggingRef.current) return
    draggingRef.current = false
    pointerIdRef.current = null
    removeOverlay()
    if (commit) {
      try { localStorage.setItem(storageKey, String(pct)) } catch {}
      onCommitPct?.(pct)
      try { logEvent('SplitDragEnd', { pct: Math.round(pct * 100) }) } catch {}
    }
  }, [pct, storageKey, onCommitPct])

  // Calculate pct from clientX respecting min widths
  const computePctFromX = (clientX: number) => {
    const el = containerRef.current
    if (!el) return pct
    const rect = el.getBoundingClientRect()
    const total = rect.width
    const leftPx = Math.max(minLeftPx, Math.min(total - minRightPx, clientX - rect.left))
    const nextPct = leftPx / total
    return clampPct(nextPct)
  }

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return
    const gutter = gutterRef.current
    if (!gutter) return
    try { gutter.setPointerCapture(e.pointerId) } catch {}
    draggingRef.current = true
    pointerIdRef.current = e.pointerId
    startXRef.current = e.clientX
    startPctRef.current = pct
    addOverlay()
    try { logEvent('SplitDragStart', { pct: Math.round(pct * 100) }) } catch {}
    try { onDragStart?.() } catch {}
    e.preventDefault()
    e.stopPropagation()
  }

  const onPointerMove = (e: PointerEvent) => {
    if (!draggingRef.current) return
    if (pointerIdRef.current !== null && e.pointerId !== pointerIdRef.current) return
    // Some devices report buttons=0 when up
    if (e.buttons === 0) { endDrag(true); return }
    e.preventDefault()
    const next = computePctFromX(e.clientX)
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(() => applyPct(next, false))
  }

  const onPointerUpLike = () => {
    try { onDragEnd?.() } catch {}
    endDrag(true)
  }

  useEffect(() => {
    const handleLostCapture = () => endDrag(true)
    const handleBlur = () => endDrag(true)
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUpLike)
    window.addEventListener('pointercancel', onPointerUpLike)
    window.addEventListener('blur', handleBlur)
    const g = gutterRef.current
    if (g) g.addEventListener('lostpointercapture', handleLostCapture)
    return () => {
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUpLike)
      window.removeEventListener('pointercancel', onPointerUpLike)
      window.removeEventListener('blur', handleBlur)
      if (g) g.removeEventListener('lostpointercapture', handleLostCapture)
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      removeOverlay()
    }
  }, [endDrag])

  const leftStyle: React.CSSProperties = { width: `${pct * 100}%`, minWidth: `${minLeftPx}px` }
  const rightStyle: React.CSSProperties = { width: `${(1 - pct) * 100}%`, minWidth: `${minRightPx}px` }

  // Debounced resize event for telemetry
  useEffect(() => {
    const t = setTimeout(() => { try { logEvent('SplitResized', { pct: Math.round(pct * 100) }) } catch {} }, 100)
    return () => clearTimeout(t)
  }, [pct])

  // Keyboard nudge
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.preventDefault()
    const step = e.shiftKey ? 0.10 : 0.02
    const dir = e.key === 'ArrowLeft' ? -1 : 1
    const el = containerRef.current
    const rect = el?.getBoundingClientRect()
    const total = rect?.width || 1000
    const newPct = clampPct(pct + dir * step)
    const leftPx = newPct * total
    const rightPx = total - leftPx
    if (leftPx < minLeftPx || rightPx < minRightPx) return
    applyPct(newPct, false)
  }

  const onDoubleClick = () => {
    const reset = 0.5
    applyPct(reset, false)
    try { localStorage.setItem(storageKey, String(reset)) } catch {}
    onCommitPct?.(reset)
    try { logEvent('SplitResized', { pct: Math.round(reset * 100), reason: 'doubleclick' }) } catch {}
  }

  return (
    <div ref={containerRef} className="flex-1 min-h-0 flex">
      <div style={leftStyle} className="h-full flex flex-col">
        {left}
      </div>
      <div
        ref={gutterRef}
        role="separator"
        aria-orientation="vertical"
        aria-valuemin={15}
        aria-valuemax={85}
        aria-valuenow={Math.round(pct * 100)}
        tabIndex={0}
        onKeyDown={onKeyDown}
        onPointerDown={onPointerDown}
        onDoubleClick={onDoubleClick}
        style={{ touchAction: 'none', userSelect: 'none', cursor: 'col-resize' }}
        className="w-2 bg-transparent hover:bg-gray-200"
      />
      <div style={rightStyle} className="border-l border-gray-200 min-h-0 min-w-0 overflow-hidden">
        <div className="w-full h-full overflow-auto">
          {right}
        </div>
      </div>
    </div>
  )
}

export default Splitter
