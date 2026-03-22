import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { X, Bot, Loader2, AlertTriangle, Trash2 } from 'lucide-react'
import { projectReferencesAPI, projectsAPI, projectDiscussionAPI } from '../../services/api'
import { useAssistantChat, type AssistantExchange } from '../../hooks/useAssistantChat'
import { useOpenRouterModels } from './ModelSelector'
import { AssistantExchangeRenderer } from './AssistantExchangeRenderer'
import { useAuth } from '../../contexts/AuthContext'
import { DiscussionAssistantSuggestedAction } from '../../types'

interface PaperChatReference {
  reference_id: string
  title: string
  authors?: string[] | null
  year?: number | null
  status?: string | null
}

interface PaperChatDrawerProps {
  isOpen: boolean
  onClose: () => void
  projectId: string
  reference: PaperChatReference | null
}

export function PaperChatDrawer({ isOpen, onClose, projectId, reference }: PaperChatDrawerProps) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const [inputValue, setInputValue] = useState('')
  const [closedInlineResults, setClosedInlineResults] = useState<Set<string>>(new Set())
  const [clearing, setClearing] = useState(false)

  // Fetch models + discussion settings
  const { models: openrouterModels } = useOpenRouterModels(projectId)
  const settingsQuery = useQuery({
    queryKey: ['discussionSettings', projectId],
    queryFn: async () => {
      const res = await projectsAPI.getDiscussionSettings(projectId)
      return res.data
    },
    enabled: isOpen,
    staleTime: 30000,
  })

  const selectedModel =
    openrouterModels.find((m) => m.id === settingsQuery.data?.model)?.id ||
    openrouterModels[0]?.id

  const currentModelInfo = openrouterModels.find((m) => m.id === selectedModel) || openrouterModels[0]

  // Get or create the paper chat channel
  const channelQuery = useQuery({
    queryKey: ['paperChatChannel', projectId, reference?.reference_id],
    queryFn: async () => {
      if (!reference) throw new Error('No reference')
      const res = await projectReferencesAPI.getOrCreateChatChannel(projectId, reference.reference_id)
      return res.data
    },
    enabled: isOpen && !!reference,
    staleTime: Infinity,
  })

  const channelId = channelQuery.data?.channel_id ?? null

  const viewerDisplayName =
    user?.first_name && user?.last_name
      ? `${user.first_name} ${user.last_name}`
      : user?.email?.split('@')[0] ?? 'You'

  const {
    assistantHistory,
    setAssistantHistory,
    sendAssistantMessage,
    cancelAssistantRequest,
    markActionApplied,
  } = useAssistantChat({
    projectId,
    activeChannelId: channelId,
    selectedModel: selectedModel || '',
    userId: user?.id,
    viewerDisplayName,
  })

  const isGenerating = assistantHistory.some((e) => {
    const p = e.streamPhase.phase
    return p !== 'complete' && p !== 'error' && p !== 'idle'
  })

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [assistantHistory])

  // Focus input when drawer opens
  useEffect(() => {
    if (isOpen && channelId && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 200)
    }
  }, [isOpen, channelId])

  const handleSend = useCallback(() => {
    const q = inputValue.trim()
    if (!q || !channelId || isGenerating) return
    sendAssistantMessage({
      question: q,
      reasoning: false,
      scope: [],
    })
    setInputValue('')
  }, [inputValue, channelId, isGenerating, sendAssistantMessage])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    },
    [handleSend]
  )

  const handleSuggestedAction = useCallback(
    (exchange: AssistantExchange, _action: DiscussionAssistantSuggestedAction, idx: number) => {
      const actionKey = `${exchange.id}:${idx}`
      markActionApplied(exchange.id, actionKey)
    },
    [markActionApplied]
  )

  const handleCloseInlineResult = useCallback((exchangeId: string) => {
    setClosedInlineResults((prev) => new Set(prev).add(exchangeId))
  }, [])

  const handleClearChat = useCallback(async () => {
    if (!channelId || clearing) return
    setClearing(true)
    try {
      await projectDiscussionAPI.deleteChannel(projectId, channelId)
      // Clear local state
      setAssistantHistory([])
      setClosedInlineResults(new Set())
      // Invalidate so next message creates a fresh channel
      queryClient.removeQueries({ queryKey: ['paperChatChannel', projectId, reference?.reference_id] })
      queryClient.removeQueries({ queryKey: ['assistant-history', projectId, channelId] })
      // Re-fetch to create a new channel
      queryClient.invalidateQueries({ queryKey: ['paperChatChannel', projectId, reference?.reference_id] })
    } catch (err) {
      console.error('Failed to clear chat:', err)
    } finally {
      setClearing(false)
    }
  }, [channelId, clearing, projectId, reference?.reference_id, setAssistantHistory, queryClient])

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isOpen, onClose])

  if (!isOpen || !reference) return null

  const authorLine = reference.authors?.length
    ? reference.authors.slice(0, 3).join(', ') + (reference.authors.length > 3 ? ' et al.' : '')
    : null

  const isPending = reference.status === 'pending'

  return createPortal(
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[60] bg-black/30 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />
      {/* Drawer */}
      <div className="fixed inset-y-0 right-0 z-[70] flex w-full flex-col bg-white shadow-2xl sm:w-[520px] dark:bg-slate-900">
        {/* Header */}
        <div className="flex items-start gap-3 border-b border-gray-200 px-4 py-3 dark:border-slate-700">
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-indigo-100 dark:bg-indigo-500/20">
            <Bot className="h-5 w-5 text-indigo-600 dark:text-indigo-300" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-sm font-semibold text-gray-900 dark:text-slate-100">
              {reference.title}
            </h3>
            {(authorLine || reference.year) && (
              <p className="truncate text-xs text-gray-500 dark:text-slate-400">
                {[authorLine, reference.year].filter(Boolean).join(' · ')}
              </p>
            )}
          </div>
          <div className="flex flex-shrink-0 items-center gap-1">
            {channelId && assistantHistory.length > 0 && (
              <button
                onClick={handleClearChat}
                disabled={clearing || isGenerating}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 transition hover:bg-red-50 hover:text-red-500 disabled:opacity-40 dark:hover:bg-red-500/10 dark:hover:text-red-400"
                title="Clear conversation"
              >
                {clearing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
              </button>
            )}
            <button
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-slate-800 dark:hover:text-slate-300"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Not-ingested notice */}
        {isPending && (
          <div className="mx-4 mt-3 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-400/30 dark:bg-amber-500/10 dark:text-amber-300">
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
            <span>This paper hasn't been fully analyzed yet. The AI may only have access to the abstract.</span>
          </div>
        )}

        {/* Chat body */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-2">
          {channelQuery.isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-indigo-500" />
              <span className="ml-2 text-sm text-gray-500 dark:text-slate-400">Setting up chat...</span>
            </div>
          ) : channelQuery.isError ? (
            <div className="flex items-center justify-center py-12 text-sm text-red-500">
              Failed to load chat channel. Please try again.
            </div>
          ) : assistantHistory.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <Bot className="mb-3 h-10 w-10 text-indigo-300 dark:text-indigo-500" />
              <p className="text-sm font-medium text-gray-700 dark:text-slate-300">
                Chat with this paper
              </p>
              <p className="mt-1 max-w-xs text-xs text-gray-500 dark:text-slate-400">
                Ask questions about the paper's methodology, findings, or anything else. The AI has access to the full text.
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {assistantHistory.map((exchange) => (
                <AssistantExchangeRenderer
                  key={exchange.id}
                  exchange={exchange}
                  openrouterModels={openrouterModels}
                  currentModelInfo={currentModelInfo || { name: 'AI' }}
                  authorLabel={viewerDisplayName}
                  onCancelRequest={cancelAssistantRequest}
                  onSuggestedAction={handleSuggestedAction}
                  projectId={projectId}
                  closedInlineResults={closedInlineResults}
                  onCloseInlineResult={handleCloseInlineResult}
                />
              ))}
            </div>
          )}
        </div>

        {/* Input */}
        {channelId && (
          <div className="border-t border-gray-200 px-4 py-3 dark:border-slate-700">
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about this paper..."
                rows={1}
                className="flex-1 resize-none rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 outline-none transition focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder-slate-500 dark:focus:border-indigo-500 dark:focus:ring-indigo-500/20"
                style={{ maxHeight: '120px' }}
                disabled={isGenerating}
              />
              <button
                onClick={handleSend}
                disabled={!inputValue.trim() || isGenerating}
                className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white transition hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed dark:bg-indigo-500 dark:hover:bg-indigo-600"
              >
                {isGenerating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0l-7 7m7-7l7 7" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </>,
    document.body
  )
}
