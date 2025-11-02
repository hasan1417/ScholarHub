import React, { useCallback, useEffect, useRef, useState } from 'react'
import { buildApiUrl, API_ROOT } from '../../services/api'
import pdfViewerHtml from '../../assets/pdf-viewer.html?raw'

type CompileStatus = 'idle' | 'compiling' | 'success' | 'error'

interface LatexPdfViewerProps {
  latexSource: string
  paperId?: string
}

const LatexPdfViewer: React.FC<LatexPdfViewerProps> = ({ latexSource, paperId }) => {
  const [status, setStatus] = useState<CompileStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const seqRef = useRef(0)
  const lastObjectUrlRef = useRef<string | null>(null)
  const lastRevRef = useRef<number>(0)

  const cleanupObjectUrl = useCallback(() => {
    const prev = lastObjectUrlRef.current
    if (prev && prev.startsWith('blob:')) {
      try { URL.revokeObjectURL(prev) } catch {}
    }
    lastObjectUrlRef.current = null
  }, [])

  const postPdfToIframe = useCallback((url: string, rev: number) => {
    if (!url) return
    const iframe = iframeRef.current
    if (!iframe) return
    const send = () => {
      try {
        iframe.contentWindow?.postMessage({ type: 'loadFile', url, rev }, '*')
      } catch (e) {
        console.warn('[LatexPdfViewer] Failed to post PDF url to iframe', e)
      }
    }
    // If iframe already loaded, send immediately; otherwise wait for load event
    if (iframe.dataset.loaded === 'true') {
      send()
      return
    }
    try {
      const state = iframe.contentDocument?.readyState || iframe.contentWindow?.document?.readyState
      if (state === 'complete' || state === 'interactive') {
        iframe.dataset.loaded = 'true'
        send()
        return
      }
    } catch {}
    const handleLoad = () => {
      iframe.dataset.loaded = 'true'
      send()
    }
    iframe.addEventListener('load', handleLoad, { once: true })
  }, [])

  const resolveApiUrl = useCallback((url: string | null | undefined) => {
    if (!url) return url || ''
    if (/^https?:/i.test(url)) return url
    const sanitized = url.startsWith('/') ? url : `/${url}`
    return `${API_ROOT}${sanitized}`
  }, [])

  const compile = useCallback(async () => {
    if (!latexSource || !latexSource.trim()) {
      setStatus('error')
      setError('Paper does not have LaTeX content yet.')
      return
    }

    seqRef.current += 1
    const mySeq = seqRef.current
    setStatus('compiling')
    setError(null)
    // clear previous logs (suppressed)

    if (abortRef.current) {
      try { abortRef.current.abort() } catch {}
    }

    const controller = new AbortController()
    abortRef.current = controller
    let encounteredError = false
    let producedPdf = false

    try {
      const resp = await fetch(buildApiUrl('/latex/compile/stream'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token') || ''}`
        },
        body: JSON.stringify({
          latex_source: latexSource,
          paper_id: paperId ?? null,
          include_bibtex: true,
          job_label: `viewer-${Date.now()}`
        }),
        signal: controller.signal
      })

      if (!resp.ok || !resp.body) {
        throw new Error(`Compilation failed (${resp.status})`)
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''
        for (const raw of parts) {
          const line = raw.trim()
          if (!line.startsWith('data:')) continue
          const payloadText = line.replace(/^data:\s*/, '')
          let payload: any = null
          try {
            payload = JSON.parse(payloadText)
          } catch (e) {
            console.warn('[LatexPdfViewer] Failed to parse SSE payload', e)
            continue
          }

          if (payload.type === 'log') {
            // logs suppressed
          } else if (payload.type === 'cache') {
            // cache log suppressed
          } else if (payload.type === 'error') {
            encounteredError = true
            const msg = typeof payload.message === 'string' ? payload.message : 'Compilation error'
            setStatus('error')
            setError(msg)
          } else if (payload.type === 'final') {
            if (!payload.pdf_url) continue
            try {
              const token = localStorage.getItem('access_token') || ''
              const fetchUrl = resolveApiUrl(payload.pdf_url)
              const pdfResp = await fetch(fetchUrl, {
                headers: token ? { 'Authorization': `Bearer ${token}` } : undefined
              })
              if (!pdfResp.ok) {
                throw new Error(`Failed to fetch PDF (${pdfResp.status})`)
              }
              const blob = await pdfResp.blob()
              if (mySeq !== seqRef.current) {
                // Stale compile result; ignore
                continue
              }
              const objectUrl = URL.createObjectURL(blob)
              cleanupObjectUrl()
              lastObjectUrlRef.current = objectUrl
              lastRevRef.current = mySeq
              postPdfToIframe(objectUrl, mySeq)
              producedPdf = true
            } catch (err: any) {
              encounteredError = true
              const msg = err?.message || 'Failed to load compiled PDF'
              setStatus('error')
              setError(msg)
            }
          }
        }
      }

      if (!encounteredError && producedPdf) {
        setStatus('success')
      } else if (encounteredError && !producedPdf) {
        setStatus('error')
      }
    } catch (err: any) {
      if (controller.signal.aborted) return
      encounteredError = true
      setStatus('error')
      setError(err?.message || 'Failed to compile LaTeX')
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null
      }
      if (!encounteredError && producedPdf) {
        setError(null)
      }
    }
  }, [cleanupObjectUrl, latexSource, paperId, postPdfToIframe, resolveApiUrl])

  useEffect(() => {
    void compile()
    return () => {
      if (abortRef.current) {
        try { abortRef.current.abort() } catch {}
        abortRef.current = null
      }
      cleanupObjectUrl()
    }
  }, [compile, cleanupObjectUrl])

  useEffect(() => {
    const iframe = iframeRef.current
    if (!iframe) return
    const handleLoad = () => {
      iframe.dataset.loaded = 'true'
      const url = lastObjectUrlRef.current
      const rev = lastRevRef.current
      if (url && rev) {
        postPdfToIframe(url, rev)
      }
    }
    iframe.addEventListener('load', handleLoad)
    return () => {
      iframe.removeEventListener('load', handleLoad)
    }
  }, [postPdfToIframe])

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const data = event.data
      if (!data || typeof data !== 'object') return
      if (data.type !== 'viewer-ready') return
      const iframe = iframeRef.current
      if (iframe && event.source !== iframe.contentWindow) return
      const url = lastObjectUrlRef.current
      const rev = lastRevRef.current
      if (!url || !rev) return
      postPdfToIframe(url, rev)
    }
    window.addEventListener('message', onMessage)
    return () => {
      window.removeEventListener('message', onMessage)
    }
  }, [postPdfToIframe])

  return (
    <div className="flex-1 min-h-0 flex flex-col bg-gray-100">
      <iframe
        ref={iframeRef}
        title="LaTeX PDF Preview"
        srcDoc={pdfViewerHtml}
        className="w-full h-full border-0 bg-gray-200"
        data-loaded="false"
      />
      {status === 'error' && error && (
        <div className="px-3 py-2 border-t border-gray-200 bg-white text-sm text-red-600">{error}</div>
      )}
    </div>
  )
}

export default React.memo(LatexPdfViewer)
