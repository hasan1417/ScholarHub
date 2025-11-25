import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Bot, Loader2, Send, X } from 'lucide-react'
import { projectReferencesAPI, streamAPI } from '../../services/api'

interface EditorAIChatProps {
  paperId: string
  projectId?: string
  documentText: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

type ChatMessage = { role: 'user' | 'assistant'; content: string }

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
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [references, setReferences] = useState<ReferenceItem[]>([])
  const listRef = useRef<HTMLDivElement | null>(null)

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
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    if (!listRef.current) return
    listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, open])

  const docContext = useMemo(() => {
    const trimmed = (documentText || '').slice(0, MAX_DOC_CONTEXT_CHARS).trim()
    if (!trimmed) return null
    return trimmed
  }, [documentText])

  const referencesContext = useMemo(() => {
    if (!references.length) return null
    return references
      .map((ref, idx) => `${idx + 1}. ${ref.title}`)
      .join('\n')
  }, [references])

  const missingPdfCount = useMemo(() => references.filter((r) => !r.pdfUrl).length, [references])

  const buildQueryWithContext = useCallback(
    (userPrompt: string) => {
      const trimmed = userPrompt.trim().toLowerCase()
      const greetings = new Set([
        'hi',
        'hello',
        'hey',
        'hi there',
        'hello there',
        'hey there',
        'hiya',
        'howdy',
        'yo'
      ])
      if (trimmed && trimmed.length <= 12 && greetings.has(trimmed)) {
        // Avoid wrapping greetings with extra context to prevent long RAG responses
        return userPrompt.trim()
      }
      const chunks: string[] = []
      chunks.push(`User question:\n${userPrompt}`)
      if (docContext) {
        chunks.push(`Document excerpt (truncated to ${MAX_DOC_CONTEXT_CHARS} chars):\n${docContext}`)
      }
      if (referencesContext) {
        chunks.push('Attached references:\n' + referencesContext)
      } else if (projectId && paperId) {
        chunks.push('Attached references: none available for this paper yet.')
      }
      return chunks.join('\n\n')
    },
    [docContext, referencesContext, paperId, projectId]
  )

  const handleSend = useCallback(async () => {
    if (!input.trim() || sending) return
    const prompt = input.trim()
    setSending(true)
    setError(null)
    setMessages((prev) => [...prev, { role: 'user', content: prompt }, { role: 'assistant', content: '' }])
    try {
      const query = buildQueryWithContext(prompt)
      const res = await streamAPI.chatWithReferencesStream(query, paperId)
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
              copy[last] = { ...copy[last], content: (copy[last].content || '') + chunk }
            }
            return copy
          })
        }
      }
      if (!fullText.trim()) {
        setMessages((prev) => {
          const copy = [...prev]
          const last = copy.length - 1
          if (last >= 0 && copy[last].role === 'assistant') {
            copy[last] = { ...copy[last], content: 'No response received.' }
          }
          return copy
        })
      }
      setInput('')
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Chat request failed.'
      setError(msg)
      setMessages((prev) => {
        const copy = [...prev]
        // remove the last assistant placeholder and user entry if they were added
        if (copy.length >= 2 && copy[copy.length - 2].role === 'user' && copy[copy.length - 2].content === prompt) {
          copy.pop()
          copy.pop()
        }
        return copy
      })
    } finally {
      setSending(false)
    }
  }, [buildQueryWithContext, input, messages, paperId, sending])

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
            <div className="text-xs text-slate-500 dark:text-slate-400">Ask questions about this paper</div>
          </div>
        </div>
        <button
          onClick={() => onOpenChange(false)}
          className="rounded-full p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          aria-label="Close AI chat"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

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
              <p className="text-xs">Start a chat to get answers grounded in this paper.</p>
            </div>
          )}
          {messages.map((m, idx) => (
            <div key={idx} className="mb-3 last:mb-0">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {m.role === 'assistant' ? 'Assistant' : 'You'}
              </div>
              <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-900 dark:text-slate-100">{m.content}</div>
            </div>
          ))}
          {sending && (
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
            placeholder="Ask about this draft…"
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
