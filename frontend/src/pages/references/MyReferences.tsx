import React, { useEffect, useState } from 'react'
import { referencesAPI, researchPapersAPI, usersAPI } from '../../services/api'
import { Link } from 'react-router-dom'
import ZoteroImportModal from '../../components/references/ZoteroImportModal'
import { useToast } from '../../hooks/useToast'

interface RefItem {
  id: string
  title: string
  authors?: string[]
  year?: number
  doi?: string
  url?: string
  source?: string
  journal?: string
  abstract?: string
  is_open_access?: boolean
  pdf_url?: string | null
  document_id?: string | null
  paper_id?: string | null
  status: string
}

const MyReferences: React.FC = () => {
  const { toast } = useToast()
  const [items, setItems] = useState<RefItem[]>([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)
  const [uploadingId, setUploadingId] = useState<string | null>(null)
  const [attachId, setAttachId] = useState<string | null>(null)
  const [papers, setPapers] = useState<Array<{ id: string; title: string }>>([])
  const [banner, setBanner] = useState<string | null>(null)
  const [paperTitleById, setPaperTitleById] = useState<Record<string, string>>({})
  const [showAdd, setShowAdd] = useState(false)
  const [newRef, setNewRef] = useState<Partial<RefItem> & { authorsText?: string }>({ title: '', authors: [], authorsText: '', year: undefined, doi: '', url: '', source: 'manual', journal: '', abstract: '', is_open_access: false, pdf_url: '' })
  const [newPdf, setNewPdf] = useState<File | null>(null)
  const [savingNew, setSavingNew] = useState(false)
  const [zoteroConfigured, setZoteroConfigured] = useState(false)
  const [showZoteroModal, setShowZoteroModal] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const resp = await referencesAPI.listMy({ q, limit: 100 })
      const data = resp.data as { references?: RefItem[]; total?: number } | RefItem[] | null
      const list = Array.isArray(data)
        ? data
        : Array.isArray(data?.references)
          ? data.references as RefItem[]
          : []
      const totalCount = Array.isArray(data)
        ? data.length
        : Number(data?.total ?? list.length)
      setItems(list)
      setTotal(totalCount)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    usersAPI.getApiKeys().then((res) => {
      setZoteroConfigured(res.data.zotero?.configured ?? false)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    // Load user's papers for title lookup
    (async () => {
      try {
        const r = await researchPapersAPI.getPapers(0, 500)
        const raw = r.data as { papers?: Array<{ id: string; title: string }> } | null
        const list = Array.isArray(raw?.papers) ? raw!.papers : []
        setPapers(list)
        const map: Record<string, string> = {}
        list.forEach(p => { map[p.id] = p.title })
        setPaperTitleById(map)
      } catch {
        setPapers([])
        setPaperTitleById({})
      }
    })()
  }, [])

  useEffect(() => {
    // Show a banner if there are PDFs enqueued for ingestion
    const pending = items.filter(i => i.pdf_url && !i.document_id)
    if (pending.length > 0) {
      setBanner(`Auto‑ingesting ${pending.length} PDF${pending.length > 1 ? 's' : ''}… Content will appear shortly.`)
      // Light polling while ingestion is pending
      const t = window.setTimeout(() => {
        load().catch(() => void 0)
      }, 8000)
      return () => window.clearTimeout(t)
    } else {
      setBanner(null)
    }
  }, [items])

  const handleUploadPdf = async (ref: RefItem, file: File) => {
    try {
      setUploadingId(ref.id)
      await referencesAPI.uploadPdf(ref.id, file)
      await load()
    } catch (e) {
      toast.error('Failed to upload PDF')
    } finally {
      setUploadingId(null)
    }
  }

  const openAttach = async (refId: string) => {
    setAttachId(refId)
    try {
      const r = await researchPapersAPI.getPapers(0, 100)
      const raw = r.data as { papers?: Array<{ id: string; title: string }> } | null
      const list = Array.isArray(raw?.papers) ? raw!.papers : []
      setPapers(list)
    } catch {
      setPapers([])
    }
  }

  const confirmAttach = async (paperId: string) => {
    if (!attachId) return
    try {
      await referencesAPI.attachToPaper(attachId, paperId)
      setAttachId(null)
      await load()
    } catch (e) {
      toast.error('Failed to attach to paper')
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-end justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">My References</h1>
              <p className="text-gray-600 mt-1">Manage references discovered or uploaded, with optional PDFs for AI chat.</p>
            </div>
            <div className="text-sm text-gray-500">Total: {total}</div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-4">
        {banner && (
          <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-3 rounded">
            {banner}
          </div>
        )}
        <div className="bg-white p-4 rounded-md shadow-sm border flex items-center gap-3">
          <input
            placeholder="Search references (title)"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="flex-1 border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button onClick={load} className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">Search</button>
          <Link to="/discovery" className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700">Discover</Link>
          <button
            onClick={() => {
              if (zoteroConfigured) {
                setShowZoteroModal(true)
              } else {
                toast.warning('Connect your Zotero account first in Settings > Integrations.')
              }
            }}
            className="px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700"
          >
            Import from Zotero
          </button>
          <button onClick={() => setShowAdd(true)} className="px-4 py-2 bg-gray-100 border rounded hover:bg-gray-200">Add Reference</button>
        </div>

        {loading ? (
          <div className="text-center text-gray-600 py-12">Loading…</div>
        ) : items.length === 0 ? (
          <div className="text-center text-gray-600 py-12">No references yet. Use Discovery or upload PDFs.</div>
        ) : (
          <div className="bg-white border rounded-md shadow-sm">
            <div className="divide-y">
              {items.map((ref) => (
                <div key={ref.id} className="p-4 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm text-gray-500">{ref.source || 'manual'}</div>
                    <div className="font-medium text-gray-900 truncate">{ref.title}</div>
                    <div className="text-sm text-gray-600 truncate">{(ref.authors || []).join(', ')}</div>
                    <div className="text-xs text-gray-500 flex gap-3 mt-1 items-center">
                      {ref.year && <span>{ref.year}</span>}
                      {ref.doi && <a className="text-blue-600" href={`https://doi.org/${ref.doi}`} target="_blank" rel="noreferrer">DOI</a>}
                      {ref.pdf_url && (
                        ref.pdf_url!.startsWith('/api/') ? (
                          <button className="text-blue-600 underline" onClick={async () => {
                            try {
                              const token = localStorage.getItem('access_token')
                              if (!token) {
                                toast.warning('Please login again to download the PDF')
                                return
                              }
                              const resp = await fetch(ref.pdf_url!, { headers: { Authorization: `Bearer ${token}` } })
                              if (!resp.ok) throw new Error('Download failed')
                              const blob = await resp.blob()
                              const url = URL.createObjectURL(blob)
                              window.open(url, '_blank')
                              // Optional: revoke after some time
                              setTimeout(() => URL.revokeObjectURL(url), 30_000)
                            } catch (e) {
                              toast.error('Failed to open PDF')
                            }
                          }}>PDF</button>
                        ) : (
                          <a className="text-blue-600" href={ref.pdf_url!} target="_blank" rel="noreferrer">PDF</a>
                        )
                      )}
                      {ref.document_id && <span className="px-2 py-0.5 rounded bg-blue-100 text-blue-800">Content uploaded</span>}
                      <span className="uppercase text-gray-600">{ref.status}</span>
                    </div>
                    {/* Attachment info */}
                    <div className="text-xs text-gray-600 mt-2 flex flex-wrap gap-2 items-center">
                      {ref.paper_id ? (
                        <>
                          <span className="text-gray-500">Attached to:</span>
                          <Link className="text-blue-600 hover:underline" to={`/papers/${ref.paper_id}`}>
                            {paperTitleById[ref.paper_id] || ref.paper_id}
                          </Link>
                        </>
                      ) : (
                        <span className="text-gray-500">Not attached</span>
                      )}
                      {/* Also in: show other papers with same DOI among this user's references */}
                      {ref.doi && (
                        (() => {
                          const also = items.filter(r => r.id !== ref.id && r.doi === ref.doi && r.paper_id)
                          const titles = also.map(r => paperTitleById[r.paper_id!]).filter(Boolean)
                          if (titles.length > 0) {
                            return (
                              <span className="text-gray-500">• Also in: {titles.join(', ')}</span>
                            )
                          }
                          return null
                        })()
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {!ref.document_id && !(ref.is_open_access && ref.pdf_url && ref.status === 'pending') && (
                      <label className="px-3 py-1 border rounded cursor-pointer bg-gray-50 hover:bg-gray-100 text-sm">
                        {uploadingId === ref.id ? 'Uploading…' : 'Upload PDF'}
                        <input type="file" accept="application/pdf" className="hidden" onChange={(e) => {
                          const f = e.target.files?.[0]
                          if (f) handleUploadPdf(ref, f)
                        }} />
                      </label>
                    )}
                    {/* Find PDF feature removed */}
                    {(!ref.document_id && ref.is_open_access && ref.pdf_url && ref.status === 'pending') && (
                      <span className="px-3 py-1 border rounded bg-yellow-50 text-yellow-800 text-sm">Auto‑ingesting PDF…</span>
                    )}
                    <button className="px-3 py-1 border rounded bg-gray-50 hover:bg-gray-100 text-sm" onClick={() => openAttach(ref.id!)}>
                      Attach to Paper
                    </button>
                    <button className="px-3 py-1 border rounded bg-red-50 text-red-700 hover:bg-red-100 text-sm" onClick={async () => { await referencesAPI.delete(ref.id); await load() }}>
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {attachId && (
          <div className="fixed inset-0 bg-black/40 flex items-center justify-center">
            <div className="bg-white rounded-md shadow-lg p-6 w-full max-w-md">
              <div className="font-semibold mb-3">Attach to Paper</div>
              <div className="max-h-64 overflow-y-auto divide-y">
                {papers.map(p => (
                  <button key={p.id} className="w-full text-left p-2 hover:bg-gray-50" onClick={() => confirmAttach(p.id)}>
                    {p.title}
                  </button>
                ))}
              </div>
              <div className="mt-4 text-right">
                <button onClick={() => setAttachId(null)} className="px-4 py-2 border rounded">Cancel</button>
              </div>
            </div>
          </div>
        )}
      </div>

      <ZoteroImportModal
        isOpen={showZoteroModal}
        onClose={() => setShowZoteroModal(false)}
        onImportComplete={() => load()}
      />

      {showAdd && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-md shadow-lg w-full max-w-2xl">
            <div className="px-4 py-3 border-b font-semibold">Add Reference</div>
            <div className="p-4 grid grid-cols-2 gap-4 text-sm">
              <div className="col-span-2">
                <label className="block text-gray-600 mb-1">Title <span className="text-red-500">*</span></label>
                <input className="w-full border rounded px-3 py-2" value={newRef.title || ''} onChange={e => setNewRef({ ...newRef, title: e.target.value })} placeholder="Paper title" />
              </div>
              <div className="col-span-2">
                <label className="block text-gray-600 mb-1">Authors</label>
                <input className="w-full border rounded px-3 py-2" value={newRef.authorsText || ''} onChange={e => setNewRef({ ...newRef, authorsText: e.target.value })} placeholder="Comma-separated (e.g., Jane Doe, John Smith)" />
              </div>
              <div>
                <label className="block text-gray-600 mb-1">Year</label>
                <input type="number" className="w-full border rounded px-3 py-2" value={newRef.year || ''} onChange={e => setNewRef({ ...newRef, year: e.target.value ? parseInt(e.target.value, 10) : undefined })} placeholder="2023" />
              </div>
              <div>
                <label className="block text-gray-600 mb-1">Journal</label>
                <input className="w-full border rounded px-3 py-2" value={newRef.journal || ''} onChange={e => setNewRef({ ...newRef, journal: e.target.value })} placeholder="Journal name" />
              </div>
              <div>
                <label className="block text-gray-600 mb-1">DOI</label>
                <input className="w-full border rounded px-3 py-2" value={newRef.doi || ''} onChange={e => setNewRef({ ...newRef, doi: e.target.value })} placeholder="10.xxxx/xxxxx" />
              </div>
              <div>
                <label className="block text-gray-600 mb-1">URL</label>
                <input className="w-full border rounded px-3 py-2" value={newRef.url || ''} onChange={e => setNewRef({ ...newRef, url: e.target.value })} placeholder="https://..." />
              </div>
              <div>
                <label className="block text-gray-600 mb-1">Source</label>
                <input className="w-full border rounded px-3 py-2" value={newRef.source || 'manual'} onChange={e => setNewRef({ ...newRef, source: e.target.value })} placeholder="semantic_scholar / openalex / manual" />
              </div>
              <div>
                <label className="block text-gray-600 mb-1">Open Access</label>
                <input type="checkbox" checked={!!newRef.is_open_access} onChange={e => setNewRef({ ...newRef, is_open_access: e.target.checked })} />
              </div>
              <div className="col-span-2">
                <label className="block text-gray-600 mb-1">Abstract</label>
                <textarea className="w-full border rounded px-3 py-2 h-24" value={newRef.abstract || ''} onChange={e => setNewRef({ ...newRef, abstract: e.target.value })} placeholder="Short abstract (optional)" />
              </div>
              <div className="col-span-2">
                <label className="block text-gray-600 mb-1">Attach PDF (optional)</label>
                <input type="file" accept="application/pdf" onChange={(e) => setNewPdf(e.target.files?.[0] || null)} />
              </div>
            </div>
            <div className="px-4 py-3 border-t flex justify-end gap-2">
              <button className="px-3 py-2 border rounded" onClick={() => { setShowAdd(false); setNewPdf(null) }}>Cancel</button>
              <button
                className="px-3 py-2 rounded bg-blue-600 text-white disabled:opacity-50"
                disabled={savingNew || !newRef.title?.trim()}
                onClick={async () => {
                  if (!newRef.title?.trim()) return
                  setSavingNew(true)
                  try {
                    const payload = {
                      title: newRef.title!,
                      authors: (newRef.authorsText || '').split(',').map(s => s.trim()).filter(Boolean),
                      year: newRef.year,
                      doi: newRef.doi || undefined,
                      url: newRef.url || undefined,
                      source: newRef.source || 'manual',
                      journal: newRef.journal || undefined,
                      abstract: newRef.abstract || undefined,
                      is_open_access: !!newRef.is_open_access,
                      pdf_url: undefined as string | undefined
                    }
                    const r = await referencesAPI.create(payload as any)
                    const created = r.data as { id?: string } | null
                    const refId = created?.id
                    if (!refId) {
                      throw new Error('Failed to determine created reference ID')
                    }
                    if (newPdf) {
                      await referencesAPI.uploadPdf(refId, newPdf)
                    }
                    setShowAdd(false); setNewPdf(null); setNewRef({ title: '', authors: [], authorsText: '', year: undefined, doi: '', url: '', source: 'manual', journal: '', abstract: '', is_open_access: false, pdf_url: '' })
                    await load()
                  } catch (e) {
                    toast.error('Failed to create reference')
                  } finally {
                    setSavingNew(false)
                  }
                }}
              >{savingNew ? 'Saving…' : 'Save Reference'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default MyReferences
