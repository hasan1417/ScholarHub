import { useCallback, useRef, useState } from 'react'
import { inflate } from 'pako'
import { buildApiUrl } from '../../../services/api'
import { parseSyncTex } from '../utils/synctexParser'
import type { SyncTeXData, SyncTeXElement } from '../utils/synctexParser'

interface ForwardSyncResult {
  page: number
  x: number
  y: number
}

interface BackwardSyncResult {
  line: number
  file: string
}

interface UseSyncTeXOptions {
  contentHash: string | null
  enabled: boolean
}

interface UseSyncTeXReturn {
  forwardSync: (line: number) => ForwardSyncResult | null
  backwardSync: (page: number, x: number, y: number) => BackwardSyncResult | null
  synctexReady: boolean
  loading: boolean
}

export function useSyncTeX({ contentHash, enabled }: UseSyncTeXOptions): UseSyncTeXReturn {
  const [synctexReady, setSynctexReady] = useState(false)
  const [loading, setLoading] = useState(false)
  const dataRef = useRef<SyncTeXData | null>(null)
  const lastHashRef = useRef<string | null>(null)

  // Fetch and parse synctex data when content hash changes
  const ensureLoaded = useCallback(async (): Promise<SyncTeXData | null> => {
    if (!enabled || !contentHash) return null
    if (contentHash === lastHashRef.current && dataRef.current) return dataRef.current

    setLoading(true)
    try {
      const url = buildApiUrl(`/latex/artifacts/${contentHash}/main.synctex.gz`)
      const token = localStorage.getItem('access_token') || ''
      const resp = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      })
      if (!resp.ok) {
        console.warn('[useSyncTeX] Failed to fetch synctex.gz:', resp.status)
        return null
      }

      const buffer = await resp.arrayBuffer()
      const decompressed = inflate(new Uint8Array(buffer))
      const text = new TextDecoder().decode(decompressed)

      const parsed = parseSyncTex(text)

      dataRef.current = parsed
      lastHashRef.current = contentHash
      setSynctexReady(true)
      return parsed
    } catch (err) {
      console.warn('[useSyncTeX] Failed to parse synctex:', err)
      dataRef.current = null
      setSynctexReady(false)
      return null
    } finally {
      setLoading(false)
    }
  }, [contentHash, enabled])

  const forwardSync = useCallback(
    (line: number): ForwardSyncResult | null => {
      // Trigger load if not ready, but return null synchronously
      const data = dataRef.current
      if (!data) {
        void ensureLoaded()
        return null
      }

      // Look up main.tex in blockNumberLine
      const bnl = data.blockNumberLine
      // Try "main.tex" first, then the first file entry
      const fileName =
        bnl['main.tex'] ? 'main.tex' : Object.keys(bnl)[0]
      if (!fileName || !bnl[fileName]) return null

      const lineMap = bnl[fileName]
      // Try exact line, then nearby lines within +-5
      let elements: SyncTeXElement[] | null = null
      for (let offset = 0; offset <= 10; offset++) {
        for (const delta of offset === 0 ? [0] : [-offset, offset]) {
          const tryLine = line + delta
          const pageMap = lineMap[tryLine]
          if (pageMap) {
            // Pick the first page with elements
            for (const pageNum of Object.keys(pageMap)) {
              const elems = pageMap[Number(pageNum)]
              if (elems && elems.length > 0) {
                elements = elems
                break
              }
            }
            if (elements) break
          }
        }
        if (elements) break
      }

      if (!elements || elements.length === 0) return null

      const el = elements[0]
      return {
        page: el.page,
        x: el.left + (data.offset?.x || 0),
        y: el.bottom - el.height + (data.offset?.y || 0),
      }
    },
    [ensureLoaded]
  )

  const backwardSync = useCallback(
    (page: number, x: number, y: number): BackwardSyncResult | null => {
      const data = dataRef.current
      if (!data) return null

      const offsetX = data.offset?.x || 0
      const offsetY = data.offset?.y || 0

      // Find the closest hBlock on this page
      let bestDist = Infinity
      let bestLine = -1
      let bestFile = 'main.tex'

      for (const block of data.hBlocks) {
        if (block.page !== page) continue
        const bx = block.left + offsetX
        const by = block.bottom - block.height + offsetY
        const dx = x - bx
        const dy = y - by
        const dist = dx * dx + dy * dy
        if (dist < bestDist) {
          bestDist = dist
          bestLine = block.line
          bestFile = block.file?.name || 'main.tex'
        }
      }

      if (bestLine < 0) return null
      return { line: bestLine, file: bestFile }
    },
    []
  )

  return { forwardSync, backwardSync, synctexReady, loading }
}
