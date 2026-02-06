import { useEffect, useRef, useState } from 'react'
import type { EditorView } from '@codemirror/view'

export interface OutlineEntry {
  level: number
  title: string
  line: number
  from: number
  command: string
}

const SECTION_COMMANDS: [string, number][] = [
  ['part', 0],
  ['chapter', 1],
  ['section', 2],
  ['subsection', 3],
  ['subsubsection', 4],
  ['paragraph', 5],
  ['subparagraph', 6],
]

// Regex: matches \section{Title}, \section*{Title}, etc.
// Handles nested braces one level deep inside the title.
const SECTION_RE = new RegExp(
  '\\\\(' +
    SECTION_COMMANDS.map(([cmd]) => cmd).join('|') +
  ')\\*?\\{((?:[^{}]|\\{[^{}]*\\})*)\\}',
  'g',
)

const LEVEL_MAP = new Map(SECTION_COMMANDS)

export function parseOutline(doc: string): OutlineEntry[] {
  const entries: OutlineEntry[] = []
  // Build a line offset lookup for fast line-number resolution
  const lineStarts: number[] = [0]
  for (let i = 0; i < doc.length; i++) {
    if (doc[i] === '\n') lineStarts.push(i + 1)
  }

  const getLine = (offset: number): number => {
    let lo = 0, hi = lineStarts.length - 1
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1
      if (lineStarts[mid] <= offset) lo = mid
      else hi = mid - 1
    }
    return lo + 1 // 1-indexed
  }

  SECTION_RE.lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = SECTION_RE.exec(doc)) !== null) {
    // Skip if inside a comment (check if line starts with %)
    const lineStart = lineStarts[getLine(match.index) - 1]
    const prefix = doc.slice(lineStart, match.index)
    if (prefix.includes('%')) continue

    const command = match[1]
    const level = LEVEL_MAP.get(command) ?? 2
    const title = match[2].trim()
    entries.push({
      level,
      title,
      line: getLine(match.index),
      from: match.index,
      command,
    })
  }

  return entries
}

interface UseDocumentOutlineOptions {
  viewRef: React.MutableRefObject<EditorView | null>
  enabled: boolean
}

export function useDocumentOutline({ viewRef, enabled }: UseDocumentOutlineOptions) {
  const [outline, setOutline] = useState<OutlineEntry[]>([])
  const lastDocRef = useRef<string>('')
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    if (!enabled) {
      setOutline([])
      lastDocRef.current = ''
      return
    }

    const check = () => {
      const view = viewRef.current
      if (!view) return
      const doc = view.state.doc.toString()
      if (doc === lastDocRef.current) return
      lastDocRef.current = doc

      // Debounce the parse
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
      }
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null
        setOutline(parseOutline(doc))
      }, 300)
    }

    // Initial parse
    check()

    // Poll every 500ms for changes
    const interval = window.setInterval(check, 500)

    return () => {
      window.clearInterval(interval)
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [enabled, viewRef])

  return { outline }
}
