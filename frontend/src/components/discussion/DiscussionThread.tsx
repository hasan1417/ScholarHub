import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { DiscussionThread as DiscussionThreadType, DiscussionMessage } from '../../types'
import MessageBubble from './MessageBubble'

interface DiscussionThreadProps {
  thread: DiscussionThreadType
  currentUserId: string
  onReply: (message: DiscussionMessage) => void
  onEdit: (message: DiscussionMessage) => void
  onDelete: (messageId: string) => void
}

const DiscussionThread = ({
  thread,
  currentUserId,
  onReply,
  onEdit,
  onDelete,
}: DiscussionThreadProps) => {
  const [isExpanded, setIsExpanded] = useState(true)
  const hasReplies = thread.replies && thread.replies.length > 0

  return (
    <div className="border-b border-gray-100 pb-4 last:border-b-0 dark:border-slate-700">
      {/* Main Message */}
      <MessageBubble
        message={thread.message}
        currentUserId={currentUserId}
        onReply={onReply}
        onEdit={onEdit}
        onDelete={onDelete}
      />

      {/* Replies Section */}
      {hasReplies && (
        <div className="mt-2">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="ml-12 inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700 dark:text-indigo-300 dark:hover:text-indigo-200"
          >
            {isExpanded ? (
              <>
                <ChevronUp className="h-3 w-3" />
                Hide replies ({thread.replies.length})
              </>
            ) : (
              <>
                <ChevronDown className="h-3 w-3" />
                Show replies ({thread.replies.length})
              </>
            )}
          </button>

          {isExpanded && (
            <div className="space-y-2">
              {thread.replies.map((reply) => (
                <MessageBubble
                  key={reply.id}
                  message={reply}
                  currentUserId={currentUserId}
                  onEdit={onEdit}
                  onDelete={onDelete}
                  isReply
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default DiscussionThread
