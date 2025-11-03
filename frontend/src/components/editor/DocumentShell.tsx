import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { EditorAdapterHandle, EditorAdapterProps } from './adapters/EditorAdapter'
import BranchManager from './BranchManager'
import MergeView from './MergeView'
import VersionsModal from './VersionsModal'
import ChangesSidebar from './ChangesSidebar'
import { useAuth } from '../../contexts/AuthContext'
import { branchService } from '../../services/branchService'
import { researchPapersAPI, teamAPI } from '../../services/api'
import { fetchCollabToken } from '../../services/collabService'
import { isCollabEnabled } from '../../config/collab'
import { useCollabProvider } from '../../hooks/useCollabProvider'
import { useThemePreference } from '../../hooks/useThemePreference'
import EnhancedAIWritingTools from './EnhancedAIWritingTools'

type AdapterComponent = React.ForwardRefExoticComponent<EditorAdapterProps & React.RefAttributes<EditorAdapterHandle>>

interface DocumentShellProps {
  paperId: string
  projectId?: string
  paperTitle?: string
  initialContent?: string | any
  initialContentJson?: any
  Adapter: AdapterComponent
  fullBleed?: boolean
  onHostContentChange?: (html: string, json?: any) => void
  initialPaperRole?: 'admin' | 'editor' | 'viewer'
  forceReadOnly?: boolean
}

const DocumentShell: React.FC<DocumentShellProps> = ({ paperId, projectId, paperTitle, initialContent = '', initialContentJson, Adapter, fullBleed = false, onHostContentChange, initialPaperRole, forceReadOnly = false }) => {
  const navigate = useNavigate()
  const { user } = useAuth()
  const adapterRef = useRef<EditorAdapterHandle>(null)
  const { theme } = useThemePreference()
  const [selection, setSelection] = useState('')
  const [branchOpen, setBranchOpen] = useState(false)
  const [mergeOpen, setMergeOpen] = useState(false)
  const [currentBranchId, setCurrentBranchId] = useState<string | undefined>(undefined)
  // One-mode workflow
  const [baselinePublished, setBaselinePublished] = useState<string>('')
  const [commitOpen, setCommitOpen] = useState(false)
  const [commitMessage, setCommitMessage] = useState('')
  const [outlineOpen, setOutlineOpen] = useState(false)
  const [sectionLocks, setSectionLocks] = useState<Record<string, { userName: string; expiresAt: string }>>({})
  const [lastHtml, setLastHtml] = useState('')
  const [toast, setToast] = useState<{ visible: boolean; text: string }>({ visible: false, text: '' })
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [pendingVersion, setPendingVersion] = useState<string | null>(null)
  const [currentVersion, setCurrentVersion] = useState<string | null>(null)
  const fallbackRole: 'admin' | 'editor' | 'viewer' = forceReadOnly ? 'viewer' : (initialPaperRole ?? 'viewer')
  const [paperRole, setPaperRole] = useState<'admin' | 'editor' | 'viewer'>(fallbackRole)
  const [aiPanelOpen, setAiPanelOpen] = useState(false)
  const [aiAnchor, setAiAnchor] = useState<HTMLElement | null>(null)
  const readOnly = forceReadOnly || paperRole === 'viewer'
  const collabFeatureEnabled = useMemo(() => isCollabEnabled(), [])
  const [collabToken, setCollabToken] = useState<{ token: string; ws_url?: string } | null>(null)
  const [collabPeers, setCollabPeers] = useState<Array<{ id: string; name: string; email: string; color?: string }>>([])
  const [collabStatusMessage, setCollabStatusMessage] = useState<string | null>(null)
  const [collabTokenVersion, setCollabTokenVersion] = useState(0)
  const showToast = (text: string) => {
    setToast({ visible: true, text })
    setTimeout(() => setToast({ visible: false, text: '' }), 3000)
  }
  const contentWrapRef = useRef<HTMLDivElement>(null)
  const [containerH, setContainerH] = useState<number>(600)
  const isLatex = Boolean(initialContentJson && typeof initialContentJson === 'object' && (initialContentJson as any).authoring_mode === 'latex')
  const initialLatexSource = useMemo(() => {
    if (!isLatex) return ''
    return typeof initialContentJson?.latex_source === 'string' ? initialContentJson?.latex_source : ''
  }, [initialContentJson, isLatex])
  // No global paper id; pass through props

  useEffect(() => {
    if (typeof window !== 'undefined') {
      console.info('[DocumentShell] collab state', {
        collabFeatureEnabled,
        readOnly,
        paperId,
        hasToken: Boolean(collabToken?.token),
      })
    }
  }, [collabFeatureEnabled, readOnly, paperId, collabToken?.token])

  useEffect(() => {
    const calc = () => {
      try {
        const top = contentWrapRef.current?.getBoundingClientRect().top || 0
        const vh = window.innerHeight || 800
        const h = Math.max(360, vh - top - 12)
        setContainerH(h)
      } catch {}
    }
    calc()
    window.addEventListener('resize', calc)
    return () => window.removeEventListener('resize', calc)
  }, [])

  // Branchless workflow: no-op placeholder to keep state consistent
  useEffect(() => {
    setCurrentBranchId(undefined)
  }, [paperId])

  const collab = useCollabProvider({
    paperId,
    enabled: !readOnly && Boolean(collabToken?.token),
    token: collabToken?.token ?? null,
    wsUrl: collabToken?.ws_url ?? null,
  })
  const collabBootstrappedRef = useRef(false)
  useEffect(() => {
    collabBootstrappedRef.current = false
  }, [collab.doc, collab.enabled])

  useEffect(() => {
    if (!collabFeatureEnabled || readOnly || !paperId) {
      setCollabToken(null)
      setCollabStatusMessage(null)
      return
    }

    const controller = new AbortController()
    let isMounted = true

    const loadToken = async () => {
      try {
        const data = await fetchCollabToken(paperId, controller.signal)
        if (!isMounted) return
        setCollabToken({ token: data.token, ws_url: data.ws_url })
        setCollabStatusMessage(null)
      } catch (error: any) {
        if (controller.signal.aborted || !isMounted) return
        console.warn('[DocumentShell] failed to fetch collab token', error)
        setCollabToken(null)
        setCollabStatusMessage('Collaboration unavailable')
      }
    }

    loadToken()

    return () => {
      isMounted = false
      controller.abort()
    }
  }, [collabFeatureEnabled, paperId, readOnly, collabTokenVersion])

  useEffect(() => {
    let cancelled = false

    const loadRole = async () => {
      if (forceReadOnly) {
        setPaperRole('viewer')
        return
      }
      if (!paperId) {
        setPaperRole(fallbackRole)
        return
      }
      try {
        const response = await teamAPI.getTeamMembers(paperId)
        const members = Array.isArray(response.data) ? response.data : []
        const match = members.find((member: any) => member.user_id === user?.id)
        if (!match) {
          if (!cancelled) {
            setPaperRole(fallbackRole)
          }
          return
        }
        const rawRole = (match?.role || 'viewer').toLowerCase()
        const normalized = rawRole === 'reviewer'
          ? 'viewer'
          : rawRole === 'owner'
            ? 'admin'
            : (rawRole as 'admin' | 'editor' | 'viewer')
        if (!cancelled) {
          setPaperRole(normalized || fallbackRole)
        }
      } catch (err) {
        if (!cancelled) {
          setPaperRole(prev => prev || fallbackRole)
        }
      }
    }

    loadRole()

    return () => {
      cancelled = true
    }
  }, [paperId, user?.id, fallbackRole, forceReadOnly])

  useEffect(() => {
    setPaperRole(forceReadOnly ? 'viewer' : fallbackRole)
  }, [fallbackRole, forceReadOnly, paperId])

  useEffect(() => {
    const awareness = collab.awareness
    if (!awareness || !collab.enabled) {
      setCollabPeers([])
      return
    }

    const updatePeers = () => {
      const next: Array<{ id: string; name: string; email: string; color?: string }> = []
      awareness.getStates().forEach((state: any, clientId: number) => {
        if (clientId === awareness.clientID) return
        const userState = state?.user || {}
        next.push({
          id: userState.id ?? String(clientId),
          name: userState.name ?? userState.email ?? 'Collaborator',
          email: userState.email ?? userState.name ?? 'collaborator@local',
          color: userState.color ?? '#3B82F6',
        })
      })
      setCollabPeers(next)
    }

    updatePeers()
    awareness.on('update', updatePeers)

    return () => {
      awareness.off('update', updatePeers)
    }
  }, [collab.awareness, collab.enabled])

  useEffect(() => {
    if (!collab.awareness || !collab.enabled) return

    const displayName = [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email || 'You'

    try {
      collab.awareness.setLocalStateField('user', {
        id: user?.id ?? 'current-user',
        name: displayName,
        email: user?.email || 'you@local',
        color: '#3B82F6',
      })
    } catch (error) {
      console.warn('[DocumentShell] failed to set local collaboration state', error)
    }

    return () => {
      try {
        collab.awareness?.setLocalStateField('user', null)
      } catch {}
    }
  }, [collab.awareness, collab.enabled, user?.email, user?.first_name, user?.last_name, user?.id])

  useEffect(() => {
    if (!collabFeatureEnabled || readOnly) return
    if (collab.status === 'disconnected' && collabToken) {
      setCollabToken(null)
      setCollabTokenVersion(v => v + 1)
    }
  }, [collab.status, collabFeatureEnabled, readOnly, collabToken])

  useEffect(() => {
    if (!collab.enabled || !collab.doc) return
    if (collabBootstrappedRef.current) return
    if (collab.status !== 'connected') return
    if (!collab.providerVersion) return

    const yText = collab.doc.getText('main')
    try {
      const current = yText.toString()
      if (typeof initialLatexSource === 'string' && initialLatexSource.length > 0 && current !== initialLatexSource) {
        yText.delete(0, current.length)
        yText.insert(0, initialLatexSource)
      } else if (current.length === 0 && initialLatexSource) {
        yText.insert(0, initialLatexSource)
      }
    } catch (error) {
      console.warn('[DocumentShell] failed to align collab doc with initial content', error)
    }

    collabBootstrappedRef.current = true
  }, [collab.enabled, collab.doc, collab.status, collab.providerVersion, initialLatexSource])

  useEffect(() => {
    if (!collabFeatureEnabled || readOnly) return
    if (collab.status === 'connected') {
      setCollabStatusMessage(prev => (prev === 'Collaboration unavailable' ? prev : null))
    } else if (collab.status === 'disconnected') {
      setCollabStatusMessage('Collaboration offline')
    } else if (collab.status === 'connecting') {
      setCollabStatusMessage(prev => (prev === 'Collaboration unavailable' ? prev : null))
    }
  }, [collab.status, collabFeatureEnabled, readOnly])

  // Removed mode-based content injection in one-mode workflow

  const realtimeContext = useMemo(() => {
    if (!collab.enabled || !collab.doc) return undefined
    return {
      doc: collab.doc,
      awareness: collab.awareness ?? null,
      provider: collab.provider ?? null,
      status: collab.status,
      peers: collabPeers,
      version: collab.providerVersion ?? 0,
    }
  }, [collab.awareness, collab.doc, collab.enabled, collab.status, collab.providerVersion, collabPeers])

  const handleContentChange = (html: string, json?: any) => {
    console.log('[DocumentShell] 🔄 handleContentChange called:', {
      htmlLength: html?.length || 0,
      hasJson: Boolean(json),
      isLatex,
      latexSourceLength: json?.latex_source?.length || 0,
      paperId,
      timestamp: new Date().toISOString()
    })
    
    // Hook for autosave or collaboration in later milestones
    ;(window as any).__SH_LAST_HTML = html
    ;(window as any).__SH_LAST_JSON = json
    try { setLastHtml(html || '') } catch {}
    // Compute hasChanges vs baseline
    try { onHostContentChange?.(html, json) } catch {}
  }

  const refreshVersions = useCallback(async () => {
    try {
      const pv = await researchPapersAPI.getPaperVersions(paperId)
      const pvData = pv?.data as { versions?: any[]; current_version?: string | null } | undefined
      const list = (pvData?.versions || []) as Array<Record<string, any>>
      const current = pvData?.current_version || (list[0]?.version_number ?? null)
      setCurrentVersion(current || null)
      const currentEntry = current ? list.find((v: any) => v.version_number === current) : null
      const baselineSource = currentEntry
        ? ((currentEntry.content_json && currentEntry.content_json.latex_source)
            ? currentEntry.content_json.latex_source
            : (currentEntry.content || ''))
        : ''
      setBaselinePublished(baselineSource || '')
      const latest = list[0]
      if (latest && latest.version_number && latest.version_number !== current) {
        setPendingVersion(latest.version_number)
      } else {
        setPendingVersion(null)
      }
    } catch (e) {
      console.warn('Failed to refresh versions', e)
    }
  }, [paperId])

  // Load initial content once from the server (fallback for non-realtime or pre-CRDT bootstrap)
  useEffect(() => {
    let mounted = true
    ;(async () => {
      try {
        const resp = await researchPapersAPI.getPaper(paperId)
        const data: any = resp.data || {}
        const isLatexMode = Boolean(data?.content_json && typeof data.content_json === 'object' && data.content_json.authoring_mode === 'latex')
        const latexSource: string = isLatexMode ? (data.content_json?.latex_source || '') : ''
        const richHtml: string = !isLatexMode ? (data.content || '') : ''
        if (!mounted) return
        const working = isLatexMode ? (latexSource || '') : (richHtml || '')
        setLastHtml(working)
        adapterRef.current?.setContent?.(working)
        await refreshVersions()
      } catch (e) {
        console.warn('Failed to load paper content for shell', e)
      }
    })()
    return () => { mounted = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paperId, refreshVersions])

  const handleNavigateBack = useCallback(() => {
    navigate(projectId ? `/projects/${projectId}/papers/${paperId}` : '/projects')
  }, [navigate, projectId, paperId])

  const handleOpenReferences = useCallback(() => {
    /* references sidebar disabled */
  }, [])

  const handleInsertBibliographyShortcut = useCallback(() => {
    if (readOnly) return
    const snippet = '\n\\bibliographystyle{plain}\n\\bibliography{references}\n'
    adapterRef.current?.insertText(snippet)
  }, [readOnly])

  const handleOpenAiAssistant = useCallback((anchor: HTMLElement | null) => {
    if (readOnly) return
    setAiAnchor(anchor)
    setAiPanelOpen(true)
  }, [readOnly])

  const rootCls = fullBleed
    ? 'fixed inset-0 flex flex-col overflow-auto bg-slate-100 transition-colors duration-200 dark:bg-slate-900'
    : 'min-h-screen flex flex-col overflow-auto bg-slate-100 transition-colors duration-200 dark:bg-slate-900'

  const collaborationStatus = useMemo(() => {
    if (!collabFeatureEnabled || readOnly) return null
    if (collabStatusMessage) return collabStatusMessage
    switch (collab.status) {
      case 'connected':
        return 'Collaboration active'
      case 'connecting':
        return 'Connecting collaborators…'
      case 'disconnected':
        return 'Collaboration offline'
      case 'idle':
      default:
        return 'Collaboration idle'
    }
  }, [collab.status, collabStatusMessage, collabFeatureEnabled, readOnly])

  return (
    <div className={rootCls}>
      <div className="pointer-events-none absolute top-20 right-4 z-30 flex flex-col items-end gap-2">
        {toast?.visible && (
          <div className="pointer-events-auto rounded-md border border-green-300 bg-green-100 px-3 py-1 text-[11px] font-medium text-green-800 shadow dark:border-green-500/50 dark:bg-green-500/10 dark:text-green-200">
            {toast.text}
          </div>
        )}
        {pendingVersion && (
          <div className="pointer-events-auto flex items-center gap-3 rounded-md bg-white/80 px-2.5 py-1.5 shadow backdrop-blur dark:bg-slate-800/80 dark:text-slate-100">
            <button
              className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-[11px] font-medium text-amber-700 hover:bg-amber-100"
              onClick={() => setVersionsOpen(true)}
            >
              Version {pendingVersion} ready — review versions
            </button>
          </div>
        )}
      </div>

      <div
        ref={contentWrapRef}
        className="flex-1 min-h-0 flex flex-col p-0"
        style={fullBleed ? { } : { height: containerH }}
      >
        <Adapter
          ref={adapterRef}
          content={initialContent || ''}
          contentJson={initialContentJson}
          paperId={paperId}
          projectId={projectId}
          paperTitle={paperTitle}
          onContentChange={handleContentChange}
          onSelectionChange={setSelection}
          className="h-full"
          lockedSectionKeys={Object.keys(sectionLocks)}
          readOnly={readOnly}
          onNavigateBack={handleNavigateBack}
          onOpenReferences={handleOpenReferences}
          onOpenAiAssistant={handleOpenAiAssistant}
          onInsertBibliographyShortcut={handleInsertBibliographyShortcut}
          realtime={realtimeContext}
          collaborationStatus={collaborationStatus}
          theme={theme}
        />
      </div>

      {branchOpen && (
        <div className="fixed inset-0 z-50 bg-black bg-opacity-30 flex items-center justify-center" onClick={() => setBranchOpen(false)}>
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-[800px] p-4" onClick={(e)=>e.stopPropagation()}>
            <BranchManager
              paperId={paperId}
              currentBranchId={currentBranchId}
              onBranchSwitch={async (_branchId) => { /* adapter will reload via onContentUpdate */ }}
              onContentUpdate={async (html) => { await adapterRef.current?.setContent?.(html); setLastHtml(html || '') }}
            />
          </div>
        </div>
      )}

      {outlineOpen && (
        <ChangesSidebar
          paperId={paperId}
          content={lastHtml}
          baseline={baselinePublished}
          onRevertAll={async () => { try { await adapterRef.current?.setContent?.(baselinePublished || ''); setLastHtml(baselinePublished || '') } catch {} }}
          lockedKeys={sectionLocks}
          onClose={()=> setOutlineOpen(false)}
          onJumpToLine={(line)=> adapterRef.current?.scrollToLine?.(line)}
          onReplaceLines={(from,to,text)=> adapterRef.current?.replaceLines?.(from,to,text)}
          onLockToggle={(key, lock)=> {
            setSectionLocks(prev => {
              const next = { ...prev }
              if (lock) {
                next[key] = { userName: user?.email || 'You', expiresAt: '' }
              } else {
                delete next[key]
              }
              return next
            })
          }}
        />
      )}

      {mergeOpen && (
        <div className="fixed inset-0 z-50 bg-black bg-opacity-30 flex items-center justify-center" onClick={() => setMergeOpen(false)}>
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-[900px] p-4" onClick={(e)=>e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <div className="text-base font-semibold">Merge</div>
              <button className="text-sm px-2 py-1 border rounded" onClick={() => setMergeOpen(false)}>Close</button>
            </div>
            <MergeView
              paperId={paperId}
              onMerged={async (merged) => { await adapterRef.current?.setContent?.(merged); setMergeOpen(false) }}
            />
          </div>
        </div>
      )}

      {commitOpen && (
        <div className="fixed inset-0 z-50 bg-black bg-opacity-30 flex items-center justify-center" onClick={() => setCommitOpen(false)}>
          <div className="bg-white rounded-lg shadow-xl w-[560px] p-5" onClick={(e)=>e.stopPropagation()}>
            <div className="text-lg font-semibold mb-2">Commit Changes</div>
            <div className="text-sm text-gray-600 mb-3">Current branch: <span className="font-mono">{currentBranchId || 'unknown'}</span></div>
            <textarea
              className="w-full border border-gray-300 rounded-md p-2 text-sm mb-3"
              rows={3}
              placeholder="Commit message"
              value={commitMessage}
              onChange={e => setCommitMessage(e.target.value)}
            />
            <div className="flex justify-end gap-2">
              <button className="px-3 py-1.5 border rounded-md" onClick={() => setCommitOpen(false)}>Cancel</button>
              <button
                className="px-3 py-1.5 rounded-md bg-blue-600 text-white"
                onClick={async () => {
                    try {
                    if (!currentBranchId) throw new Error('No branch selected')
                    let commitContent = lastHtml || ''
                    let commitContentJson: any = undefined
                    if (isLatex) {
                      commitContentJson = {
                        authoring_mode: 'latex',
                        latex_source: commitContent,
                      }
                    }
                    await branchService.commitChanges(currentBranchId, commitMessage || 'Update', commitContent, commitContentJson)
                    try {
                      await refreshVersions()
                    } catch (err) {
                      console.warn('[DocumentShell] failed to refresh versions after commit', err)
                    }
                    setCommitOpen(false)
                    setCommitMessage('')
                  } catch (e) { console.error('Commit failed', e) }
                }}
              >Commit</button>
            </div>
          </div>
        </div>
      )}

      <VersionsModal
        paperId={paperId}
        open={versionsOpen}
        currentVersion={currentVersion || undefined}
        pendingVersion={pendingVersion || undefined}
        onClose={() => setVersionsOpen(false)}
        onLoadVersion={async (content) => { try { await adapterRef.current?.setContent?.(content) } catch {} }}
        onPromote={async () => {
          await refreshVersions()
          showToast('Default version updated')
        }}
      />

      {/* AI Writing Assistant: floating UI that uses adapter APIs */}
      <EnhancedAIWritingTools
        selectedText={selection || ''}
        onReplaceText={(text) => adapterRef.current?.replaceSelection?.(text || '')}
        onInsertText={(text) => adapterRef.current?.insertText(text || '')}
        currentPaperContent={lastHtml}
        onCitationInsert={(c) => adapterRef.current?.insertText(c || '')}
        open={!readOnly && aiPanelOpen}
        onOpenChange={(next) => setAiPanelOpen(readOnly ? false : next)}
        showLauncher={false}
        anchorElement={aiAnchor}
      />
    </div>
  )
}

export default DocumentShell
