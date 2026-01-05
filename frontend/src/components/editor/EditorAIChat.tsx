import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Bot, Brain, Check, ChevronDown, ChevronUp, Edit3, Loader2, Send, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { projectReferencesAPI, buildApiUrl, buildAuthHeaders } from '../../services/api'

/** Proposed edit from AI */
interface EditProposal {
  id: string
  description: string
  original: string
  proposed: string
  status: 'pending' | 'approved' | 'rejected'
}

interface EditorAIChatProps {
  paperId: string
  projectId?: string
  documentText: string
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Callback to apply an approved edit to the document */
  onApplyEdit?: (original: string, replacement: string) => boolean
}

type ChatMessage = { role: 'user' | 'assistant'; content: string; proposals?: EditProposal[] }

interface ReferenceItem {
  id: string
  title: string
  pdfUrl?: string | null
}

const MAX_DOC_CONTEXT_CHARS = 4000

const EditorAIChat: React.FC<EditorAIChatProps> = ({
  paperId,
  projectId,
  documentText,
  open,
  onOpenChange,
  onApplyEdit,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [references, setReferences] = useState<ReferenceItem[]>([])
  const [reasoningMode, setReasoningMode] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [expandedProposals, setExpandedProposals] = useState<Set<string>>(new Set())
  const listRef = useRef<HTMLDivElement | null>(null)

  /** Parse edit proposals from AI response using special markers */
  const parseEditProposals = useCallback((text: string): { cleanText: string; proposals: EditProposal[] } => {
    const proposals: EditProposal[] = []
    // Match format: <<<EDIT>>> description <<<ORIGINAL>>> text <<<PROPOSED>>> text <<<END>>>
    const editRegex = /<<<EDIT>>>\s*([\s\S]*?)<<<ORIGINAL>>>\s*([\s\S]*?)<<<PROPOSED>>>\s*([\s\S]*?)<<<END>>>/g
    let match
    let cleanText = text

    while ((match = editRegex.exec(text)) !== null) {
      const [fullMatch, description, original, proposed] = match
      proposals.push({
        id: `edit-${Date.now()}-${proposals.length}`,
        description: description.trim(),
        original: original.trim(),
        proposed: proposed.trim(),
        status: 'pending',
      })
      cleanText = cleanText.replace(fullMatch, '')
    }

    return { cleanText: cleanText.trim(), proposals }
  }, [])

  /** Handle approving an edit proposal */
  const handleApproveEdit = useCallback((messageIdx: number, proposalId: string) => {
    setMessages((prev) => {
      const copy = [...prev]
      const msg = copy[messageIdx]
      if (!msg?.proposals) return prev

      const proposal = msg.proposals.find((p) => p.id === proposalId)
      if (!proposal || proposal.status !== 'pending') return prev

      // Try to apply the edit
      const success = onApplyEdit?.(proposal.original, proposal.proposed) ?? false

      if (success) {
        msg.proposals = msg.proposals.map((p) =>
          p.id === proposalId ? { ...p, status: 'approved' as const } : p
        )
      } else {
        setError('Could not find the text to replace. The document may have changed.')
      }

      return copy
    })
  }, [onApplyEdit])

  /** Handle rejecting an edit proposal */
  const handleRejectEdit = useCallback((messageIdx: number, proposalId: string) => {
    setMessages((prev) => {
      const copy = [...prev]
      const msg = copy[messageIdx]
      if (!msg?.proposals) return prev

      msg.proposals = msg.proposals.map((p) =>
        p.id === proposalId ? { ...p, status: 'rejected' as const } : p
      )

      return copy
    })
  }, [])

  /** Toggle proposal expansion */
  const toggleProposalExpanded = useCallback((proposalId: string) => {
    setExpandedProposals((prev) => {
      const next = new Set(prev)
      if (next.has(proposalId)) {
        next.delete(proposalId)
      } else {
        next.add(proposalId)
      }
      return next
    })
  }, [])

  useEffect(() => {
    if (!open) return
    const load = async () => {
      if (!projectId || !paperId) {
        setReferences([])
        return
      }
      try {
        const res = await projectReferencesAPI.listPaperReferences(projectId, paperId)
        const refs = Array.isArray(res.data?.references)
          ? res.data.references
              .map((ref: any) => ({
                id: String(ref.id ?? ref.reference_id ?? Math.random()),
                title: ref.title || ref.citation || ref.original_title || 'Untitled reference',
                pdfUrl: ref.pdf_url ?? null,
              }))
              .slice(0, 12)
          : []
        setReferences(refs)
      } catch (e: any) {
        console.warn('[EditorAIChat] Failed to load references', e)
      }
    }
    void load()
  }, [open, paperId, projectId])

  useEffect(() => {
    if (!open) {
      setMessages([])
      setInput('')
      setError(null)
      setExpandedProposals(new Set())
      // Reset edit mode when closing to avoid stale state
      setEditMode(false)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    if (!listRef.current) return
    listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, open])

  const docContext = useMemo(() => {
    if (!documentText) return null
    try {
      const stripped = documentText.replace(/<[^>]+>/g, ' ')
      const normalized = stripped.replace(/\s+/g, ' ').trim()
      const truncated = normalized.slice(0, MAX_DOC_CONTEXT_CHARS)
      return truncated || null
    } catch {
      const fallback = (documentText || '').slice(0, MAX_DOC_CONTEXT_CHARS).trim()
      return fallback || null
    }
  }, [documentText])

  const missingPdfCount = useMemo(() => references.filter((r) => !r.pdfUrl).length, [references])

  /** Document content stats for debugging */
  const docStats = useMemo(() => {
    const len = documentText?.length || 0
    const lines = documentText?.split('\n').length || 0
    return { len, lines }
  }, [documentText])

  const handleSend = useCallback(async () => {
    if (!input.trim() || sending) return
    const prompt = input.trim()
    setInput('')
    setSending(true)
    setError(null)
    setMessages((prev) => [...prev, { role: 'user', content: prompt }])

    // In edit mode, send full document (up to 50k chars); otherwise use excerpt
    const MAX_EDIT_DOC_CHARS = 50000
    const docToSend = editMode
      ? (documentText || '').slice(0, MAX_EDIT_DOC_CHARS)
      : docContext || null

    console.log('[EditorAIChat] Sending request:', {
      editMode,
      reasoningMode,
      docLength: docToSend?.length || 0,
      prompt: prompt.slice(0, 50),
    })

    try {
      // Use smart agent endpoint
      const res = await fetch(buildApiUrl('/agent/chat/stream'), {
        method: 'POST',
        headers: buildAuthHeaders(),
        body: JSON.stringify({
          query: prompt,
          paper_id: paperId,
          project_id: projectId || null,
          document_excerpt: docToSend,
          reasoning_mode: reasoningMode,
          edit_mode: editMode,
        }),
      })

      if (!res.ok) {
        const errText = await res.text()
        throw new Error(errText || 'Chat request failed.')
      }

      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      let fullText = ''

      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const chunk = decoder.decode(value || new Uint8Array(), { stream: true })
          fullText += chunk
          setMessages((prev) => {
            const copy = [...prev]
            const last = copy.length - 1
            if (last >= 0 && copy[last].role === 'assistant') {
              copy[last] = { ...copy[last], content: copy[last].content + chunk }
            } else {
              copy.push({ role: 'assistant', content: chunk })
            }
            return copy
          })
        }
      }

      // After streaming completes, parse edit proposals if in edit mode
      if (editMode && fullText.includes('<<<EDIT>>>')) {
        const { cleanText, proposals } = parseEditProposals(fullText)
        setMessages((prev) => {
          const copy = [...prev]
          const last = copy.length - 1
          if (last >= 0 && copy[last].role === 'assistant') {
            copy[last] = { ...copy[last], content: cleanText, proposals }
            // Auto-expand first proposal
            if (proposals.length > 0) {
              setExpandedProposals(new Set([proposals[0].id]))
            }
          }
          return copy
        })
      }

      if (!fullText.trim()) {
        setMessages((prev) => {
          const last = prev.length - 1
          if (last < 0 || prev[last].role !== 'assistant') {
            return [...prev, { role: 'assistant', content: 'No response received.' }]
          }
          return prev
        })
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Chat request failed.'
      setError(msg)
      setMessages((prev) => {
        const copy = [...prev]
        if (copy.length >= 1 && copy[copy.length - 1].role === 'user' && copy[copy.length - 1].content === prompt) {
          copy.pop()
        }
        return copy
      })
    } finally {
      setSending(false)
    }
  }, [docContext, documentText, editMode, input, paperId, parseEditProposals, projectId, reasoningMode, sending])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        void handleSend()
      }
    },
    [handleSend]
  )

  if (!open) return null

  return (
    <div className="fixed bottom-24 left-1/2 z-40 w-[min(960px,95vw)] -translate-x-1/2 rounded-2xl border border-slate-200 bg-white/95 shadow-2xl backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-700">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-200">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">AI Chat</div>
            <div className="text-xs text-slate-500 dark:text-slate-400">Smart agent with tiered routing</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Edit Mode Toggle */}
          <button
            onClick={() => setEditMode(!editMode)}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
              editMode
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
            }`}
            title={editMode ? 'AI can suggest document edits (requires approval)' : 'Enable to let AI suggest edits'}
          >
            <Edit3 className="h-3.5 w-3.5" />
            {editMode ? 'Edit Mode' : 'Edit'}
          </button>
          {/* Reasoning Mode Toggle */}
          <button
            onClick={() => setReasoningMode(!reasoningMode)}
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
              reasoningMode
                ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
            }`}
            title={reasoningMode ? 'Using GPT-5.2 (slower, more accurate)' : 'Standard mode (faster)'}
          >
            <Brain className="h-3.5 w-3.5" />
            {reasoningMode ? 'GPT-5.2' : 'Reasoning'}
          </button>
          <button
            onClick={() => onOpenChange(false)}
            className="rounded-full p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            aria-label="Close AI chat"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Edit mode status banner */}
      {editMode && (
        <div className={`mx-4 mt-3 rounded-lg border px-3 py-2 text-sm shadow-sm ${
          docStats.len > 0
            ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-400/50 dark:bg-emerald-900/30 dark:text-emerald-100'
            : 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-400/50 dark:bg-rose-900/30 dark:text-rose-100'
        }`}>
          {docStats.len > 0 ? (
            <>Edit Mode active — AI can see your draft ({docStats.lines} lines, {Math.round(docStats.len / 1000)}k chars)</>
          ) : (
            <>Edit Mode active but no document content detected. Try making an edit in your draft first.</>
          )}
        </div>
      )}

      {missingPdfCount > 0 && (
        <div className="mx-4 mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 shadow-sm dark:border-amber-400/50 dark:bg-amber-900/30 dark:text-amber-100">
          {missingPdfCount === 1
            ? 'One attached reference is missing its PDF. Attach the PDF for more accurate answers.'
            : `${missingPdfCount} attached references are missing PDFs. Attach PDFs for more accurate answers.`}
        </div>
      )}

      <div className="px-4 py-3">
        <div
          ref={listRef}
          className="h-64 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-800/80 dark:text-slate-100"
        >
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-slate-500 dark:text-slate-400">
              <Bot className="h-5 w-5" />
              <p className="text-xs">Ask questions about your paper or references.</p>
              <p className="text-[10px] text-slate-400 dark:text-slate-500">
                Simple queries → Fast | Research queries → Full RAG
              </p>
            </div>
          )}
          {messages.map((m, idx) => (
            <div key={idx} className="mb-3 last:mb-0">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {m.role === 'assistant' ? 'Assistant' : 'You'}
              </div>
              {m.role === 'assistant' ? (
                <>
                  {m.content && (
                    <div className="prose prose-sm prose-slate dark:prose-invert max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 prose-headings:text-slate-900 dark:prose-headings:text-slate-100">
                      <ReactMarkdown>{m.content}</ReactMarkdown>
                    </div>
                  )}
                  {/* Edit Proposals */}
                  {m.proposals && m.proposals.length > 0 && (
                    <div className="mt-3 space-y-2">
                      {m.proposals.map((proposal) => {
                        const isExpanded = expandedProposals.has(proposal.id)
                        return (
                          <div
                            key={proposal.id}
                            className={`rounded-lg border ${
                              proposal.status === 'approved'
                                ? 'border-emerald-300 bg-emerald-50 dark:border-emerald-600 dark:bg-emerald-900/20'
                                : proposal.status === 'rejected'
                                ? 'border-slate-200 bg-slate-50 opacity-60 dark:border-slate-700 dark:bg-slate-800/50'
                                : 'border-indigo-200 bg-indigo-50 dark:border-indigo-600 dark:bg-indigo-900/20'
                            }`}
                          >
                            {/* Proposal Header */}
                            <div
                              className="flex cursor-pointer items-center justify-between px-3 py-2"
                              onClick={() => toggleProposalExpanded(proposal.id)}
                            >
                              <div className="flex items-center gap-2">
                                <Edit3 className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
                                <span className="text-sm font-medium text-slate-800 dark:text-slate-200">
                                  {proposal.description || 'Suggested Edit'}
                                </span>
                                {proposal.status === 'approved' && (
                                  <span className="rounded-full bg-emerald-200 px-2 py-0.5 text-[10px] font-semibold uppercase text-emerald-800 dark:bg-emerald-800 dark:text-emerald-200">
                                    Applied
                                  </span>
                                )}
                                {proposal.status === 'rejected' && (
                                  <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-600 dark:bg-slate-700 dark:text-slate-400">
                                    Dismissed
                                  </span>
                                )}
                              </div>
                              {isExpanded ? (
                                <ChevronUp className="h-4 w-4 text-slate-500" />
                              ) : (
                                <ChevronDown className="h-4 w-4 text-slate-500" />
                              )}
                            </div>

                            {/* Expanded Diff View */}
                            {isExpanded && (
                              <div className="border-t border-slate-200 px-3 py-2 dark:border-slate-700">
                                <div className="mb-2 grid grid-cols-2 gap-2 text-xs">
                                  <div>
                                    <div className="mb-1 font-semibold text-rose-600 dark:text-rose-400">Original</div>
                                    <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded border border-rose-200 bg-rose-50 p-2 text-slate-700 dark:border-rose-800 dark:bg-rose-900/30 dark:text-slate-300">
                                      {proposal.original}
                                    </pre>
                                  </div>
                                  <div>
                                    <div className="mb-1 font-semibold text-emerald-600 dark:text-emerald-400">Proposed</div>
                                    <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded border border-emerald-200 bg-emerald-50 p-2 text-slate-700 dark:border-emerald-800 dark:bg-emerald-900/30 dark:text-slate-300">
                                      {proposal.proposed}
                                    </pre>
                                  </div>
                                </div>

                                {/* Action Buttons */}
                                {proposal.status === 'pending' && (
                                  <div className="flex items-center justify-end gap-2 pt-2">
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        handleRejectEdit(idx, proposal.id)
                                      }}
                                      className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                                    >
                                      Dismiss
                                    </button>
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        handleApproveEdit(idx, proposal.id)
                                      }}
                                      className="flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700"
                                    >
                                      <Check className="h-3.5 w-3.5" />
                                      Apply Edit
                                    </button>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </>
              ) : (
                <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-900 dark:text-slate-100">
                  {m.content}
                </div>
              )}
            </div>
          ))}
          {sending && (messages.length === 0 || messages[messages.length - 1].role !== 'assistant') && (
            <div className="mb-3 last:mb-0">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Assistant
              </div>
              <div className="inline-flex items-center gap-1 rounded-full bg-slate-200 px-3 py-2 text-sm font-medium text-slate-700 dark:bg-slate-700 dark:text-slate-100">
                <span className="h-2 w-2 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="h-2 w-2 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="h-2 w-2 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          )}
        </div>
        {error && (
          <div className="mt-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-400/60 dark:bg-rose-900/30 dark:text-rose-100">
            {error}
          </div>
        )}
        <div className="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm dark:border-slate-700 dark:bg-slate-800">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={3}
            placeholder="Ask about your draft or references…"
            className="w-full resize-none border-none bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none dark:text-slate-100 dark:placeholder:text-slate-500"
          />
          <div className="mt-2 flex items-center justify-between">
            <div className="text-[11px] text-slate-500 dark:text-slate-400">
              Enter to send • Shift+Enter for newline
            </div>
            <button
              onClick={() => void handleSend()}
              disabled={sending || !input.trim()}
              className="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default EditorAIChat
