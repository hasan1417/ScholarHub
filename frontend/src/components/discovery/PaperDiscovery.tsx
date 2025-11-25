import React, { useState, useRef } from 'react'
import { Search, Star, ExternalLink, Plus, BookOpen, Calendar, Users, TrendingUp, CheckCircle, Clock, ArrowUpDown } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { researchPapersAPI, referencesAPI, buildApiUrl } from '../../services/api'

interface DiscoveredPaper {
  title: string
  authors: string[]
  abstract: string
  year?: number
  doi?: string
  url?: string
  source: string
  relevance_score: number
  citations_count?: number
  journal?: string
  keywords?: string[]
  // OA enrichment (optional)
  is_open_access?: boolean
  open_access_url?: string
  pdf_url?: string
}

interface PaperDiscoveryProps {
  onAddPaper?: (paper: DiscoveredPaper) => void
  onClose?: () => void
  paperId?: string // if provided, add as reference to this paper
  forcePaperMode?: boolean // lock UI to paper mode (used when launched from Discovery Hub picker)
}

const PaperDiscovery: React.FC<PaperDiscoveryProps> = ({ onAddPaper, onClose, paperId: paperIdProp, forcePaperMode }) => {
  const { isAuthenticated } = useAuth()
  const [toast, setToast] = useState<{ type: 'success' | 'info' | 'error'; message: string } | null>(null)
  const showToast = (message: string, type: 'success' | 'info' | 'error' = 'info', ms = 3500) => {
    setToast({ type, message })
    window.setTimeout(() => setToast(null), ms)
  }
  const [query, setQuery] = useState('')
  const [researchTopic, setResearchTopic] = useState('')
  const [papers, setPapers] = useState<DiscoveredPaper[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [searchTime, setSearchTime] = useState(0)
  const [selectedSources, setSelectedSources] = useState<string[]>(['crossref'])
  console.log('🔍 PaperDiscovery initialized with selectedSources:', selectedSources)
  const [maxResults, setMaxResults] = useState(20)
  const [sortBy, setSortBy] = useState<'relevance' | 'year' | 'citations'>('relevance')
  // Relevance threshold filter (null = no filter)
  const [relevanceThreshold, setRelevanceThreshold] = useState<number | null>(null)
  // Filter: only show results with a direct PDF URL
  const [pdfOnly, setPdfOnly] = useState(false)
  const [deepRescoring, setDeepRescoring] = useState(false)
  const [filterByYear, setFilterByYear] = useState<number | null>(null)
  const [addingPapers, setAddingPapers] = useState<Set<string>>(new Set())
  const [addedPapers, setAddedPapers] = useState<Set<string>>(new Set())
  // Removed manual ingestion/content viewing from discovery list
  const [hasSearched, setHasSearched] = useState(false)
  const [selectedPaper, setSelectedPaper] = useState<DiscoveredPaper | null>(null)
  const [viewingContent, setViewingContent] = useState<Record<string, any>>({})

  // Milestone 1.5: Mode support (Query vs Paper)
  const [mode, setMode] = useState<'query' | 'paper'>(forcePaperMode || !!paperIdProp ? 'paper' : 'query')
  console.log('🎯 PaperDiscovery mode:', mode, 'forcePaperMode:', forcePaperMode, 'paperIdProp:', paperIdProp)
  const initialUseCurrent = Boolean(paperIdProp)
  const [paperModeSource, setPaperModeSource] = useState<'current' | 'text'>(initialUseCurrent ? 'current' : 'current')
  const [includeContent, setIncludeContent] = useState(true) // for current paper context

  // Select paper modal state (for global discovery linkage)
  const [showSelectPaper, setShowSelectPaper] = useState(false)
  const [myPapers, setMyPapers] = useState<Array<{ id: string; title: string }>>([])
  const [selectedTargetPapers, setSelectedTargetPapers] = useState<Set<string>>(new Set())
  const [attachCandidate, setAttachCandidate] = useState<DiscoveredPaper | null>(null)
  const [uploadingPdf, setUploadingPdf] = useState(false)
  const [uploadStatus, setUploadStatus] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  // Source paper picker (global discovery to select a paper as context)
  const [showSourcePicker, setShowSourcePicker] = useState(false)
  const [sourcePapers, setSourcePapers] = useState<Array<{ id: string; title: string; year?: number; status?: string }>>([])
  const [sourcePaperId, setSourcePaperId] = useState<string | null>(null)
  const [sourcePaperTitle, setSourcePaperTitle] = useState<string | null>(null)
  const [sourceLoading, setSourceLoading] = useState(false)
  const [sourceError, setSourceError] = useState<string | null>(null)
  const [sourceFilter, setSourceFilter] = useState('')
  const [selectedSourcePaperTemp, setSelectedSourcePaperTemp] = useState<string | null>(null)
  const [selectedSourcePaperTitleTemp, setSelectedSourcePaperTitleTemp] = useState<string | null>(null)

  const openSelectPaperModal = async () => {
    try {
      const resp = await fetch(buildApiUrl('/research-papers/?skip=0&limit=100'), {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
      })
      if (resp.ok) {
        const data = await resp.json()
        const items = (data.papers || []).map((p: any) => ({ id: p.id, title: p.title }))
        setMyPapers(items)
        setShowSelectPaper(true)
      } else {
        setMyPapers([])
        setShowSelectPaper(true)
      }
    } catch {
      setMyPapers([])
      setShowSelectPaper(true)
    }
  }

  // Add to My References (create in user reference library)
  const handleAddToLibrary = async (paper: DiscoveredPaper) => {
    const key = `${paper.title}-${paper.source}`
    setAddingPapers(prev => new Set([...prev, key]))
    try {
      const payload = {
        title: paper.title,
        authors: paper.authors,
        abstract: paper.abstract,
        year: paper.year,
        doi: paper.doi,
        url: paper.url,
        source: paper.source,
        journal: paper.journal,
        is_open_access: (paper as any).is_open_access || false,
        pdf_url: (paper as any).pdf_url || undefined,
      }
      const response = await referencesAPI.create(payload)
      const responseData = response.data as { reference?: { id?: string } | null; id?: string | null } | null
      if (response.status === 201 || responseData?.reference || responseData?.id) {
        setAddedPapers(prev => new Set([...prev, key]))
        const hasPdf = Boolean(payload.pdf_url)
        if (hasPdf) {
          showToast('Added to My References. PDF detected — ingesting now.', 'success')
        } else {
          showToast('Added to My References.', 'success')
        }
      } else {
        showToast('Failed to add to My References.', 'error')
      }
    } catch (e) {
      console.error('Error adding to My References', e)
      showToast('Failed to add to My References.', 'error')
    } finally {
      setAddingPapers(prev => { const s = new Set(prev); s.delete(key); return s })
    }
  }

  const handleViewContent = (paper: DiscoveredPaper) => {
    const key = `${paper.title}-${paper.source}`
    setViewingContent(prev => ({
      ...prev,
      [key]: {
        error: 'Content preview is not available in the current build. Please open the original source.',
      },
    }))
    setSelectedPaper(paper)
  }


  const availableSources = [
    { id: 'semantic_scholar', name: 'Semantic Scholar', description: 'AI-powered academic search' },
    { id: 'sciencedirect', name: 'ScienceDirect', description: 'Elsevier articles (API key)' },
    { id: 'openalex', name: 'OpenAlex', description: 'Open scholarly index' },
    { id: 'arxiv', name: 'arXiv', description: 'Preprint repository' },
    { id: 'crossref', name: 'Crossref', description: 'DOI database' },
    { id: 'pubmed', name: 'PubMed', description: 'Medical literature' }
  ]

  const canSearch = () => {
    if (!isAuthenticated) return false
    if (!forcePaperMode && mode === 'query') return query.trim().length >= 3
    // paper mode
    if (paperIdProp) return true
    if (sourcePaperId) return true
    return false
  }

  const buildPayload = (overrideMax?: number) => {
    const base: any = {
      mode,
      research_topic: researchTopic.trim() || null,
      max_results: overrideMax ?? maxResults,
      sources: selectedSources,
    }
    console.log('📦 buildPayload called, returning:', base)

    // Only send query for query mode; paper mode relies on research_topic + paper
    if (mode === 'query' && query.trim()) base.query = query.trim()
    if (mode === 'paper') {
      if ((paperModeSource === 'current' || forcePaperMode) && paperIdProp) {
        base.paper_id = paperIdProp
        base.use_content = includeContent
      } else if (sourcePaperId) {
        base.paper_id = sourcePaperId
        base.use_content = includeContent
      }
    }
    return base
  }

  const [isLoadingMore, setIsLoadingMore] = useState(false)

  // Prevent cascading results across searches
  const currentSearchIdRef = useRef(0)
  const activeControllerRef = useRef<AbortController | null>(null)

  const runStreamSearch = async (payload: any, opts?: { append?: boolean }) => {
    const append = Boolean(opts?.append)
    if (append) setIsLoadingMore(true)
    if (!append) setIsSearching(true)
    const startTime = Date.now()
    // Create/attach controller & search id
    let searchId = currentSearchIdRef.current
    if (!append) {
      // Abort any in-flight search
      try { activeControllerRef.current?.abort() } catch {}
      activeControllerRef.current = new AbortController()
      currentSearchIdRef.current += 1
      searchId = currentSearchIdRef.current
    }
    try {
      if (!append) {
        setPapers([])
      }
      const response = await fetch(buildApiUrl('/discovery/papers/discover/stream'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify(payload),
        signal: activeControllerRef.current?.signal
      })
      if (!response.ok || !response.body) throw new Error(`Search failed: ${response.status} ${response.statusText}`)
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        // If a newer search started, stop processing this stream
        if (searchId !== currentSearchIdRef.current) {
          try { reader.cancel() } catch {}
          break
        }
        buf += decoder.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() || ''
        for (const part of parts) {
          const line = part.trim()
          if (!line.startsWith('data:')) continue
          const jsonStr = line.replace(/^data:\s*/, '')
          try {
            const evt = JSON.parse(jsonStr)
            if (evt.type === 'final' && Array.isArray(evt.papers)) {
              // Ignore if stale
              if (searchId !== currentSearchIdRef.current) return (prev: DiscoveredPaper[]) => prev

              console.log(`Received ${evt.papers.length} papers from sources:`, evt.papers.map((p: DiscoveredPaper) => p.source))

              if (append) {
                setPapers(prev => {
                  const seen = new Set(prev.map(p => p.title + '|' + p.source))
                  const merged = [...prev]
                  for (const p of evt.papers as DiscoveredPaper[]) {
                    const key = p.title + '|' + p.source
                    if (!seen.has(key)) { seen.add(key); merged.push(p) }
                  }
                  return merged
                })
              } else {
                setPapers(evt.papers as DiscoveredPaper[])
              }
              if (searchId === currentSearchIdRef.current) {
                setSearchTime((Date.now() - startTime) / 1000)
              }
            } else if (evt.type === 'done') {
              if (searchId === currentSearchIdRef.current) {
                setSearchTime((Date.now() - startTime) / 1000)
              }
            } else if (evt.type === 'error') {
              throw new Error(evt.message || 'Search failed')
            }
          } catch (err) {
            console.error('Error parsing stream event:', err)
          }
        }
      }
    } catch (error) {
      // Suppress noise for user-initiated aborts
      if ((error as any)?.name === 'AbortError') return
      console.error('Error searching papers:', error)
      alert(error instanceof Error ? error.message : 'Search failed. Please try again.')
    } finally {
      if (append) setIsLoadingMore(false)
      if (!append && searchId === currentSearchIdRef.current) setIsSearching(false)
    }
  }

  const handleSearch = async () => {
    if (!canSearch()) {
      if (!isAuthenticated) alert('Please login to search for papers.')
      else if (mode === 'query') alert('Please enter at least 3 characters for your search query.')
      else if (paperModeSource === 'current') alert('Open discovery from a paper to use current paper context.')
      else alert('Please paste at least 10 characters for paper context.')
      return
    }
    setHasSearched(true)

    const payload = buildPayload()
    console.log('Sending search with payload:', payload)
    await runStreamSearch(payload)
  }

  const handleLoadMore = async () => {
    const newLimit = papers.length + 20
    await runStreamSearch(buildPayload(newLimit), { append: true })
  }

  // Deep Rescore PDFs using backend endpoint
  const handleDeepRescore = async () => {
    try {
      setDeepRescoring(true)
      // Prepare request
      const payload: any = {
        mode,
        query: mode === 'query' ? (query.trim() || null) : null,
        paper_id: mode === 'paper' ? (paperIdProp || sourcePaperId) : null,
        use_content: includeContent,
        items: getSortedAndFilteredPapers().slice(0, 20) // send up to 20
          .map(p => ({
            title: p.title,
            authors: Array.isArray(p.authors) ? p.authors : [],
            abstract: p.abstract,
            year: p.year,
            doi: p.doi,
            url: p.url,
            source: p.source,
            pdf_url: (p as any).pdf_url,
            relevance_score: p.relevance_score,
            citations_count: (p as any).citations_count,
            journal: p.journal,
            keywords: p.keywords
          })),
        top_n: 10
      }
      const resp = await fetch(buildApiUrl('/discovery/papers/deep-rescore'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify(payload)
      })
      if (!resp.ok) throw new Error('Deep rescore failed')
      const data = await resp.json()
      if (Array.isArray(data.items)) {
        setPapers(data.items as DiscoveredPaper[])
        showToast(`Deep rescored ${data.rescored} paper(s) using ${data.method}.`, 'success')
      } else {
        showToast('Deep rescore returned no items.', 'info')
      }
    } catch (e) {
      console.error('Deep rescore error', e)
      showToast('Deep rescore failed.', 'error')
    } finally {
      setDeepRescoring(false)
    }
  }

  // Content viewer removed for simplified reference flow

  const handleAddPaper = async (paper: DiscoveredPaper) => {
    // If already inside a specific paper, add reference directly; otherwise open select modal
    if (paperIdProp) {
      try {
        await researchPapersAPI.addReference(paperIdProp, {
          title: paper.title,
          authors: paper.authors || [],
          year: paper.year,
          doi: paper.doi,
          url: paper.url,
          source: paper.source,
          is_open_access: (paper as any).is_open_access || false,
          pdf_url: (paper as any).pdf_url || undefined
        })
        alert('Reference added to this paper.')
        if (onAddPaper) onAddPaper(paper)
      } catch (e) {
        console.error('Failed to add reference', e)
        alert('Failed to add reference.')
      }
      return
    }
    // Global discovery: let user pick target papers
    setAttachCandidate(paper)
    setSelectedTargetPapers(new Set())
    await openSelectPaperModal()
  }


  // Ingest OA PDF removed in favor of reference upload in My References

  const handleSourceToggle = (sourceId: string) => {
    setSelectedSources(prev => {
      const newSources = prev.includes(sourceId)
        ? prev.filter(s => s !== sourceId)
        : [...prev, sourceId]
      console.log('🔄 Source toggled:', sourceId, 'New selectedSources:', newSources)
      return newSources
    })
  }

  const getSortedAndFilteredPapers = () => {
    let filtered = papers

    // Filter by year
    if (filterByYear) {
      filtered = filtered.filter(p => p.year && p.year >= filterByYear)
    }

    // Filter by relevance threshold (client-side)
    if (relevanceThreshold !== null) {
      filtered = filtered.filter(p => (p.relevance_score ?? 0) >= relevanceThreshold)
    }

    // Filter: PDF available only
    if (pdfOnly) {
      filtered = filtered.filter(p => Boolean((p as any).pdf_url))
    }

    // Sort papers
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'relevance':
          return b.relevance_score - a.relevance_score
        case 'year':
          return (b.year || 0) - (a.year || 0)
        case 'citations':
          return (b.citations_count || 0) - (a.citations_count || 0)
        default:
          return 0
      }
    })

    return filtered
  }

  const getSourceIcon = (source: string) => {
    const icons: Record<string, string> = {
      semantic_scholar: '🧠',
      arxiv: '📄',
      crossref: '🔗',
      pubmed: '🏥'
    }
    return icons[source] || '📚'
  }

  const formatAuthors = (authors?: string[]) => {
    if (!Array.isArray(authors) || authors.length === 0) return 'Unknown Authors'
    if (authors.length <= 3) return authors.join(', ')
    return `${authors[0]} et al. (${authors.length} authors)`
  }

  return (
    <div className="bg-white dark:bg-slate-900 rounded-lg shadow-lg max-w-6xl mx-auto relative text-gray-900 dark:text-slate-100 border border-gray-100 dark:border-slate-800">
      {/* Header */}
      <div className="p-6 border-b border-gray-200 dark:border-slate-800">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-slate-100">Discover Research Papers</h2>
          {onClose && (
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-700 dark:text-slate-400 dark:hover:text-slate-200"
            >
              ×
            </button>
          )}
        </div>

        {/* Mode Toggle */}
        {!forcePaperMode && (
          <div className="mb-3 flex items-center gap-2">
            <button
              className={`px-3 py-1.5 rounded ${mode==='query' ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-800 dark:bg-slate-800 dark:text-slate-100'}`}
              onClick={() => setMode('query')}
            >Query</button>
            <button
              className={`px-3 py-1.5 rounded ${mode==='paper' ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-800 dark:bg-slate-800 dark:text-slate-100'}`}
              onClick={() => setMode('paper')}
            >Paper</button>
          </div>
        )}

        {/* Search Form */}
        <div className="space-y-4">
          {/* Top inputs differ by mode */}
          {(!forcePaperMode && mode === 'query') ? (
            <div className="flex space-x-2">
              <div className="flex-1">
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                  placeholder="Search for research papers..."
                  className="w-full px-4 py-2 border border-gray-300 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100 placeholder:text-gray-400 dark:placeholder:text-slate-500"
                />
              </div>
              <button
                onClick={handleSearch}
                disabled={isSearching || !canSearch()}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 flex items-center space-x-2"
              >
                <Search size={16} />
                <span>{isSearching ? 'Searching...' : 'Search'}</span>
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {paperIdProp ? (
                <div className="flex items-center gap-4 flex-wrap">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="radio"
                      checked={paperModeSource==='current'}
                      onChange={() => setPaperModeSource('current')}
                    /> Use current paper context
                  </label>
                  {paperModeSource==='current' && (
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={includeContent}
                        onChange={(e) => setIncludeContent(e.target.checked)}
                      /> Include full content
                    </label>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={async () => {
                        setSourceError(null)
                        setSourceLoading(true)
                        setShowSourcePicker(true)
                        setSelectedSourcePaperTemp(sourcePaperId)
                        setSelectedSourcePaperTitleTemp(sourcePaperTitle)
                        try {
                          const resp = await fetch(buildApiUrl('/research-papers/?skip=0&limit=100'), {
                            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
                          })
                          if (resp.ok) {
                            const data = await resp.json()
                            const items = (data.papers || []).map((p: any) => ({ id: p.id, title: p.title, year: p.year, status: p.status }))
                            setSourcePapers(items)
                          } else {
                            setSourcePapers([])
                            setSourceError('Failed to load your papers.')
                          }
                        } catch (e) {
                          setSourceError('Failed to load your papers.')
                          setSourcePapers([])
                        } finally {
                          setSourceLoading(false)
                        }
                      }}
                      className="px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
                    >
                      {sourcePaperId ? 'Change Paper' : 'Choose Paper'}
                    </button>
                    {sourcePaperId && (
                      <span className="text-sm text-gray-700 truncate max-w-[60%]" title={sourcePaperTitle || ''}>
                        Using: {sourcePaperTitle || 'selected paper'}
                      </span>
                    )}
                    <label className="ml-auto flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={includeContent}
                        onChange={(e) => setIncludeContent(e.target.checked)}
                      /> Include full content
                    </label>
                  </div>
                </div>
              )}
              {/* Research topic/context is available below; hide paste-text and bias keywords in paper mode */}
              {mode === 'query' && (
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                  placeholder="Optional keywords to bias search"
                  className="w-full px-4 py-2 border border-gray-300 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100 placeholder:text-gray-400 dark:placeholder:text-slate-500"
                />
              )}
              <div>
                <button
                  onClick={handleSearch}
                  disabled={isSearching || !canSearch()}
                  className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 flex items-center space-x-2"
                >
                  <Search size={16} />
                  <span>{isSearching ? 'Searching...' : 'Find similar papers'}</span>
                </button>
      </div>
    </div>

          )}

          <div className="flex space-x-2">
            <div className="flex-1">
              <input
                type="text"
                value={researchTopic}
                onChange={(e) => setResearchTopic(e.target.value)}
                placeholder="Research topic/context (optional - improves relevance)"
                className="w-full px-4 py-2 border border-gray-300 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100 placeholder:text-gray-400 dark:placeholder:text-slate-500"
              />
            </div>
            <button
              onClick={handleSearch}
              disabled={isSearching || !canSearch()}
              className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:bg-gray-400 flex items-center space-x-2"
            >
              <Search size={16} />
              <span>{isSearching ? 'Searching...' : 'Run Discovery'}</span>
            </button>
          </div>

          {/* Advanced Options */}
          <div className="bg-gray-50 dark:bg-slate-800/70 border border-gray-100 dark:border-slate-700 p-4 rounded-lg">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Sources */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-slate-200 mb-2">Sources</label>
                <div className="space-y-1 text-gray-800 dark:text-slate-100">
                  {availableSources.map(source => (
                    <label key={source.id} className="flex items-center">
                      <input
                        type="checkbox"
                        checked={selectedSources.includes(source.id)}
                        onChange={() => handleSourceToggle(source.id)}
                        className="mr-2 rounded"
                      />
                      <span className="text-sm">{source.name}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Max Results */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-slate-200 mb-2">Max Results</label>
                <select
                  value={maxResults}
                  onChange={(e) => setMaxResults(Number(e.target.value))}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100"
                >
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={30}>30</option>
                  <option value={50}>50</option>
                </select>
              </div>

              {/* Year Filter */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-slate-200 mb-2">Year Filter</label>
                <select
                  value={filterByYear || ''}
                  onChange={(e) => setFilterByYear(e.target.value ? Number(e.target.value) : null)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100"
                >
                  <option value="">All years</option>
                  <option value={2024}>2024+</option>
                  <option value={2020}>2020+</option>
                  <option value={2015}>2015+</option>
                  <option value={2010}>2010+</option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Results Header */}
      {papers.length > 0 && (
        <div className="p-4 bg-gray-50 dark:bg-slate-800/70 border-b border-gray-200 dark:border-slate-800">
          <div className="flex justify-between items-center">
            <div className="text-sm text-gray-600 dark:text-slate-200">
              Found {getSortedAndFilteredPapers().length} / {papers.length} papers in {searchTime.toFixed(2)}s{relevanceThreshold !== null ? ` (≥ ${relevanceThreshold.toFixed(1)} relevance)` : ''}
            </div>
            <div className="flex items-center gap-3">
              <ArrowUpDown size={16} className="text-gray-400 dark:text-slate-400" />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'relevance' | 'year' | 'citations')}
                className="rounded-md border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-sm text-gray-700 dark:text-slate-100 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="relevance">Relevance</option>
                <option value="year">Year</option>
                <option value="citations">Citations</option>
              </select>
              <select
                value={relevanceThreshold === null ? '' : String(relevanceThreshold)}
                onChange={(e) => {
                  const val = e.target.value
                  setRelevanceThreshold(val === '' ? null : parseFloat(val))
                }}
                className="rounded-md border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-sm text-gray-700 dark:text-slate-100 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                title="Filter by minimum relevance score"
              >
                <option value="">All relevance</option>
                <option value="0.3">≥ 0.3</option>
                <option value="0.5">≥ 0.5</option>
                <option value="0.7">≥ 0.7</option>
              </select>
              <div className="flex items-center gap-2">
                <input
                  id="pdfOnly"
                  type="checkbox"
                  checked={pdfOnly}
                  onChange={(e) => setPdfOnly(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <label htmlFor="pdfOnly" className="text-sm text-gray-700 dark:text-slate-200">PDF only</label>
              </div>
              <button
                onClick={handleLoadMore}
                disabled={isLoadingMore}
                className={`inline-flex items-center rounded-md px-3 py-1.5 text-sm font-medium shadow-sm ring-1 ring-inset ${
                  isLoadingMore
                    ? 'bg-gray-100 text-gray-500 ring-gray-200 cursor-not-allowed dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-700'
                    : 'bg-white text-gray-700 ring-gray-300 hover:bg-gray-50 dark:bg-slate-800 dark:text-slate-100 dark:ring-slate-700 dark:hover:bg-slate-700'
                }`}
              >
                {isLoadingMore && <Clock className="animate-spin h-4 w-4 text-blue-600 mr-2" />}
                More papers
              </button>
              <button
                onClick={handleDeepRescore}
                disabled={deepRescoring}
                className={`inline-flex items-center rounded-md px-3 py-1.5 text-sm font-medium shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ${deepRescoring ? 'bg-gray-300 text-gray-600 cursor-not-allowed' : 'bg-blue-600 text-white hover:bg-blue-700 focus-visible:outline-blue-600'}`}
                title="Use PDF content (when available) to refine top results"
              >
                {deepRescoring ? 'Rescoring…' : 'Deep Rescore PDFs'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      <div className="overflow-visible">
        {isSearching && papers.length === 0 ? (
          <div className="flex items-center justify-center p-12">
            <div className="text-center">
              <Clock className="animate-spin h-8 w-8 text-blue-600 mx-auto mb-2" />
              <p className="text-gray-600 dark:text-slate-200">Searching multiple academic databases...</p>
            </div>
          </div>
        ) : papers.length === 0 ? (
          <div className="text-center p-12">
            <BookOpen className="h-12 w-12 text-gray-400 dark:text-slate-400 mx-auto mb-4" />
            <p className="text-gray-600 dark:text-slate-200">{hasSearched ? 'No papers found. Try different keywords or sources.' : 'Enter a search query to discover papers'}</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-200 dark:divide-slate-800">
            {getSortedAndFilteredPapers().map((paper, index) => {
              const paperId = `${paper.title}-${paper.source}`
              const isAdding = addingPapers.has(paperId)
              const isAdded = addedPapers.has(paperId)

              return (
                <div key={index} className="p-6 hover:bg-gray-50 dark:hover:bg-slate-800/60">
                  <div className="flex justify-between items-start">
                    <div className="flex-1 min-w-0">
                      {/* Title and Source */}
                      <div className="flex items-start justify-between mb-2">
                        <div className="pr-4">
                          <h3 className="text-lg font-semibold text-gray-900 dark:text-slate-100 leading-tight">
                            {paper.title}
                          </h3>
                      <div className="mt-1 flex items-center gap-2">
                        {(paper as any).is_open_access && (
                          <span className="px-2 py-0.5 text-xs bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200 rounded">OA</span>
                        )}
                        {!(paper as any).pdf_url && (
                          <span className="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 dark:bg-slate-800 dark:text-slate-200 rounded">No PDF found</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center space-x-1 text-xs text-gray-500 flex-shrink-0">
                      <span>{getSourceIcon(paper.source)}</span>
                          <span className="capitalize">{paper.source.replace('_', ' ')}</span>
                        </div>
                      </div>

                      {/* Authors and Year */}
                      <div className="flex items-center text-sm text-gray-600 dark:text-slate-200 mb-2 space-x-4">
                        <div className="flex items-center">
                          <Users size={14} className="mr-1" />
                          {formatAuthors(paper.authors)}
                        </div>
                        {paper.year && (
                          <div className="flex items-center">
                            <Calendar size={14} className="mr-1" />
                            {paper.year}
                          </div>
                        )}
                        {paper.citations_count !== null && paper.citations_count !== undefined && (
                          <div className="flex items-center">
                            <TrendingUp size={14} className="mr-1" />
                            {paper.citations_count} citations
                          </div>
                        )}
                      </div>

                      {/* Relevance Score (calibrated for display) */}
                      <div className="flex items-center mb-3">
                        {(() => {
                          const list = getSortedAndFilteredPapers()
                          const maxScore = list.reduce((m, p) => Math.max(m, p.relevance_score ?? 0), 0)
                          const raw = paper.relevance_score ?? 0
                          // Map raw to display: top maps to ~0.9, preserve order
                          const display = maxScore > 0 ? (0.9 * (raw / maxScore)) : raw
                          const pct = Math.round(display * 100)
                          const bar = Math.max(2, Math.min(100, pct))
                          return (
                            <>
                              <div className="flex items-center">
                                <Star size={14} className="text-yellow-500 mr-1" />
                                <span className="text-sm font-medium text-gray-700 dark:text-slate-200">
                                  Relevance: {pct}%
                                </span>
                              </div>
                              <div className="ml-2 flex-1 bg-gray-200 dark:bg-slate-700 rounded-full h-2 max-w-20">
                                <div
                                  className="bg-yellow-500 h-2 rounded-full"
                                  style={{ width: `${bar}%` }}
                                />
                              </div>
                            </>
                          )
                        })()}
                      </div>

                      {/* Abstract */}
                      <p className="text-sm text-gray-600 dark:text-slate-200 mb-3 leading-relaxed">
                        {paper.abstract.length > 300 
                          ? `${paper.abstract.substring(0, 300)}...`
                          : paper.abstract
                        }
                      </p>

                      {/* Keywords */}
                      {paper.keywords && paper.keywords.length > 0 && (
                        <div className="flex flex-wrap gap-1 mb-3">
                          {paper.keywords.slice(0, 5).map((keyword, idx) => (
                            <span
                              key={idx}
                              className="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded-full"
                            >
                              {keyword}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Journal */}
                      {paper.journal && (
                        <p className="text-sm text-gray-500 dark:text-slate-300 italic mb-3">{paper.journal}</p>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex flex-col space-y-2 ml-4">
                      <button
                        onClick={() => handleAddToLibrary(paper)}
                        disabled={isAdding || isAdded}
                        className={`flex items-center px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                          isAdded
                            ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200 cursor-not-allowed'
                            : isAdding
                            ? 'bg-gray-100 text-gray-400 dark:bg-slate-800 dark:text-slate-400 cursor-not-allowed'
                            : 'bg-blue-100 text-blue-800 hover:bg-blue-200 dark:bg-blue-900/40 dark:text-blue-100 dark:hover:bg-blue-800/60'
                        }`}
                      >
                        {isAdded ? (
                          <>
                            <CheckCircle size={14} className="mr-1" />
                            Added
                          </>
                        ) : isAdding ? (
                          <>
                            <Clock size={14} className="mr-1 animate-spin" />
                            Adding...
                          </>
                        ) : (
                          <>
                            <Plus size={14} className="mr-1" />
                            Add to My References
                          </>
                        )}
                      </button>
                      <button
                        onClick={() => handleAddPaper(paper)}
                        className="flex items-center px-3 py-2 bg-indigo-100 text-indigo-800 rounded-lg text-sm font-medium hover:bg-indigo-200 transition-colors dark:bg-indigo-900/40 dark:text-indigo-100 dark:hover:bg-indigo-800/60"
                      >
                        <Plus size={14} className="mr-1" />
                        Attach to Paper
                      </button>

                      {(paper as any).pdf_url && (
                        <button
                          onClick={() => window.open((paper as any).pdf_url, '_blank', 'noopener,noreferrer')}
                          className="flex items-center px-3 py-2 bg-blue-100 text-blue-800 rounded-lg text-sm font-medium hover:bg-blue-200 transition-colors dark:bg-blue-900/40 dark:text-blue-100 dark:hover:bg-blue-800/60"
                        >
                          <ExternalLink size={14} className="mr-1" />
                          View PDF
                        </button>
                      )}
                      <div className="text-xs text-gray-600 dark:text-slate-300 max-w-[16rem]">
                        {(paper as any).pdf_url
                          ? 'Attach to Paper for improved relevance using the PDF content.'
                          : 'Upload a PDF to improve relevance scoring and enable chat.'}
                      </div>

                      {paper.url && (
                        <a
                          href={paper.url}
                          target="_blank"
                          rel="noopener noreferrer"
                className="flex items-center px-3 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
              >
                <ExternalLink size={14} className="mr-1" />
                View
              </a>
                      )}
                      {/* Ingest button removed; ingestion happens automatically on reference creation */}
                    </div>
                  </div>
                </div>
              )
            })}
            {isLoadingMore && (
              <div className="py-6 flex items-center justify-center text-sm text-gray-600">
                <Clock className="animate-spin h-5 w-5 text-blue-600 mr-2" />
                Searching for more papers...
              </div>
            )}
          </div>
        )}
      </div>

      {/* Floating "More papers" button (visible while scrolling) */}
      {papers.length > 0 && (
        <button
          onClick={handleLoadMore}
          disabled={isLoadingMore}
          className={`fixed bottom-6 right-6 z-50 inline-flex items-center rounded-full px-4 py-2 text-sm font-medium shadow-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ${isLoadingMore ? 'bg-gray-200 text-gray-600 cursor-not-allowed' : 'bg-blue-600 text-white hover:bg-blue-700 focus-visible:outline-blue-600'}`}
          title="Load more papers"
        >
          {isLoadingMore && <Clock className="animate-spin h-4 w-4 mr-2" />}
          More papers
        </button>
      )}

      {/* Select Paper Modal */}
      {showSelectPaper && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-slate-900 rounded-lg w-full max-w-lg overflow-hidden">
            <div className="p-4 border-b border-gray-200 dark:border-slate-800 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-slate-100">Add to Paper</h3>
              <button className="text-gray-400 hover:text-gray-600 text-xl dark:text-slate-400 dark:hover:text-slate-200" onClick={() => setShowSelectPaper(false)}>×</button>
            </div>
            <div className="p-4 space-y-3 max-h-[60vh] overflow-y-auto">
              {myPapers.length === 0 ? (
                <p className="text-sm text-gray-600 dark:text-slate-300">No papers found. Create a paper first.</p>
              ) : (
                myPapers.map((p) => (
                  <label key={p.id} className="flex items-center gap-2 text-gray-800 dark:text-slate-100">
                    <input
                      type="checkbox"
                      checked={selectedTargetPapers.has(p.id)}
                      onChange={(e) => {
                        setSelectedTargetPapers(prev => {
                          const s = new Set(prev)
                          if (e.target.checked) s.add(p.id); else s.delete(p.id)
                          return s
                        })
                      }}
                    />
                    <span className="text-sm">{p.title}</span>
                  </label>
                ))
              )}
              {attachCandidate && (
                <div className="mt-3 text-xs text-gray-500 dark:text-slate-300">
                  Adding reference: <span className="font-medium">{attachCandidate.title}</span>
                </div>
              )}
              <div className="text-xs text-gray-600 dark:text-slate-300 mt-2">
                {(attachCandidate as any)?.pdf_url ? (
                  <span className="text-green-700">PDF available — a verified PDF will be attached.</span>
                ) : (
                  <div className="space-y-2">
                    <p className="text-gray-700 dark:text-slate-200">
                      No verified PDF found. You can attach this reference now and optionally upload a PDF to improve relevance score and enable knowledge‑base answers for the selected paper.
                    </p>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        className="px-3 py-1.5 bg-purple-600 text-white rounded disabled:opacity-50"
                        disabled={uploadingPdf || selectedTargetPapers.size !== 1}
                        onClick={() => {
                          setUploadStatus(null)
                          if (selectedTargetPapers.size !== 1) {
                            alert('Select exactly one paper to upload a PDF to its knowledge base.')
                            return
                          }
                          fileInputRef.current?.click()
                        }}
                      >
                        {uploadingPdf ? 'Uploading…' : 'Upload PDF to selected paper'}
                      </button>
                      <span className="text-[11px] text-gray-500 dark:text-slate-400">
                        Select exactly one paper to upload.
                      </span>
                    </div>
                    {uploadStatus && (
                      <div className="text-[11px] text-gray-700 dark:text-slate-200">{uploadStatus}</div>
                    )}
                  </div>
                )}
              </div>
            </div>
            <div className="p-4 border-t border-gray-200 dark:border-slate-800 flex justify-end gap-2">
              <button className="px-3 py-1 bg-gray-200 dark:bg-slate-800 dark:text-slate-100 rounded" onClick={() => setShowSelectPaper(false)}>Cancel</button>
              <button
                className="px-3 py-1 bg-blue-600 text-white rounded disabled:opacity-50"
                disabled={selectedTargetPapers.size === 0}
                onClick={async () => {
                  if (!attachCandidate) return
                  try {
                    const refs = Array.from(selectedTargetPapers)
                    const payloadBase = {
                      title: attachCandidate.title,
                      authors: attachCandidate.authors || [],
                      year: attachCandidate.year,
                      doi: attachCandidate.doi,
                      url: attachCandidate.url,
                      source: attachCandidate.source,
                      journal: attachCandidate.journal,
                      abstract: attachCandidate.abstract,
                      is_open_access: (attachCandidate as any).is_open_access || false,
                      pdf_url: (attachCandidate as any).pdf_url || undefined,
                    }
                    for (const pid of refs) {
                      await referencesAPI.create({ ...payloadBase, paper_id: pid })
                    }
                    alert(`Attached to ${refs.length} paper(s) and saved in My References.`)
                    setShowSelectPaper(false)
                    setSelectedTargetPapers(new Set())
                    setAttachCandidate(null)
                  } catch (e) {
                    console.error('Failed to attach references', e)
                    alert('Failed to attach references.')
                  }
                }}
              >
                Attach Reference(s)
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Source Paper Picker Modal */}
      {showSourcePicker && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 max-w-3xl w-full rounded-lg shadow-xl">
            <div className="p-4 border-b border-gray-200 dark:border-slate-800 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-slate-100">Choose a Paper</h3>
              <button className="text-gray-500 dark:text-slate-400" onClick={() => setShowSourcePicker(false)}>×</button>
            </div>
            <div className="p-4 space-y-3 max-h-[70vh] overflow-y-auto">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={sourceFilter}
                  onChange={(e) => setSourceFilter(e.target.value)}
                  placeholder="Search by title or year..."
                  className="w-full px-3 py-2 border border-gray-300 dark:border-slate-700 rounded bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100"
                />
                {selectedSourcePaperTemp && (
                  <button
                    className="px-2 py-1 text-sm text-gray-600 hover:text-gray-800 dark:text-slate-300 dark:hover:text-slate-100"
                    onClick={() => { setSelectedSourcePaperTemp(null); setSelectedSourcePaperTitleTemp(null) }}
                  >
                    Clear
                  </button>
                )}
              </div>

              {sourceLoading ? (
                <div className="py-12 text-center text-gray-600 dark:text-slate-300">Loading your papers...</div>
              ) : sourceError ? (
                <div className="py-8 text-center text-red-400 text-sm">{sourceError}</div>
              ) : sourcePapers.length === 0 ? (
                <div className="py-12 text-center text-gray-600 dark:text-slate-300">
                  No papers found. Create a paper first from the Projects page.
                </div>
              ) : (
                <ul className="divide-y divide-gray-200 dark:divide-slate-800">
                  {sourcePapers
                    .filter(p => {
                      const q = sourceFilter.trim().toLowerCase()
                      if (!q) return true
                      return (p.title || '').toLowerCase().includes(q) || String(p.year || '').includes(q)
                    })
                    .map((p) => (
                      <li
                        key={p.id}
                        className={`p-3 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-slate-800 cursor-pointer ${selectedSourcePaperTemp === p.id ? 'bg-blue-50 dark:bg-slate-800/70' : ''}`}
                        onClick={() => { setSelectedSourcePaperTemp(p.id); setSelectedSourcePaperTitleTemp(p.title) }}
                      >
                        <div className="flex items-center gap-3 pr-4 min-w-0">
                          <input
                            type="radio"
                            checked={selectedSourcePaperTemp === p.id}
                            onChange={() => { setSelectedSourcePaperTemp(p.id); setSelectedSourcePaperTitleTemp(p.title) }}
                          />
                          <div className="min-w-0">
                            <div className="truncate font-medium text-gray-900 dark:text-slate-100" title={p.title}>{p.title}</div>
                            <div className="mt-1 text-xs text-gray-600 dark:text-slate-300 flex items-center gap-2">
                              {p.year && <span className="px-1.5 py-0.5 bg-gray-100 dark:bg-slate-800 rounded">{p.year}</span>}
                              {p.status && <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200 rounded capitalize">{p.status.replace('_',' ')}</span>}
                            </div>
                          </div>
                        </div>
                      </li>
                    ))}
                </ul>
              )}
            </div>
            <div className="p-4 border-t border-gray-200 dark:border-slate-800 flex justify-end gap-2">
              <button className="px-3 py-1 text-gray-600 dark:text-slate-300" onClick={() => setShowSourcePicker(false)}>Cancel</button>
              <button
                className="px-3 py-1 bg-blue-600 text-white rounded disabled:opacity-50"
                disabled={!selectedSourcePaperTemp}
                onClick={() => {
                  if (selectedSourcePaperTemp) {
                    setSourcePaperId(selectedSourcePaperTemp)
                    setSourcePaperTitle(selectedSourcePaperTitleTemp || null)
                    setShowSourcePicker(false)
                  }
                }}
              >
                Use selected
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Hidden file input for PDF upload in modal */}
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        hidden
        onChange={async (e) => {
          const file = e.target.files?.[0]
          if (!file || !attachCandidate) return
          const selected = Array.from(selectedTargetPapers)
          if (selected.length !== 1) {
            alert('Please select exactly one target paper.')
            return
          }
          const paperIdTarget = selected[0]
          setUploadingPdf(true)
          setUploadStatus(null)
          try {
            const fd = new FormData()
            fd.append('file', file)
            fd.append('title', attachCandidate.title || file.name)
            fd.append('paper_id', paperIdTarget)
            // Optional: tags left empty
            const resp = await fetch(buildApiUrl('/documents/upload'), {
              method: 'POST',
              headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` },
              body: fd
            })
            if (resp.status === 409) {
              const detail = await resp.json().catch(() => ({} as any))
              const dupTitle = detail?.duplicate_document?.title || 'existing document'
              setUploadStatus(`A matching PDF already exists (${dupTitle}). It is already usable for relevance and knowledge‑base answers.`)
              return
            }
            if (!resp.ok) {
              const text = await resp.text()
              throw new Error(`${resp.status} ${resp.statusText}: ${text}`)
            }
            setUploadStatus('PDF uploaded and processing. It will improve relevance and enable knowledge‑base answers for this paper.')
          } catch (err) {
            console.error('Upload failed', err)
            setUploadStatus('Upload failed. Please try again or attach reference without a PDF.')
          } finally {
            setUploadingPdf(false)
            if (fileInputRef.current) fileInputRef.current.value = ''
          }
        }}
      />

      {/* Paper Content Modal */}
      {selectedPaper && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-slate-900 rounded-lg max-w-4xl max-h-[90vh] w-full overflow-hidden">
            <div className="p-6 border-b border-gray-200 dark:border-slate-800 flex justify-between items-start">
              <div>
                <h3 className="text-xl font-bold text-gray-900 dark:text-slate-100 mb-2">{selectedPaper.title}</h3>
                <div className="flex items-center text-sm text-gray-600 dark:text-slate-300">
                  <span className="mr-4">Source: {selectedPaper.source}</span>
                  {selectedPaper.year && <span>Year: {selectedPaper.year}</span>}
                </div>
              </div>
              <button
                onClick={() => {
                  setSelectedPaper(null)
                  setViewingContent({})
                }}
                className="text-gray-400 hover:text-gray-600 text-2xl font-bold dark:text-slate-400 dark:hover:text-slate-200"
              >
                ×
              </button>
            </div>
            
            <div className="p-6 overflow-y-auto max-h-[70vh] text-gray-900 dark:text-slate-100">
              {(() => {
                const paperKey = `${selectedPaper.title}-${selectedPaper.source}`
                const content = viewingContent[paperKey]

                if (content === 'loading') {
                  return (
                    <div className="flex items-center justify-center py-12">
                      <Clock size={24} className="animate-spin mr-3" />
                      Loading content...
                    </div>
                  )
                }

                if (!content || (content as any)?.error) {
                  return (
                    <div className="text-center py-12">
                      <p className="text-red-600 mb-4">Failed to load content</p>
                      <button
                        onClick={() => handleViewContent(selectedPaper)}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                      >
                        Try Again
                      </button>
                    </div>
                  )
                }

                if (Array.isArray((content as any).chunks)) {
                  const chunks = (content as any).chunks as Array<{ chunk_index: number; text: string }>
                  return (
                    <div className="space-y-3">
                      <div className="text-sm text-gray-600">Showing ingested content ({chunks.length} chunks)</div>
                      <div className="bg-gray-50 p-4 rounded border max-h-[60vh] overflow-y-auto">
                        {chunks.slice(0, 20).map((chunk, idx) => (
                          <p key={idx} className="mb-3 text-gray-800 whitespace-pre-wrap">{chunk.text}</p>
                        ))}
                        {chunks.length > 20 && (
                          <div className="text-xs text-gray-500">Showing first 20 chunks…</div>
                        )}
                      </div>
                    </div>
                  )
                }

                const contentType = (content as any)?.content_type

                if (contentType === 'pdf' || contentType === 'authenticated_access') {
                  return (
                    <div className="text-center space-y-4">
                      <BookOpen size={48} className="mx-auto text-blue-600" />
                      <p className="text-gray-600">This is a PDF document</p>

                      {(content as any)?.error && (content as any).error.includes('demonstration only') && (
                        <div className="p-3 bg-orange-100 border border-orange-300 rounded-lg text-sm text-orange-800">
                          <strong>⚠️ Alternative Access:</strong> {(content as any).error}
                        </div>
                      )}

                      {contentType === 'authenticated_access' && (
                        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-left space-y-3">
                          <div className="flex items-start space-x-3">
                            <span className="text-2xl">🏫</span>
                            <div className="space-y-2">
                              <h4 className="font-semibold text-blue-900">KFUPM University Access Available</h4>
                              <p className="text-blue-800">
                                This paper is available through your KFUPM subscription. Access it using your university credentials:
                              </p>
                              <div className="space-y-2">
                                {(content as any)?.sso_url && (content as any).sso_url.includes('kfupm.edu.sa') ? (
                                  <button
                                    onClick={() => window.open((content as any).sso_url, '_blank', 'noopener,noreferrer')}
                                    className="px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
                                  >
                                    🔗 Open KFUPM Library Portal
                                  </button>
                                ) : (content as any)?.sso_url ? (
                                  <div className="space-x-2">
                                    <button
                                      onClick={() => window.open((content as any).sso_url, '_blank', 'noopener,noreferrer')}
                                      className="px-4 py-2 bg-green-600 text-white text-sm rounded hover:bg-green-700"
                                    >
                                      🎯 Direct KFUPM Access
                                    </button>
                                    <button
                                      onClick={() => window.open('https://library-web.kfupm.edu.sa/e-resources/online-databases/', '_blank', 'noopener,noreferrer')}
                                      className="px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
                                    >
                                      📚 KFUPM Library Portal
                                    </button>
                                  </div>
                                ) : null}
                              </div>
                              <div className="text-xs text-blue-700 space-y-1">
                                <p><strong>Steps:</strong></p>
                                <p>1. Click the button above to access through KFUPM</p>
                                <p>2. Login with your KFUPM credentials (g202403940@kfupm.edu.sa)</p>
                                <p>3. Search for the paper or navigate to the publisher's database</p>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      <a
                        href={(content as any).pdf_url || selectedPaper.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                      >
                        <ExternalLink size={16} className="mr-2" />
                        Open PDF
                      </a>

                      {(content as any)?.error && (content as any).error.includes('demonstration only') && (
                        <p className="text-xs text-gray-500">
                          This link is for demonstration purposes only. In production, use legal institutional access.
                        </p>
                      )}
                    </div>
                  )
                }

                const fullText = (content as any)?.full_text

                return (
                  <div className="prose max-w-none">
                    {fullText && (
                      <div className="bg-gray-50 p-4 rounded-lg mb-4">
                        <h4 className="font-semibold mb-2">Content Preview:</h4>
                        <p className="text-gray-700 whitespace-pre-wrap">{fullText}</p>
                      </div>
                    )}

                    <div className="mt-4 pt-4 border-t">
                      <a
                        href={selectedPaper.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                      >
                        <ExternalLink size={16} className="mr-2" />
                        View Full Paper
                      </a>
                    </div>
                  </div>
                )
              })()}
            </div>
          </div>
        </div>
      )}


      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 rounded shadow-lg px-4 py-3 text-sm ${
            toast.type === 'success'
              ? 'bg-green-600 text-white'
              : toast.type === 'error'
              ? 'bg-red-600 text-white'
              : 'bg-gray-900 text-white'
          }`}
        >
          {toast.message}
        </div>
      )}
    </div>
  )
}

export default PaperDiscovery
