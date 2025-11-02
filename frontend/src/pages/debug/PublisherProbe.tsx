import React, { useState } from 'react'
import { buildApiUrl } from '../../services/api'

type ProviderLink = { provider: string; url: string }

type ProbeResponse = {
  target: string
  resolved_url?: string
  proxied_url?: string
  provider_search_urls?: ProviderLink[]
  proxy_fetch?: {
    status?: number
    final_url?: string
    content_type?: string
    html_title?: string | null
    sso_login_url?: string | null
    html_excerpt?: string | null
    error?: string
  }
  unpaywall?: {
    is_oa?: boolean
    oa_url?: string | null
    host_type?: string | null
  }
}

const PublisherProbe: React.FC = () => {
  const [doi, setDoi] = useState('')
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [withUnpaywall, setWithUnpaywall] = useState(true)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ProbeResponse | null>(null)

  // Optional local-only credential helpers (never sent to backend)
  const [kfupmUser, setKfupmUser] = useState<string>(() => localStorage.getItem('kfupm_user') || '')
  const [kfupmPass, setKfupmPass] = useState<string>(() => localStorage.getItem('kfupm_pass') || '')
  const saveCreds = () => {
    localStorage.setItem('kfupm_user', kfupmUser)
    localStorage.setItem('kfupm_pass', kfupmPass)
    alert('Saved locally (not sent to server).')
  }
  const clearCreds = () => {
    localStorage.removeItem('kfupm_user')
    localStorage.removeItem('kfupm_pass')
    setKfupmUser('')
    setKfupmPass('')
  }

  const runProbe = async () => {
    setLoading(true)
    setResult(null)
    try {
      const resp = await fetch(buildApiUrl('/discovery/debug/probe-publisher'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({ url: url || null, doi: doi || null, title: title || null, with_unpaywall: withUnpaywall })
      })
      const data = await resp.json()
      setResult(data)
    } catch (e) {
      setResult({ target: doi || url || '', proxy_fetch: { error: 'Request failed' } })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Publisher Probe (OA-only)</h1>

      <div className="bg-white border rounded p-4 space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">DOI</label>
            <input className="w-full border rounded px-3 py-2" value={doi} onChange={(e) => setDoi(e.target.value)} placeholder="10.xxxx/xxxxx" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
            <input className="w-full border rounded px-3 py-2" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://publisher/article" />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Title (for provider search)</label>
          <input className="w-full border rounded px-3 py-2" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Paper title (optional)" />
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={withUnpaywall} onChange={(e) => setWithUnpaywall(e.target.checked)} />
            Include Unpaywall (OA) lookup
          </label>
          <button onClick={runProbe} disabled={loading || (!doi && !url)} className="px-4 py-2 bg-blue-600 text-white rounded disabled:bg-gray-400">
            {loading ? 'Probing…' : 'Run Probe'}
          </button>
        </div>
      </div>

      <div className="bg-white border rounded p-4 space-y-3">
        <h2 className="font-semibold">Optional: KFUPM Credentials (Local Only)</h2>
        <p className="text-sm text-gray-600">Stored only in your browser for convenience. Not sent to our servers.</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input className="w-full border rounded px-3 py-2" placeholder="KFUPM username/email" value={kfupmUser} onChange={(e) => setKfupmUser(e.target.value)} />
          <input className="w-full border rounded px-3 py-2" placeholder="KFUPM password" type="password" value={kfupmPass} onChange={(e) => setKfupmPass(e.target.value)} />
        </div>
        <div className="flex gap-2">
          <button onClick={saveCreds} className="px-3 py-1 bg-gray-800 text-white rounded">Save Locally</button>
          <button onClick={clearCreds} className="px-3 py-1 bg-gray-200 rounded">Clear</button>
        </div>
      </div>

      {result && (
        <div className="bg-white border rounded p-4 space-y-4">
          <div className="text-sm text-gray-700">Target: <span className="font-mono">{result.target}</span></div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <h3 className="font-semibold mb-2">Resolution & OA</h3>
              <ul className="text-sm space-y-1">
                <li>Resolved URL: <a className="text-blue-600" href={result.resolved_url} target="_blank" rel="noreferrer">{result.resolved_url}</a></li>
                <li>Proxied URL: <a className="text-blue-600" href={result.proxied_url} target="_blank" rel="noreferrer">{result.proxied_url}</a></li>
                {result.unpaywall && (
                  <li>Unpaywall: {result.unpaywall.is_oa ? 'Open Access' : 'Not OA'} {result.unpaywall.oa_url && (<a className="text-blue-600 ml-2" href={result.unpaywall.oa_url || ''} target="_blank" rel="noreferrer">OA Link</a>)}</li>
                )}
              </ul>
            </div>
            <div>
              <h3 className="font-semibold mb-2">Provider Search (Proxied)</h3>
              <ul className="text-sm space-y-1">
                {(result.provider_search_urls || []).map((l) => (
                  <li key={l.url}><a className="text-blue-600" href={l.url} target="_blank" rel="noreferrer">{l.provider}</a></li>
                ))}
              </ul>
            </div>
          </div>
          <div>
            <h3 className="font-semibold mb-2">Proxied Page Summary</h3>
            <pre className="bg-gray-50 p-2 rounded text-xs overflow-auto" style={{maxHeight: 300}}>{JSON.stringify(result.proxy_fetch || {}, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  )
}

export default PublisherProbe
