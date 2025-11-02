import React, { useEffect, useMemo, useState } from 'react'
import { projectReferencesAPI } from '../../services/api'
import { ProjectReferenceSuggestion } from '../../types'
import { Loader2, Search, X } from 'lucide-react'

type AttachProjectReferenceModalProps = {
  isOpen: boolean
  projectId: string
  paperId: string
  attachedProjectReferenceIds: string[]
  onClose: () => void
  onUpdated?: () => Promise<void> | void
}

const AttachProjectReferenceModal: React.FC<AttachProjectReferenceModalProps> = ({
  isOpen,
  projectId,
  paperId,
  attachedProjectReferenceIds,
  onClose,
  onUpdated,
}) => {
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [references, setReferences] = useState<ProjectReferenceSuggestion[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [initialSelected, setInitialSelected] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false

    const load = async () => {
      try {
        setIsLoading(true)
        setError(null)
        const response = await projectReferencesAPI.list(projectId, { status: 'approved' })
        if (cancelled) return
        const items = (response.data?.references || []) as ProjectReferenceSuggestion[]
        setReferences(items)

        const attachedSet = new Set<string>(
          items
            .filter((item) => (item.papers || []).some((paper) => paper.paper_id === paperId))
            .map((item) => item.id)
        )

        // Include any ids passed from parent (safety for stale cache)
        for (const id of attachedProjectReferenceIds) {
          attachedSet.add(id)
        }

        setSelectedIds(attachedSet)
        setInitialSelected(new Set(attachedSet))
      } catch (err) {
        console.error('Failed to load project references', err)
        if (!cancelled) {
          setReferences([])
          setError('Unable to load project references right now.')
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    load()

    return () => {
      cancelled = true
    }
  }, [isOpen, projectId, paperId, attachedProjectReferenceIds])

  useEffect(() => {
    if (!isOpen) {
      setSearch('')
    }
  }, [isOpen])

  const filteredReferences = useMemo(() => {
    if (!search.trim()) return references
    const needle = search.toLowerCase()
    return references.filter((item) => {
      const ref = item.reference
      const haystack = [
        ref?.title || '',
        (ref?.authors || []).join(' '),
        ref?.journal || '',
        ref?.doi || '',
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(needle)
    })
  }, [references, search])

  const toggleSelection = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleApply = async () => {
    try {
      setIsSaving(true)
      setError(null)
      const toAttach = Array.from(selectedIds).filter((id) => !initialSelected.has(id))
      const toDetach = Array.from(initialSelected).filter((id) => !selectedIds.has(id))

      for (const id of toAttach) {
        await projectReferencesAPI.attachToPaper(projectId, id, paperId)
      }
      for (const id of toDetach) {
        await projectReferencesAPI.detachFromPaper(projectId, id, paperId)
      }

      await onUpdated?.()
    } catch (err) {
      console.error('Failed to update reference attachments', err)
      setError('Unable to update attachments. Please try again.')
    } finally {
      setIsSaving(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-3xl rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Attach References</h2>
            <p className="text-xs text-gray-500">Select approved project references to link them to this paper.</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            title="Close"
            disabled={isSaving}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              className="w-full rounded-md border border-gray-200 py-2 pl-9 pr-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="Search by title, author, journal, or DOI"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>

          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          )}

          <div className="max-h-80 overflow-y-auto rounded-md border border-gray-200">
            {isLoading ? (
              <div className="flex items-center justify-center py-12 text-sm text-gray-500">
                <Loader2 className="mr-2 h-4 w-4 animate-spin text-indigo-600" />
                Loading project references…
              </div>
            ) : filteredReferences.length === 0 ? (
              <div className="py-12 text-center text-sm text-gray-500">
                {references.length === 0
                  ? 'No approved project references are available yet.'
                  : 'No references match your search.'}
              </div>
            ) : (
              <ul className="divide-y divide-gray-100 text-sm">
                {filteredReferences.map((item) => {
                  const ref = item.reference
                  const isSelected = selectedIds.has(item.id)
                  const attachedElsewhere = (item.papers || []).filter((p) => p.paper_id !== paperId)
                  return (
                    <li key={item.id} className="flex items-start gap-3 px-4 py-3">
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={isSelected}
                        onChange={() => toggleSelection(item.id)}
                      />
                      <div className="flex-1">
                        <div className="font-medium text-gray-900">{ref?.title || 'Untitled reference'}</div>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-600">
                          {ref?.authors && ref.authors.length > 0 && <span>{ref.authors.join(', ')}</span>}
                          {ref?.year && <span>Year: {ref.year}</span>}
                          {ref?.journal && <span>{ref.journal}</span>}
                          {ref?.doi && (
                            <a
                              href={`https://doi.org/${ref.doi}`}
                              target="_blank"
                              rel="noreferrer"
                              className="text-indigo-600 hover:underline"
                            >
                              DOI
                            </a>
                          )}
                        </div>
                        {attachedElsewhere.length > 0 && (
                          <p className="mt-2 text-xs text-gray-500">
                            Also attached to {attachedElsewhere.length} other paper{attachedElsewhere.length === 1 ? '' : 's'} in this project.
                          </p>
                        )}
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-gray-100 bg-gray-50 px-5 py-4 text-sm">
          <span className="text-gray-500">
            {selectedIds.size} reference{selectedIds.size === 1 ? '' : 's'} selected
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="rounded-full border border-gray-200 px-4 py-2 text-gray-600 hover:bg-gray-100"
              disabled={isSaving}
            >
              Cancel
            </button>
            <button
              onClick={handleApply}
              className="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              disabled={isSaving || isLoading}
            >
              {isSaving && <Loader2 className="h-4 w-4 animate-spin" />}
              Save attachments
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default AttachProjectReferenceModal
