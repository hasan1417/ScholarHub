import React, { useState } from 'react'
import { buildApiUrl } from '../../services/api'

type ResolveResp = {
  url: string
  pmc_url?: string
  pmcid?: string
  pdf_candidates?: string[]
  chosen_pdf?: string
  is_open_access?: boolean
  detail?: string
}

const PDFResolverDebug: React.FC = () => {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ResolveResp | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const resp = await fetch(buildApiUrl('/references/debug/resolve-pdf'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({ url })
      })
      const data = await resp.json()
      if (!resp.ok) {
        throw new Error(data?.detail || 'Failed to resolve')
      }
      setResult(data)
    } catch (e: any) {
      setError(e?.message || 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-bold">PDF Resolver Debug</h1>
      <div className="bg-white border rounded p-4 space-y-3">
        <input
          className="w-full border rounded px-3 py-2"
          placeholder="Enter PubMed/PMC/publisher URL"
          value={url}
          onChange={e => setUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && run()}
        />
        <button onClick={run} disabled={!url || loading} className="px-4 py-2 bg-blue-600 text-white rounded disabled:bg-gray-400">
          {loading ? 'Resolving…' : 'Resolve PDF'}
        </button>
      </div>
      {error && (<div className="bg-red-50 border border-red-200 text-red-700 p-3 rounded">{error}</div>)}
      {result && (
        <div className="bg-white border rounded p-4 space-y-3">
          <div className="text-sm">URL: <span className="font-mono">{result.url}</span></div>
          {result.pmc_url && <div className="text-sm">PMC URL: <a className="text-blue-600" href={result.pmc_url} target="_blank" rel="noreferrer">{result.pmc_url}</a></div>}
          {result.pmcid && <div className="text-sm">PMCID: <span className="font-mono">{result.pmcid}</span></div>}
          {result.chosen_pdf && <div className="text-sm">Chosen PDF: <a className="text-blue-600" href={result.chosen_pdf} target="_blank" rel="noreferrer">Open</a></div>}
          <div>
            <h3 className="font-semibold mb-1">Candidates</h3>
            <ul className="list-disc ml-5 text-sm space-y-1">
              {(result.pdf_candidates || []).map((c, i) => (
                <li key={i}><a className="text-blue-600" href={c} target="_blank" rel="noreferrer">{c}</a></li>
              ))}
            </ul>
          </div>
          <pre className="bg-gray-50 p-2 rounded text-xs overflow-auto">{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}

export default PDFResolverDebug
