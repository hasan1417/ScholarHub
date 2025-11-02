import React, { useEffect, useMemo, useState } from 'react'
import { referencesAPI } from '../../services/api'

interface ReferenceItem {
  id: string
  title: string
  authors?: string[]
  year?: number
  doi?: string
}

interface ReferencePickerModalProps {
  isOpen: boolean
  onClose: () => void
  selectedIds: string[]
  onConfirm: (ids: string[]) => void
}

const ReferencePickerModal: React.FC<ReferencePickerModalProps> = ({ isOpen, onClose, selectedIds, onConfirm }) => {
  const [loading, setLoading] = useState(false)
  const [refs, setRefs] = useState<ReferenceItem[]>([])
  const [search, setSearch] = useState('')
  const [localSelected, setLocalSelected] = useState<Set<string>>(new Set(selectedIds))

  useEffect(() => { setLocalSelected(new Set(selectedIds)) }, [selectedIds])

  useEffect(() => {
    if (!isOpen) return
    let mounted = true
    const load = async () => {
      try {
        setLoading(true)
        const res = await referencesAPI.listMy({ skip: 0, limit: 500 })
        if (!mounted) return
        const data = res.data as { references?: any[] } | any[] | null
        const items = Array.isArray(data)
          ? data
          : Array.isArray(data?.references)
            ? data.references
            : []
        setRefs(items.map((r: any) => ({ id: r.id, title: r.title, authors: r.authors, year: r.year, doi: r.doi })))
      } catch (e) {
        setRefs([])
      } finally {
        setLoading(false)
      }
    }
    load()
    return () => { mounted = false }
  }, [isOpen])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return refs
    return refs.filter(r => (
      (r.title || '').toLowerCase().includes(q) ||
      (r.authors || []).join(' ').toLowerCase().includes(q) ||
      (r.doi || '').toLowerCase().includes(q)
    ))
  }, [refs, search])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl max-h-[80vh] overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between">
          <h3 className="text-lg font-semibold">Select References</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">✕</button>
        </div>
        <div className="p-4">
          <div className="mb-3">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by title, author, or DOI…"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="border rounded-md divide-y max-h-[46vh] overflow-auto">
            {loading ? (
              <div className="p-4 text-sm text-gray-500">Loading references…</div>
            ) : filtered.length === 0 ? (
              <div className="p-4 text-sm text-gray-500">No references found.</div>
            ) : (
              filtered.map(ref => (
                <label key={ref.id} className="p-3 flex items-start gap-3 cursor-pointer hover:bg-gray-50">
                  <input
                    type="checkbox"
                    checked={localSelected.has(ref.id)}
                    onChange={(e) => {
                      setLocalSelected(prev => {
                        const next = new Set(prev)
                        if (e.target.checked) next.add(ref.id); else next.delete(ref.id)
                        return next
                      })
                    }}
                    className="mt-1"
                  />
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-gray-900 truncate">{ref.title}</div>
                    <div className="text-xs text-gray-600 truncate">
                      {(ref.authors || []).join(', ')}{ref.year ? ` • ${ref.year}` : ''}{ref.doi ? ` • ${ref.doi}` : ''}
                    </div>
                  </div>
                </label>
              ))
            )}
          </div>
          <div className="mt-3 text-xs text-gray-500">Selected: {localSelected.size}</div>
        </div>
        <div className="p-4 border-t flex items-center justify-end gap-2 bg-gray-50">
          <button onClick={onClose} className="px-3 py-1.5 text-sm rounded-md border border-gray-200 hover:bg-gray-100">Cancel</button>
          <button
            onClick={() => { onConfirm(Array.from(localSelected)); onClose() }}
            className="px-3 py-1.5 text-sm rounded-md bg-blue-600 text-white hover:bg-blue-700"
          >
            Add Selected
          </button>
        </div>
      </div>
    </div>
  )
}

export default ReferencePickerModal
