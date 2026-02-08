import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Bot, Brain, Check, ChevronDown, ChevronUp, Edit3, Loader2, Send, Sparkles, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { projectReferencesAPI, buildApiUrl, buildAuthHeaders } from '../../services/api'

/** Proposed edit from AI - now line-based for reliable matching */
interface EditProposal {
  id: string
  description: string
  startLine: number
  endLine: number
  anchor: string
  proposed: string
  status: 'pending' | 'approved' | 'rejected'
}

interface Clarification {
  question: string
  options: string[]
}

interface EditorAIChatProps {
  paperId: string
  projectId?: string
  documentText: string
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Callback to apply an approved edit to the document (line-based) */
  onApplyEdit?: (startLine: number, endLine: number, anchor: string, replacement: string) => boolean
  /** Callback to apply a batch of edits against a snapshot */
  onApplyEditsBatch?: (proposals: EditProposal[], sourceDocument: string) => boolean
}

type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
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
 * Context limits for the standard agent (uses OpenAI directly)
 * GPT-5.2 has 256k context, GPT-4o has 128k
 * Reserve 8k tokens for system prompt + response
 */
const STANDARD_MODEL_CONTEXT = 256000 // GPT-5.2
const RESERVED_TOKENS = 8000
const CHARS_PER_TOKEN = 4

// Dynamic limit: (256k - 8k reserved) * 4 chars = ~992k, capped at 500k
const MAX_DOC_CHARS = Math.min(
  (STANDARD_MODEL_CONTEXT - RESERVED_TOKENS) * CHARS_PER_TOKEN,
  500000
)

/**
 * Query-focused document preparation for LaTeX documents.
 *
 * Instead of sending everything, we analyze what the user is asking about
 * and send only relevant parts:
 *
 * 1. ALWAYS: Preamble (needed for LaTeX structure)
 * 2. ALWAYS: Document outline (section headers) for navigation
 * 3. TARGETED: Full content of sections matching the query
 * 4. MINIMAL: Just headers for unrelated sections
 *
 * This is much more efficient and gives better results since AI can focus.
 */

// Common section name mappings for query matching
const SECTION_ALIASES: Record<string, string[]> = {
  'abstract': ['abstract', 'summary', 'overview'],
  'introduction': ['introduction', 'intro', 'background', 'motivation'],
  'methodology': ['methodology', 'methods', 'method', 'approach', 'technique', 'algorithm'],
  'related': ['related work', 'related', 'literature', 'prior work', 'background'],
  'results': ['results', 'experiments', 'evaluation', 'findings', 'analysis'],
  'discussion': ['discussion', 'analysis', 'interpretation'],
  'conclusion': ['conclusion', 'conclusions', 'summary', 'future work', 'concluding'],
  'references': ['references', 'bibliography', 'citations'],
}

function detectTargetSections(query: string): Set<string> {
  const queryLower = query.toLowerCase()
  const targets = new Set<string>()

  // Check for explicit section mentions
  for (const [key, aliases] of Object.entries(SECTION_ALIASES)) {
    if (aliases.some(alias => queryLower.includes(alias))) {
      targets.add(key)
    }
  }

  // Check for action words that imply full document
  const fullDocActions = ['review', 'check', 'proofread', 'evaluate', 'assess', 'feedback', 'overall']
  if (fullDocActions.some(action => queryLower.includes(action))) {
    targets.add('__full__')
  }

  // Check for specific content mentions (equations, figures, tables)
  if (queryLower.includes('equation') || queryLower.includes('formula') || queryLower.includes('math')) {
    targets.add('methodology')
    targets.add('results')
  }
  if (queryLower.includes('figure') || queryLower.includes('table') || queryLower.includes('graph')) {
    targets.add('results')
  }
  if (queryLower.includes('cite') || queryLower.includes('citation') || queryLower.includes('reference')) {
    targets.add('references')
    targets.add('related')
  }

  return targets
}

function prepareDocumentForAI(doc: string, query: string, maxChars: number = MAX_DOC_CHARS): string {
  // For small documents, send everything
  if (!doc || doc.length <= maxChars * 0.5) {
    return doc
  }

  const isLatex = doc.includes('\\documentclass') || doc.includes('\\begin{document}')
  if (!isLatex) {
    // For non-LaTeX, simple truncation with context around query keywords
    return doc.slice(0, maxChars) + '\n\n[...document truncated...]'
  }

  // Detect what sections the user is asking about
  const targetSections = detectTargetSections(query)
  const needsFullDoc = targetSections.has('__full__') || targetSections.size === 0

  // Extract preamble (always include - usually small)
  const preambleMatch = doc.match(/^([\s\S]*?\\begin\{document\})/m)
  const preamble = preambleMatch ? preambleMatch[1] : ''
  const afterPreamble = preambleMatch ? doc.slice(preambleMatch[0].length) : doc

  // Extract abstract separately (special handling - often before sections)
  const abstractMatch = afterPreamble.match(/\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}/m)
  const abstractContent = abstractMatch ? abstractMatch[1].trim() : null

  // Extract sections
  const sectionRegex = /\\(section|subsection|subsubsection)\*?\{([^}]+)\}([\s\S]*?)(?=\\(?:section|subsection|subsubsection)\*?\{|\\end\{document\}|$)/g
  const sections: Array<{ type: string; title: string; content: string; isTarget: boolean }> = []
  let match

  while ((match = sectionRegex.exec(afterPreamble)) !== null) {
    const [, type, title, content] = match
    const titleLower = title.toLowerCase()

    // Check if this section matches any target
    let isTarget = needsFullDoc
    if (!isTarget) {
      for (const [key, aliases] of Object.entries(SECTION_ALIASES)) {
        if (targetSections.has(key) && aliases.some(alias => titleLower.includes(alias))) {
          isTarget = true
          break
        }
      }
    }

    // Also check if query keywords appear in section content (fuzzy match)
    if (!isTarget) {
      const queryWords = query.toLowerCase().split(/\s+/).filter(w => w.length > 4)
      const contentLower = content.toLowerCase()
      const matchCount = queryWords.filter(w => contentLower.includes(w)).length
      if (matchCount >= 2 || (queryWords.length === 1 && matchCount === 1)) {
        isTarget = true
      }
    }

    sections.push({ type, title, content: content.trim(), isTarget })
  }

  // Build focused document
  let result = preamble + '\n\n'

  // Add abstract if it exists and is relevant (or if asking about abstract/summary)
  if (abstractContent) {
    const includeAbstract = needsFullDoc ||
      targetSections.has('abstract') ||
      query.toLowerCase().includes('abstract') ||
      query.toLowerCase().includes('summary')

    if (includeAbstract) {
      result += `\\begin{abstract}\n${abstractContent}\n\\end{abstract}\n\n`
    } else {
      result += `\\begin{abstract}\n[Abstract: ${abstractContent.slice(0, 100)}...]\n\\end{abstract}\n\n`
    }
  }

  // Add document structure comment for AI orientation
  if (sections.length > 0) {
    result += `% Document structure: ${sections.map(s => s.title).join(' → ')}\n\n`
  }

  // Add sections - full content for targets, headers only for others
  let currentLength = result.length
  for (const section of sections) {
    if (section.isTarget) {
      const sectionText = `\\${section.type}{${section.title}}\n${section.content}\n\n`
      if (currentLength + sectionText.length < maxChars * 0.9) {
        result += sectionText
        currentLength += sectionText.length
      } else {
        // Even target sections need truncation if too long
        const available = maxChars * 0.9 - currentLength - 200
        if (available > 500) {
          result += `\\${section.type}{${section.title}}\n${section.content.slice(0, available)}...\n[...section continues, ${section.content.length} chars total...]\n\n`
          currentLength = maxChars * 0.9
        }
      }
    } else {
      // Just header + brief indicator
      result += `\\${section.type}{${section.title}}\n[...${section.content.length} chars - not included, ask if needed...]\n\n`
      currentLength += 100
    }
  }

  if (doc.includes('\\end{document}')) {
    result += '\\end{document}'
  }

  return result
}

const EditorAIChat: React.FC<EditorAIChatProps> = ({
  paperId,
  projectId,
  documentText,
  open,
  onOpenChange,
  onApplyEdit,
  onApplyEditsBatch,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [statusMessage, setStatusMessage] = useState<string>('Thinking')
  const [error, setError] = useState<string | null>(null)
  const [references, setReferences] = useState<ReferenceItem[]>([])
  const [reasoningMode, setReasoningMode] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)
  // Edit mode is now auto-detected by the backend based on user intent
  // No manual toggle needed - AI automatically proposes edits when appropriate
  const [expandedProposals, setExpandedProposals] = useState<Set<string>>(new Set())
  const listRef = useRef<HTMLDivElement | null>(null)

  const isReviewMessage = useCallback((content: string) => {
    if (!content) return false
    return content.includes('## Review') || content.includes('Suggested Improvements')
  }, [])

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
    const proposals: EditProposal[] = []
    // Match new line-based format: <<<EDIT>>> description <<<LINES>>> start-end <<<ANCHOR>>> text <<<PROPOSED>>> text <<<END>>>
    const editRegex = /<<<EDIT>>>\s*([\s\S]*?)<<<LINES>>>\s*([\s\S]*?)<<<ANCHOR>>>\s*([\s\S]*?)<<<PROPOSED>>>\s*([\s\S]*?)<<<END>>>/g
    let match
    let cleanText = text

    while ((match = editRegex.exec(text)) !== null) {
      const [fullMatch, description, linesStr, anchor, proposed] = match
      // Parse lines like "15-20" or "15"
      const linesParts = linesStr.trim().split('-')
      const startLine = parseInt(linesParts[0], 10) || 1
      const endLine = parseInt(linesParts[1] || linesParts[0], 10) || startLine

      proposals.push({
        id: `edit-${Date.now()}-${proposals.length}`,
        description: description.trim(),
        startLine,
        endLine,
        anchor: anchor.trim(),
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

      // Try to apply the edit using line numbers
      const success = onApplyEdit?.(proposal.startLine, proposal.endLine, proposal.anchor, proposal.proposed) ?? false

      if (success) {
        msg.proposals = msg.proposals.map((p) =>
          p.id === proposalId ? { ...p, status: 'approved' as const } : p
        )
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

      const success = onApplyEditsBatch?.(msg.proposals, msg.sourceDocument) ?? false
      if (success) {
        msg.proposals = msg.proposals.map((p) => ({ ...p, status: 'approved' as const }))
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

  const missingPdfCount = useMemo(() => {
    const hasFullText = (ref: ReferenceItem) => Boolean(
      ref.pdfProcessed || ref.documentStatus === 'processed' || ref.documentId
    )
    return references.filter((r) => !hasFullText(r)).length
  }, [references])

  /** Document content stats with smart context info */
  const docStats = useMemo(() => {
    const len = documentText?.length || 0
    const lines = documentText?.split('\n').length || 0
    const isLarge = len > MAX_DOC_CHARS * 0.5
    return { len, lines, isLarge }
  }, [documentText])

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

      // Cycle through status messages for better UX
      const statusMessages = [
        { delay: 0, message: 'Thinking' },
        { delay: 2000, message: 'Analyzing document' },
        { delay: 4000, message: 'Processing request' },
        { delay: 7000, message: 'Preparing response' },
        { delay: 12000, message: 'Almost there' },
      ]
      const statusTimers: number[] = []
      statusMessages.forEach(({ delay, message }) => {
        const timer = window.setTimeout(() => setStatusMessage(message), delay)
        statusTimers.push(timer)
      })

      // Smart document preparation - preserves structure for large docs
      const rawDoc = documentText || ''
      const docSnapshot = rawDoc
      const sourcePrompt = prompt
      const docToSend = prepareDocumentForAI(rawDoc, prompt, MAX_DOC_CHARS) || docContext || null

      console.log('[EditorAIChat] Sending request:', {
        smartEditDetection: 'enabled',
        reasoningMode,
        originalDocLength: rawDoc.length,
        preparedDocLength: docToSend?.length || 0,
        wasTruncated: rawDoc.length > MAX_DOC_CHARS,
        prompt: prompt.slice(0, 50),
      })

      // Create abort controller for cancel functionality
      abortControllerRef.current = new AbortController()

      try {
        // Use smart agent endpoint with automatic edit detection
        const res = await fetch(buildApiUrl('/agent/chat/stream'), {
          signal: abortControllerRef.current.signal,
          method: 'POST',
          headers: buildAuthHeaders(),
          body: JSON.stringify({
            query: prompt,
            paper_id: paperId,
            project_id: projectId || null,
            document_excerpt: docToSend,
            reasoning_mode: reasoningMode,
            // edit_mode is now auto-detected by backend based on user intent
            edit_mode: false,
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
          console.log('[EditorAIChat] Request cancelled by user')
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
        // Clear status timers
        statusTimers.forEach((t) => window.clearTimeout(t))
        abortControllerRef.current = null
        setSending(false)
        setStatusMessage('Thinking')
      }
    },
    [docContext, documentText, paperId, parseClarification, parseEditProposals, projectId, reasoningMode, sending]
  )

  const handleApplyReviewChanges = useCallback((mode: 'critical' | 'all') => {
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
      console.log('[EditorAIChat] Clarification selected:', { question, option })
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
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-200">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">AI Assistant</div>
            <div className="text-xs text-slate-500 dark:text-slate-400">Smart edit detection enabled</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Smart Edit Detection is automatic - no toggle needed */}
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

      {/* Smart edit detection info - only show when document is available */}
      {docStats.len > 0 && (
        <div className="mx-4 mt-3 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm shadow-sm dark:border-indigo-400/50 dark:bg-indigo-900/30 dark:text-indigo-100">
          <span className="text-indigo-800 dark:text-indigo-100">
            Smart Mode — {docStats.lines} lines, {Math.round(docStats.len / 1000)}k chars.
            {docStats.isLarge ? (
              <span className="ml-1 text-indigo-600 dark:text-indigo-300">
                Query-focused: AI sees sections relevant to your question.
              </span>
            ) : (
              <span className="ml-1">Full document attached.</span>
            )}
          </span>
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
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-slate-500 dark:text-slate-400">
              <div className="flex items-center gap-1.5">
                <Sparkles className="h-4 w-4 text-indigo-500" />
                <Bot className="h-5 w-5" />
              </div>
              <p className="text-xs">Ask questions, request reviews, or ask for changes to your paper.</p>
              <p className="text-[10px] text-slate-400 dark:text-slate-500">
                AI automatically detects when to propose edits vs. just answer
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
                    <div className="prose prose-sm prose-slate dark:prose-invert max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 prose-headings:font-semibold prose-headings:text-slate-900 dark:prose-headings:text-slate-100 prose-h3:text-sm prose-strong:text-slate-900 dark:prose-strong:text-white prose-code:rounded prose-code:bg-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:text-indigo-700 prose-code:before:content-none prose-code:after:content-none dark:prose-code:bg-slate-700 dark:prose-code:text-indigo-300 prose-blockquote:border-indigo-300 dark:prose-blockquote:border-indigo-500 prose-a:text-indigo-600 dark:prose-a:text-indigo-400 prose-a:no-underline hover:prose-a:underline">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                    </div>
                  )}
                  {m.content && isReviewMessage(m.content) && (!m.proposals || m.proposals.length === 0) && (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <button
                        onClick={() => handleApplyReviewChanges('critical')}
                        disabled={sending}
                        className="rounded-md border border-amber-300 bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-900 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-amber-500/60 dark:bg-amber-900/30 dark:text-amber-100"
                      >
                        Apply critical fixes
                      </button>
                      <button
                        onClick={() => handleApplyReviewChanges('all')}
                        disabled={sending}
                        className="rounded-md bg-emerald-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Apply all suggestions
                      </button>
                    </div>
                  )}
                  {m.clarification && (
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
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleRegenerateEdits(idx)}
                            disabled={sending}
                            className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
                          >
                            Regenerate
                          </button>
                          <button
                            onClick={() => handleApplyAllEdits(idx)}
                            disabled={sending}
                            className="rounded-md bg-emerald-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            Apply All
                          </button>
                        </div>
                      </div>
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
              <div className="space-y-2">
                <div className="flex items-center gap-2.5">
                  <div className="flex items-center gap-2 text-sm font-medium text-indigo-600 dark:text-indigo-300">
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
                  <div className="h-1 w-1 animate-pulse rounded-full bg-indigo-400 dark:bg-indigo-500" style={{ animationDelay: '0ms' }} />
                  <div className="h-1 w-1 animate-pulse rounded-full bg-indigo-400 dark:bg-indigo-500" style={{ animationDelay: '150ms' }} />
                  <div className="h-1 w-1 animate-pulse rounded-full bg-indigo-400 dark:bg-indigo-500" style={{ animationDelay: '300ms' }} />
                </div>
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
            placeholder="Ask questions, request feedback, or ask for changes…"
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
