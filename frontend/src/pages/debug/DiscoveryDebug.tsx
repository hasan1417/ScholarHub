import React, { useState } from 'react'
import { buildApiUrl } from '../../services/api'

type DiscoveredPaper = {
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
}

type DiscoveryResponse = {
  papers: DiscoveredPaper[]
  total_found: number
  query: string
  search_time: number
  sources_raw_counts?: Record<string, number>
  sources_unique_counts?: Record<string, number>
}

const DiscoveryDebug: React.FC = () => {
  const [query, setQuery] = useState('')
  const [sources, setSources] = useState<string[]>(['openalex', 'sciencedirect', 'arxiv', 'crossref'])
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<DiscoveryResponse | null>(null)
  const [endpointTests, setEndpointTests] = useState<Record<string, any>>({})
  const [error, setError] = useState<string | null>(null)

  const allSources = [
    { id: 'openalex', label: 'OpenAlex' },
    { id: 'sciencedirect', label: 'ScienceDirect' },
    { id: 'scopus', label: 'Scopus' },
    { id: 'arxiv', label: 'arXiv' },
    { id: 'crossref', label: 'Crossref' },
    { id: 'pubmed', label: 'PubMed' },
    { id: 'semantic_scholar', label: 'Semantic Scholar' },
  ]

  const toggleSource = (id: string) => {
    setSources(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id])
  }

  const runDiscovery = async () => {
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const resp = await fetch(buildApiUrl('/discovery/papers/discover'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({
          query: query.trim(),
          research_topic: null,
          max_results: 20,
          sources,
          include_breakdown: true
        })
      })
      if (!resp.ok) {
        const text = await resp.text()
        throw new Error(`${resp.status} ${resp.statusText}: ${text}`)
      }
      const data = await resp.json()
      setResult(data)
    } catch (e: any) {
      setError(e?.message || 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  const testEndpoint = async (source: string) => {
    if (!query.trim()) return
    try {
      const resp = await fetch(buildApiUrl('/discovery/debug/test-source'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({ source, query: query.trim(), limit: 5 })
      })
      const data = await resp.json()
      setEndpointTests(prev => ({ ...prev, [source]: data }))
    } catch (e) {
      setEndpointTests(prev => ({ ...prev, [source]: { error: 'Request failed' } }))
    }
  }

  const grouped = (result?.papers || []).reduce((acc: Record<string, DiscoveredPaper[]>, p) => {
    acc[p.source] = acc[p.source] || []
    acc[p.source].push(p)
    return acc
  }, {})

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Discovery Debug</h1>

      <div className="bg-white rounded border p-4 mb-6">
        <div className="flex gap-2 mb-3">
          <input
            className="flex-1 border rounded px-3 py-2"
            placeholder="Enter query..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && runDiscovery()}
          />
          <button
            onClick={runDiscovery}
            disabled={loading || !query.trim()}
            className="px-4 py-2 bg-blue-600 text-white rounded disabled:bg-gray-400"
          >
            {loading ? 'Running...' : 'Run'}
          </button>
        </div>

        <div className="flex flex-wrap gap-3">
          {allSources.map(s => (
            <label key={s.id} className="flex items-center gap-2">
              <input type="checkbox" checked={sources.includes(s.id)} onChange={() => toggleSource(s.id)} />
              <span>{s.label}</span>
            </label>
          ))}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded mb-4">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-6">
          <div className="bg-white rounded border p-4">
            <div className="text-sm text-gray-600">Query: <span className="font-mono">{result.query}</span> • Time: {result.search_time.toFixed(2)}s • Total: {result.total_found}</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
              <div>
                <h3 className="font-semibold mb-2">Raw Counts</h3>
                <pre className="bg-gray-50 p-2 rounded text-sm overflow-auto">{JSON.stringify(result.sources_raw_counts || {}, null, 2)}</pre>
              </div>
              <div>
                <h3 className="font-semibold mb-2">Unique Counts</h3>
                <pre className="bg-gray-50 p-2 rounded text-sm overflow-auto">{JSON.stringify(result.sources_unique_counts || {}, null, 2)}</pre>
              </div>
            </div>
          </div>

          <div className="bg-white rounded border p-4">
            <h3 className="font-semibold mb-3">Results by Source</h3>
            <div className="space-y-4">
              {Object.keys(grouped).sort().map(src => (
                <div key={src}>
                  <div className="font-medium text-gray-800 mb-2">{src} ({grouped[src].length})</div>
                  <ul className="list-disc ml-5 space-y-1">
                    {grouped[src].slice(0, 10).map((p, idx) => {
                      const anyp = p as any
                      return (
                        <li key={idx}>
                          <span className="font-semibold">{p.title}</span>{p.year ? ` (${p.year})` : ''} — <span className="text-gray-600">{p.journal || 'n/a'}</span>
                          {p.doi ? <span className="ml-2 text-xs text-gray-500">DOI: {p.doi}</span> : null}
                          {anyp.is_open_access ? <span className="ml-2 px-2 py-0.5 text-xs bg-green-100 text-green-800 rounded">OA</span> : null}
                          {anyp.pdf_url ? <a className="ml-2 text-xs text-blue-600" href={anyp.pdf_url} target="_blank" rel="noreferrer">PDF</a> : null}
                        </li>
                      )
                    })}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="bg-white rounded border p-4 mt-6">
        <h3 className="font-semibold mb-3">Endpoint Tests</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {allSources.map(s => (
            <div key={s.id} className="border rounded p-3">
              <div className="flex items-center justify-between mb-2">
                <div className="font-medium">{s.label}</div>
                <button className="px-3 py-1 text-sm bg-gray-800 text-white rounded" onClick={() => testEndpoint(s.id)}>Test</button>
              </div>
              <pre className="bg-gray-50 p-2 rounded text-xs overflow-auto" style={{maxHeight: 200}}>{JSON.stringify(endpointTests[s.id] || {}, null, 2)}</pre>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default DiscoveryDebug
