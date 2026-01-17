import React, { useEffect, useMemo, useState } from 'react'
import { projectReferencesAPI } from '../../services/api'
import { ProjectReferenceSuggestion } from '../../types'
import { BookOpen, Check, ExternalLink, Link2, Loader2, Search, X } from 'lucide-react'

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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-3xl overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl transition-colors dark:border-slate-700 dark:bg-slate-900">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-5 dark:border-slate-800">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">Attach References</h2>
            <p className="mt-0.5 text-sm text-gray-500 dark:text-slate-400">
              Select references from your project library
            </p>
          </div>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-300"
            title="Close"
            disabled={isSaving}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Search */}
        <div className="border-b border-gray-100 px-6 py-4 dark:border-slate-800">
          <div className="relative">
            <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 dark:text-slate-500" />
            <input
              type="text"
              className="w-full rounded-xl border border-gray-200 bg-gray-50 py-2.5 pl-10 pr-4 text-sm text-gray-900 placeholder-gray-400 transition focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:bg-slate-800"
              placeholder="Search by title, author, journal, or DOI..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mx-6 mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-400/40 dark:bg-rose-900/30 dark:text-rose-100">
            {error}
          </div>
        )}

        {/* Reference List */}
        <div className="max-h-[400px] overflow-y-auto px-6 py-4">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-16 text-sm text-gray-500 dark:text-slate-400">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600 dark:text-indigo-400" />
              <p className="mt-3">Loading references...</p>
            </div>
          ) : filteredReferences.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <BookOpen className="h-10 w-10 text-gray-300 dark:text-slate-600" />
              <p className="mt-3 text-sm text-gray-500 dark:text-slate-400">
                {references.length === 0
                  ? 'No approved references in your project library yet'
                  : 'No references match your search'}
              </p>
            </div>
          ) : (
            <ul className="space-y-2">
              {filteredReferences.map((item) => {
                const ref = item.reference
                const isSelected = selectedIds.has(item.id)
                const attachedElsewhere = (item.papers || []).filter((p) => p.paper_id !== paperId)
                const authorDisplay = ref?.authors?.length
                  ? ref.authors.length > 2
                    ? `${ref.authors.slice(0, 2).join(', ')} et al.`
                    : ref.authors.join(', ')
                  : null

                return (
                  <li
                    key={item.id}
                    onClick={() => toggleSelection(item.id)}
                    className={`group cursor-pointer rounded-xl border-2 p-4 transition-all ${
                      isSelected
                        ? 'border-indigo-500 bg-indigo-50 dark:border-indigo-400 dark:bg-indigo-500/10'
                        : 'border-gray-100 bg-gray-50/50 hover:border-gray-200 hover:bg-gray-50 dark:border-slate-800 dark:bg-slate-800/50 dark:hover:border-slate-700 dark:hover:bg-slate-800'
                    }`}
                  >
                    <div className="flex gap-3">
                      {/* Custom Checkbox */}
                      <div
                        className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-md border-2 transition ${
                          isSelected
                            ? 'border-indigo-500 bg-indigo-500 dark:border-indigo-400 dark:bg-indigo-500'
                            : 'border-gray-300 bg-white group-hover:border-gray-400 dark:border-slate-600 dark:bg-slate-800'
                        }`}
                      >
                        {isSelected && <Check className="h-3 w-3 text-white" />}
                      </div>

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        {/* Title */}
                        <h4 className={`font-medium leading-snug ${
                          isSelected ? 'text-indigo-900 dark:text-indigo-100' : 'text-gray-900 dark:text-slate-100'
                        }`}>
                          {ref?.title || 'Untitled reference'}
                        </h4>

                        {/* Metadata row */}
                        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                          {authorDisplay && (
                            <span className="text-gray-600 dark:text-slate-400">{authorDisplay}</span>
                          )}
                          {ref?.year && (
                            <span className="rounded bg-gray-200 px-1.5 py-0.5 font-medium text-gray-700 dark:bg-slate-700 dark:text-slate-300">
                              {ref.year}
                            </span>
                          )}
                          {ref?.journal && (
                            <>
                              {(authorDisplay || ref?.year) && (
                                <span className="text-gray-300 dark:text-slate-600">•</span>
                              )}
                              <span className="italic text-gray-500 dark:text-slate-400">{ref.journal}</span>
                            </>
                          )}
                          {ref?.doi && (
                            <a
                              href={`https://doi.org/${ref.doi}`}
                              target="_blank"
                              rel="noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="inline-flex items-center gap-1 font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                            >
                              <Link2 className="h-3 w-3" />
                              DOI
                              <ExternalLink className="h-2.5 w-2.5" />
                            </a>
                          )}
                        </div>

                        {/* Attached elsewhere badge */}
                        {attachedElsewhere.length > 0 && (
                          <div className="mt-2">
                            <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-500/20 dark:text-amber-300">
                              <BookOpen className="h-3 w-3" />
                              Used in {attachedElsewhere.length} other paper{attachedElsewhere.length === 1 ? '' : 's'}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-gray-100 bg-gray-50 px-6 py-4 dark:border-slate-800 dark:bg-slate-800/50">
          <div className="flex items-center gap-2 text-sm">
            {selectedIds.size > 0 ? (
              <>
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-600 text-xs font-semibold text-white dark:bg-indigo-500">
                  {selectedIds.size}
                </span>
                <span className="text-gray-600 dark:text-slate-300">
                  reference{selectedIds.size === 1 ? '' : 's'} selected
                </span>
              </>
            ) : (
              <span className="text-gray-400 dark:text-slate-500">No references selected</span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="rounded-xl border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
              disabled={isSaving}
            >
              Cancel
            </button>
            <button
              onClick={handleApply}
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 disabled:opacity-60 dark:bg-indigo-500 dark:hover:bg-indigo-400"
              disabled={isSaving || isLoading}
            >
              {isSaving && <Loader2 className="h-4 w-4 animate-spin" />}
              {isSaving ? 'Saving...' : 'Save attachments'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default AttachProjectReferenceModal
