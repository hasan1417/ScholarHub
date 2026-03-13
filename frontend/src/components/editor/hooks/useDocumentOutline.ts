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

// Environments that appear as outline landmarks
const ENV_RE = /\\begin\{(abstract|document)\}/g

const LEVEL_MAP = new Map(SECTION_COMMANDS)

export function parseOutline(doc: string): OutlineEntry[] {
  const entries: OutlineEntry[] = []
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
    return lo + 1
  }

  const isCommented = (offset: number): boolean => {
    const lineStart = lineStarts[getLine(offset) - 1]
    return doc.slice(lineStart, offset).includes('%')
  }

  // Detect \begin{abstract} and \begin{document} as outline landmarks
  ENV_RE.lastIndex = 0
  let envMatch: RegExpExecArray | null
  while ((envMatch = ENV_RE.exec(doc)) !== null) {
    if (isCommented(envMatch.index)) continue
    const envName = envMatch[1]
    entries.push({
      level: envName === 'document' ? 0 : 2,
      title: envName.charAt(0).toUpperCase() + envName.slice(1),
      line: getLine(envMatch.index),
      from: envMatch.index,
      command: `begin{${envName}}`,
    })
  }

  SECTION_RE.lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = SECTION_RE.exec(doc)) !== null) {
    if (isCommented(match.index)) continue
    const command = match[1]
    const level = LEVEL_MAP.get(command) ?? 2
    const title = match[2].trim()
    entries.push({ level, title, line: getLine(match.index), from: match.index, command })
  }

  entries.sort((a, b) => a.from - b.from)
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
