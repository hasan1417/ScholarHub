import { useState } from 'react'
import {
  Loader2,
} from 'lucide-react'
import {
  ChannelScopeConfig,
  DiscussionChannelSummary,
  ResearchPaper,
  ProjectReferenceSuggestion,
  MeetingSummary,
} from '../../types'
import ResourceScopePicker from './ResourceScopePicker'
import { useToast } from '../../hooks/useToast'

const ChannelSettingsModal = ({
  channel,
  onClose,
  onSave,
  onDelete,
  isSaving,
  isDeleting,
  papers,
  references,
  meetings,
  isLoadingResources,
}: {
  channel: DiscussionChannelSummary
  onClose: () => void
  onSave: (payload: { name?: string; description?: string | null; scope?: ChannelScopeConfig | null }) => void
  onDelete: () => void
  isSaving: boolean
  isDeleting: boolean
  papers: ResearchPaper[]
  references: ProjectReferenceSuggestion[]
  meetings: MeetingSummary[]
  isLoadingResources: boolean
}) => {
  const { toast } = useToast()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')
  const [name, setName] = useState(channel.name)
  const [description, setDescription] = useState(channel.description || '')
  const [scope, setScope] = useState<ChannelScopeConfig | null>(channel.scope ?? null)

  const toggleScopeResource = (type: 'paper' | 'reference' | 'meeting', id: string) => {
    setScope((prev) => {
      const keyMap = { paper: 'paper_ids', reference: 'reference_ids', meeting: 'meeting_ids' } as const
      const key = keyMap[type]

      if (prev === null) {
        return { [key]: [id] } as ChannelScopeConfig
      }

      const currentIds = prev[key] || []
      if (currentIds.includes(id)) {
        const filtered = currentIds.filter((existingId) => existingId !== id)
        const newScope = { ...prev, [key]: filtered.length > 0 ? filtered : null }
        const hasAny = newScope.paper_ids?.length || newScope.reference_ids?.length || newScope.meeting_ids?.length
        return hasAny ? newScope : null
      }

      return { ...prev, [key]: [...currentIds, id] }
    })
  }

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!name.trim()) {
      toast.warning('Channel name is required.')
      return
    }

    const payload: { name?: string; description?: string | null; scope?: ChannelScopeConfig | null } = {}
    if (name.trim() !== channel.name) {
      payload.name = name.trim()
    }
    if (description.trim() !== (channel.description || '')) {
      payload.description = description.trim() || null
    }
    const currentScope = channel.scope ?? null
    const newScope = scope
    if (JSON.stringify(currentScope) !== JSON.stringify(newScope)) {
      payload.scope = newScope === null ? { paper_ids: null, reference_ids: null, meeting_ids: null } : newScope
    }

    if (Object.keys(payload).length === 0) {
      onClose()
      return
    }

    onSave(payload)
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end sm:items-center justify-center bg-gray-900/40 backdrop-blur-sm dark:bg-black/70">
      <div className="w-full sm:max-w-md max-h-[90vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl bg-white p-4 sm:p-6 shadow-xl transition-colors dark:bg-slate-900/90">
        <h3 className="text-base font-semibold text-gray-900 dark:text-slate-100">Channel Settings</h3>
        <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-slate-400">
          Update channel configuration and AI scope
        </p>
        <form className="mt-3 sm:mt-4 space-y-3 sm:space-y-4" onSubmit={handleSubmit}>
          <div>
            <label
              htmlFor="settings-channel-name"
              className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300"
            >
              Channel name
            </label>
            <input
              id="settings-channel-name"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
              placeholder="e.g. Brainstorming"
              maxLength={255}
              required
            />
          </div>

          <div>
            <label
              htmlFor="settings-channel-description"
              className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300"
            >
              Description <span className="text-gray-400 dark:text-slate-500">(optional)</span>
            </label>
            <textarea
              id="settings-channel-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
              rows={3}
              maxLength={2000}
              placeholder="Describe the focus of this channel"
            />
          </div>

          <div>
            <label className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300">
              AI Context Scope
            </label>
            <p className="mt-0.5 text-xs text-gray-500 dark:text-slate-400">
              Choose which resources the AI can access in this channel
            </p>
            <div className="mt-2 space-y-2">
              <button
                type="button"
                onClick={() => setScope(null)}
                className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition ${
                  scope === null
                    ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:border-indigo-400 dark:bg-indigo-500/20 dark:text-indigo-100'
                    : 'border-gray-200 text-gray-600 hover:border-gray-300 dark:border-slate-600 dark:text-slate-300 dark:hover:border-slate-500'
                }`}
              >
                <span className="font-medium">Project-wide</span>
                <span className="ml-1 text-xs opacity-70">(all papers, references, transcripts)</span>
              </button>

              {scope !== null && (
                <div className="mt-3 max-h-64 overflow-y-auto rounded-lg border border-gray-200 dark:border-slate-700">
                  <ResourceScopePicker
                    scope={scope}
                    papers={papers}
                    references={references}
                    meetings={meetings}
                    onToggle={toggleScopeResource}
                    isLoading={isLoadingResources}
                  />
                </div>
              )}

              {scope === null && (
                <button
                  type="button"
                  onClick={() => setScope({})}
                  className="text-xs text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300"
                >
                  Or select specific resources...
                </button>
              )}
            </div>
          </div>

          {/* Delete confirmation */}
          {confirmDelete && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 dark:border-red-500/30 dark:bg-red-500/10">
              <p className="text-sm text-red-700 dark:text-red-300">
                This will permanently delete the channel and all its messages and artifacts.
              </p>
              <p className="mt-2 text-xs text-red-600 dark:text-red-400">
                Type <strong>{channel.name}</strong> to confirm:
              </p>
              <input
                type="text"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                className="mt-2 w-full rounded-md border border-red-300 px-2 py-1.5 text-sm focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500 dark:border-red-500/50 dark:bg-slate-900/60 dark:text-slate-100"
                placeholder={channel.name}
              />
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setConfirmDelete(false)
                    setDeleteConfirmText('')
                  }}
                  className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={onDelete}
                  disabled={deleteConfirmText !== channel.name || isDeleting}
                  className="flex-1 inline-flex items-center justify-center gap-1 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-red-300 dark:disabled:bg-red-500/40"
                >
                  {isDeleting && <Loader2 className="h-3 w-3 animate-spin" />}
                  Delete channel
                </button>
              </div>
            </div>
          )}

          <div className="flex justify-between gap-2 pt-2">
            {!channel.is_default && !confirmDelete && (
              <button
                type="button"
                onClick={() => setConfirmDelete(true)}
                className="rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:border-red-500/40 dark:text-red-400 dark:hover:bg-red-500/10"
                disabled={isSaving || isDeleting}
              >
                Delete
              </button>
            )}
            {(channel.is_default || confirmDelete) && <div />}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                disabled={isSaving || isDeleting}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSaving || isDeleting || confirmDelete}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300 dark:disabled:bg-indigo-500/40"
              >
                {isSaving && <Loader2 className="h-4 w-4 animate-spin" />}
                Save changes
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}

export default ChannelSettingsModal
