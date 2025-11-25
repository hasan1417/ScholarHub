import { useEffect, useMemo, useState } from 'react'
import { Plus, X } from 'lucide-react'
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
  const [keyboardsInput, setKeyboardsInput] = useState('')
  const [objectives, setObjectives] = useState<string[]>([''])

  const sanitizedObjectives = useMemo(
    () => objectives.map((objective) => objective.trim()).filter(Boolean),
    [objectives],
  )

  useEffect(() => {
    if (!isOpen) {
      setTitle('')
      setDescription('')
      setKeyboardsInput('')
      setObjectives([''])
      return
    }

    if (mode === 'edit' && initialProject) {
      setTitle(initialProject.title ?? '')
      setDescription(initialProject.idea ?? '')
      const parsedObjectives = normalizeObjectives(initialProject.scope)
      setObjectives(parsedObjectives.length ? parsedObjectives : [''])
      setKeyboardsInput(normalizeKeywords(initialProject.keywords).join(', '))
    } else {
      setTitle('')
      setDescription('')
      setObjectives([''])
      setKeyboardsInput('')
    }
  }, [isOpen, initialProject, mode])

  if (!isOpen) return null

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!title.trim()) return

    const keywords = keyboardsInput
      .split(',')
      .map((kw) => kw.trim())
      .filter(Boolean)

    const objectivesPayload = sanitizedObjectives.join('\n') || undefined

    const payload: ProjectCreateInput = {
      title: title.trim(),
      idea: description.trim() || undefined,
      scope: objectivesPayload,
      keywords: keywords.length ? keywords : undefined,
    }

    onSubmit(payload)
  }

  const heading = mode === 'create' ? 'Create a new project' : 'Edit project details'
  const modalDescription =
    mode === 'create'
      ? 'Set the stage for your next research initiative.'
      : 'Update the title, description, objectives, and keyboards for this project.'
  const submitLabel = mode === 'create' ? 'Create project' : 'Save changes'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-gray-900/40 dark:bg-black/60" aria-hidden="true" onClick={onClose} />
      <form
        onSubmit={handleSubmit}
        className="relative w-full max-w-lg rounded-2xl bg-white shadow-xl transition-colors dark:bg-slate-800"
      >
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4 dark:border-slate-700">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">{heading}</h2>
            <p className="text-sm text-gray-500 dark:text-slate-300">{modalDescription}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-700"
            aria-label={mode === 'create' ? 'Close create project modal' : 'Close edit project modal'}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-5 px-6 py-5 text-gray-700 dark:text-slate-200">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-slate-200">Project title</label>
            <input
              type="text"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="mt-2 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
              placeholder="e.g. Neural Interface Study"
              autoFocus
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-slate-200">Description</label>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
              className="mt-2 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
              placeholder="Summarize the project vision or problem statement"
            />
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-slate-200">Keyboards</label>
              <input
                type="text"
                value={keyboardsInput}
                onChange={(event) => setKeyboardsInput(event.target.value)}
                className="mt-2 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
                placeholder="biology, robotics, ..."
              />
              <p className="mt-1 text-xs text-gray-400 dark:text-slate-400">Separate keyboards with commas.</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-slate-200">Objectives</label>
              <ol className="mt-3 space-y-3">
                {objectives.map((objective, index) => (
                  <li key={`objective-${index}`} className="flex items-start gap-3">
                    <span className="mt-2 text-sm font-semibold text-gray-500 dark:text-slate-400">{index + 1}.</span>
                    <textarea
                      value={objective}
                      onChange={(event) => {
                        const value = event.target.value
                        setObjectives((prev) => {
                          const next = [...prev]
                          next[index] = value
                          return next
                        })
                      }}
                      rows={2}
                      className="mt-0 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
                      placeholder="Summarize this objective in a single sentence"
                    />
                    {objectives.length > 1 && (
                      <button
                        type="button"
                        onClick={() => {
                          setObjectives((prev) => prev.filter((_, idx) => idx !== index))
                        }}
                        className="mt-1 inline-flex h-8 w-8 items-center justify-center rounded-full text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-100"
                        aria-label={`Remove objective ${index + 1}`}
                      >
                        <X className="h-4 w-4" />
                      </button>
                    )}
                  </li>
                ))}
              </ol>
              <div className="mt-3">
                <button
                  type="button"
                  onClick={() => setObjectives((prev) => [...prev, ''])}
                  className="inline-flex items-center rounded-md border border-dashed border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-600 transition hover:border-indigo-300 hover:text-indigo-600 dark:border-slate-600 dark:text-slate-300 dark:hover:border-indigo-500 dark:hover:text-indigo-300"
                >
                  <Plus className="mr-1.5 h-4 w-4" />
                  Add objective
                </button>
              </div>
              <p className="mt-2 text-xs text-gray-400 dark:text-slate-400">Each objective should be a single sentence; they will be shown as numbered bullet points.</p>
            </div>
          </div>
          {error && <p className="text-sm text-red-600 dark:text-red-300">{error}</p>}
        </div>
        <div className="flex items-center justify-end gap-3 border-t border-gray-100 px-6 py-4 dark:border-slate-700">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-700"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="inline-flex items-center rounded-md border border-transparent bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={isSubmitting || !title.trim()}
          >
            {isSubmitting ? (mode === 'create' ? 'Creating…' : 'Saving…') : submitLabel}
          </button>
        </div>
      </form>
    </div>
  )
}

export default ProjectFormModal
