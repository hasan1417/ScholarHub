import { useState, useEffect, useCallback, useRef, useLayoutEffect } from 'react'
import { ChevronDown } from 'lucide-react'
import type { EditorView } from '@codemirror/view'

interface SectionHeadingDropdownProps {
  editorViewRef: React.RefObject<EditorView | null>
}

interface HeadingOption {
  label: string
  command: string | null // null = normal text (remove heading)
  style: string
}

const HEADING_OPTIONS: HeadingOption[] = [
  { label: 'Normal text', command: null, style: 'text-xs text-slate-600 dark:text-slate-300' },
  { label: 'Section', command: '\\section', style: 'text-sm font-bold text-slate-800 dark:text-slate-100' },
  { label: 'Subsection', command: '\\subsection', style: 'text-xs font-semibold text-slate-700 dark:text-slate-200' },
  { label: 'Subsubsection', command: '\\subsubsection', style: 'text-xs font-medium text-slate-600 dark:text-slate-300' },
  { label: 'Paragraph', command: '\\paragraph', style: 'text-[11px] text-slate-500 dark:text-slate-400' },
  { label: 'Subparagraph', command: '\\subparagraph', style: 'text-[11px] text-slate-400 dark:text-slate-500' },
]

// Regex to detect heading commands at the start of a line
const HEADING_RE = /^\\(section|subsection|subsubsection|paragraph|subparagraph)\{(.*)\}\s*$/
const HEADING_CMD_RE = /^\\(section|subsection|subsubsection|paragraph|subparagraph)\{/

export const SectionHeadingDropdown: React.FC<SectionHeadingDropdownProps> = ({ editorViewRef }) => {
  const [open, setOpen] = useState(false)
  const [currentLabel, setCurrentLabel] = useState('Normal text')

  const buttonRef = useRef<HTMLButtonElement>(null)
  const [menuPos, setMenuPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 })

  // Position the fixed menu below the button
  useLayoutEffect(() => {
    if (open && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect()
      setMenuPos({ top: rect.bottom + 4, left: rect.left })
    }
  }, [open])

  // Detect current heading at cursor position.
  // Uses a short interval that reads from editorViewRef.current each tick,
  // so it always targets the latest CM view even after view recreation.
  const updateCurrent = useCallback(() => {
    try {
      const v = editorViewRef.current
      if (!v) return
      const pos = v.state.selection.main.head
      const line = v.state.doc.lineAt(pos)
      const match = line.text.match(HEADING_CMD_RE)
      if (match) {
        const cmd = match[1]
        const opt = HEADING_OPTIONS.find(o => o.command === `\\${cmd}`)
        setCurrentLabel(opt?.label ?? 'Normal text')
      } else {
        setCurrentLabel('Normal text')
      }
    } catch {
      setCurrentLabel('Normal text')
    }
  }, [editorViewRef])

  useEffect(() => {
    updateCurrent()
    const id = setInterval(updateCurrent, 250)
    return () => clearInterval(id)
  }, [updateCurrent])


  const handleSelect = useCallback((option: HeadingOption) => {
    const view = editorViewRef.current
    if (!view) return
    setOpen(false)

    const pos = view.state.selection.main.head
    const line = view.state.doc.lineAt(pos)
    const match = line.text.match(HEADING_RE)

    if (match) {
      // Current line is a heading -- replace or remove
      const innerText = match[2]
      if (option.command) {
        // Replace with new heading command
        const newText = `${option.command}{${innerText}}`
        view.dispatch({ changes: { from: line.from, to: line.to, insert: newText } })
      } else {
        // Convert to normal text (remove heading command)
        view.dispatch({ changes: { from: line.from, to: line.to, insert: innerText } })
      }
    } else {
      // Current line is normal text -- wrap with heading command
      if (option.command) {
        const lineText = line.text.trimEnd()
        const newText = `${option.command}{${lineText}}`
        view.dispatch({ changes: { from: line.from, to: line.to, insert: newText } })
      }
      // If selecting "Normal text" on normal text, do nothing
    }

    view.focus()
    updateCurrent()
  }, [editorViewRef, updateCurrent])

  return (
    <div className="relative flex-shrink-0">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen(!open)}
        className={`inline-flex w-[130px] items-center justify-between gap-1 rounded px-2 py-1 text-xs font-medium transition-colors ${
          open
            ? 'bg-slate-300 text-slate-900 dark:bg-slate-600 dark:text-white'
            : 'text-slate-600 hover:bg-slate-200 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-700/60 dark:hover:text-white'
        }`}
      >
        <span className="truncate">{currentLabel}</span>
        <ChevronDown className="h-3 w-3 flex-shrink-0" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="fixed z-50 w-[180px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800"
            style={{ top: menuPos.top, left: menuPos.left }}
          >
            {HEADING_OPTIONS.map((option) => (
              <button
                key={option.label}
                type="button"
                onClick={() => handleSelect(option)}
                className={`flex w-full items-center px-3 py-1.5 text-left transition-colors hover:bg-slate-100 dark:hover:bg-slate-700/60 ${option.style} ${
                  currentLabel === option.label ? 'bg-slate-50 dark:bg-slate-700/50' : ''
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
