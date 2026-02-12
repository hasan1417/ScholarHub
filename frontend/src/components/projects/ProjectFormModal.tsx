import { useEffect, useMemo, useState } from 'react'
import { Plus, X, Folder, FileText, Tag, Flag, GripVertical } from 'lucide-react'
import { ProjectCreateInput, ProjectSummary } from '../../types'

type ProjectFormModalMode = 'create' | 'edit'

type ProjectFormModalProps = {
  isOpen: boolean
  mode: ProjectFormModalMode
  isSubmitting?: boolean
  error?: string | null
  initialProject?: Pick<ProjectSummary, 'title' | 'idea' | 'scope' | 'keywords'>
  onClose: () => void
  onSubmit: (payload: ProjectCreateInput) => void
}

const normalizeKeywords = (value?: ProjectSummary['keywords']) => {
  if (!value) return []
  if (Array.isArray(value)) return value.filter(Boolean)
  return value ? [value] : []
}

const normalizeObjectives = (value?: string | null) => {
  if (!value) return []
  return value
    .split(/\r?\n|[•]/)
    .map((segment) => segment.replace(/^\d+[\).\s-]*/, '').trim())
    .filter(Boolean)
}

const ProjectFormModal = ({
  isOpen,
  mode,
  isSubmitting,
  error,
  initialProject,
  onClose,
  onSubmit,
}: ProjectFormModalProps) => {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [keywords, setKeywords] = useState<string[]>([])
  const [keywordInput, setKeywordInput] = useState('')
  const [objectives, setObjectives] = useState<string[]>([''])
  const [editingTitle, setEditingTitle] = useState(false)
  const [editingDescription, setEditingDescription] = useState(false)

  const sanitizedObjectives = useMemo(
    () => objectives.map((objective) => objective.trim()).filter(Boolean),
    [objectives],
  )

  useEffect(() => {
    if (!isOpen) {
      setTitle('')
      setDescription('')
      setKeywords([])
      setKeywordInput('')
      setObjectives([''])
      setEditingTitle(false)
      setEditingDescription(false)
      return
    }

    if (mode === 'edit' && initialProject) {
      setTitle(initialProject.title ?? '')
      setDescription(initialProject.idea ?? '')
      const parsedObjectives = normalizeObjectives(initialProject.scope)
      setObjectives(parsedObjectives.length ? parsedObjectives : [''])
      setKeywords(normalizeKeywords(initialProject.keywords))
    } else {
      setTitle('')
      setDescription('')
      setObjectives([''])
      setKeywords([])
    }
  }, [isOpen, initialProject, mode])

  if (!isOpen) return null

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!title.trim()) return

    const objectivesPayload = sanitizedObjectives.join('\n') || undefined

    const payload: ProjectCreateInput = {
      title: title.trim(),
      idea: description.trim() || undefined,
      scope: objectivesPayload,
      keywords: keywords.length ? keywords : undefined,
    }

    onSubmit(payload)
  }

  const handleAddKeyword = () => {
    const trimmed = keywordInput.trim()
    if (trimmed && !keywords.includes(trimmed)) {
      setKeywords([...keywords, trimmed])
      setKeywordInput('')
    }
  }

  const handleKeywordKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      handleAddKeyword()
    }
  }

  const handleRemoveKeyword = (keyword: string) => {
    setKeywords(keywords.filter((kw) => kw !== keyword))
  }

  const heading = mode === 'create' ? 'Create New Project' : 'Edit Project'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-gray-900/50 backdrop-blur-sm dark:bg-black/70" aria-hidden="true" onClick={onClose} />
      <form
        onSubmit={handleSubmit}
        className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl bg-gray-50 shadow-2xl dark:bg-slate-900"
      >
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between bg-gray-50 px-6 py-4 dark:bg-slate-900">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-slate-100">{heading}</h2>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-gray-200 dark:text-slate-400 dark:hover:bg-slate-700"
            aria-label="Close modal"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-3 px-6 pb-6">
          {/* Title Card */}
          <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/30">
                <Folder className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              </div>
              <div className="flex-1 min-w-0">
                <label className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-slate-400">
                  Project Title
                </label>
                {editingTitle || mode === 'create' ? (
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    onBlur={() => mode === 'edit' && setEditingTitle(false)}
                    className="mt-1 w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-base font-medium text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100"
                    placeholder="e.g. Neural Interface Study"
                    autoFocus={mode === 'create'}
                    required
                  />
                ) : (
                  <p
                    onClick={() => setEditingTitle(true)}
                    className="mt-1 cursor-pointer rounded-lg px-3 py-2 text-base font-medium text-gray-900 hover:bg-gray-50 dark:text-slate-100 dark:hover:bg-slate-700"
                  >
                    {title || 'Click to add title'}
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Description Card */}
          <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-purple-100 dark:bg-purple-900/30">
                <FileText className="h-5 w-5 text-purple-600 dark:text-purple-400" />
              </div>
              <div className="flex-1 min-w-0">
                <label className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-slate-400">
                  Description
                </label>
                {editingDescription || mode === 'create' ? (
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    onBlur={() => mode === 'edit' && setEditingDescription(false)}
                    rows={3}
                    className="mt-1 w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700 focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200"
                    placeholder="Summarize the project vision or problem statement"
                  />
                ) : (
                  <p
                    onClick={() => setEditingDescription(true)}
                    className="mt-1 cursor-pointer rounded-lg px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 dark:text-slate-300 dark:hover:bg-slate-700"
                  >
                    {description || 'Click to add description'}
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Keywords Card */}
          <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
                <Tag className="h-5 w-5 text-green-600 dark:text-green-400" />
              </div>
              <div className="flex-1 min-w-0">
                <label className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-slate-400">
                  Keywords
                </label>
                <div className="mt-2 flex flex-wrap gap-2">
                  {keywords.map((keyword) => (
                    <span
                      key={keyword}
                      className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-700 dark:bg-slate-700 dark:text-slate-300"
                    >
                      {keyword}
                      <button
                        type="button"
                        onClick={() => handleRemoveKeyword(keyword)}
                        className="ml-1 rounded-full p-0.5 text-gray-400 hover:bg-gray-200 hover:text-gray-600 dark:hover:bg-slate-600 dark:hover:text-slate-200"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                  <div className="inline-flex items-center">
                    <input
                      type="text"
                      value={keywordInput}
                      onChange={(e) => setKeywordInput(e.target.value)}
                      onKeyDown={handleKeywordKeyDown}
                      onBlur={handleAddKeyword}
                      className="w-28 rounded-full border border-dashed border-gray-300 bg-transparent px-3 py-1 text-sm text-gray-700 placeholder:text-gray-400 focus:border-green-500 focus:outline-none dark:border-slate-600 dark:text-slate-300 dark:placeholder:text-slate-500"
                      placeholder="Add keyword"
                    />
                  </div>
                </div>
                <p className="mt-2 text-xs text-gray-400 dark:text-slate-500">Press Enter or comma to add</p>
              </div>
            </div>
          </div>

          {/* Objectives Card */}
          <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-orange-100 dark:bg-orange-900/30">
                <Flag className="h-5 w-5 text-orange-600 dark:text-orange-400" />
              </div>
              <div className="flex-1 min-w-0">
                <label className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-slate-400">
                  Objectives
                </label>
                <div className="mt-2 space-y-2">
                  {objectives.map((objective, index) => (
                    <div
                      key={`objective-${index}`}
                      className="group flex items-center gap-2 rounded-lg border border-gray-100 bg-gray-50 p-2 transition-colors hover:border-gray-200 dark:border-slate-700 dark:bg-slate-800 dark:hover:border-slate-600"
                    >
                      <GripVertical className="h-4 w-4 shrink-0 cursor-grab text-gray-300 dark:text-slate-600" />
                      <input
                        type="text"
                        value={objective}
                        onChange={(e) => {
                          const value = e.target.value
                          setObjectives((prev) => {
                            const next = [...prev]
                            next[index] = value
                            return next
                          })
                        }}
                        className="flex-1 bg-transparent text-sm text-gray-700 placeholder:text-gray-400 focus:outline-none dark:text-slate-200 dark:placeholder:text-slate-500"
                        placeholder="Describe this objective"
                      />
                      {objectives.length > 1 && (
                        <button
                          type="button"
                          onClick={() => setObjectives((prev) => prev.filter((_, idx) => idx !== index))}
                          className="opacity-0 group-hover:opacity-100 rounded-full p-1 text-gray-400 transition-opacity hover:bg-gray-200 hover:text-gray-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => setObjectives((prev) => [...prev, ''])}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-dashed border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-500 transition-colors hover:border-orange-400 hover:text-orange-600 dark:border-slate-600 dark:text-slate-400 dark:hover:border-orange-500 dark:hover:text-orange-400"
                >
                  <Plus className="h-4 w-4" />
                  Add objective
                </button>
              </div>
            </div>
          </div>

          {/* Error message */}
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-400">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 flex items-center justify-end gap-3 border-t border-gray-200 bg-gray-50 px-6 py-4 dark:border-slate-700 dark:bg-slate-900">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-200 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="inline-flex items-center rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 dark:focus:ring-offset-slate-900"
            disabled={isSubmitting || !title.trim()}
          >
            {isSubmitting ? (mode === 'create' ? 'Creating…' : 'Saving…') : mode === 'create' ? 'Create Project' : 'Save Changes'}
          </button>
        </div>
      </form>
    </div>
  )
}

export default ProjectFormModal
