// Lightweight telemetry utility
// Usage: logEvent('CompileStart', { ... })

import { buildApiUrl } from '../services/api'

export const ENABLE_METRICS = (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_ENABLE_METRICS === 'true')
const SAMPLE_RATE = (() => {
  const raw = (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_METRICS_SAMPLE_RATE) || '1'
  const n = parseFloat(raw as string)
  if (isNaN(n) || n <= 0) return 0
  if (n > 1) return 1
  return n
})()
const METRICS_ENDPOINT = (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_METRICS_ENDPOINT) || buildApiUrl('/metrics')

type Payload = Record<string, any>

function hashString(s: string): string {
  let h = 5381
  for (let i = 0; i < s.length; i++) h = (h * 33) ^ s.charCodeAt(i)
  return (h >>> 0).toString(16)
}

export async function logEvent(name: string, payload: Payload = {}): Promise<void> {
  if (!ENABLE_METRICS) return
  if (Math.random() > SAMPLE_RATE) return
  const appVersion = (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_APP_VERSION) || 'dev'
  const env = (typeof import.meta !== 'undefined' && (import.meta as any).env?.MODE) || 'development'
  const projectId = (payload.projectId || (typeof window !== 'undefined' && (window as any).__SH_ACTIVE_PAPER_ID)) || null
  const projectIdHash = projectId ? hashString(String(projectId)) : null
  const body = {
    ts: new Date().toISOString(),
    name,
    payload,
    buildId: payload.buildId,
    appVersion,
    env,
    projectIdHash,
    app: 'latex-editor',
    ver: 1,
  }

  try {
    // Prefer POST to backend; if it fails, fall back to console.warn
    await fetch(METRICS_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch (e) {
    try { console.warn('[metrics]', body) } catch {}
  }
}
