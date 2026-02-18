import { useState } from 'react'
import clsx from 'clsx'
import { Edit2, Trash2, Reply, MoreVertical } from 'lucide-react'
import { DiscussionMessage } from '../../types'
import { formatDistanceToNow } from 'date-fns'

interface MessageBubbleProps {
  message: DiscussionMessage
  currentUserId: string
  onReply?: (message: DiscussionMessage) => void
  onEdit?: (message: DiscussionMessage) => void
  onDelete?: (messageId: string) => void
  isReply?: boolean
}

const MessageBubble = ({
  message,
  currentUserId,
  onReply,
  onEdit,
  onDelete,
  isReply = false,
}: MessageBubbleProps) => {
  const [showActions, setShowActions] = useState(false)
  const isAuthor = message.user_id === currentUserId
  const canEdit = isAuthor && !message.is_deleted
  const canDelete = isAuthor

  const displayName = message.user.name || message.user.email.split('@')[0]
  const timeAgo = formatDistanceToNow(new Date(message.created_at), { addSuffix: true })

  return (
    <div className={clsx('group relative', isReply ? 'ml-8 sm:ml-12 mt-3' : 'mt-4')}>
      <div className="flex gap-2 sm:gap-3">
        {/* Avatar */}
        <div className="flex-shrink-0">
          <div className="flex h-7 w-7 sm:h-8 sm:w-8 items-center justify-center rounded-full bg-indigo-100 text-xs sm:text-sm font-medium text-indigo-600 dark:bg-indigo-500/25 dark:text-indigo-200">
            {displayName.charAt(0).toUpperCase()}
          </div>
        </div>

        {/* Message Content */}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="mb-1 flex flex-wrap items-center gap-1.5 sm:gap-2">
            <span className="text-xs sm:text-sm font-medium text-gray-900 dark:text-slate-100 truncate max-w-[120px] sm:max-w-none">{displayName}</span>
            <span className="text-[10px] sm:text-xs text-gray-500">{timeAgo}</span>
            {message.is_edited && (
              <span className="text-[10px] sm:text-xs text-gray-400">(edited)</span>
            )}
          </div>

          <div
            className={clsx(
              'inline-block max-w-full sm:max-w-fit rounded-xl sm:rounded-2xl px-3 py-1.5 sm:px-4 sm:py-2 transition',
              isAuthor
                ? 'bg-indigo-100 shadow-sm ring-1 ring-indigo-200 dark:bg-indigo-500/20 dark:ring-indigo-400/40 dark:shadow-indigo-900/30'
                : 'bg-gray-50 ring-1 ring-gray-200 dark:bg-slate-800/70 dark:ring-slate-700'
            )}
          >
            <div className={clsx(
              'whitespace-pre-wrap break-words text-xs sm:text-sm',
              isAuthor ? 'text-indigo-900 dark:text-indigo-100' : 'text-gray-700 dark:text-slate-100'
            )}>
              {message.content}
            </div>
          </div>

          {/* Actions Bar */}
          <div className="mt-1 flex items-center gap-2 sm:gap-3">
            {!message.is_deleted && onReply && (
              <button
                onClick={() => onReply(message)}
                className="inline-flex items-center gap-1 text-[10px] sm:text-xs text-gray-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-300"
              >
                <Reply className="h-3 w-3" />
                Reply
              </button>
            )}
            {message.reply_count > 0 && (
              <span className="text-[10px] sm:text-xs text-gray-500">
                {message.reply_count} {message.reply_count === 1 ? 'reply' : 'replies'}
              </span>
            )}
          </div>
        </div>

        {/* More Actions Menu */}
        {(canEdit || canDelete) && (
          <div className="relative flex-shrink-0">
            <button
              onClick={() => setShowActions(!showActions)}
              className="rounded-full p-1 text-gray-400 sm:opacity-0 transition sm:group-hover:opacity-100 hover:bg-gray-100 hover:text-gray-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
            >
              <MoreVertical className="h-4 w-4" />
            </button>

            {showActions && (
              <div className="absolute right-0 top-6 z-10 w-28 sm:w-32 rounded-lg border border-gray-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-800 dark:shadow-black/30">
                {canEdit && onEdit && (
                  <button
                    onClick={() => {
                      onEdit(message)
                      setShowActions(false)
                    }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-xs sm:text-sm text-gray-700 hover:bg-gray-50 dark:text-slate-200 dark:hover:bg-slate-700"
                  >
                    <Edit2 className="h-3 w-3" />
                    Edit
                  </button>
                )}
                {canDelete && onDelete && (
                  <button
                    onClick={() => {
                      onDelete(message.id)
                      setShowActions(false)
                    }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-xs sm:text-sm text-red-600 hover:bg-red-50 dark:text-rose-300 dark:hover:bg-rose-500/10"
                  >
                    <Trash2 className="h-3 w-3" />
                    Delete
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default MessageBubble
