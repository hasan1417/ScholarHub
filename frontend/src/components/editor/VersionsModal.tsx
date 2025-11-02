import React, { useEffect, useState } from 'react'
import { researchPapersAPI } from '../../services/api'

interface VersionsModalProps {
  paperId: string
  open: boolean
  onClose: () => void
  onLoadVersion: (content: string) => void
  currentVersion?: string
  pendingVersion?: string
  onPromote?: (versionNumber: string) => void | Promise<void>
}

const VersionsModal: React.FC<VersionsModalProps> = ({ paperId, open, onClose, onLoadVersion, currentVersion, pendingVersion, onPromote }) => {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [versions, setVersions] = useState<any[]>([])
  const [current, setCurrent] = useState<string | null>(currentVersion || null)
  const [tab, setTab] = useState<'commits' | 'autosave'>('commits')
  const autosave = versions.filter(v => String(v.version_number || '').startsWith('autosave-'))
  const commitVersions = versions.filter(v => !String(v.version_number || '').startsWith('autosave-'))

  useEffect(() => {
    if (!open) return
    let cancelled = false
    const run = async () => {
      try {
        setLoading(true)
        setError(null)
        const resp = await researchPapersAPI.getPaperVersions(paperId)
        if (cancelled) return
        const respData = resp?.data as { versions?: any[]; current_version?: string | null } | undefined
        setVersions((respData?.versions || []) as any[])
        setCurrent(respData?.current_version || currentVersion || null)
      } catch (e: any) {
        if (!cancelled) setError(e?.message || 'Failed to load versions')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [open, paperId, currentVersion])

  useEffect(() => {
    if (open) {
      setCurrent(currentVersion || null)
    }
  }, [currentVersion, open])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 bg-black bg-opacity-30 flex items-center justify-center" onClick={onClose}>
      <div className="bg-white w-[720px] max-h-[80vh] rounded-lg shadow-xl overflow-hidden" onClick={e=>e.stopPropagation()}>
        <div className="px-4 py-3 border-b flex items-center justify-between">
          <div className="text-base font-semibold">Versions</div>
          <button className="text-sm px-2 py-1 border rounded" onClick={onClose}>Close</button>
        </div>
        {loading && <div className="p-4 text-sm text-gray-600">Loading…</div>}
        {error && <div className="p-4 text-sm text-red-700">{error}</div>}
        {!loading && !error && (
          <div className="p-2 overflow-auto" style={{ maxHeight: 'calc(80vh - 56px)' }}>
            <div className="flex items-center gap-2 px-1 pb-2">
              <button
                className={`text-xs px-2 py-1 rounded-md border ${tab === 'commits' ? 'border-blue-500 text-blue-600 bg-blue-50' : 'border-slate-200 text-slate-600'}`}
                onClick={() => setTab('commits')}
              >Saved commits</button>
              <button
                className={`text-xs px-2 py-1 rounded-md border ${tab === 'autosave' ? 'border-blue-500 text-blue-600 bg-blue-50' : 'border-slate-200 text-slate-600'}`}
                onClick={() => setTab('autosave')}
              >Autosaves</button>
            </div>
            {pendingVersion && (
              <div className="px-3 py-2 mb-2 text-xs rounded-md border border-amber-300 bg-amber-50 text-amber-700">
                Version {pendingVersion} is awaiting approval. Promote it to make it the default.
              </div>
            )}
            {tab === 'commits' && commitVersions.length === 0 ? (
              <div className="p-4 text-sm text-gray-500">No versions yet.</div>
            ) : tab === 'commits' ? (
              <div className="divide-y">
                {commitVersions.map((v: any, idx: number) => {
                  const when = v.created_at ? new Date(v.created_at).toLocaleString() : ''
                  const label = v.version_number || 'Version'
                  const summary = v.change_summary || ''
                  const author = v.created_by || ''
                  const len = (v.content_json && typeof v.content_json.latex_source === 'string') ? v.content_json.latex_source.length : (v.content || '').length
                  const isCurrent = current ? v.version_number === current : false
                  const isPending = !isCurrent && pendingVersion ? v.version_number === pendingVersion : (!isCurrent && idx === 0)
                  return (
                    <div key={v.id} className="px-3 py-2 flex items-start gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gray-900 truncate">{label}</div>
                        <div className="text-[11px] text-gray-600">{when}{author ? ` • by ${author}` : ''}{len ? ` • ${len} chars` : ''}</div>
                        <div className="flex items-center gap-2 mt-1 flex-wrap">
                          {summary && <span className="text-xs text-gray-700">{summary}</span>}
                          {isCurrent && (
                            <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 border border-emerald-200">Default</span>
                          )}
                          {isPending && (
                            <span className="text-[11px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-200">Awaiting approval</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button className="px-2 py-1 text-xs border rounded" onClick={() => {
                          const content = (v.content_json && v.content_json.latex_source) ? v.content_json.latex_source : (v.content || '')
                          onLoadVersion(content || '')
                          onClose()
                        }}>Load</button>
                        {!isCurrent && (
                          <button className="px-2 py-1 text-xs border rounded bg-purple-600 text-white hover:bg-purple-700" onClick={async () => {
                            try {
                              await researchPapersAPI.restorePaperVersion(paperId, v.version_number)
                              const resp = await researchPapersAPI.getPaperVersions(paperId)
                              setError(null)
                              const respData = resp?.data as { versions?: any[]; current_version?: string | null } | undefined
                              setVersions((respData?.versions || []) as any[])
                              setCurrent(respData?.current_version || v.version_number)
                              if (onPromote) await onPromote(v.version_number)
                            } catch (e: any) {
                              setError(e?.message || 'Failed to promote version')
                            }
                          }}>{isPending ? 'Make Default' : 'Set Default'}</button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : autosave.length === 0 ? (
              <div className="p-4 text-sm text-gray-500">Autosave history will appear here once realtime edits occur.</div>
            ) : (
              <div className="divide-y">
                {autosave.map((v: any) => {
                  const when = v.created_at ? new Date(v.created_at).toLocaleString() : ''
                  const label = v.version_number || 'Autosave'
                  const len = (v.content_json && v.content_json.latex_source) ? v.content_json.latex_source.length : (v.content || '').length
                  return (
                    <div key={v.id} className="px-3 py-2 flex items-start gap-3 text-xs text-slate-600">
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-slate-700 truncate">{label}</div>
                        <div>{when}{len ? ` • ${len} chars` : ''}</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button className="px-2 py-1 text-xs border rounded" onClick={() => {
                          const content = (v.content_json && v.content_json.latex_source) ? v.content_json.latex_source : (v.content || '')
                          onLoadVersion(content || '')
                          onClose()
                        }}>Load</button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default VersionsModal
