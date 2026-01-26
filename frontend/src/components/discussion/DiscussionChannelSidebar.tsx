import { useState, useRef, useEffect } from 'react'
import { Plus, MessageCircle, Archive, RotateCcw, Settings, ChevronDown, Hash } from 'lucide-react'
import clsx from 'clsx'
import { formatDistanceToNow } from 'date-fns'
import { DiscussionChannelSummary } from '../../types'

interface DiscussionChannelSidebarProps {
  channels: DiscussionChannelSummary[]
  activeChannelId: string | null
  onSelectChannel: (channelId: string) => void
  onCreateChannel: () => void
  isCreating?: boolean
  onArchiveToggle?: (channel: DiscussionChannelSummary) => void
  onOpenSettings?: (channel: DiscussionChannelSummary) => void
  showArchived?: boolean
  onToggleShowArchived?: () => void
}

// Format relative time in a compact way
const formatCompactTime = (dateString: string): string => {
  try {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return 'now'
    if (diffMins < 60) return `${diffMins}m`
    if (diffHours < 24) return `${diffHours}h`
    if (diffDays < 7) return `${diffDays}d`
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}w`
    return formatDistanceToNow(date, { addSuffix: false }).replace(' months', 'mo').replace(' month', 'mo')
  } catch {
    return ''
  }
}

const DiscussionChannelSidebar = ({
  channels,
  activeChannelId,
  onSelectChannel,
  onCreateChannel,
  isCreating = false,
  onArchiveToggle,
  onOpenSettings,
  showArchived = false,
  onToggleShowArchived,
}: DiscussionChannelSidebarProps) => {
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const archivedCount = channels.filter((c) => c.is_archived).length
  const activeCount = channels.filter((c) => !c.is_archived).length
  const visibleChannels = showArchived
    ? channels.filter((c) => c.is_archived)
    : channels.filter((c) => !c.is_archived)

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleFilterSelect = (archived: boolean) => {
    if (archived !== showArchived && onToggleShowArchived) {
      onToggleShowArchived()
    }
    setDropdownOpen(false)
  }

  return (
    <aside className="flex h-full w-60 flex-col rounded-2xl border border-gray-200 bg-white shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-900/40">
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-slate-700/80">
        <div className="flex items-center gap-2">
          <MessageCircle className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
          <span className="text-sm font-semibold text-gray-800 dark:text-slate-100">Channels</span>
          {archivedCount > 0 && (
            <div className="relative" ref={dropdownRef}>
              <button
                type="button"
                onClick={() => setDropdownOpen(!dropdownOpen)}
                className={clsx(
                  'flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium transition',
                  showArchived
                    ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300'
                    : 'text-gray-500 hover:bg-gray-200 dark:text-slate-400 dark:hover:bg-slate-700'
                )}
              >
                {showArchived ? (
                  <>
                    <Archive className="h-3 w-3" />
                    <span>{archivedCount}</span>
                  </>
                ) : (
                  <>
                    <span>All</span>
                    <ChevronDown className={clsx('h-3 w-3 transition-transform', dropdownOpen && 'rotate-180')} />
                  </>
                )}
              </button>

              {dropdownOpen && (
                <div className="absolute left-0 top-full z-50 mt-1 w-36 rounded-md border border-gray-200 bg-white py-0.5 shadow-md dark:border-slate-700 dark:bg-slate-800">
                  <button
                    type="button"
                    onClick={() => handleFilterSelect(false)}
                    className={clsx(
                      'flex w-full items-center justify-between px-2.5 py-1.5 text-xs transition',
                      !showArchived
                        ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300'
                        : 'text-gray-600 hover:bg-gray-50 dark:text-slate-300 dark:hover:bg-slate-700'
                    )}
                  >
                    <span>All</span>
                    <span className="text-[10px] text-gray-400 dark:text-slate-500">{activeCount}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleFilterSelect(true)}
                    className={clsx(
                      'flex w-full items-center justify-between px-2.5 py-1.5 text-xs transition',
                      showArchived
                        ? 'bg-amber-50 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300'
                        : 'text-gray-600 hover:bg-gray-50 dark:text-slate-300 dark:hover:bg-slate-700'
                    )}
                  >
                    <div className="flex items-center gap-1.5">
                      <Archive className="h-3 w-3" />
                      <span>Archived</span>
                    </div>
                    <span className="text-[10px] text-gray-400 dark:text-slate-500">{archivedCount}</span>
                  </button>
                </div>
              )}
            </div>
          )}
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
        {visibleChannels.length === 0 ? (
          <div className="px-4 py-6 text-center text-xs text-gray-500">
            {showArchived
              ? 'No archived channels.'
              : archivedCount > 0
              ? 'All channels are archived.'
              : 'No channels yet. Create one to get started.'}
          </div>
        ) : (
          <ul className="space-y-0.5 px-2 py-2">
            {visibleChannels.map((channel) => {
              const isActive = channel.id === activeChannelId
              const messageCount = channel.stats?.total_messages ?? 0
              const lastActivity = formatCompactTime(channel.updated_at)

              return (
                <li key={channel.id}>
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={() => onSelectChannel(channel.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        onSelectChannel(channel.id)
                      }
                    }}
                    className={clsx(
                      'group relative rounded-lg transition-all cursor-pointer border-l-2 px-2.5 py-2.5',
                      isActive
                        ? 'bg-indigo-50 border-l-indigo-500 dark:bg-indigo-500/10 dark:border-l-indigo-400'
                        : channel.is_default
                          ? 'border-l-transparent hover:bg-indigo-50/50 hover:border-l-indigo-300 dark:hover:bg-indigo-500/5'
                          : 'border-l-transparent hover:bg-gray-50 hover:border-l-gray-300 dark:hover:bg-slate-800/50 dark:hover:border-l-slate-500'
                    )}
                  >
                    <div className="flex items-start gap-2">
                      {/* Hash icon */}
                      <Hash className={clsx(
                        'h-4 w-4 flex-shrink-0 mt-0.5',
                        isActive
                          ? 'text-indigo-500 dark:text-indigo-400'
                          : 'text-gray-400 dark:text-slate-500'
                      )} />

                      {/* Channel info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className={clsx(
                            'text-sm font-medium truncate',
                            isActive
                              ? 'text-indigo-700 dark:text-indigo-200'
                              : channel.is_default
                                ? 'text-gray-800 dark:text-slate-100'
                                : 'text-gray-700 dark:text-slate-200'
                          )}>
                            {channel.name}
                          </span>

                          {/* Right side: timestamp + actions */}
                          <div className="flex items-center gap-1.5 flex-shrink-0">
                            {lastActivity && !channel.is_archived && (
                              <span className="text-[10px] text-gray-400 dark:text-slate-500">
                                {lastActivity}
                              </span>
                            )}

                            {/* Action buttons - show on hover or when active */}
                            {onOpenSettings && !channel.is_default && (
                              <button
                                type="button"
                                className={clsx(
                                  'rounded p-0.5 text-gray-400 transition hover:bg-gray-200 hover:text-gray-600 dark:text-slate-500 dark:hover:bg-slate-700 dark:hover:text-slate-300',
                                  isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                                )}
                                onClick={(event) => {
                                  event.stopPropagation()
                                  onOpenSettings(channel)
                                }}
                                title="Channel settings"
                              >
                                <Settings className="h-3.5 w-3.5" />
                              </button>
                            )}
                            {onArchiveToggle && !channel.is_default && (
                              <button
                                type="button"
                                className={clsx(
                                  'rounded p-0.5 text-gray-400 transition hover:bg-gray-200 hover:text-gray-600 dark:text-slate-500 dark:hover:bg-slate-700 dark:hover:text-slate-300',
                                  isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                                )}
                                onClick={(event) => {
                                  event.stopPropagation()
                                  onArchiveToggle(channel)
                                }}
                                title={channel.is_archived ? 'Unarchive' : 'Archive'}
                              >
                                {channel.is_archived ? (
                                  <RotateCcw className="h-3.5 w-3.5" />
                                ) : (
                                  <Archive className="h-3.5 w-3.5" />
                                )}
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Second row: badges and description preview */}
                        <div className="mt-1 flex items-center gap-2">
                          {channel.is_default && (
                            <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300">
                              Default
                            </span>
                          )}
                          {channel.is_archived && (
                            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-amber-600 dark:bg-amber-500/20 dark:text-amber-300">
                              Archived
                            </span>
                          )}
                          {messageCount > 0 && !channel.is_archived && (
                            <span className="text-[10px] text-gray-400 dark:text-slate-500">
                              {messageCount} message{messageCount !== 1 ? 's' : ''}
                            </span>
                          )}
                          {channel.description && !channel.is_default && !channel.is_archived && (
                            <span className="text-[10px] text-gray-400 dark:text-slate-500 truncate">
                              {channel.description}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
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
