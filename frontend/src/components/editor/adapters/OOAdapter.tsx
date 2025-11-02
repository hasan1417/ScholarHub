import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { EditorAdapterHandle, EditorAdapterProps } from './EditorAdapter'

declare global {
  interface Window {
    DocsAPI?: { DocEditor: new (targetElementId: string, config: any) => any }
  }
}

const OOAdapter = forwardRef<EditorAdapterHandle, EditorAdapterProps>(function OOAdapter(
  { paperId, paperTitle, className, onDirtyChange, readOnly = false, collaborationStatus: _collaborationStatus, theme = 'light' },
  ref
) {
  const containerRef = useRef<HTMLDivElement>(null)
  const editorIdRef = useRef<string>('oo-editor-' + Math.random().toString(36).slice(2))
  const docEditorRef = useRef<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const pluginWinRef = useRef<Window | null>(null)
  const pluginOriginRef = useRef<string>('*')
  const pendingRef = useRef(new Map<string, { resolve: (v:any)=>void, reject: (e:any)=>void }>())
  const themeRef = useRef<'light' | 'dark'>(theme)

  useEffect(() => {
    themeRef.current = theme
  }, [theme])

  useEffect(() => {
    let cancelled = false
    const loadScript = () => new Promise<void>((resolve, reject) => {
      if (window.DocsAPI) return resolve()
      const base = import.meta.env.VITE_ONLYOFFICE_URL || 'http://localhost:8080'
      const script = document.createElement('script')
      script.src = `${base}/web-apps/apps/api/documents/api.js?ts=${Date.now()}`
      script.async = true
      script.onload = () => resolve()
      script.onerror = () => reject(new Error('Failed to load OnlyOffice API'))
      document.head.appendChild(script)
    })

    const init = async () => {
      try {
        setLoading(true)
        setError(null)
        await loadScript()
        if (cancelled) return
        // Host URL used by DocServer to fetch the document
        // URL that OnlyOffice Document Server will use to reach our backend.
        // For Docker Desktop (macOS/Windows), host.docker.internal resolves to the host.
        const backendForDocServer = 'http://host.docker.internal:8000'
        const documentUrl = paperId
          ? `${backendForDocServer}/onlyoffice/document?paperId=${encodeURIComponent(paperId)}`
          : `${backendForDocServer}/onlyoffice/sample-document`
        // Use a stable key per paper to join the same OnlyOffice co-authoring session across clients
        // Changing the key forces a new session/version; for live co-editing we keep it constant
        const documentKey = paperId ? `paper-${paperId}` : `demo`

        const permissions = readOnly ? {
          edit: false,
          print: true,
          download: true,
          comment: false,
          review: false,
          fillForms: false,
        } : undefined

        const targetTheme = themeRef.current === 'dark' ? 'theme-dark' : 'theme-light'

        const config: any = {
          documentType: 'word',
          document: {
            fileType: 'docx',
            key: documentKey,
            title: paperTitle || 'ScholarHub Document',
            url: documentUrl,
            permissions,
          },
          editorConfig: {
            mode: readOnly ? 'view' : 'edit',
            lang: 'en',
            uiTheme: targetTheme,
            theme: targetTheme,
            user: { id: '1', name: 'ScholarHub User' },
            customization: {
              chat: true, // Enable built-in chat
              comments: false,
              feedback: false,
              plugins: true,
              hideRightMenu: false,
              leftMenu: true,
              rightMenu: true,
              compactToolbar: false,
              toolbarNoTabs: false,
              autosave: !readOnly,
              autosaveDelay: 600,
              forcesave: !readOnly,
              uiTheme: targetTheme,
            },
            callbackUrl: `${backendForDocServer}/onlyoffice/callback`,
          },
          width: '100%',
          height: '100%',
          events: {}
        }
        config.events.onDocumentStateChange = (payload: any) => {
          const isModified = typeof payload === 'boolean' ? payload : !!(payload && payload.data)
          try { onDirtyChange && onDirtyChange(isModified) } catch {}
          try { console.debug('[OOAdapter] onDocumentStateChange:', { isModified, raw: payload }) } catch {}
        }
        config.events.onRequestSaveAs = () => { console.debug('[OOAdapter] onRequestSaveAs'); return true }
        config.events.onRequestSave = () => {
          if (!readOnly) {
            try {
              console.debug('[OOAdapter] onRequestSave -> forceSave')
              if (docEditorRef.current && typeof docEditorRef.current.forceSave === 'function') {
                docEditorRef.current.forceSave()
              }
            } catch (e) { console.warn('[OOAdapter] onRequestSave forceSave failed', e) }
          }
          return true
        }
        config.events.onError = (event: any) => {
          try { console.error('[OOAdapter] onError:', event) } catch {}
        }
        config.events.onRequestClose = () => {
          if (!readOnly) {
            try {
              if (docEditorRef.current && typeof docEditorRef.current.forceSave === 'function') {
                docEditorRef.current.forceSave()
              }
            } catch {}
          }
          // Let the editor close normally
          return true
        }

        // Clear any existing editor in the container
        if (docEditorRef.current) {
          try { docEditorRef.current.destroyEditor() } catch {}
          docEditorRef.current = null
        }
        const hostId = editorIdRef.current
        const hostEl = document.getElementById(hostId)
        if (hostEl) hostEl.innerHTML = ''

        docEditorRef.current = new window.DocsAPI!.DocEditor(hostId, config)
        setLoading(false)
      } catch (e: any) {
        setError(e?.message || 'OnlyOffice failed to initialize')
        setLoading(false)
      }
    }
    init()
    return () => {
      cancelled = true
      if (docEditorRef.current) {
        if (!readOnly) {
          try {
            if (typeof docEditorRef.current.forceSave === 'function') {
              docEditorRef.current.forceSave()
            }
          } catch {}
        }
        try { docEditorRef.current.destroyEditor() } catch {}
        docEditorRef.current = null
      }
    }
  }, [paperId, paperTitle, readOnly])

  useEffect(() => {
    if (!docEditorRef.current) return
    const targetTheme = theme === 'dark' ? 'theme-dark' : 'theme-light'
    try {
      if (typeof docEditorRef.current.setTheme === 'function') {
        docEditorRef.current.setTheme(targetTheme)
      } else if (typeof docEditorRef.current.refreshUserInterface === 'function') {
        docEditorRef.current.refreshUserInterface({ uiTheme: targetTheme })
      }
    } catch (error) {
      console.warn('[OOAdapter] Failed to apply theme dynamically', error)
    }
  }, [theme])

  // Bridge messaging: listen for plugin READY and responses
  useEffect(() => {
    const allowedPluginOrigin = (() => {
      try { return new URL(import.meta.env.VITE_ONLYOFFICE_URL || 'http://localhost:8080').origin } catch { return 'http://localhost:8080' }
    })()
    async function afterReady(){
      try {
        // Initialize bridge with our app origin and verify with ping
        const wnd = pluginWinRef.current
        if (!wnd) return
        wnd.postMessage({ __shbridge: true, type: 'SH_BRIDGE_INIT', allowedOrigin: window.location.origin }, allowedPluginOrigin)
        // Ping will be sent via sendBridge once origin is configured
        setTimeout(async () => { try { await sendBridge('ping') } catch (e) { console.warn('Bridge ping failed', e) } }, 100)
      } catch {}
    }
    function onMessage(evt: MessageEvent){
      const data: any = evt.data || {}
      if (!data || !data.__shbridge) return
      if (evt.origin !== allowedPluginOrigin) return
      if (data.type === 'SH_BRIDGE_READY'){
        pluginWinRef.current = evt.source as Window
        pluginOriginRef.current = evt.origin || allowedPluginOrigin
        afterReady()
        return
      }
      if (data.type === 'SH_BRIDGE_RESP' || data.type === 'SH_BRIDGE_INIT_ACK'){
        const reqId = data.requestId
        if (reqId && pendingRef.current.has(reqId)){
          const entry = pendingRef.current.get(reqId)!
          pendingRef.current.delete(reqId)
          if (data.ok) entry.resolve(data.result)
          else entry.reject(new Error(data.error || 'Bridge error'))
        }
      }
    }
    window.addEventListener('message', onMessage)
    return () => { window.removeEventListener('message', onMessage) }
  }, [])

  function sendBridge(cmd: string, payload?: any): Promise<any> {
    return new Promise((resolve, reject) => {
      const wnd = pluginWinRef.current
      if (!wnd){ return reject(new Error('Bridge not ready')) }
      const requestId = Math.random().toString(36).slice(2)
      pendingRef.current.set(requestId, { resolve, reject })
      try {
        wnd.postMessage({ __shbridge: true, type: 'SH_BRIDGE_CMD', cmd, requestId, ...(payload||{}) }, pluginOriginRef.current || '*')
      } catch (e){ pendingRef.current.delete(requestId); reject(e) }
      // Optional timeout
      setTimeout(() => {
        if (pendingRef.current.has(requestId)){
          pendingRef.current.delete(requestId)
          reject(new Error('Bridge timeout'))
        }
      }, 8000)
    })
  }

  useImperativeHandle(ref, () => ({
    async getSelection() {
      try { return await sendBridge('getSelection') } catch { return '' }
    },
    async insertText(text: string) {
      if (readOnly) return
      try { await sendBridge('insertText', { text }) } catch (e){ alert('Insert failed (bridge): '+ (e as any)?.message) }
    },
    async replaceSelection(text: string) {
      if (readOnly) return
      try { await sendBridge('replaceSelection', { text }) } catch (e){ alert('Replace selection failed (bridge): '+ (e as any)?.message) }
    },
    async setContent(_html: string) {
      // Not supported; OnlyOffice requires server-side document replace. No-op silently.
      return
    },
    async save() {
      if (readOnly) return Promise.resolve()
      try {
        if (docEditorRef.current && typeof docEditorRef.current.forceSave === 'function') {
          console.log('OOAdapter.save: invoking forceSave')
          docEditorRef.current.forceSave()
        } else {
          console.log('OOAdapter.save: no forceSave available; relying on autosave')
        }
      } catch (e) {
        console.warn('OOAdapter.save: forceSave failed', e)
      }
      return Promise.resolve()
    },
    async insertHTML(html: string) {
      if (readOnly) return
      // Fallback to plain text for OO via bridge
      const tmp = document.createElement('div')
      tmp.innerHTML = html || ''
      const text = (tmp.textContent || '').trim()
      if (text) { await (this as any).insertText?.(text) }
    },
    async insertBibliography(heading: string, items: string[]) {
      if (readOnly) return
      try { await sendBridge('insertBibliography', { heading, items }) } catch (e){ alert('Insert bibliography failed (bridge): '+ (e as any)?.message) }
    },
    focus() {
      try { containerRef.current?.querySelector('iframe')?.focus() } catch {}
    },
  }), [readOnly])

  const containerClassName = ['relative', className].filter(Boolean).join(' ')

  return (
    <div ref={containerRef} className={containerClassName} style={{ height: '100%', minHeight: '600px' }}>
      <div id={editorIdRef.current} style={{ width: '100%', height: '100%' }} />
      {loading && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-white/60 text-sm text-gray-600 dark:bg-slate-950/60 dark:text-slate-200">Loading OnlyOffice…</div>
      )}
      {error && (
        <div className="absolute inset-0 z-20 flex items-center justify-center">
          <div className="rounded-md border border-red-200 bg-white px-3 py-2 text-sm text-red-600">
            {error}
          </div>
        </div>
      )}
    </div>
  )
})

export default OOAdapter
