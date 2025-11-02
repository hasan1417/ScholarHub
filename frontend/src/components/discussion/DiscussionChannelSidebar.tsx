import { Plus, MessageCircle, Archive, RotateCcw } from 'lucide-react'
import clsx from 'clsx'
import { DiscussionChannelSummary } from '../../types'

interface DiscussionChannelSidebarProps {
  channels: DiscussionChannelSummary[]
  activeChannelId: string | null
  onSelectChannel: (channelId: string) => void
  onCreateChannel: () => void
  isCreating?: boolean
  onArchiveToggle?: (channel: DiscussionChannelSummary) => void
}

const DiscussionChannelSidebar = ({
  channels,
  activeChannelId,
  onSelectChannel,
  onCreateChannel,
  isCreating = false,
  onArchiveToggle,
}: DiscussionChannelSidebarProps) => {
  return (
    <aside className="flex h-full w-60 flex-col border-r border-gray-200 bg-gray-50 transition-colors dark:border-slate-700/80 dark:bg-slate-900/40">
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-slate-700/80">
        <div className="flex items-center gap-2">
          <MessageCircle className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
          <span className="text-sm font-semibold text-gray-800 dark:text-slate-100">Channels</span>
        </div>
        <button
          type="button"
          onClick={onCreateChannel}
          disabled={isCreating}
          className="inline-flex items-center gap-1 rounded-full border border-indigo-200 px-3 py-1 text-xs font-medium text-indigo-600 transition hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
        >
          <Plus className="h-3.5 w-3.5" />
          New
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {channels.length === 0 ? (
          <div className="px-4 py-6 text-center text-xs text-gray-500">
            No channels yet. Create one to get started.
          </div>
        ) : (
          <ul className="space-y-1 px-2 py-3">
            {channels.map((channel) => {
              const isActive = channel.id === activeChannelId
              const threads = channel.stats?.total_threads ?? 0
              const messages = channel.stats?.total_messages ?? 0

              return (
                <li key={channel.id}>
                  <div
                    className={clsx(
                      'group relative rounded-xl transition',
                      isActive
                        ? 'bg-white shadow-sm ring-1 ring-indigo-200 dark:bg-slate-800/70 dark:ring-indigo-500/40 dark:shadow-lg'
                        : 'hover:bg-white dark:hover:bg-slate-800/50'
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => onSelectChannel(channel.id)}
                      className="w-full px-3 py-3 text-left text-gray-900 dark:text-slate-100"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-gray-900 dark:text-slate-100">{channel.name}</span>
                        <div className="flex items-center gap-2">
                          {channel.is_default && (
                            <span className="text-[10px] uppercase tracking-wide text-indigo-500 dark:text-indigo-300">Default</span>
                          )}
                          {onArchiveToggle && !channel.is_default && (
                            <button
                              type="button"
                              className={clsx(
                                'rounded-full p-1 text-gray-400 transition hover:bg-gray-200 hover:text-gray-700 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200',
                                isActive ? 'inline-flex' : 'hidden group-hover:inline-flex'
                              )}
                              onClick={(event) => {
                                event.stopPropagation()
                                onArchiveToggle(channel)
                              }}
                              title={channel.is_archived ? 'Unarchive channel' : 'Archive channel'}
                              aria-label={channel.is_archived ? `Unarchive ${channel.name}` : `Archive ${channel.name}`}
                            >
                              {channel.is_archived ? (
                                <RotateCcw className="h-4 w-4" />
                              ) : (
                                <Archive className="h-4 w-4" />
                              )}
                            </button>
                          )}
                        </div>
                      </div>
                      {channel.description && (
                        <p className="mt-1 line-clamp-2 text-xs text-gray-500 dark:text-slate-300">{channel.description}</p>
                      )}
                      <div className="mt-2 flex items-center gap-3 text-[11px] text-gray-500 dark:text-slate-400">
                        <span>{threads} {threads === 1 ? 'thread' : 'threads'}</span>
                        <span>•</span>
                        <span>{messages} {messages === 1 ? 'message' : 'messages'}</span>
                        {channel.is_archived && (
                          <span className="text-[10px] uppercase tracking-wide text-amber-500 dark:text-amber-300">Archived</span>
                        )}
                      </div>
                    </button>

                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </aside>
  )
}

export default DiscussionChannelSidebar
