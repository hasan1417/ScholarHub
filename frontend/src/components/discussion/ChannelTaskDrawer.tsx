import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { Loader2, CheckCircle2, Circle, Clock4, XCircle, Plus, ChevronDown } from 'lucide-react'
import {
  DiscussionTask,
  DiscussionTaskStatus,
  DiscussionTaskUpdate,
  DiscussionTaskCreate,
} from '../../types'

interface ChannelTaskDrawerProps {
  tasks: DiscussionTask[]
  loading: boolean
  error: Error | null
  onCreateTask: (payload: DiscussionTaskCreate) => void
  onUpdateTask: (taskId: string, payload: DiscussionTaskUpdate) => void
  onDeleteTask: (taskId: string) => void
  allowCreate: boolean
  defaultMessageId?: string | null
  isCollapsed?: boolean
  onToggleCollapse?: () => void
}

const statusIcon = (status: DiscussionTaskStatus) => {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="h-4 w-4 text-emerald-500" />
    case 'in_progress':
      return <Clock4 className="h-4 w-4 text-sky-500" />
    case 'cancelled':
      return <XCircle className="h-4 w-4 text-rose-500" />
    case 'open':
    default:
      return <Circle className="h-4 w-4 text-gray-400" />
  }
}

const ChannelTaskDrawer = ({
  tasks,
  loading,
  error,
  onCreateTask,
  onUpdateTask,
  onDeleteTask,
  allowCreate,
  defaultMessageId,
  isCollapsed = false,
  onToggleCollapse,
}: ChannelTaskDrawerProps) => {
  const [isCreating, setIsCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newDescription, setNewDescription] = useState('')

  useEffect(() => {
    if (isCollapsed) {
      setIsCreating(false)
    }
  }, [isCollapsed])

  const sortedTasks = useMemo(() => {
    const order = ['open', 'in_progress', 'completed', 'cancelled'] as DiscussionTaskStatus[]
    return [...tasks].sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status))
  }, [tasks])

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!newTitle.trim()) {
      alert('Task title is required.')
      return
    }

    onCreateTask({
      title: newTitle.trim(),
      description: newDescription.trim() || undefined,
      message_id: defaultMessageId ?? undefined,
    })
    setNewTitle('')
    setNewDescription('')
    setIsCreating(false)
  }

  const cycleStatus = (status: DiscussionTaskStatus): DiscussionTaskStatus => {
    const flow: DiscussionTaskStatus[] = ['open', 'in_progress', 'completed', 'cancelled']
    const index = flow.indexOf(status)
    return flow[(index + 1) % flow.length]
  }

  return (
    <div className="flex flex-col rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-900/40">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {onToggleCollapse && (
            <button
              type="button"
              onClick={onToggleCollapse}
              className="rounded-full border border-gray-200 p-1 text-gray-500 transition hover:bg-gray-100 hover:text-gray-700 dark:border-slate-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
              aria-label={isCollapsed ? 'Expand tasks panel' : 'Collapse tasks panel'}
            >
              <ChevronDown className={clsx('h-4 w-4 transition-transform', isCollapsed ? '-rotate-90' : 'rotate-0')} />
            </button>
          )}
          <h3 className="text-sm font-semibold text-gray-900 dark:text-slate-100">Channel tasks</h3>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-slate-400">
          <span>{tasks.length}</span>
          {!isCollapsed && allowCreate && (
            <button
              type="button"
              onClick={() => setIsCreating((prev) => !prev)}
              className="inline-flex items-center gap-1 rounded-full border border-indigo-200 px-3 py-1 text-xs font-medium text-indigo-600 transition hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
            >
              <Plus className="h-3.5 w-3.5" />
              New task
            </button>
          )}
        </div>
      </div>

      {!isCollapsed && (
        <div className="mt-3 space-y-3 overflow-y-auto max-h-72">
        {loading && (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-indigo-500" />
          </div>
        )}

        {error && !loading && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-200">
            Unable to load channel tasks.
          </div>
        )}

        {!loading && !error && tasks.length === 0 && !isCreating && (
          <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 p-4 text-xs text-gray-500 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-300">
            No tasks yet. Track action items from this channel to keep the team aligned.
          </div>
        )}

        {isCreating && allowCreate && (
          <form className="mb-4 space-y-3 rounded-lg border border-indigo-100 bg-indigo-50/40 p-3 transition-colors dark:border-indigo-400/40 dark:bg-slate-800/60" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="task-title" className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300">
                Task title
              </label>
              <input
                id="task-title"
                type="text"
                value={newTitle}
                onChange={(event) => setNewTitle(event.target.value)}
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
                maxLength={255}
                placeholder="Capture the next action"
                required
              />
            </div>
            <div>
              <label htmlFor="task-description" className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300">
                Description <span className="text-gray-400 dark:text-slate-500">(optional)</span>
              </label>
              <textarea
                id="task-description"
                value={newDescription}
                onChange={(event) => setNewDescription(event.target.value)}
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
                rows={3}
                maxLength={2000}
                placeholder="Add details or context for the assignee"
              />
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setIsCreating(false)}
                className="rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-700"
              >
                Create task
              </button>
            </div>
          </form>
        )}

        {!loading && !error && sortedTasks.length > 0 && (
          <ul className="space-y-3">
            {sortedTasks.map((task) => (
              <li key={task.id} className="rounded-lg border border-gray-100 bg-gray-50/60 p-3 transition-colors dark:border-slate-700 dark:bg-slate-800/60">
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3">
                    <button
                      type="button"
                      onClick={() => onUpdateTask(task.id, { status: cycleStatus(task.status) })}
                      className="mt-0.5 rounded-full border border-gray-200 bg-white p-1 transition hover:bg-gray-100 dark:border-slate-600 dark:bg-slate-900/60 dark:hover:bg-slate-700"
                      title="Advance status"
                    >
                      {statusIcon(task.status)}
                    </button>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 dark:text-slate-100">{task.title}</p>
                      {task.description && (
                        <p className="mt-1 text-xs text-gray-500 dark:text-slate-300">{task.description}</p>
                      )}
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-wide text-gray-400 dark:text-slate-500">
                        <span>Status: {task.status.replace('_', ' ')}</span>
                        {task.due_date && <span>Due {new Date(task.due_date).toLocaleDateString()}</span>}
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onDeleteTask(task.id)}
                    className="rounded-full p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                    title="Delete task"
                  >
                    <XCircle className="h-4 w-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      )}
    </div>
  )
}

export default ChannelTaskDrawer
