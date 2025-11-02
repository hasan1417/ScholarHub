import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
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
  const [idea, setIdea] = useState('')
  const [keywordsInput, setKeywordsInput] = useState('')
  const [scope, setScope] = useState('')

  useEffect(() => {
    if (!isOpen) {
      setTitle('')
      setIdea('')
      setKeywordsInput('')
      setScope('')
      return
    }

    if (mode === 'edit' && initialProject) {
      setTitle(initialProject.title ?? '')
      setIdea(initialProject.idea ?? '')
      setScope(initialProject.scope ?? '')
      setKeywordsInput(normalizeKeywords(initialProject.keywords).join(', '))
    } else {
      setTitle('')
      setIdea('')
      setScope('')
      setKeywordsInput('')
    }
  }, [isOpen, initialProject, mode])

  if (!isOpen) return null

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!title.trim()) return

    const keywords = keywordsInput
      .split(',')
      .map((kw) => kw.trim())
      .filter(Boolean)

    const payload: ProjectCreateInput = {
      title: title.trim(),
      idea: idea.trim() || undefined,
      scope: scope.trim() || undefined,
      keywords: keywords.length ? keywords : undefined,
    }

    onSubmit(payload)
  }

  const heading = mode === 'create' ? 'Create a new project' : 'Edit project details'
  const description =
    mode === 'create'
      ? 'Set the stage for your next research initiative.'
      : 'Update the title, scope, and keywords for this project.'
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
            <p className="text-sm text-gray-500 dark:text-slate-300">{description}</p>
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
            <label className="block text-sm font-medium text-gray-700 dark:text-slate-200">Idea / problem statement</label>
            <textarea
              value={idea}
              onChange={(event) => setIdea(event.target.value)}
              rows={3}
              className="mt-2 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
              placeholder="Capture the vision for this project"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-slate-200">Keywords</label>
              <input
                type="text"
                value={keywordsInput}
                onChange={(event) => setKeywordsInput(event.target.value)}
                className="mt-2 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
                placeholder="biology, robotics, ..."
              />
              <p className="mt-1 text-xs text-gray-400 dark:text-slate-400">Separate keywords with commas.</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-slate-200">Scope</label>
              <input
                type="text"
                value={scope}
                onChange={(event) => setScope(event.target.value)}
                className="mt-2 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
                placeholder="Exploratory phase"
              />
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
