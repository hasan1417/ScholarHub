import React from 'react'

interface TrackedChangeItem {
  id: string
  type: 'insert' | 'delete'
  text: string
  userName: string
  userColor?: string
  timestamp: number
}

interface TrackChangesPanelProps {
  changes: TrackedChangeItem[]
  onAcceptChange: (changeId: string) => void
  onRejectChange: (changeId: string) => void
  onAcceptAll: () => void
  onRejectAll: () => void
  onClose: () => void
}

function relativeTime(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + '...' : text
}

export const TrackChangesPanel: React.FC<TrackChangesPanelProps> = ({
  changes,
  onAcceptChange,
  onRejectChange,
  onAcceptAll,
  onRejectAll,
  onClose,
}) => {
  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-[300px] flex-col border-l border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2.5 dark:border-slate-700">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Track Changes
          </span>
          {changes.length > 0 && (
            <span className="rounded-full bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
              {changes.length} {changes.length === 1 ? 'change' : 'changes'}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          aria-label="Close track changes"
        >
          <span className="text-lg leading-none">&times;</span>
        </button>
      </div>

      {/* Bulk Actions */}
      {changes.length > 0 && (
        <div className="flex gap-2 border-b border-slate-200 px-3 py-2 dark:border-slate-700">
          <button
            type="button"
            onClick={onAcceptAll}
            className="flex-1 rounded border border-green-300 px-2 py-1 text-xs font-medium text-green-700 transition-colors hover:bg-green-50 dark:border-green-700 dark:text-green-400 dark:hover:bg-green-900/30"
          >
            Accept All
          </button>
          <button
            type="button"
            onClick={onRejectAll}
            className="flex-1 rounded border border-red-300 px-2 py-1 text-xs font-medium text-red-700 transition-colors hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/30"
          >
            Reject All
          </button>
        </div>
      )}

      {/* Change List */}
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {changes.length > 0 ? (
          <div className="flex flex-col gap-1.5">
            {changes.map((change) => (
              <div
                key={change.id}
                className="group rounded-md border border-slate-200 px-2.5 py-2 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800/60"
              >
                <div className="flex items-start gap-2">
                  {/* Type indicator */}
                  <span
                    className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded text-xs font-bold ${
                      change.type === 'insert'
                        ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400'
                        : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400'
                    }`}
                  >
                    {change.type === 'insert' ? '+' : '\u2212'}
                  </span>

                  {/* Text preview and meta */}
                  <div className="min-w-0 flex-1">
                    <p
                      className={`break-words text-sm ${
                        change.type === 'insert'
                          ? 'text-green-700 dark:text-green-400'
                          : 'text-red-700 line-through dark:text-red-400'
                      }`}
                    >
                      {truncate(change.text, 80)}
                    </p>
                    <div className="mt-1 flex items-center gap-1.5 text-[11px] text-slate-400 dark:text-slate-500">
                      {change.userColor && (
                        <span
                          className="inline-block h-2 w-2 rounded-full"
                          style={{ backgroundColor: change.userColor }}
                        />
                      )}
                      <span>{change.userName}</span>
                      <span>&middot;</span>
                      <span>{relativeTime(change.timestamp)}</span>
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="flex shrink-0 gap-1">
                    <button
                      type="button"
                      onClick={() => onAcceptChange(change.id)}
                      className="rounded p-1 text-slate-400 transition-colors hover:bg-green-100 hover:text-green-700 dark:hover:bg-green-900/40 dark:hover:text-green-400"
                      aria-label="Accept change"
                      title="Accept"
                    >
                      <span className="text-sm leading-none">&#10003;</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => onRejectChange(change.id)}
                      className="rounded p-1 text-slate-400 transition-colors hover:bg-red-100 hover:text-red-700 dark:hover:bg-red-900/40 dark:hover:text-red-400"
                      aria-label="Reject change"
                      title="Reject"
                    >
                      <span className="text-sm leading-none">&times;</span>
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              No tracked changes
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
