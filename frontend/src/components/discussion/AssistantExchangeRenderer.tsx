import {
  Loader2,
  Sparkles,
  X,
  Bot,
  FileText,
  BookOpen,
  Calendar,
  Check,
  FilePlus,
  Pencil,
  Search,
  Download,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { formatDistanceToNow } from 'date-fns'
import {
  OpenRouterModel,
  DiscussionAssistantSuggestedAction,
} from '../../types'
import {
  buildCitationLookup,
  formatAssistantMessage,
  type AssistantExchange,
} from '../../hooks/useAssistantChat'
import { DiscoveredPaper } from './DiscoveredPaperCard'
import { ReferenceSearchResults, LibraryUpdateItem } from './ReferenceSearchResults'

interface AssistantExchangeRendererProps {
  exchange: AssistantExchange
  openrouterModels: OpenRouterModel[]
  currentModelInfo: { name: string }
  authorLabel: string
  onCancelRequest: () => void
  onSuggestedAction: (exchange: AssistantExchange, action: DiscussionAssistantSuggestedAction, idx: number) => void
  onNavigateToPaper?: (urlId: string) => void
  paperActionPending?: boolean
  searchReferencesPending?: boolean
  projectId?: string
  closedInlineResults?: Set<string>
  onCloseInlineResult?: (exchangeId: string) => void
  libraryUpdatesBySearchId?: Record<string, LibraryUpdateItem[]>
  onDismissPaper?: (paperId: string) => void
}

export function AssistantExchangeRenderer({
  exchange,
  openrouterModels,
  currentModelInfo,
  authorLabel,
  onCancelRequest,
  onSuggestedAction,
  onNavigateToPaper,
  paperActionPending,
  searchReferencesPending,
  projectId,
  closedInlineResults,
  onCloseInlineResult,
  libraryUpdatesBySearchId,
  onDismissPaper,
}: AssistantExchangeRendererProps) {
  const citationLookup = buildCitationLookup(exchange.response.citations)
  const formattedMessage = formatAssistantMessage(exchange.response.message, citationLookup)
  const askedLabel = formatDistanceToNow(exchange.createdAt, { addSuffix: true })
  const answerLabel = exchange.completedAt
    ? formatDistanceToNow(exchange.completedAt, { addSuffix: true })
    : askedLabel
  const displayedMessage = exchange.displayMessage || formattedMessage
  const showTyping = !displayedMessage && exchange.status !== 'complete'
  const isExecutingTools = displayedMessage && exchange.isWaitingForTools && exchange.status !== 'complete'
  const avatarText = authorLabel.trim().charAt(0).toUpperCase() || 'U'
  const modelName = exchange.model
    ? openrouterModels.find((m) => m.id === exchange.model)?.name || exchange.model
    : currentModelInfo.name

  const promptBubbleClass = 'inline-block max-w-full sm:max-w-fit rounded-xl sm:rounded-2xl bg-purple-50/70 px-3 py-1.5 sm:px-4 sm:py-2 shadow-sm ring-2 ring-purple-200 transition dark:bg-purple-500/15 dark:ring-purple-400/40 dark:shadow-purple-900/30'
  const responseBubbleClass = 'inline-block max-w-full sm:max-w-fit rounded-xl sm:rounded-2xl bg-white px-3 py-1.5 sm:px-4 sm:py-2 transition dark:bg-slate-800/70 dark:ring-1 dark:ring-slate-700'

  return (
    <div className="border-b border-gray-100 pb-3 sm:pb-4 last:border-b-0 dark:border-slate-700">
      <div className="space-y-3 sm:space-y-4 pt-3 sm:pt-4">
        {/* User question */}
        <div className="flex items-start gap-2 sm:gap-3">
          <div className="flex h-6 w-6 sm:h-8 sm:w-8 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs sm:text-sm font-medium text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-200">
            {avatarText}
          </div>
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="mb-1 flex flex-wrap items-center gap-1.5 sm:gap-2">
              <span className="text-xs sm:text-sm font-medium text-gray-900 dark:text-slate-100">{authorLabel}</span>
              <span className="text-[10px] sm:text-xs text-gray-500">{askedLabel}</span>
              <span className="inline-flex items-center gap-0.5 sm:gap-1 rounded-full bg-indigo-100 px-1.5 py-0.5 text-[9px] sm:text-[10px] font-medium text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200">
                <Bot className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                {modelName}
              </span>
            </div>
            <div className={promptBubbleClass}>
              <p className="text-xs sm:text-sm text-gray-700 dark:text-slate-200 break-words">{exchange.question}</p>
            </div>
          </div>
        </div>
        {/* AI response */}
        <div className="flex items-start gap-2 sm:gap-3">
          <div className="flex h-6 w-6 sm:h-8 sm:w-8 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs sm:text-sm font-medium text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-200">
            AI
          </div>
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="mb-1 flex flex-wrap items-center gap-1.5 sm:gap-2">
              <span className="text-xs sm:text-sm font-medium text-gray-900 dark:text-slate-100">Scholar AI</span>
              <span className="text-[10px] sm:text-xs text-gray-500">{answerLabel}</span>
              {exchange.response.reasoning_used && (
                <span className="inline-flex items-center gap-0.5 sm:gap-1 rounded-full bg-emerald-50 px-1.5 py-0.5 text-[9px] sm:text-[10px] font-medium text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-200">
                  <Sparkles className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                  Reasoning
                </span>
              )}
            </div>
            <div className={responseBubbleClass}>
              {showTyping ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2.5 text-sm font-medium text-indigo-600 dark:text-indigo-300">
                      <div className="relative">
                        <Loader2 className="h-4 w-4 animate-spin" />
                      </div>
                      <span>{exchange.statusMessage || 'Thinking'}...</span>
                    </div>
                    <button
                      onClick={onCancelRequest}
                      className="ml-auto flex h-6 w-6 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
                      title="Cancel"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="h-1 w-1 animate-pulse rounded-full bg-indigo-400 dark:bg-indigo-500" style={{ animationDelay: '0ms' }} />
                    <div className="h-1 w-1 animate-pulse rounded-full bg-indigo-400 dark:bg-indigo-500" style={{ animationDelay: '150ms' }} />
                    <div className="h-1 w-1 animate-pulse rounded-full bg-indigo-400 dark:bg-indigo-500" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              ) : (
                <div className="prose prose-sm max-w-none text-gray-900 dark:prose-invert prose-headings:font-semibold prose-headings:text-gray-900 dark:prose-headings:text-slate-100 prose-h2:text-base prose-h3:text-sm prose-h4:text-sm prose-p:leading-relaxed prose-p:my-1.5 prose-strong:text-gray-900 dark:prose-strong:text-white prose-strong:font-semibold prose-code:rounded prose-code:bg-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:text-indigo-700 prose-code:before:content-none prose-code:after:content-none dark:prose-code:bg-slate-700 dark:prose-code:text-indigo-300 prose-blockquote:border-indigo-300 prose-blockquote:text-gray-600 dark:prose-blockquote:border-indigo-500 dark:prose-blockquote:text-slate-300 prose-li:marker:text-gray-400 prose-a:text-indigo-600 dark:prose-a:text-indigo-400 prose-a:no-underline hover:prose-a:underline">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {displayedMessage}
                  </ReactMarkdown>
                </div>
              )}
              {isExecutingTools && (
                <div className="mt-3 flex items-center gap-2 text-sm text-indigo-600 dark:text-indigo-400">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>{exchange.statusMessage}...</span>
                </div>
              )}
            </div>
            {/* Citations */}
            {!showTyping && exchange.response.citations.length > 0 && (
              <div className="mt-2 sm:mt-3 space-y-1 sm:space-y-1.5">
                <p className="text-[10px] sm:text-xs font-medium text-slate-500 dark:text-slate-400">Sources Used:</p>
                <div className="flex flex-wrap gap-1.5 sm:gap-2">
                  {exchange.response.citations.map((citation) => {
                    const getResourceIcon = (resourceType?: string) => {
                      switch (resourceType) {
                        case 'paper': return <FileText className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-blue-500" />
                        case 'reference': return <BookOpen className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-emerald-500" />
                        case 'meeting': return <Calendar className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-purple-500" />
                        default: return <FileText className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-slate-400" />
                      }
                    }
                    return (
                      <div
                        key={`${exchange.id}-${citation.origin}-${citation.origin_id}`}
                        className="inline-flex items-center gap-1 sm:gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-1.5 py-1 sm:px-2.5 sm:py-1.5 text-[10px] sm:text-xs dark:border-slate-700 dark:bg-slate-800"
                      >
                        {getResourceIcon(citation.resource_type ?? undefined)}
                        <span className="font-medium text-slate-700 dark:text-slate-200 truncate max-w-[100px] sm:max-w-none">
                          {citation.label}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
            {/* Paper created/updated actions */}
            {!showTyping && exchange.response.suggested_actions?.some(a => a.action_type === 'paper_created' || a.action_type === 'paper_updated') && (
              <div className="mt-2 sm:mt-3 flex flex-wrap gap-1.5 sm:gap-2">
                {exchange.response.suggested_actions
                  .filter(a => a.action_type === 'paper_created' || a.action_type === 'paper_updated')
                  .map((action, idx) => {
                    const urlId = action.payload?.url_id || action.payload?.paper_id
                    return (
                      <button
                        key={idx}
                        onClick={() => onNavigateToPaper?.(urlId)}
                        className="inline-flex items-center gap-1.5 sm:gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 sm:px-3 sm:py-2 text-xs sm:text-sm font-medium text-emerald-700 hover:bg-emerald-100 dark:border-emerald-400/30 dark:bg-emerald-500/10 dark:text-emerald-300 dark:hover:bg-emerald-500/20 transition-colors"
                      >
                        <FileText className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-emerald-600 dark:text-emerald-400" />
                        View Paper
                      </button>
                    )
                  })}
              </div>
            )}
            {/* Suggested actions */}
            {!showTyping && exchange.response.suggested_actions && exchange.response.suggested_actions.filter(a =>
              a.action_type !== 'paper_created' &&
              a.action_type !== 'paper_updated' &&
              a.action_type !== 'library_update' &&
              a.action_type !== 'search_results'
            ).length > 0 && (
              <div className="mt-2 space-y-1">
                <p className="text-[10px] sm:text-[11px] uppercase tracking-wide text-gray-400">Suggested actions</p>
                <div className="flex flex-wrap gap-1.5 sm:gap-2">
                  {exchange.response.suggested_actions.filter(a =>
                    a.action_type !== 'paper_created' &&
                    a.action_type !== 'paper_updated' &&
                    a.action_type !== 'library_update' &&
                    a.action_type !== 'search_results'
                  ).map((action, idx) => {
                    const actionKey = `${exchange.id}:${idx}`
                    const applied = exchange.appliedActions.includes(actionKey)
                    const isPending = (paperActionPending || searchReferencesPending) ?? false
                    const getActionIcon = () => {
                      if (applied) return <Check className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                      switch (action.action_type) {
                        case 'create_paper': return <FilePlus className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                        case 'edit_paper': return <Pencil className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                        case 'search_references': return <Search className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                        case 'artifact_created': return <Download className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                        default: return <Sparkles className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
                      }
                    }
                    return (
                      <button
                        key={actionKey}
                        type="button"
                        onClick={() => onSuggestedAction(exchange, action, idx)}
                        disabled={applied || isPending}
                        className={`inline-flex items-center gap-1 sm:gap-1.5 rounded-full border px-2 py-0.5 sm:px-3 sm:py-1 text-[10px] sm:text-xs font-medium transition ${applied ? 'border-emerald-300 bg-emerald-50 text-emerald-600 dark:border-emerald-400/40 dark:bg-emerald-500/20 dark:text-emerald-200' : 'border-indigo-200 bg-white text-indigo-600 hover:bg-indigo-50 dark:border-indigo-400/40 dark:bg-slate-800/70 dark:text-indigo-200 dark:hover:bg-indigo-500/10'}`}
                      >
                        {getActionIcon()}
                        <span className="truncate max-w-[80px] sm:max-w-none">{applied ? 'Applied' : action.summary}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
            {/* Model info */}
            {!showTyping && (
              <div className="mt-1.5 sm:mt-2 flex flex-wrap items-center gap-2 sm:gap-3 text-[9px] sm:text-[11px] text-gray-400 dark:text-slate-500">
                <span>Model: {modelName}</span>
              </div>
            )}
          </div>
        </div>
      </div>
      {/* Inline paper search results */}
      {!showTyping && (() => {
        const searchAction = exchange.response.suggested_actions?.find(
          a => a.action_type === 'search_results'
        )
        if (!searchAction) return null
        const payload = searchAction.payload as {
          query?: string
          papers?: DiscoveredPaper[]
          search_id?: string
        } | undefined
        const papers = payload?.papers || []
        const query = payload?.query || ''
        const searchId = payload?.search_id
        if (papers.length === 0 && exchange.status === 'complete') return null
        if (closedInlineResults?.has(exchange.id)) return null
        const externalUpdates = searchId ? libraryUpdatesBySearchId?.[searchId] : undefined
        return (
          <div className="ml-8 sm:ml-11">
            <ReferenceSearchResults
              papers={papers}
              query={query}
              projectId={projectId || ''}
              onClose={() => onCloseInlineResult?.(exchange.id)}
              isSearching={exchange.status !== 'complete'}
              externalUpdates={externalUpdates}
              onDismissPaper={onDismissPaper}
            />
          </div>
        )
      })()}
    </div>
  )
}
