import React, { useState, useRef, useEffect, useCallback } from 'react'
import {
  Bot,
  Send,
  Loader2,
  Search,
  BookOpen,
  ArrowLeft,
  Trash2,
  MessageSquare,
  Sparkles,
  ExternalLink,
  ChevronDown,
  Brain,
  FileText,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import api from '../services/api'

interface SearchResult {
  id: string
  title: string
  authors: string
  year: number | null
  source: string
  abstract: string
  url?: string
  doi?: string
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  actions?: Array<{
    type: string
    summary?: string
    payload?: Record<string, unknown>
  }>
  model?: string
  reasoning_used?: boolean
}

interface Project {
  id: string
  title: string
}

interface Channel {
  id: string
  name: string
  slug: string
}

export default function DiscussionAITestPage() {
  // Project/Channel selection
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [channels, setChannels] = useState<Channel[]>([])
  const [selectedChannelId, setSelectedChannelId] = useState<string | null>(null)

  // Search state
  const [searchQuery, setSearchQuery] = useState('')
  const [searchCount, setSearchCount] = useState(5)
  const [searching, setSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])

  // Chat state
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [reasoningMode, setReasoningMode] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Fetch projects on mount
  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const response = await api.get('/projects/')
        const data = response.data as { projects?: Project[] } | Project[]
        const projectList = Array.isArray(data) ? data : data.projects || []
        setProjects(projectList)
        if (projectList.length > 0) {
          setSelectedProjectId(projectList[0].id)
        }
      } catch (error) {
        console.error('Failed to fetch projects:', error)
      }
    }
    fetchProjects()
  }, [])

  // Fetch channels when project changes
  useEffect(() => {
    if (!selectedProjectId) {
      setChannels([])
      setSelectedChannelId(null)
      return
    }
    const fetchChannels = async () => {
      try {
        const response = await api.get(`/projects/${selectedProjectId}/discussion/channels`)
        const channelList = response.data as Channel[]
        setChannels(channelList)
        if (channelList.length > 0) {
          setSelectedChannelId(channelList[0].id)
        }
      } catch (error) {
        console.error('Failed to fetch channels:', error)
        // Create default channel if none exists
        try {
          const createResponse = await api.post(`/projects/${selectedProjectId}/discussion/channels`, {
            name: 'AI Test',
          })
          const newChannel = createResponse.data as Channel
          setChannels([newChannel])
          setSelectedChannelId(newChannel.id)
        } catch (createError) {
          console.error('Failed to create channel:', createError)
        }
      }
    }
    fetchChannels()
  }, [selectedProjectId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Search for papers
  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim() || searching) return

    setSearching(true)
    try {
      // Use the project discovery API for searching
      await api.post(`/projects/${selectedProjectId}/discovery/run`, {
        query: searchQuery,
        max_results: searchCount,
        sources: ['semantic_scholar', 'arxiv', 'crossref'],
      })

      // Wait a bit for results to be processed
      await new Promise((resolve) => setTimeout(resolve, 2000))

      // Fetch the results
      const resultsResponse = await api.get(`/projects/${selectedProjectId}/discovery/results`, {
        params: { status: 'pending', limit: searchCount },
      })

      const results = resultsResponse.data as { results?: SearchResult[] } | SearchResult[]
      const resultList = Array.isArray(results) ? results : results.results || []

      // Map to our format (discovery API returns published_year, summary)
      const mappedResults: SearchResult[] = resultList.map((r: any, idx: number) => ({
        id: r.id || `result-${idx}`,
        title: r.title || 'Untitled',
        authors: Array.isArray(r.authors) ? r.authors.join(', ') : r.authors || 'Unknown',
        year: r.year || r.published_year || r.publication_year || null,
        source: r.source || 'Unknown',
        abstract: r.abstract || r.summary || '',
        url: r.url || r.source_url || r.pdf_url,
        doi: r.doi,
      }))

      setSearchResults(mappedResults)

      // Add a system message about the search
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Found ${mappedResults.length} papers about "${searchQuery}". You can now ask me to create a literature review, explain these papers, or search for more.`,
        },
      ])
    } catch (error: any) {
      console.error('Search failed:', error)
      // Fallback: use mock results for testing
      const mockResults: SearchResult[] = [
        {
          id: '1',
          title: `Sample Paper about ${searchQuery}`,
          authors: 'Smith, J., Johnson, A.',
          year: 2024,
          source: 'arXiv',
          abstract: `This paper discusses ${searchQuery} and its applications in modern research...`,
        },
        {
          id: '2',
          title: `A Survey on ${searchQuery}`,
          authors: 'Brown, M., Davis, K.',
          year: 2023,
          source: 'Semantic Scholar',
          abstract: `A comprehensive survey covering recent advances in ${searchQuery}...`,
        },
      ]
      setSearchResults(mockResults)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `(Using mock data) Found ${mockResults.length} sample papers. You can now test the AI interactions.`,
        },
      ])
    } finally {
      setSearching(false)
    }
  }, [searchQuery, searchCount, searching, selectedProjectId])

  // Send message to Discussion AI
  const handleSend = useCallback(async () => {
    if (!input.trim() || sending || !selectedProjectId || !selectedChannelId) return

    const userMessage = input.trim()
    setInput('')
    setSending(true)

    setMessages((prev) => [...prev, { role: 'user', content: userMessage }])

    try {
      // Build conversation history from previous messages (exclude current)
      const conversationHistory = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }))

      // DEBUG: Log what we're sending
      console.log('=== SENDING TO API ===')
      console.log('Question:', userMessage)
      console.log('Conversation history:', conversationHistory.length, 'messages')
      conversationHistory.forEach((m, i) => {
        console.log(`  [${i}] ${m.role}: ${m.content.substring(0, 80)}...`)
      })

      const response = await api.post(
        `/projects/${selectedProjectId}/discussion/channels/${selectedChannelId}/assistant`,
        {
          question: userMessage,
          reasoning: reasoningMode,
          recent_search_results: searchResults.map((r) => ({
            title: r.title,
            authors: r.authors,
            year: r.year,
            source: r.source,
            abstract: r.abstract,
          })),
          conversation_history: conversationHistory,
        }
      )

      const data = response.data as {
        message: string
        citations?: Array<{ label: string }>
        reasoning_used: boolean
        model: string
        suggested_actions?: Array<{
          action_type: string
          summary: string
          payload?: Record<string, unknown>
        }>
      }

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.message,
          actions: data.suggested_actions?.map((a) => ({
            type: a.action_type,
            summary: a.summary,
            payload: a.payload,
          })),
          model: data.model,
          reasoning_used: data.reasoning_used,
        },
      ])

      // Handle actions if any - auto-execute searches (batch them together)
      if (data.suggested_actions && data.suggested_actions.length > 0) {
        const searchActions = data.suggested_actions.filter(
          (a) => a.action_type === 'search_references' && a.payload?.query
        )

        if (searchActions.length > 0) {
          setSearching(true)
          const searchQueries: string[] = []
          const allNewPapers: SearchResult[] = []
          const seenTitles = new Set<string>()

          try {
            // Execute all searches and collect results
            for (const action of searchActions) {
              const payload = action.payload as { query?: string; max_results?: number }
              if (!payload?.query) continue

              searchQueries.push(payload.query)

              // Execute search
              await api.post(`/projects/${selectedProjectId}/discovery/run`, {
                query: payload.query,
                max_results: payload.max_results || 1,
                sources: ['semantic_scholar', 'arxiv', 'crossref'],
              })

              // Brief wait between searches
              await new Promise((resolve) => setTimeout(resolve, 1500))

              // Fetch results
              const resultsResponse = await api.get(
                `/projects/${selectedProjectId}/discovery/results`,
                { params: { status: 'pending', limit: payload.max_results || 1 } }
              )

              const results = resultsResponse.data as { results?: any[] } | any[]
              const resultList = Array.isArray(results) ? results : results.results || []

              // Map results and track unique papers
              for (const r of resultList) {
                const titleLower = (r.title || 'Untitled').toLowerCase()
                if (!seenTitles.has(titleLower)) {
                  seenTitles.add(titleLower)
                  allNewPapers.push({
                    id: r.id || `result-${Date.now()}-${allNewPapers.length}`,
                    title: r.title || 'Untitled',
                    authors: Array.isArray(r.authors) ? r.authors.join(', ') : r.authors || 'Unknown',
                    year: r.year || r.published_year || null,
                    source: r.source || 'Unknown',
                    abstract: r.abstract || r.summary || '',
                    url: r.url || r.source_url || r.pdf_url,
                    doi: r.doi,
                  })
                }
              }
            }

            // Update state once with all collected papers
            setSearchResults((prev) => {
              const existingTitles = new Set(prev.map((p) => p.title?.toLowerCase()))
              const trulyNew = allNewPapers.filter((p) => !existingTitles.has(p.title?.toLowerCase()))
              return [...prev, ...trulyNew]
            })

            // Show ONE summary message at the end
            if (allNewPapers.length > 0 || searchQueries.length > 0) {
              setMessages((prev) => [
                ...prev,
                {
                  role: 'assistant',
                  content: `Found ${allNewPapers.length} papers across ${searchQueries.length} searches. Results are shown in the panel on the left.`,
                },
              ])
            }
          } catch (searchError) {
            console.error('Search failed:', searchError)
          } finally {
            setSearching(false)
          }
        }
      }
    } catch (error: any) {
      console.error('Chat error:', error)
      // Handle Pydantic validation errors (which come as array)
      let errorMessage = error.message
      if (error.response?.data?.detail) {
        const detail = error.response.data.detail
        if (Array.isArray(detail)) {
          // Pydantic validation error - format nicely
          errorMessage = detail.map((e: any) => `${e.loc?.join('.')}: ${e.msg}`).join('; ')
        } else {
          errorMessage = String(detail)
        }
      }
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Error: ${errorMessage}`,
        },
      ])
    } finally {
      setSending(false)
    }
  }, [input, sending, selectedProjectId, selectedChannelId, reasoningMode, searchResults])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const clearResults = () => {
    setSearchResults([])
    setMessages([])
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <div className="border-b border-slate-700 bg-slate-800/50 backdrop-blur sticky top-0 z-10">
        <div className="mx-auto max-w-6xl px-4 py-4">
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
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600">
                  <MessageSquare className="h-5 w-5 text-white" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-white">Discussion AI Test</h1>
                  <p className="text-xs text-slate-400">Test the new skill-based architecture</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-4 py-6">
        {/* Project/Channel Selection */}
        <div className="mb-4 grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm text-slate-400 mb-1 block">Project</label>
            <div className="relative">
              <select
                value={selectedProjectId || ''}
                onChange={(e) => setSelectedProjectId(e.target.value || null)}
                className="w-full appearance-none rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 pr-10 text-sm text-white focus:border-emerald-500 focus:outline-none"
              >
                <option value="">Select project...</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
            </div>
          </div>
          <div>
            <label className="text-sm text-slate-400 mb-1 block">Channel</label>
            <div className="relative">
              <select
                value={selectedChannelId || ''}
                onChange={(e) => setSelectedChannelId(e.target.value || null)}
                className="w-full appearance-none rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 pr-10 text-sm text-white focus:border-emerald-500 focus:outline-none"
                disabled={!selectedProjectId}
              >
                <option value="">Select channel...</option>
                {channels.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Search Panel */}
          <div className="lg:col-span-1">
            <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-medium text-white flex items-center gap-2">
                  <Search className="h-4 w-4 text-emerald-400" />
                  Reference Search
                </h2>
                {searchResults.length > 0 && (
                  <button
                    onClick={clearResults}
                    className="text-xs text-slate-400 hover:text-red-400 flex items-center gap-1"
                  >
                    <Trash2 className="h-3 w-3" />
                    Clear
                  </button>
                )}
              </div>

              <div className="space-y-3">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  placeholder="Search topic..."
                  className="w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-emerald-500 focus:outline-none"
                />

                <div className="flex items-center gap-2">
                  <label className="text-xs text-slate-400">Count:</label>
                  <input
                    type="number"
                    value={searchCount}
                    onChange={(e) => setSearchCount(Math.min(20, Math.max(1, parseInt(e.target.value) || 5)))}
                    min={1}
                    max={20}
                    className="w-16 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-sm text-white focus:border-emerald-500 focus:outline-none"
                  />
                </div>

                <button
                  onClick={handleSearch}
                  disabled={searching || !searchQuery.trim() || !selectedProjectId}
                  className="w-full flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm text-white hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {searching ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Searching...
                    </>
                  ) : (
                    <>
                      <Search className="h-4 w-4" />
                      Search
                    </>
                  )}
                </button>
              </div>

              {/* Search Results */}
              {searchResults.length > 0 && (
                <div className="mt-4 space-y-2 max-h-[400px] overflow-y-auto">
                  <h3 className="text-xs text-slate-400 uppercase tracking-wide">
                    {searchResults.length} Results
                  </h3>
                  {searchResults.map((result, idx) => (
                    <div
                      key={result.id}
                      className="rounded-lg border border-slate-600 bg-slate-900/50 p-3"
                    >
                      <div className="flex items-start gap-2">
                        <span className="flex-shrink-0 w-5 h-5 rounded-full bg-emerald-600/20 text-emerald-400 text-xs flex items-center justify-center">
                          {idx + 1}
                        </span>
                        <div className="flex-1 min-w-0">
                          <h4 className="text-sm font-medium text-white line-clamp-2">
                            {result.title}
                          </h4>
                          <p className="text-xs text-slate-400 mt-1">
                            {result.authors} {result.year && `(${result.year})`}
                          </p>
                          <p className="text-xs text-slate-500 mt-1 line-clamp-2">
                            {result.abstract}
                          </p>
                          <div className="flex items-center gap-2 mt-2">
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-300">
                              {result.source}
                            </span>
                            {result.url && (
                              <a
                                href={result.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-emerald-400 hover:text-emerald-300"
                              >
                                <ExternalLink className="h-3 w-3" />
                              </a>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Chat Panel */}
          <div className="lg:col-span-2">
            {/* Reasoning Toggle */}
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
                <span className={`text-sm ${reasoningMode ? 'text-purple-300' : 'text-slate-300'}`}>
                  Reasoning Mode
                </span>
              </div>
            </div>

            {/* Messages */}
            <div className="rounded-xl border border-slate-700 bg-slate-800/50 min-h-[400px] max-h-[500px] overflow-y-auto p-4">
              {messages.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full text-center py-12">
                  <Bot className="h-12 w-12 text-slate-600 mb-4" />
                  <h3 className="text-lg font-medium text-slate-300 mb-2">Discussion AI Test</h3>
                  <p className="text-sm text-slate-500 max-w-md mb-4">
                    Search for papers first, then try these commands:
                  </p>
                  <div className="grid gap-2 text-left text-sm">
                    <div className="flex items-center gap-2 text-slate-400">
                      <Search className="h-4 w-4 text-emerald-500" />
                      <span>"Find 5 papers about transformers"</span>
                    </div>
                    <div className="flex items-center gap-2 text-slate-400">
                      <FileText className="h-4 w-4 text-blue-500" />
                      <span>"Create a literature review about these papers"</span>
                    </div>
                    <div className="flex items-center gap-2 text-slate-400">
                      <BookOpen className="h-4 w-4 text-purple-500" />
                      <span>"Explain the first paper"</span>
                    </div>
                    <div className="flex items-center gap-2 text-slate-400">
                      <Sparkles className="h-4 w-4 text-yellow-500" />
                      <span>"What are our project objectives?"</span>
                    </div>
                  </div>
                </div>
              )}

              {messages.map((msg, idx) => (
                <div key={idx} className={`mb-4 ${msg.role === 'user' ? 'text-right' : ''}`}>
                  {msg.role === 'user' ? (
                    <div className="inline-block max-w-[80%] rounded-2xl bg-emerald-600 px-4 py-2 text-white">
                      {msg.content}
                    </div>
                  ) : (
                    <div className="max-w-[85%]">
                      <div className="flex items-center gap-2 mb-1">
                        <Bot className="h-4 w-4 text-slate-400" />
                        {msg.model && <span className="text-xs text-slate-500">{msg.model}</span>}
                        {msg.reasoning_used && (
                          <span className="text-xs text-purple-400 flex items-center gap-1">
                            <Brain className="h-3 w-3" />
                            Reasoning
                          </span>
                        )}
                      </div>
                      <div className="rounded-2xl bg-slate-700 px-4 py-3 text-slate-100 prose prose-invert prose-sm max-w-none">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
                      {msg.actions && msg.actions.length > 0 && (
                        <div className="mt-2">
                          {/* Show summary for search actions instead of listing each one */}
                          {(() => {
                            const searchActions = msg.actions.filter((a) => a.type === 'search_references')
                            const otherActions = msg.actions.filter((a) => a.type !== 'search_references')

                            return (
                              <>
                                {searchActions.length > 0 && (
                                  <div className="flex items-center gap-2 text-xs text-slate-400 bg-slate-800 rounded px-2 py-1 mb-1">
                                    <Search className="h-3 w-3 text-emerald-400" />
                                    <span>Searching for {searchActions.length} topic{searchActions.length > 1 ? 's' : ''}...</span>
                                  </div>
                                )}
                                {otherActions.map((action, actionIdx) => (
                                  <div
                                    key={actionIdx}
                                    className="flex items-center gap-2 text-xs text-slate-400 bg-slate-800 rounded px-2 py-1 mb-1"
                                  >
                                    <Sparkles className="h-3 w-3 text-yellow-400" />
                                    <span>Action: {action.type}</span>
                                    {action.summary && <span className="text-slate-500">- {action.summary}</span>}
                                  </div>
                                ))}
                              </>
                            )
                          })()}
                        </div>
                      )}
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
                placeholder="Ask about the papers, create a literature review, or ask questions..."
                rows={2}
                disabled={!selectedProjectId || !selectedChannelId}
                className="flex-1 rounded-xl border border-slate-600 bg-slate-800 px-4 py-3 text-white placeholder:text-slate-500 focus:border-emerald-500 focus:outline-none resize-none disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={sending || !input.trim() || !selectedProjectId || !selectedChannelId}
                className="flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-6 py-2 text-white hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {sending ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
              </button>
            </div>

            {!selectedProjectId && (
              <p className="mt-2 text-xs text-yellow-400 text-center">
                Please select a project and channel to start chatting
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
