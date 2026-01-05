import React, { useState, useRef, useEffect, useCallback } from 'react'
import { Bot, Send, Loader2, Zap, FileText, BookOpen, Clock, ArrowLeft, Library, ChevronDown, Brain } from 'lucide-react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import api, { buildApiUrl, buildAuthHeaders } from '../services/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  route?: string
  model?: string
  time?: number
}

interface Paper {
  id: string
  title: string
  reference_count?: number
}

const ROUTE_INFO = {
  simple: { icon: Zap, color: 'text-green-500', bg: 'bg-green-100', label: 'Simple', desc: 'Fast response' },
  paper: { icon: FileText, color: 'text-blue-500', bg: 'bg-blue-100', label: 'Paper', desc: 'With draft context' },
  research: { icon: BookOpen, color: 'text-purple-500', bg: 'bg-purple-100', label: 'Research', desc: 'Full RAG' },
}

export default function AgentTestPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [documentContext, setDocumentContext] = useState('')
  const [showContext, setShowContext] = useState(false)
  const [papers, setPapers] = useState<Paper[]>([])
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null)
  const [refCount, setRefCount] = useState<number>(0)
  const [reasoningMode, setReasoningMode] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Fetch papers on mount
  useEffect(() => {
    const fetchPapers = async () => {
      try {
        const response = await api.get('/research-papers/')
        const data = response.data as { papers?: Paper[] } | Paper[]
        const paperList = Array.isArray(data) ? data : (data.papers || [])
        setPapers(paperList)
      } catch (error) {
        console.error('Failed to fetch papers:', error)
      }
    }
    fetchPapers()
  }, [])

  // Fetch reference count when paper is selected
  useEffect(() => {
    if (!selectedPaperId) {
      setRefCount(0)
      return
    }
    const fetchRefCount = async () => {
      try {
        const response = await api.get(`/research-papers/${selectedPaperId}/references`)
        const data = response.data as { total?: number; references?: unknown[] }
        setRefCount(data.total || data.references?.length || 0)
      } catch (error) {
        console.error('Failed to fetch references:', error)
        setRefCount(0)
      }
    }
    fetchRefCount()
  }, [selectedPaperId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(async () => {
    if (!input.trim() || sending) return

    const userMessage = input.trim()
    setInput('')
    setSending(true)

    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: userMessage }])

    const startTime = Date.now()

    try {
      // Use streaming endpoint
      const response = await fetch(buildApiUrl('/agent/chat/stream'), {
        method: 'POST',
        headers: buildAuthHeaders(),
        body: JSON.stringify({
          query: userMessage,
          document_excerpt: documentContext || null,
          paper_id: selectedPaperId || null,
          reasoning_mode: reasoningMode,
        }),
      })

      if (!response.ok) {
        throw new Error('Request failed')
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (reader) {
        let fullText = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const chunk = decoder.decode(value, { stream: true })
          fullText += chunk

          setMessages(prev => {
            const copy = [...prev]
            const lastIdx = copy.length - 1
            if (lastIdx >= 0 && copy[lastIdx].role === 'assistant') {
              copy[lastIdx] = { ...copy[lastIdx], content: copy[lastIdx].content + chunk }
            } else {
              copy.push({ role: 'assistant', content: chunk })
            }
            return copy
          })
        }

        // Update with timing
        const elapsed = Date.now() - startTime
        setMessages(prev => {
          const copy = [...prev]
          const lastIdx = copy.length - 1
          if (lastIdx >= 0 && copy[lastIdx].role === 'assistant') {
            copy[lastIdx] = { ...copy[lastIdx], time: elapsed }
          }
          return copy
        })
      }
    } catch (error: any) {
      console.error('Agent chat error:', error)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${error.message || 'Failed to get response'}`,
      }])
    } finally {
      setSending(false)
    }
  }, [input, sending, documentContext, selectedPaperId, reasoningMode])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Test with non-streaming to see route info
  const handleSendWithRouteInfo = useCallback(async () => {
    if (!input.trim() || sending) return

    const userMessage = input.trim()
    setInput('')
    setSending(true)

    setMessages(prev => [...prev, { role: 'user', content: userMessage }])

    try {
      const response = await api.post('/agent/chat', {
        query: userMessage,
        document_excerpt: documentContext || null,
        paper_id: selectedPaperId || null,
        reasoning_mode: reasoningMode,
      })

      const data = response.data as {
        response: string
        route_used: string
        model_used: string
        processing_time_ms: number
      }
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response,
        route: data.route_used,
        model: data.model_used,
        time: data.processing_time_ms,
      }])
    } catch (error: any) {
      console.error('Agent chat error:', error)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${error.response?.data?.detail || error.message}`,
      }])
    } finally {
      setSending(false)
    }
  }, [input, sending, documentContext, selectedPaperId, reasoningMode])

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <div className="border-b border-slate-700 bg-slate-800/50 backdrop-blur">
        <div className="mx-auto max-w-4xl px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Link
                to="/projects"
                className="flex items-center gap-2 text-slate-400 hover:text-white transition"
              >
                <ArrowLeft className="h-4 w-4" />
                Back
              </Link>
              <div className="h-6 w-px bg-slate-600" />
              <div className="flex items-center gap-2">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600">
                  <Bot className="h-5 w-5 text-white" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-white">Smart Agent Test</h1>
                  <p className="text-xs text-slate-400">Experimental tiered routing</p>
                </div>
              </div>
            </div>

            {/* Route Legend */}
            <div className="flex items-center gap-4 text-xs">
              {Object.entries(ROUTE_INFO).map(([key, info]) => (
                <div key={key} className="flex items-center gap-1.5">
                  <div className={`rounded-full p-1 ${info.bg}`}>
                    <info.icon className={`h-3 w-3 ${info.color}`} />
                  </div>
                  <span className="text-slate-400">{info.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-4xl px-4 py-6">
        {/* Reasoning Mode Toggle */}
        <div className="mb-4 flex items-center gap-3 p-3 rounded-lg border border-slate-700 bg-slate-800/50">
          <button
            onClick={() => setReasoningMode(!reasoningMode)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              reasoningMode ? 'bg-purple-600' : 'bg-slate-600'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                reasoningMode ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
          <div className="flex items-center gap-2">
            <Brain className={`h-5 w-5 ${reasoningMode ? 'text-purple-400' : 'text-slate-400'}`} />
            <div>
              <span className={`font-medium ${reasoningMode ? 'text-purple-300' : 'text-slate-300'}`}>
                Reasoning Mode
              </span>
              <p className="text-xs text-slate-500">
                {reasoningMode
                  ? 'Using GPT-5.2 with extended reasoning (slower but more accurate)'
                  : 'Standard mode with fast responses'}
              </p>
            </div>
          </div>
        </div>

        {/* Paper & Context Selection */}
        <div className="mb-4 flex flex-wrap gap-4">
          {/* Paper Selector */}
          <div className="flex-1 min-w-[200px]">
            <label className="text-sm text-slate-400 flex items-center gap-2 mb-2">
              <Library className="h-4 w-4" />
              Select Paper (for Research route)
            </label>
            <div className="relative">
              <select
                value={selectedPaperId || ''}
                onChange={(e) => setSelectedPaperId(e.target.value || null)}
                className="w-full appearance-none rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 pr-10 text-sm text-white focus:border-indigo-500 focus:outline-none"
              >
                <option value="">No paper selected</option>
                {papers.map((paper) => (
                  <option key={paper.id} value={paper.id}>
                    {paper.title?.slice(0, 50) || 'Untitled'}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
            </div>
            {selectedPaperId && (
              <p className="mt-1 text-xs text-slate-500">
                {refCount > 0 ? (
                  <span className="text-green-400">{refCount} references available for RAG</span>
                ) : (
                  <span className="text-yellow-400">No references found - add some to test Research route</span>
                )}
              </p>
            )}
          </div>

          {/* Document Context Toggle */}
          <div className="flex-1 min-w-[200px]">
            <button
              onClick={() => setShowContext(!showContext)}
              className="text-sm text-slate-400 hover:text-white flex items-center gap-2 mb-2"
            >
              <FileText className="h-4 w-4" />
              {showContext ? 'Hide' : 'Add'} document context (for Paper route)
            </button>
            {showContext && (
              <textarea
                value={documentContext}
                onChange={(e) => setDocumentContext(e.target.value)}
                placeholder="Paste your paper draft here to test paper-focused queries..."
                className="w-full h-24 rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none resize-none"
              />
            )}
          </div>
        </div>

        {/* Messages */}
        <div className="rounded-xl border border-slate-700 bg-slate-800/50 backdrop-blur min-h-[400px] max-h-[500px] overflow-y-auto p-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center py-12">
              <Bot className="h-12 w-12 text-slate-600 mb-4" />
              <h3 className="text-lg font-medium text-slate-300 mb-2">Test the Smart Agent</h3>
              <p className="text-sm text-slate-500 max-w-md">
                Try different types of queries to see how they're routed:
              </p>
              <div className="mt-4 grid gap-2 text-left text-sm">
                <div className="flex items-center gap-2 text-slate-400">
                  <Zap className="h-4 w-4 text-green-500" />
                  <span>"hi" or "what can you do?" → Simple route</span>
                </div>
                <div className="flex items-center gap-2 text-slate-400">
                  <FileText className="h-4 w-4 text-blue-500" />
                  <span>"summarize my introduction" → Paper route</span>
                </div>
                <div className="flex items-center gap-2 text-slate-400">
                  <BookOpen className="h-4 w-4 text-purple-500" />
                  <span>"what do my references say about X?" → Research route</span>
                </div>
              </div>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`mb-4 ${msg.role === 'user' ? 'text-right' : ''}`}
            >
              {msg.role === 'user' ? (
                <div className="inline-block max-w-[80%] rounded-2xl bg-indigo-600 px-4 py-2 text-white">
                  {msg.content}
                </div>
              ) : (
                <div className="max-w-[80%]">
                  <div className="flex items-center gap-2 mb-1">
                    {msg.route && ROUTE_INFO[msg.route as keyof typeof ROUTE_INFO] && (
                      <>
                        <div className={`rounded-full p-1 ${ROUTE_INFO[msg.route as keyof typeof ROUTE_INFO].bg}`}>
                          {React.createElement(ROUTE_INFO[msg.route as keyof typeof ROUTE_INFO].icon, {
                            className: `h-3 w-3 ${ROUTE_INFO[msg.route as keyof typeof ROUTE_INFO].color}`
                          })}
                        </div>
                        <span className="text-xs text-slate-500">
                          {ROUTE_INFO[msg.route as keyof typeof ROUTE_INFO].label}
                        </span>
                      </>
                    )}
                    {msg.model && (
                      <span className="text-xs text-slate-600">• {msg.model}</span>
                    )}
                    {msg.time && (
                      <span className="text-xs text-slate-600 flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {msg.time}ms
                      </span>
                    )}
                  </div>
                  <div className="rounded-2xl bg-slate-700 px-4 py-3 text-slate-100 prose prose-invert prose-sm max-w-none prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-li:my-0.5 prose-headings:text-slate-100">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                </div>
              )}
            </div>
          ))}

          {sending && (
            <div className="flex items-center gap-2 text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">Thinking...</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="mt-4 flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Try: 'hi', 'summarize my paper', 'what do references say about...'"
            rows={2}
            className="flex-1 rounded-xl border border-slate-600 bg-slate-800 px-4 py-3 text-white placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none resize-none"
          />
          <div className="flex flex-col gap-2">
            <button
              onClick={handleSend}
              disabled={sending || !input.trim()}
              className="flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
              title="Stream response"
            >
              {sending ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
            </button>
            <button
              onClick={handleSendWithRouteInfo}
              disabled={sending || !input.trim()}
              className="flex items-center justify-center gap-2 rounded-xl bg-slate-700 px-4 py-2 text-slate-300 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed text-xs"
              title="Send with route info (non-streaming)"
            >
              + Info
            </button>
          </div>
        </div>

        <p className="mt-2 text-xs text-slate-500 text-center">
          Press Enter to send • Use "+ Info" button to see routing details
        </p>
      </div>
    </div>
  )
}
