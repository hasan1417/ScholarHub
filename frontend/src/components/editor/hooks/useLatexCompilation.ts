import { useCallback, useEffect, useRef, useState } from 'react'
import { logEvent } from '../../../utils/metrics'
import { buildApiUrl, API_ROOT } from '../../../services/api'

interface UseLatexCompilationOptions {
  paperId: string | undefined
  readOnly: boolean
  getLatestSource: () => string
  flushBufferedChange: () => void
}

interface UseLatexCompilationReturn {
  iframeRef: React.RefObject<HTMLIFrameElement>
  compileStatus: 'idle' | 'compiling' | 'success' | 'error'
  compileError: string | null
  compileLogs: string[]
  lastCompileAt: number | null
  compileNow: () => Promise<void>
}

export function useLatexCompilation({
  paperId,
  readOnly,
  getLatestSource,
  flushBufferedChange,
}: UseLatexCompilationOptions): UseLatexCompilationReturn {
  // Debug helper -- enable with `window.__SH_DEBUG_LTX = true` in DevTools
  const debugLog = useCallback((...args: any[]) => {
    try {
      if ((window as any).__SH_DEBUG_LTX) console.debug('[useLatexCompilation]', ...args)
    } catch {}
  }, [])

  const [compileStatus, setCompileStatus] = useState<'idle' | 'compiling' | 'success' | 'error'>('idle')
  const [compileError, setCompileError] = useState<string | null>(null)
  const [compileLogs, setCompileLogs] = useState<string[]>([])
  const [lastCompileAt, setLastCompileAt] = useState<number | null>(null)

  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const pdfBlobRef = useRef<string | null>(null)
  const lastPostedRevRef = useRef<number>(0)
  const compileAbortRef = useRef<AbortController | null>(null)

  // Bug #2: Use a proper ref instead of a static property on the component function
  const compileSeqRef = useRef<number>(0)

  const resolveApiUrl = useCallback((url: string | null | undefined) => {
    if (!url) return url || ''
    if (/^https?:/i.test(url)) return url
    const sanitized = url.startsWith('/') ? url : `/${url}`
    return `${API_ROOT}${sanitized}`
  }, [])

  const cleanupPdf = useCallback(() => {
    const current = pdfBlobRef.current
    if (current && current.startsWith('blob:')) {
      try { URL.revokeObjectURL(current) } catch {}
    }
    pdfBlobRef.current = null
  }, [])

  const postPdfToIframe = useCallback((blobUrl: string, rev: number) => {
    const iframe = iframeRef.current
    if (!iframe || !iframe.contentWindow) return
    try {
      // Bug #6: Use window.location.origin instead of '*' for security
      iframe.contentWindow.postMessage({ type: 'loadFile', url: blobUrl, rev }, window.location.origin)
      debugLog('Posted PDF to iframe:', { rev, url: blobUrl.substring(0, 50) })
    } catch (e) {
      console.error('[LaTeX] Failed to post PDF to iframe:', e)
    }
  }, [debugLog])

  const compileNow = useCallback(async () => {
    if (readOnly) {
      setCompileError('Compile disabled in read-only mode')
      setCompileStatus('error')
      return
    }
    const projectId = paperId ?? (window as any).__SH_ACTIVE_PAPER_ID ?? null
    setCompileLogs([])
    setCompileError(null)
    setCompileStatus('compiling')
    if (compileAbortRef.current) {
      try { compileAbortRef.current.abort() } catch {}
    }
    flushBufferedChange()
    const controller = new AbortController()
    compileAbortRef.current = controller
    const buildId = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`

    const src = getLatestSource()

    try { await logEvent('CompileClicked', { srcLen: src.length, projectId, buildId }) } catch {}
    const t0 = performance.now()
    let firstError: string | null = null
    let producedPdf = false
    try {
      try { await logEvent('CompileStart', { approxLen: src.length, buildId, projectId }) } catch {}

      // Bug #2: Use the ref instead of static property
      compileSeqRef.current += 1
      const mySeq = compileSeqRef.current

      const resp = await fetch(buildApiUrl('/latex/compile/stream'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`
        },
        body: JSON.stringify({ latex_source: src, paper_id: projectId, include_bibtex: true, job_label: buildId }),
        signal: controller.signal
      })
      if (!resp.ok || !resp.body) throw new Error(`Compile failed: ${resp.status} ${resp.statusText}`)
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''
        for (const chunk of parts) {
          const trimmed = chunk.trim()
          if (!trimmed.startsWith('data:')) continue
          try {
            const payload = JSON.parse(trimmed.replace(/^data:\s*/, ''))
            if (payload.type === 'log') {
              const line = typeof payload.line === 'string' ? payload.line : ''
              if (line) {
                setCompileLogs(prev => prev.length > 200 ? [...prev.slice(-199), line] : [...prev, line])
                if (!firstError && /error:/i.test(line)) firstError = line
              }
            } else if (payload.type === 'error') {
              const msg = payload.message || 'Compilation error'
              firstError = firstError || msg
            } else if (payload.type === 'final' && payload.pdf_url) {
              debugLog('Received final event with PDF URL:', payload.pdf_url)
              const pdfUrl = resolveApiUrl(payload.pdf_url)
              debugLog('Resolved PDF URL:', pdfUrl)
              const token = localStorage.getItem('access_token') || ''
              const pdfResp = await fetch(pdfUrl, { headers: token ? { 'Authorization': `Bearer ${token}` } : undefined })
              debugLog('PDF fetch response:', pdfResp.status, pdfResp.ok)
              if (!pdfResp.ok) throw new Error(`Failed to fetch PDF (${pdfResp.status})`)
              const blob = await pdfResp.blob()
              debugLog('PDF blob size:', blob.size, 'mySeq:', mySeq, 'currentSeq:', compileSeqRef.current)
              if (mySeq !== compileSeqRef.current) {
                debugLog('Skipping stale compile result')
                continue
              }
              const objectUrl = URL.createObjectURL(blob)
              debugLog('Created blob URL:', objectUrl)
              cleanupPdf()
              pdfBlobRef.current = objectUrl
              postPdfToIframe(objectUrl, mySeq)
              lastPostedRevRef.current = mySeq
              producedPdf = true
            }
          } catch {}
        }
      }
      const duration = Math.round(performance.now() - t0)
      try { await logEvent('CompileEnd', { buildId, durationMs: duration, projectId, success: producedPdf }) } catch {}
      if (producedPdf) {
        setCompileStatus('success')
        setCompileError(null)
        setLastCompileAt(Date.now())
      } else {
        setCompileStatus('error')
        setCompileError(firstError || 'Compilation failed')
      }
    } catch (err: any) {
      if (controller.signal.aborted) return
      const message = err?.message || 'Compilation failed'
      setCompileStatus('error')
      setCompileError(message)
    } finally {
      if (compileAbortRef.current === controller) compileAbortRef.current = null
    }
  }, [cleanupPdf, debugLog, flushBufferedChange, getLatestSource, paperId, postPdfToIframe, readOnly, resolveApiUrl])

  // Viewer-ready listener: re-post PDF when iframe signals readiness
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const data = event.data
      if (!data || typeof data !== 'object') return
      if (data.type !== 'viewer-ready') return
      const iframe = iframeRef.current
      if (iframe && event.source !== iframe.contentWindow) return
      const url = pdfBlobRef.current
      const rev = lastPostedRevRef.current
      if (!url || !rev) return
      postPdfToIframe(url, rev)
    }
    window.addEventListener('message', onMessage)
    return () => {
      window.removeEventListener('message', onMessage)
    }
  }, [postPdfToIframe])

  // Abort cleanup on unmount
  useEffect(() => {
    return () => {
      if (compileAbortRef.current) {
        try { compileAbortRef.current.abort() } catch {}
      }
      cleanupPdf()
    }
  }, [cleanupPdf])

  // Bug #4: Auto-compile on mount using a stable ref pattern.
  // Store compileNow in a ref so the effect does not depend on it
  // (compileNow is recreated on every render, which would cause infinite re-triggers).
  const compileNowRef = useRef(compileNow)
  compileNowRef.current = compileNow

  useEffect(() => {
    if (!readOnly) {
      void compileNowRef.current()
    }
  }, [paperId, readOnly])

  return {
    iframeRef,
    compileStatus,
    compileError,
    compileLogs,
    lastCompileAt,
    compileNow,
  }
}
