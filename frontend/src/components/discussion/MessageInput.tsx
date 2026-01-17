import { useState, useRef, useEffect } from 'react'
import { Send, X, Lightbulb } from 'lucide-react'

interface MessageInputProps {
  onSend: (content: string) => void
  placeholder?: string
  replyingTo?: { id: string; userName: string } | null
  onCancelReply?: () => void
  editingMessage?: { id: string; content: string } | null
  onCancelEdit?: () => void
  isSubmitting?: boolean
  reasoningEnabled?: boolean
  onToggleReasoning?: () => void
  reasoningPending?: boolean
}

const MessageInput = ({
  onSend,
  placeholder = 'Type your message...',
  replyingTo,
  onCancelReply,
  editingMessage,
  onCancelEdit,
  isSubmitting = false,
  reasoningEnabled = false,
  onToggleReasoning,
  reasoningPending = false,
}: MessageInputProps) => {
  const [content, setContent] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (editingMessage) {
      setContent(editingMessage.content)
      textareaRef.current?.focus()
    } else {
      setContent('')
    }
  }, [editingMessage])

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`
    }
  }, [content])

  useEffect(() => {
    if (!isSubmitting && textareaRef.current) {
      textareaRef.current.focus()
    }
  }, [isSubmitting])

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    const trimmed = content.trim()
    if (!trimmed || isSubmitting) return
    onSend(trimmed)
    setContent('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      // keep focus so users can continue typing without clicking
      textareaRef.current.focus()
    }
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleSubmit(event)
    }
  }

  return (
    <div className="border-t border-gray-200 bg-white p-4 transition-colors dark:border-slate-700 dark:bg-slate-900/40">
      {(replyingTo || editingMessage) && (
        <div className="mb-2 flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 dark:bg-slate-800/60">
          <span className="text-sm text-gray-600 dark:text-slate-300">
            {editingMessage ? (
              <>Editing message</>
            ) : (
              <>Replying to <span className="font-medium">{replyingTo?.userName}</span></>
            )}
          </span>
          <button
            onClick={editingMessage ? onCancelEdit : onCancelReply}
            className="text-gray-400 hover:text-gray-600 dark:text-slate-400 dark:hover:text-slate-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex gap-2">
        <textarea
          ref={textareaRef}
          value={content}
          onChange={(event) => setContent(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={isSubmitting}
          rows={1}
          className="min-h-[2.5rem] max-h-32 flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-50 disabled:text-gray-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:disabled:bg-slate-800/60 dark:disabled:text-slate-500"
        />
        {onToggleReasoning && (
          <button
            type="button"
            onClick={onToggleReasoning}
            disabled={isSubmitting || reasoningPending}
            className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg border border-gray-200 bg-white transition hover:bg-gray-50 dark:border-slate-600 dark:bg-slate-800 dark:hover:bg-slate-700"
            title="Toggle reasoning mode for Scholar AI"
          >
            <Lightbulb
              className={`h-4 w-4 transition ${
                reasoningPending
                  ? 'animate-pulse fill-amber-400 text-amber-500 drop-shadow-[0_0_4px_rgba(251,191,36,0.8)] dark:fill-amber-400 dark:text-amber-400'
                  : reasoningEnabled
                    ? 'fill-amber-400 text-amber-500 drop-shadow-[0_0_4px_rgba(251,191,36,0.8)] dark:fill-amber-400 dark:text-amber-400'
                    : 'text-gray-400 dark:text-slate-400'
              }`}
            />
          </button>
        )}
        <button
          type="submit"
          disabled={!content.trim() || isSubmitting}
          className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-gray-300 dark:disabled:bg-slate-700"
        >
          <Send className="h-4 w-4" />
        </button>
      </form>
      <p className="mt-1 text-xs text-gray-500 dark:text-slate-400">
        Press <kbd className="rounded bg-gray-100 px-1 py-0.5 dark:bg-slate-700 dark:text-slate-100">Enter</kbd> to send, <kbd className="rounded bg-gray-100 px-1 py-0.5 dark:bg-slate-700 dark:text-slate-100">Shift+Enter</kbd> for new line. Start with <span className="font-semibold">/</span> to ask Scholar AI; use the bulb icon to enable reasoning when needed.
      </p>
    </div>
  )
}

export default MessageInput
