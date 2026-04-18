import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Bot, Brain, Check, ChevronDown, ChevronUp, Edit3, Loader2, Send, Sparkles, Trash2, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { projectReferencesAPI, projectsAPI, buildApiUrl, buildAuthHeaders } from '../../services/api'
import { useAuth } from '../../contexts/AuthContext'
import { modelSupportsReasoning, useOpenRouterModels } from '../discussion/ModelSelector'

import { EditProposal, parseEditProposals as parseEditProposalsUtil } from './utils/editProposals'

interface Clarification {
  question: string
  options: string[]
}

interface EditorAIChatORProps {
  paperId: string
  projectId?: string
  documentText: string
  documentFiles?: Record<string, string> | null  // extra files: { 'introduction.tex': 'content', ... }
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Callback to apply an approved edit to the document (line-based) */
  onApplyEdit?: (startLine: number, endLine: number, anchor: string, replacement: string, sourceDocument?: string, file?: string) => boolean
  /** Callback to apply a batch of edits against a snapshot */
  onApplyEditsBatch?: (proposals: EditProposal[], sourceDocument: string) => string[]
  /** Initial message to auto-send when chat opens (e.g., from Sparkles explain/summarize) */
  initialMessage?: string
  /** Callback when initial message has been consumed */
  onInitialMessageConsumed?: () => void
  /** Whether current user is the paper owner (shows clear history button) */
  isOwner?: boolean
}

type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
  authorName?: string
  authorId?: string
  fromHistory?: boolean
  proposals?: EditProposal[]
  clarification?: Clarification
  sourceDocument?: string
  sourcePrompt?: string
}

interface ReferenceItem {
  id: string
  title: string
  pdfUrl?: string | null
  pdfProcessed?: boolean | null
  documentStatus?: string | null
  documentId?: string | null
}

const MAX_DOC_CONTEXT_CHARS = 4000

/**
 * BETA: Simple, best approach for document handling.
 *
 * Modern models have huge context windows (GPT-5.2: 1M chars, Claude: 800k, Gemini: 4M).
 * Most academic papers are 20-50k chars (2-5% of capacity).
 *
 * Approach:
 * - Documents < 200k chars: Send full document with line numbers (single API call, simple)
 * - Documents >= 200k chars: AI-driven section retrieval (very rare edge case)
 *
 * This is simpler, faster, and more reliable than multi-turn retrieval for 99%+ of papers.
 */
const MAX_DOC_CHARS = 500000 // 500k max for safety

const EditorAIChatOR: React.FC<EditorAIChatORProps> = ({
  paperId,
  projectId,
  documentText,
  documentFiles,
  open,
  onOpenChange,
  onApplyEdit,
  onApplyEditsBatch,
  initialMessage,
  onInitialMessageConsumed,
  isOwner = false,
}) => {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [statusMessage, setStatusMessage] = useState<string>('Thinking')
  const [error, setError] = useState<string | null>(null)
  const [references, setReferences] = useState<ReferenceItem[]>([])
  const [reasoningMode, setReasoningMode] = useState(false)
  const [appliedReviewMsgs, setAppliedReviewMsgs] = useState<Set<number>>(new Set())
  const { models: openrouterModels, warning: openrouterWarning } = useOpenRouterModels(projectId)
  const abortControllerRef = useRef<AbortController | null>(null)
  const statusRef = useRef('Thinking')
  const [expandedProposals, setExpandedProposals] = useState<Set<string>>(new Set())
  const listRef = useRef<HTMLDivElement | null>(null)
  const historyLoadedRef = useRef(false)

  // Fetch project AI settings to get the configured model
  const settingsQuery = useQuery({
    queryKey: ['project-ai-settings', projectId],
    queryFn: async () => {
      if (!projectId) return null
      const response = await projectsAPI.getDiscussionSettings(projectId)
      return response.data
    },
    enabled: Boolean(projectId),
    staleTime: 30000,
  })

  // Use model from project settings, fallback to first available model
  const selectedModel = settingsQuery.data?.model || openrouterModels[0]?.id

  // Fetch shared chat history for this paper
  const historyQuery = useQuery({
    queryKey: ['editor-chat-history', paperId],
    queryFn: async () => {
      const res = await fetch(
        buildApiUrl(`/agent-or/chat/history?paper_id=${paperId}&limit=50`),
        { headers: buildAuthHeaders() }
      )
      if (!res.ok) return []
      return res.json()
    },
    enabled: Boolean(paperId) && open,
    staleTime: 30000,
  })

  // Populate messages from history on first load
  useEffect(() => {
    if (!historyQuery.data?.length || historyLoadedRef.current || messages.length > 0) return
    historyLoadedRef.current = true

    const editRegex = /<<<EDIT>>>\s*([\s\S]*?)(?:<<<FILE>>>\s*([\s\S]*?))?\s*<<<LINES>>>\s*([\s\S]*?)<<<ANCHOR>>>\s*([\s\S]*?)<<<PROPOSED>>>\s*([\s\S]*?)<<<END>>>/g
    const clarifyRegex = /<<<CLARIFY>>>\s*QUESTION:\s*([\s\S]*?)\s*OPTIONS:\s*([\s\S]*?)<<<END>>>/i

    const loaded: ChatMessage[] = historyQuery.data.map((msg: any) => {
      const base: ChatMessage = {
        role: msg.role,
        content: msg.content || '',
        authorName: msg.author_name,
        authorId: msg.author_id,
        fromHistory: true,
      }

      if (msg.role === 'assistant') {
        // Parse edit proposals from history, mark as expired
        let cleanText = base.content
        const proposals: EditProposal[] = []
        let match: RegExpExecArray | null
        editRegex.lastIndex = 0
        while ((match = editRegex.exec(base.content)) !== null) {
          const fullMatch = match[0]
          const description = match[1]
          const file = match[2]?.trim() || undefined
          const linesStr = match[3]
          const anchor = match[4]
          const proposed = match[5]
          const linesParts = linesStr.trim().split('-')
          proposals.push({
            id: `hist-${msg.id}-${proposals.length}`,
            description: description.trim(),
            startLine: parseInt(linesParts[0], 10) || 1,
            endLine: parseInt(linesParts[1] || linesParts[0], 10) || 1,
            anchor: anchor.trim(),
            proposed: proposed.trim(),
            status: 'expired',
            file,
          })
          cleanText = cleanText.replace(fullMatch, '')
        }

        // Parse clarification from history
        const clarifyMatch = clarifyRegex.exec(base.content)
        let clarification: Clarification | undefined
        if (clarifyMatch) {
          const options = clarifyMatch[2].trim().split('|').map(o => o.trim()).filter(Boolean)
          clarification = { question: clarifyMatch[1].trim(), options }
          cleanText = cleanText.replace(clarifyMatch[0], '')
        }

        return {
          ...base,
          content: cleanText.trim(),
          proposals: proposals.length > 0 ? proposals : undefined,
          clarification,
        }
      }
      return base
    })

    setMessages(loaded)
  }, [historyQuery.data]) // eslint-disable-line react-hooks/exhaustive-deps

  // Reset history loaded ref when paperId changes
  useEffect(() => {
    historyLoadedRef.current = false
    setMessages([])
  }, [paperId])

  // Clear history handler
  const handleClearHistory = useCallback(async () => {
    if (!window.confirm('This clears AI chat history for all collaborators. Continue?')) return
    try {
      await fetch(
        buildApiUrl(`/agent-or/chat/history?paper_id=${paperId}`),
        { method: 'DELETE', headers: buildAuthHeaders() }
      )
      setMessages([])
      historyLoadedRef.current = false
      queryClient.invalidateQueries({ queryKey: ['editor-chat-history', paperId] })
    } catch (e) {
      console.warn('[EditorAIChatOR] Failed to clear history', e)
    }
  }, [paperId, queryClient])

  const isReviewMessage = useCallback((content: string) => {
    if (!content) return false
    return content.includes('## Review') || content.includes('Suggested Improvements')
  }, [])

  // Get current model info
  const currentModel = useMemo(
    () => openrouterModels.find((m) => m.id === selectedModel) || openrouterModels[0],
    [selectedModel, openrouterModels]
  )

  // Check if current model supports reasoning
  const supportsReasoning = useMemo(
    () => modelSupportsReasoning(selectedModel, openrouterModels),
    [selectedModel, openrouterModels]
  )

  const parseClarification = useCallback((text: string): { cleanText: string; clarification?: Clarification } => {
    const clarifyRegex = /<<<CLARIFY>>>\s*QUESTION:\s*([\s\S]*?)\s*OPTIONS:\s*([\s\S]*?)<<<END>>>/i
    const match = clarifyRegex.exec(text)
    if (!match) {
      return { cleanText: text.trim() }
    }

    const question = match[1].trim()
    const optionsRaw = match[2].trim()

    const parseLines = (raw: string) =>
      raw
        .split('\n')
        .map((line) => line.replace(/^[-*\s]+/, '').trim())
        .filter(Boolean)

    let options = optionsRaw
      .split('|')
      .map((opt) => opt.trim())
      .filter(Boolean)

    if (options.length <= 1) {
      options = parseLines(optionsRaw)
    }

    const cleanText = text.replace(match[0], '').trim()

    return {
      cleanText,
      clarification: {
        question,
        options,
      },
    }
  }, [])

  /** Parse edit proposals from AI response using line-based format */
  const parseEditProposals = useCallback((text: string): { cleanText: string; proposals: EditProposal[] } => {
    const result = parseEditProposalsUtil(text)
    for (const p of result.proposals) {
      console.log('[EditorAIChatOR] Parsed edit proposal:', {
        startLine: p.startLine,
        endLine: p.endLine,
        file: p.file,
        anchor: p.anchor,
        anchorLength: p.anchor.length,
        description: p.description.slice(0, 50),
      })
    }
    return result
  }, [])

  /** Handle approving an edit proposal */
  const handleApproveEdit = useCallback((messageIdx: number, proposalId: string) => {
    setMessages((prev) => {
      const copy = [...prev]
      const msg = copy[messageIdx]
      if (!msg?.proposals) return prev

      const proposal = msg.proposals.find((p) => p.id === proposalId)
      if (!proposal || proposal.status !== 'pending') return prev

      console.log('[EditorAIChatOR] Approving edit proposal:', {
        startLine: proposal.startLine,
        endLine: proposal.endLine,
        anchor: proposal.anchor,
        anchorLength: proposal.anchor?.length,
        proposedLength: proposal.proposed?.length,
      })

      // Apply edit using line numbers
      const success = onApplyEdit?.(proposal.startLine, proposal.endLine, proposal.anchor, proposal.proposed, msg.sourceDocument, proposal.file) ?? false

      if (success) {
        // Compute line delta so we can shift remaining proposals
        const oldLineCount = proposal.endLine - proposal.startLine + 1
        const newLineCount = proposal.proposed.split('\n').length
        const delta = newLineCount - oldLineCount

        // Update sourceDocument to match the post-edit document state
        // (mirrors the line splice that handleApplyAiEdit performs on the live doc)
        if (msg.sourceDocument) {
          const srcLines = msg.sourceDocument.split('\n')
          const startIdx = proposal.startLine - 1
          const endIdx = Math.min(proposal.endLine - 1, srcLines.length - 1)
          const before = srcLines.slice(0, startIdx)
          const after = srcLines.slice(endIdx + 1)
          msg.sourceDocument = [...before, ...proposal.proposed.split('\n'), ...after].join('\n')
        }

        // Mark this proposal approved, expire overlapping proposals, and shift those that come after
        msg.proposals = msg.proposals.map((p) => {
          if (p.id === proposalId) return { ...p, status: 'approved' as const }
          if (p.status !== 'pending') return p
          // Overlap: p.startLine <= applied.endLine AND p.endLine >= applied.startLine
          const overlaps = p.startLine <= proposal.endLine && p.endLine >= proposal.startLine
          if (overlaps) return { ...p, status: 'expired' as const }
          // Shift proposals that come entirely after the applied edit
          if (delta !== 0 && p.startLine > proposal.endLine) {
            return { ...p, startLine: p.startLine + delta, endLine: p.endLine + delta }
          }
          return p
        })
      } else {
        setError('Could not apply the edit. The document may have changed or the lines are out of range.')
      }

      return copy
    })
  }, [onApplyEdit])

  const handleApplyAllEdits = useCallback((messageIdx: number) => {
    setMessages((prev) => {
      const copy = [...prev]
      const msg = copy[messageIdx]
      if (!msg?.proposals || msg.proposals.length === 0 || !msg.sourceDocument) return prev

      // Only submit pending proposals — already-applied ones shouldn't be re-applied
      const pending = msg.proposals.filter((p) => p.status === 'pending')
      if (pending.length === 0) return prev

      const appliedIds = new Set(onApplyEditsBatch?.(pending, msg.sourceDocument) ?? [])
      if (appliedIds.size > 0) {
        msg.proposals = msg.proposals.map((p) => ({
          ...p,
          status: appliedIds.has(p.id) ? 'approved' as const : p.status,
        }))
      } else {
        setError('Could not apply edits. The document may have changed. Please regenerate.')
      }
      return copy
    })
  }, [onApplyEditsBatch])

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
                pdfProcessed: ref.pdf_processed ?? null,
                documentStatus: ref.document_status ?? null,
                documentId: ref.document_id ?? null,
              }))
              .slice(0, 12)
          : []
        setReferences(refs)
      } catch (e: any) {
        console.warn('[EditorAIChatOR] Failed to load references', e)
      }
    }
    void load()
  }, [open, paperId, projectId])

  useEffect(() => {
    if (!open) {
      // Don't reset messages on close to preserve conversation when switching models
      setInput('')
      setError(null)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    if (!listRef.current) return
    listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, open])

  // Auto-send initial message from Sparkles explain/summarize actions
  const [pendingAutoSend, setPendingAutoSend] = useState<string | null>(null)
  const initialMessageSentRef = useRef<string | null>(null)
  useEffect(() => {
    if (!open || !initialMessage || sending) return
    // Prevent double-sending the same message
    if (initialMessageSentRef.current === initialMessage) return
    initialMessageSentRef.current = initialMessage
    // Set input and flag for auto-send
    setInput(initialMessage)
    setPendingAutoSend(initialMessage)
    onInitialMessageConsumed?.()
  }, [open, initialMessage, sending, onInitialMessageConsumed])

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

  const missingPdfCount = useMemo(() => {
    const hasFullText = (ref: ReferenceItem) => Boolean(
      ref.pdfProcessed || ref.documentStatus === 'processed' || ref.documentId
    )
    return references.filter((r) => !hasFullText(r)).length
  }, [references])

  /**
   * Parse status markers from a buffer, returning clean text and leftover buffer.
   * Reused for both per-chunk parsing and final flush.
   */
  const parseStatusMarkers = useCallback(
    (
      buffer: string,
      onStatus: (msg: string) => void,
      isFinal: boolean = false,
    ): { cleanText: string; remaining: string } => {
      const markerRegex = /\[\[\[STATUS:(.*?)\]\]\]/g
      let lastEnd = 0
      let cleanText = ''
      let match: RegExpExecArray | null

      while ((match = markerRegex.exec(buffer)) !== null) {
        cleanText += buffer.slice(lastEnd, match.index)
        onStatus(match[1])
        lastEnd = match.index + match[0].length
      }

      // Check for partial marker at end of buffer
      const partialIdx = buffer.lastIndexOf('[[[', lastEnd)
      if (!isFinal && partialIdx !== -1 && !buffer.includes(']]]', partialIdx)) {
        // Partial marker — keep in buffer for next chunk
        cleanText += buffer.slice(lastEnd, partialIdx)
        return { cleanText, remaining: buffer.slice(partialIdx) }
      }

      // Final flush: discard incomplete marker prefix (don't render raw [[[ noise)
      if (isFinal && partialIdx !== -1 && !buffer.includes(']]]', partialIdx)) {
        cleanText += buffer.slice(lastEnd, partialIdx)
        return { cleanText, remaining: '' }
      }

      cleanText += buffer.slice(lastEnd)
      return { cleanText, remaining: '' }
    },
    [],
  )

  const sendPrompt = useCallback(
    async (prompt: string, clearInput: boolean = false) => {
      if (!prompt.trim() || sending) return
      if (clearInput) {
        setInput('')
      }
      setSending(true)
      setStatusMessage('Thinking')
      setError(null)
      setMessages((prev) => [...prev, { role: 'user', content: prompt }])

      // Two-tier idle escalation. Mirrors the Discussion AI idle timer pattern
      // so the editor chat never looks frozen during long propose_edit streams:
      //   +5s  of silence → "… — still working"
      //   +10s of silence → "… — taking longer than usual"
      //   +15s of silence → "… — the model is still drafting"
      // Resets on every real status update so it never fires in the happy path.
      let idleTimer: number | null = null
      const clearIdle = () => {
        if (idleTimer !== null) {
          window.clearTimeout(idleTimer)
          idleTimer = null
        }
      }
      const armIdle = (baseMessage: string) => {
        clearIdle()
        idleTimer = window.setTimeout(() => {
          setStatusMessage(`${baseMessage} — still working`)
          idleTimer = window.setTimeout(() => {
            setStatusMessage(`${baseMessage} — taking longer than usual`)
            idleTimer = window.setTimeout(() => {
              setStatusMessage(`${baseMessage} — the model is still drafting`)
              idleTimer = null
            }, 5000)
          }, 5000)
        }, 5000)
      }

      armIdle('Thinking')
      // Debounce timer for status UI updates (100ms) to prevent flicker
      let statusDebounceTimer: number | null = null
      const updateStatus = (msg: string) => {
        if (msg === statusRef.current) return
        statusRef.current = msg
        if (statusDebounceTimer !== null) window.clearTimeout(statusDebounceTimer)
        statusDebounceTimer = window.setTimeout(() => setStatusMessage(msg), 100)
        // Reset idle escalation on each real status update.
        armIdle(msg)
      }

      // BETA: Send full document - backend handles smart AI-driven extraction
      const rawDoc = documentText || ''
      const docSnapshot = rawDoc
      const sourcePrompt = prompt
      const docToSend = rawDoc.slice(0, MAX_DOC_CHARS) || docContext || null

      console.log('[EditorAIChatOR] BETA:', {
        model: selectedModel,
        reasoningMode,
        docLength: docToSend?.length || 0,
        mode: (docToSend?.length || 0) < 200000 ? 'full-document' : 'section-retrieval',
        prompt: prompt.slice(0, 50),
      })

      // Create abort controller for cancel functionality
      abortControllerRef.current = new AbortController()

      // Hard 3-minute ceiling that merges with the manual Cancel signal. The
      // browser default alone won't stop a request the backend has silently
      // given up on — if nginx holds a dead connection open, the UI would spin
      // forever. AbortSignal.any keeps manual Cancel working alongside this.
      const timeoutSignal =
        typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function'
          ? AbortSignal.timeout(180000)
          : null
      const combinedSignal =
        timeoutSignal && typeof (AbortSignal as unknown as { any?: unknown }).any === 'function'
          ? (AbortSignal as unknown as { any: (signals: AbortSignal[]) => AbortSignal }).any(
              [abortControllerRef.current.signal, timeoutSignal],
            )
          : abortControllerRef.current.signal

      try {
        // Use OpenRouter agent endpoint with model selection
        const res = await fetch(
          buildApiUrl(`/agent-or/chat/stream?model=${encodeURIComponent(selectedModel)}`),
          {
            signal: combinedSignal,
            method: 'POST',
            headers: buildAuthHeaders(),
            body: JSON.stringify({
              query: prompt,
              paper_id: paperId,
              project_id: projectId || null,
              document_excerpt: docToSend,
              document_files: documentFiles || null,
              reasoning_mode: reasoningMode,
            }),
          }
        )

        if (!res.ok) {
          const errText = await res.text()
          throw new Error(errText || 'Chat request failed.')
        }

        const reader = res.body?.getReader()
        const decoder = new TextDecoder()
        let fullText = ''
        let markerBuffer = ''
        const BUFFER_CAP = 1000

        if (reader) {
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            const rawChunk = decoder.decode(value || new Uint8Array(), { stream: true })
            markerBuffer += rawChunk

            // Parse first, then cap only the remaining partial-marker carryover
            const { cleanText, remaining } = parseStatusMarkers(markerBuffer, updateStatus)
            markerBuffer = remaining.length > BUFFER_CAP
              ? remaining.slice(remaining.length - BUFFER_CAP)
              : remaining

            if (cleanText) {
              fullText += cleanText
              // Streaming content counts as progress — reset idle escalation
              // against the currently-active status rather than a stale label.
              armIdle(statusRef.current)

              // Incremental edit-proposal rendering. If a <<<EDIT>>>...<<<END>>>
              // block has closed in the growing fullText, parse what's complete
              // and show it in the proposals panel so the user sees edits land
              // one-by-one instead of all at once when the stream finishes. The
              // final-flush block at the bottom of the try still runs and
              // re-parses for safety.
              let incrementalProposals: EditProposal[] | null = null
              let contentForMessage = ''
              if (fullText.includes('<<<EDIT>>>') && fullText.includes('<<<END>>>')) {
                try {
                  const parsed = parseEditProposals(fullText)
                  if (parsed.proposals.length > 0) {
                    incrementalProposals = parsed.proposals
                    contentForMessage = parsed.cleanText
                  }
                } catch {
                  // Malformed partial — ignore, the final parse will handle it.
                }
              }

              setMessages((prev) => {
                const copy = [...prev]
                const last = copy.length - 1
                if (last >= 0 && copy[last].role === 'assistant') {
                  const updated = { ...copy[last] }
                  if (incrementalProposals) {
                    // Replace content with the edit-stripped version and stash
                    // the in-progress proposals so the panel can render them.
                    updated.content = contentForMessage
                    updated.proposals = incrementalProposals
                    if (!updated.sourceDocument) updated.sourceDocument = docSnapshot
                    if (!updated.sourcePrompt) updated.sourcePrompt = sourcePrompt
                  } else {
                    updated.content = updated.content + cleanText
                  }
                  copy[last] = updated
                } else {
                  copy.push({ role: 'assistant', content: cleanText })
                }
                return copy
              })
            }
          }

          // Final flush: parse any remaining buffer (discard incomplete markers)
          if (markerBuffer) {
            const { cleanText } = parseStatusMarkers(markerBuffer, updateStatus, true)
            if (cleanText) {
              fullText += cleanText
              setMessages((prev) => {
                const copy = [...prev]
                const last = copy.length - 1
                if (last >= 0 && copy[last].role === 'assistant') {
                  copy[last] = { ...copy[last], content: copy[last].content + cleanText }
                } else {
                  copy.push({ role: 'assistant', content: cleanText })
                }
                return copy
              })
            }
          }
        }

        // After streaming completes, parse clarification + edit proposals
        let cleanText = fullText
        let clarification: Clarification | undefined
        let proposals: EditProposal[] = []

        if (fullText.includes('<<<CLARIFY>>>')) {
          const parsedClarification = parseClarification(fullText)
          cleanText = parsedClarification.cleanText
          clarification = parsedClarification.clarification
        }

        if (cleanText.includes('<<<EDIT>>>')) {
          const parsedEdits = parseEditProposals(cleanText)
          cleanText = parsedEdits.cleanText
          proposals = parsedEdits.proposals
        }

        if (clarification || proposals.length > 0) {
          setMessages((prev) => {
            const copy = [...prev]
            const last = copy.length - 1
            if (last >= 0 && copy[last].role === 'assistant') {
              copy[last] = {
                ...copy[last],
                content: cleanText,
                proposals,
                clarification,
                sourceDocument: docSnapshot,
                sourcePrompt,
              }
              if (proposals.length > 0) {
                setExpandedProposals(new Set([proposals[0].id]))
              }
            }
            return copy
          })
        }

        if (!fullText.trim() && !clarification && proposals.length === 0) {
          setMessages((prev) => {
            const last = prev.length - 1
            if (last < 0 || prev[last].role !== 'assistant') {
              return [...prev, { role: 'assistant', content: 'No response received.' }]
            }
            return prev
          })
        }
      } catch (e: any) {
        // Don't show error for user-initiated cancellation
        if (e?.name === 'AbortError') {
          console.log('[EditorAIChatOR] Request cancelled by user')
          return
        }
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
        clearIdle()
        if (statusDebounceTimer !== null) window.clearTimeout(statusDebounceTimer)
        abortControllerRef.current = null
        setSending(false)
        setStatusMessage('Thinking')
        statusRef.current = 'Thinking'
      }
    },
    [
      docContext,
      documentFiles,
      documentText,
      paperId,
      parseClarification,
      parseEditProposals,
      parseStatusMarkers,
      projectId,
      reasoningMode,
      selectedModel,
      sending,
    ]
  )

  const handleApplyReviewChanges = useCallback((mode: 'critical' | 'all', msgIdx: number) => {
    setAppliedReviewMsgs((prev) => new Set(prev).add(msgIdx))
    const prompt = mode === 'critical'
      ? 'Apply only the critical fixes from your last review. Focus on compilation blockers.'
      : 'Apply all suggested changes from your last review.'
    void sendPrompt(prompt, false)
  }, [sendPrompt])

  const handleRegenerateEdits = useCallback((messageIdx: number) => {
    const msg = messages[messageIdx]
    if (!msg?.sourcePrompt) return
    const regeneratePrompt = `${msg.sourcePrompt}\n\nPlease regenerate the edits for the current document state.`
    void sendPrompt(regeneratePrompt, false)
  }, [messages, sendPrompt])

  const handleSend = useCallback(() => {
    const prompt = input.trim()
    if (!prompt || sending) return
    void sendPrompt(prompt, true)
  }, [input, sendPrompt, sending])

  // Handle auto-send for initial messages from Sparkles
  useEffect(() => {
    if (pendingAutoSend && !sending) {
      setPendingAutoSend(null)
      void sendPrompt(pendingAutoSend, true)
    }
  }, [pendingAutoSend, sending, sendPrompt])

  /** Cancel ongoing request */
  const handleCancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      // Remove the pending user message
      setMessages((prev) => {
        const copy = [...prev]
        if (copy.length >= 1 && copy[copy.length - 1].role === 'user') {
          copy.pop()
        }
        return copy
      })
    }
  }, [])

  const handleClarificationSelect = useCallback(
    (question: string, option: string) => {
      const prompt = `Clarification: ${option}`
      console.log('[EditorAIChatOR] Clarification selected:', { question, option })
      void sendPrompt(prompt, true)
    },
    [sendPrompt]
  )

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
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-purple-500 to-indigo-600 text-white">
            <Bot className="h-5 w-5" />
          </div>
          <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">AI Assistant</span>
        </div>
        <div className="flex items-center gap-2">
          {/* Clear History (owner only) */}
          {isOwner && messages.length > 0 && (
            <button
              onClick={() => void handleClearHistory()}
              className="rounded-full p-2 text-slate-400 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-900/30 dark:hover:text-rose-400"
              title="Clear chat history for all collaborators"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
          {/* Model Display (read-only, configured in Project Settings) */}
          <div
            className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium dark:border-slate-700 dark:bg-slate-800"
            title="Model is configured in Project Settings"
          >
            <Sparkles className="h-4 w-4 text-indigo-500 dark:text-indigo-400" />
            <span className="max-w-[120px] truncate text-gray-700 dark:text-slate-200">{currentModel?.name || 'Loading...'}</span>
            <span className="text-xs text-gray-400 dark:text-slate-500">{currentModel?.provider}</span>
          </div>

          {/* Reasoning Mode Toggle - only show for supported models */}
          {supportsReasoning && (
            <button
              onClick={() => setReasoningMode(!reasoningMode)}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                reasoningMode
                  ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
              }`}
              title={reasoningMode ? 'Reasoning mode enabled (slower, more accurate)' : 'Enable reasoning mode'}
            >
              <Brain className="h-3.5 w-3.5" />
              {reasoningMode ? 'Reasoning' : 'Reason'}
            </button>
          )}
          <button
            onClick={() => onOpenChange(false)}
            className="rounded-full p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            aria-label="Close AI chat"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {openrouterWarning && (
        <div className="mx-4 mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 shadow-sm dark:border-amber-400/40 dark:bg-amber-900/30 dark:text-amber-100">
          {openrouterWarning}
        </div>
      )}


      {missingPdfCount > 0 && (
        <div className="mx-4 mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 shadow-sm dark:border-amber-400/50 dark:bg-amber-900/30 dark:text-amber-100">
          {missingPdfCount === 1
            ? 'One attached reference is missing full text. Attach the PDF for more accurate answers.'
            : `${missingPdfCount} attached references are missing full text. Attach PDFs for more accurate answers.`}
        </div>
      )}

      <div className="px-4 py-3">
        <div
          ref={listRef}
          className="h-64 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50/70 px-3 py-2 text-sm text-slate-900 dark:border-slate-800 dark:bg-slate-800/80 dark:text-slate-100"
        >
          {messages.length === 0 && !historyQuery.isLoading && (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-slate-500 dark:text-slate-400">
              <div className="flex items-center gap-1.5">
                <Sparkles className="h-4 w-4 text-purple-500" />
                <Bot className="h-5 w-5" />
              </div>
              <p className="text-xs">Ask questions, request reviews, or ask for changes to your paper.</p>
              <p className="text-[10px] text-slate-400 dark:text-slate-500">
                Try different models - switch anytime, conversation is preserved
              </p>
            </div>
          )}
          {messages.length === 0 && historyQuery.isLoading && (
            <div className="flex h-full items-center justify-center gap-2 text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-xs">Loading conversation...</span>
            </div>
          )}
          {messages.map((m, idx) => (
            <div key={idx} className="mb-3 last:mb-0">
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {m.role === 'assistant' ? 'Assistant' : (m.authorId && m.authorId !== currentUser?.id ? m.authorName : 'You')}
                {m.fromHistory && m.role === 'user' && m.authorId && m.authorId !== currentUser?.id && m.authorName && (
                  <span className="rounded-full bg-indigo-100 px-1.5 py-0.5 text-[9px] font-semibold normal-case text-indigo-600 dark:bg-indigo-900/50 dark:text-indigo-300">
                    {m.authorName}
                  </span>
                )}
              </div>
              {m.role === 'assistant' ? (
                <>
                  {m.content && (
                    <div className="prose prose-sm prose-slate dark:prose-invert max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 prose-headings:font-semibold prose-headings:text-slate-900 dark:prose-headings:text-slate-100 prose-h3:text-sm prose-strong:text-slate-900 dark:prose-strong:text-white prose-code:rounded prose-code:bg-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:text-indigo-700 prose-code:before:content-none prose-code:after:content-none dark:prose-code:bg-slate-700 dark:prose-code:text-indigo-300 prose-blockquote:border-indigo-300 dark:prose-blockquote:border-indigo-500 prose-a:text-indigo-600 dark:prose-a:text-indigo-400 prose-a:no-underline hover:prose-a:underline">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                    </div>
                  )}
                  {m.content && isReviewMessage(m.content) && (!m.proposals || m.proposals.length === 0) && !appliedReviewMsgs.has(idx) && (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <button
                        onClick={() => handleApplyReviewChanges('critical', idx)}
                        disabled={sending}
                        className="rounded-md border border-amber-300 bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-900 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-amber-500/60 dark:bg-amber-900/30 dark:text-amber-100"
                      >
                        Apply critical fixes
                      </button>
                      <button
                        onClick={() => handleApplyReviewChanges('all', idx)}
                        disabled={sending}
                        className="rounded-md bg-emerald-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Apply all suggestions
                      </button>
                    </div>
                  )}
                  {m.clarification && idx === messages.length - 1 && (
                    <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-600/60 dark:bg-amber-900/30 dark:text-amber-100">
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-200">
                        Clarification needed
                      </div>
                      <div className="mt-1 font-medium">{m.clarification.question}</div>
                      {m.clarification.options.length > 0 ? (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {m.clarification.options.map((option) => (
                            <button
                              key={option}
                              onClick={() => handleClarificationSelect(m.clarification!.question, option)}
                              disabled={sending}
                              className="rounded-full border border-amber-300 bg-white px-3 py-1 text-xs font-medium text-amber-900 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-amber-500/60 dark:bg-amber-900/40 dark:text-amber-100 dark:hover:bg-amber-900/60"
                            >
                              {option}
                            </button>
                          ))}
                        </div>
                      ) : (
                        <div className="mt-1 text-xs text-amber-700 dark:text-amber-200">
                          Reply with a bit more detail to continue.
                        </div>
                      )}
                    </div>
                  )}
                  {/* Edit Proposals */}
                  {m.proposals && m.proposals.length > 0 && (
                    <div className="mt-3 space-y-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                          {m.proposals.length} proposed edit{m.proposals.length > 1 ? 's' : ''}
                          {m.fromHistory && <span className="ml-1 text-slate-400">(from history)</span>}
                        </div>
                        {!m.fromHistory && (() => {
                          const hasPending = m.proposals?.some(p => p.status === 'pending')
                          return (
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => handleRegenerateEdits(idx)}
                                disabled={sending}
                                className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                              >
                                Regenerate
                              </button>
                              {hasPending ? (
                                <button
                                  onClick={() => handleApplyAllEdits(idx)}
                                  disabled={sending}
                                  className="rounded-md bg-emerald-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                                >
                                  Apply All
                                </button>
                              ) : (
                                <span className="rounded-md bg-emerald-100 px-2.5 py-1 text-[11px] font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
                                  All Applied
                                </span>
                              )}
                            </div>
                          )
                        })()}
                      </div>
                      {m.proposals.map((proposal) => {
                        const isExpanded = expandedProposals.has(proposal.id)
                        return (
                          <div
                            key={proposal.id}
                            className={`rounded-lg border ${
                              proposal.status === 'approved'
                                ? 'border-emerald-300 bg-emerald-50 dark:border-emerald-600 dark:bg-emerald-900/20'
                                : proposal.status === 'rejected' || proposal.status === 'expired'
                                ? 'border-slate-200 bg-slate-50 opacity-50 dark:border-slate-700 dark:bg-slate-800/50'
                                : 'border-indigo-200 bg-indigo-50 dark:border-indigo-600 dark:bg-indigo-900/20'
                            }`}
                          >
                            {/* Proposal Header */}
                            <div
                              className="flex cursor-pointer items-start gap-2 px-3 py-2"
                              onClick={() => toggleProposalExpanded(proposal.id)}
                            >
                              <Edit3 className="mt-0.5 h-4 w-4 shrink-0 text-indigo-600 dark:text-indigo-400" />
                              <div className="min-w-0 flex-1">
                                <span className="text-sm font-medium text-slate-800 dark:text-slate-200">
                                  {proposal.description || 'Suggested Edit'}
                                </span>
                                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                                  {proposal.file && (
                                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700 dark:bg-blue-900/50 dark:text-blue-300">
                                      {proposal.file}
                                    </span>
                                  )}
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
                                  {proposal.status === 'expired' && (
                                    <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-semibold text-slate-500 dark:bg-slate-700 dark:text-slate-400">
                                      {m.fromHistory ? 'From previous session' : 'Conflict — overlapping edit applied'}
                                    </span>
                                  )}
                                </div>
                              </div>
                              <div className="shrink-0">
                                {isExpanded ? (
                                  <ChevronUp className="h-4 w-4 text-slate-500" />
                                ) : (
                                  <ChevronDown className="h-4 w-4 text-slate-500" />
                                )}
                              </div>
                            </div>

                            {/* Expanded Diff View */}
                            {isExpanded && (
                              <div className="border-t border-slate-200 px-3 py-2 dark:border-slate-700">
                                <div className="mb-2 text-xs">
                                  <div className="mb-2 flex items-center gap-2">
                                    <span className="font-semibold text-rose-600 dark:text-rose-400">
                                      Lines {proposal.startLine}-{proposal.endLine}
                                    </span>
                                    <span className="text-slate-500 dark:text-slate-400">
                                      (starts with: "{proposal.anchor.slice(0, 40)}...")
                                    </span>
                                  </div>
                                  <div>
                                    <div className="mb-1 font-semibold text-emerald-600 dark:text-emerald-400">Replacement</div>
                                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded border border-emerald-200 bg-emerald-50 p-2 text-slate-700 dark:border-emerald-800 dark:bg-emerald-900/30 dark:text-slate-300">
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
                                      Apply
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
              <div className="space-y-2">
                <div className="flex items-center gap-2.5">
                  <div className="flex items-center gap-2 text-sm font-medium text-purple-600 dark:text-purple-300">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>{statusMessage}...</span>
                  </div>
                  <button
                    onClick={handleCancel}
                    className="ml-auto flex h-6 w-6 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
                    title="Cancel request"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="h-1 w-1 animate-pulse rounded-full bg-purple-400 dark:bg-purple-500" style={{ animationDelay: '0ms' }} />
                  <div className="h-1 w-1 animate-pulse rounded-full bg-purple-400 dark:bg-purple-500" style={{ animationDelay: '150ms' }} />
                  <div className="h-1 w-1 animate-pulse rounded-full bg-purple-400 dark:bg-purple-500" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          )}
          {sending && messages.length > 0 && messages[messages.length - 1].role === 'assistant' && (
            <div className="flex items-center gap-2 py-1">
              <Loader2 className="h-3 w-3 animate-spin text-purple-500 dark:text-purple-400" />
              <span className="text-xs font-medium text-purple-600 dark:text-purple-300">{statusMessage}...</span>
              <button
                onClick={handleCancel}
                className="ml-auto flex h-5 w-5 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
                title="Cancel request"
              >
                <X className="h-3 w-3" />
              </button>
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
            placeholder="Ask questions, request feedback, or ask for changes..."
            className="w-full resize-none border-none bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none dark:text-slate-100 dark:placeholder:text-slate-500"
          />
          <div className="mt-2 flex items-center justify-between">
            <div className="text-[11px] text-slate-500 dark:text-slate-400">
              Enter to send | Shift+Enter for newline
            </div>
            <button
              onClick={() => void handleSend()}
              disabled={sending || !input.trim()}
              className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-purple-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow hover:from-purple-700 hover:to-indigo-700 disabled:cursor-not-allowed disabled:from-slate-400 disabled:to-slate-400"
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

export default EditorAIChatOR
