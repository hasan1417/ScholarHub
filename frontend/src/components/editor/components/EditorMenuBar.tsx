import { useState, useCallback, useEffect, useRef, useLayoutEffect } from 'react'
import { History, LayoutGrid, Pen, FileOutput, Check, ChevronDown, Download, Package, Pencil, ArrowLeft } from 'lucide-react'
import type { EditorView } from '@codemirror/view'
import { undo, redo, selectAll, toggleComment } from '@codemirror/commands'
import { openSearchPanel } from '@codemirror/search'

interface EditorMenuBarProps {
  editorViewRef: React.RefObject<EditorView | null>
  onCompile: () => void
  onToggleView: (mode: 'split' | 'editor' | 'pdf') => void
  viewMode: string
  paperId?: string
  activeFile: string
  paperTitle?: string
  showBreadcrumbs?: boolean
  onToggleBreadcrumbs?: () => void
  onDownloadPdf?: () => void
  onSave?: () => void
  onInsertSnippet?: (snippet: string, placeholder?: string) => void
  // Snippet callbacks from useLatexSnippets (preferred over inline strings)
  onInsertBold?: () => void
  onInsertItalics?: () => void
  onInsertInlineMath?: () => void
  onInsertCite?: () => void
  onInsertFigure?: () => void
  onInsertTable?: () => void
  onInsertItemize?: () => void
  onInsertEnumerate?: () => void
  // Additional snippet callbacks from formattingActions
  formattingActions?: Record<string, () => void>
  // Items relocated from toolbar
  symbolPaletteOpen?: boolean
  onToggleSymbolPalette?: () => void
  onForwardSync?: () => void
  onOpenSubmissionBuilder?: () => void
  onOpenHistory?: () => void
  saveState?: 'idle' | 'saving' | 'success' | 'error'
  onRenamePaper?: (newTitle: string) => Promise<void>
  canRename?: boolean
  onExportSourceZip?: () => void
  onNavigateBack?: () => void
}

interface MenuItem {
  label: string
  shortcut?: string
  action: () => void
  separator?: false
}

interface MenuSeparator {
  separator: true
}

type MenuEntry = MenuItem | MenuSeparator

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/i.test(navigator.userAgent)
const modKey = isMac ? '\u2318' : 'Ctrl+'

export const EditorMenuBar: React.FC<EditorMenuBarProps> = ({
  editorViewRef,
  onCompile,
  onToggleView,
  viewMode,
  activeFile,
  paperTitle,
  showBreadcrumbs = true,
  onToggleBreadcrumbs,
  onDownloadPdf,
  onSave,
  onInsertSnippet,
  onInsertBold,
  onInsertItalics,
  onInsertInlineMath,
  onInsertCite,
  onInsertFigure,
  onInsertTable,
  onInsertItemize,
  onInsertEnumerate,
  formattingActions,
  symbolPaletteOpen,
  onToggleSymbolPalette,
  onForwardSync,
  onOpenSubmissionBuilder,
  onOpenHistory,
  saveState,
  onRenamePaper,
  canRename,
  onExportSourceZip,
  onNavigateBack,
}) => {
  const [openMenu, setOpenMenu] = useState<string | null>(null)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  const [layoutOpen, setLayoutOpen] = useState(false)
  const [titleDropdownOpen, setTitleDropdownOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [editedTitle, setEditedTitle] = useState('')
  const barRef = useRef<HTMLDivElement>(null)
  const layoutBtnRef = useRef<HTMLButtonElement>(null)
  const titleBtnRef = useRef<HTMLButtonElement>(null)
  const renameInputRef = useRef<HTMLInputElement>(null)
  const [layoutMenuPos, setLayoutMenuPos] = useState({ top: 0, right: 0 })
  const [titleMenuPos, setTitleMenuPos] = useState({ top: 0, left: 0 })

  useLayoutEffect(() => {
    if (layoutOpen && layoutBtnRef.current) {
      const rect = layoutBtnRef.current.getBoundingClientRect()
      setLayoutMenuPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right })
    }
  }, [layoutOpen])

  useLayoutEffect(() => {
    if (titleDropdownOpen && titleBtnRef.current) {
      const rect = titleBtnRef.current.getBoundingClientRect()
      setTitleMenuPos({ top: rect.bottom + 4, left: Math.max(8, rect.left + rect.width / 2 - 110) })
    }
  }, [titleDropdownOpen])

  // Focus rename input when entering rename mode
  useEffect(() => {
    if (renaming && renameInputRef.current) {
      renameInputRef.current.focus()
      renameInputRef.current.select()
    }
  }, [renaming])

  const handleRenameSubmit = useCallback(async () => {
    const trimmed = editedTitle.trim()
    if (!trimmed || trimmed === paperTitle) {
      setRenaming(false)
      return
    }
    try {
      await onRenamePaper?.(trimmed)
    } catch (e) {
      console.error('Rename failed:', e)
    }
    setRenaming(false)
  }, [editedTitle, paperTitle, onRenamePaper])

  // Close menu on outside click
  useEffect(() => {
    if (!openMenu) return
    const handleClick = (e: MouseEvent) => {
      if (barRef.current && !barRef.current.contains(e.target as Node)) {
        setOpenMenu(null)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [openMenu])

  // Close on Escape
  useEffect(() => {
    if (!openMenu && !shortcutsOpen && !layoutOpen && !titleDropdownOpen && !renaming) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpenMenu(null)
        setShortcutsOpen(false)
        setLayoutOpen(false)
        setTitleDropdownOpen(false)
        if (renaming) setRenaming(false)
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [openMenu, shortcutsOpen, layoutOpen, titleDropdownOpen, renaming])

  const dispatch = useCallback((fn: (view: EditorView) => boolean) => {
    const view = editorViewRef.current
    if (view) {
      fn(view)
      view.focus()
    }
    setOpenMenu(null)
  }, [editorViewRef])

  const insertSnippet = useCallback((snippet: string, placeholder?: string) => {
    onInsertSnippet?.(snippet, placeholder)
    setOpenMenu(null)
  }, [onInsertSnippet])

  // Wrap a hook callback: call it and close the menu
  const menuAction = useCallback((fn?: () => void) => () => {
    fn?.()
    setOpenMenu(null)
  }, [])

  const countWords = useCallback(() => {
    const view = editorViewRef.current
    if (!view) return
    const text = view.state.doc.toString()
    // Strip LaTeX commands and count words
    const stripped = text
      .replace(/\\[a-zA-Z]+\{[^}]*\}/g, ' ')
      .replace(/\\[a-zA-Z]+/g, ' ')
      .replace(/[{}$%\\]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
    const words = stripped ? stripped.split(' ').length : 0
    alert(`Word count: ${words}\nCharacters: ${text.length}\nLines: ${view.state.doc.lines}`)
    setOpenMenu(null)
  }, [editorViewRef])

  const downloadSource = useCallback(() => {
    const view = editorViewRef.current
    if (!view) return
    const text = view.state.doc.toString()
    const blob = new Blob([text], { type: 'text/x-tex' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = activeFile || 'main.tex'
    a.click()
    URL.revokeObjectURL(url)
    setOpenMenu(null)
  }, [editorViewRef, activeFile])

  const menus: Record<string, MenuEntry[]> = {
    File: [
      ...(onSave ? [{ label: 'Save', shortcut: `${modKey}S`, action: menuAction(onSave) } as MenuItem, { separator: true } as MenuSeparator] : []),
      { label: 'Word Count', action: countWords },
      { separator: true },
      { label: 'Download PDF', shortcut: `${modKey}Shift+D`, action: () => { if (onDownloadPdf) onDownloadPdf(); else onCompile(); setOpenMenu(null) } },
      { label: 'Download Source', action: downloadSource },
      ...(onOpenSubmissionBuilder ? [
        { separator: true } as MenuSeparator,
        { label: 'Submission Package...', action: () => { onOpenSubmissionBuilder(); setOpenMenu(null) } } as MenuItem,
      ] : []),
    ],
    Edit: [
      { label: 'Undo', shortcut: `${modKey}Z`, action: () => dispatch(undo) },
      { label: 'Redo', shortcut: isMac ? '\u2318\u21e7Z' : 'Ctrl+Y', action: () => dispatch(redo) },
      { separator: true },
      { label: 'Find & Replace', shortcut: `${modKey}F`, action: () => dispatch(openSearchPanel) },
      { label: 'Select All', shortcut: `${modKey}A`, action: () => dispatch(selectAll) },
    ],
    Insert: [
      { label: 'Figure', action: menuAction(onInsertFigure) },
      { label: 'Table', action: menuAction(onInsertTable) },
      { separator: true },
      { label: 'Citation', shortcut: `${modKey}Shift+C`, action: menuAction(onInsertCite) },
      { label: 'Cross Reference', action: menuAction(formattingActions?.ref) },
      { label: 'Footnote', action: menuAction(formattingActions?.footnote) },
      { label: 'Link', action: menuAction(formattingActions?.link) },
      { separator: true },
      { label: 'Inline Math', shortcut: `${modKey}M`, action: menuAction(onInsertInlineMath) },
      { label: 'Display Math', action: menuAction(formattingActions?.['math-display']) },
      { label: 'Align Block', action: menuAction(formattingActions?.align) },
      { separator: true },
      { label: 'Toggle Comment', shortcut: `${modKey}/`, action: () => dispatch(toggleComment) },
    ],
    View: [
      { label: `${viewMode === 'split' ? '\u2713 ' : '  '}Split View`, action: () => { onToggleView('split'); setOpenMenu(null) } },
      { label: `${viewMode === 'editor' || viewMode === 'code' ? '\u2713 ' : '  '}Editor Only`, action: () => { onToggleView('editor'); setOpenMenu(null) } },
      { label: `${viewMode === 'pdf' ? '\u2713 ' : '  '}PDF Only`, action: () => { onToggleView('pdf'); setOpenMenu(null) } },
      { separator: true },
      {
        label: `${showBreadcrumbs ? '\u2713 ' : '  '}Breadcrumbs`,
        action: () => { onToggleBreadcrumbs?.(); setOpenMenu(null) },
      },
      ...(onToggleSymbolPalette ? [{
        label: `${symbolPaletteOpen ? '\u2713 ' : '  '}Symbol Palette`,
        action: () => { onToggleSymbolPalette(); setOpenMenu(null) },
      } as MenuItem] : []),
      ...(onForwardSync ? [
        { separator: true } as MenuSeparator,
        { label: 'Sync to PDF', shortcut: `${modKey}Shift+→`, action: () => { onForwardSync(); setOpenMenu(null) } } as MenuItem,
      ] : []),
    ],
    Format: [
      { label: 'Bold', shortcut: `${modKey}B`, action: menuAction(onInsertBold) },
      { label: 'Italic', shortcut: `${modKey}I`, action: menuAction(onInsertItalics) },
      { label: 'Underline', action: () => insertSnippet('\\underline{}', 'underlined text') },
      { label: 'Monospace', action: menuAction(formattingActions?.code) },
      { separator: true },
      { label: 'Bullet List', action: menuAction(onInsertItemize) },
      { label: 'Numbered List', action: menuAction(onInsertEnumerate) },
      { separator: true },
      { label: 'Section', action: menuAction(formattingActions?.section) },
      { label: 'Subsection', action: menuAction(formattingActions?.subsection) },
      { label: 'Subsubsection', action: () => insertSnippet('\\subsubsection{}', 'Subsubsection Title') },
    ],
    Help: [
      { label: 'Keyboard Shortcuts', action: () => { setShortcutsOpen(true); setOpenMenu(null) } },
      { separator: true },
      { label: 'LaTeX Documentation', action: () => { window.open('https://latexref.xyz/', '_blank'); setOpenMenu(null) } },
    ],
  }

  const menuNames = ['File', 'Edit', 'Insert', 'View', 'Format', 'Help']

  return (
    <>
      <div
        ref={barRef}
        className="relative flex h-7 items-center border-b border-slate-200 bg-slate-100 px-1 text-xs dark:border-slate-700 dark:bg-slate-800"
      >
        {onNavigateBack && (
          <button
            type="button"
            onClick={onNavigateBack}
            className="mr-0.5 rounded p-1 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-700/60 dark:hover:text-slate-200"
            title="Back to paper overview"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
          </button>
        )}
        {menuNames.map(name => (
          <div key={name} className="relative">
            <button
              type="button"
              className={`rounded px-2.5 py-1 text-xs transition-colors ${
                openMenu === name
                  ? 'bg-slate-300 text-slate-900 dark:bg-slate-600 dark:text-white'
                  : 'text-slate-600 hover:bg-slate-200 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-700/60 dark:hover:text-white'
              }`}
              onClick={() => setOpenMenu(openMenu === name ? null : name)}
              onMouseEnter={() => { if (openMenu && openMenu !== name) setOpenMenu(name) }}
            >
              {name}
            </button>
            {openMenu === name && (
              <div className="absolute left-0 top-full z-50 mt-0.5 min-w-[220px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800">
                {menus[name].map((entry, i) => {
                  if (entry.separator) {
                    return <div key={i} className="my-1 border-t border-slate-200 dark:border-slate-700" />
                  }
                  const item = entry as MenuItem
                  return (
                    <button
                      key={i}
                      type="button"
                      onClick={item.action}
                      className="flex w-full items-center justify-between px-3 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700/60"
                    >
                      <span>{item.label}</span>
                      {item.shortcut && (
                        <span className="ml-6 text-[10px] text-slate-400 dark:text-slate-500">{item.shortcut}</span>
                      )}
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        ))}

        {/* Separator after menus */}
        <div className="mx-1 h-3.5 w-px bg-slate-300 dark:bg-slate-600" />

        {/* Paper title dropdown — centered (Overleaf-style) */}
        {paperTitle && (
          <div className="absolute inset-0 flex items-center justify-center" style={{ pointerEvents: 'none' }}>
            {renaming ? (
              <input
                ref={renameInputRef}
                value={editedTitle}
                onChange={e => setEditedTitle(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') handleRenameSubmit()
                  if (e.key === 'Escape') setRenaming(false)
                }}
                onBlur={handleRenameSubmit}
                className="rounded border border-indigo-400 bg-white px-2 py-0.5 text-center text-xs font-medium text-slate-800 outline-none dark:border-indigo-500 dark:bg-slate-700 dark:text-white"
                style={{ pointerEvents: 'auto', maxWidth: '70%' }}
                size={Math.max(15, editedTitle.length + 2)}
              />
            ) : (
              <button
                ref={titleBtnRef}
                type="button"
                onClick={() => { setTitleDropdownOpen(!titleDropdownOpen); setOpenMenu(null); setLayoutOpen(false) }}
                className={`flex items-center gap-1 rounded px-2.5 py-0.5 text-xs font-medium transition-colors ${
                  titleDropdownOpen
                    ? 'bg-slate-300 text-slate-900 dark:bg-slate-600 dark:text-white'
                    : 'text-slate-600 hover:bg-slate-200 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-700/60 dark:hover:text-white'
                }`}
                style={{ pointerEvents: 'auto', maxWidth: '45%' }}
              >
                <span className="truncate">{paperTitle}</span>
                <ChevronDown className="h-3 w-3 flex-shrink-0 opacity-50" />
              </button>
            )}
          </div>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Right side: Save indicator + History + Layout (Overleaf-style) */}
        <div className="flex items-center gap-0.5 mr-0.5">
          {saveState === 'saving' && (
            <span className="mr-1 text-[10px] text-slate-400 dark:text-slate-500 animate-pulse">Saving...</span>
          )}
          {saveState === 'success' && (
            <span className="mr-1 flex items-center gap-0.5 text-[10px] text-emerald-600 dark:text-emerald-400">
              <Check className="h-3 w-3" /> Saved
            </span>
          )}
          {saveState === 'error' && (
            <span className="mr-1 text-[10px] text-red-500 dark:text-red-400">Save failed</span>
          )}
          {onOpenHistory && (
            <button
              type="button"
              onClick={() => { onOpenHistory(); setOpenMenu(null) }}
              className="rounded p-1 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-700/60 dark:hover:text-slate-200"
              title="History"
            >
              <History className="h-4 w-4" />
            </button>
          )}
          <button
            ref={layoutBtnRef}
            type="button"
            onClick={() => { setLayoutOpen(!layoutOpen); setOpenMenu(null) }}
            className={`rounded p-1 transition-colors ${
              layoutOpen
                ? 'bg-slate-300 text-slate-900 dark:bg-slate-600 dark:text-white'
                : 'text-slate-500 hover:bg-slate-200 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-700/60 dark:hover:text-slate-200'
            }`}
            title="Layout"
          >
            <LayoutGrid className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Title dropdown menu */}
      {titleDropdownOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setTitleDropdownOpen(false)} />
          <div
            className="fixed z-50 min-w-[220px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800"
            style={{ top: titleMenuPos.top, left: titleMenuPos.left }}
          >
            {onOpenSubmissionBuilder && (
              <>
                <button
                  type="button"
                  onClick={() => { onOpenSubmissionBuilder(); setTitleDropdownOpen(false) }}
                  className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700/60"
                >
                  <Package className="h-3.5 w-3.5 text-slate-400" /> Submit
                </button>
                <div className="my-1 border-t border-slate-200 dark:border-slate-700" />
              </>
            )}
            {onDownloadPdf && (
              <button
                type="button"
                onClick={() => { onDownloadPdf(); setTitleDropdownOpen(false) }}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700/60"
              >
                <Download className="h-3.5 w-3.5 text-slate-400" /> Download as PDF
              </button>
            )}
            {onExportSourceZip && (
              <button
                type="button"
                onClick={() => { onExportSourceZip(); setTitleDropdownOpen(false) }}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700/60"
              >
                <Download className="h-3.5 w-3.5 text-slate-400" /> Download as source (.zip)
              </button>
            )}
            {canRename && onRenamePaper && (
              <>
                <div className="my-1 border-t border-slate-200 dark:border-slate-700" />
                <button
                  type="button"
                  onClick={() => { setEditedTitle(paperTitle || ''); setRenaming(true); setTitleDropdownOpen(false) }}
                  className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700/60"
                >
                  <Pencil className="h-3.5 w-3.5 text-slate-400" /> Rename
                </button>
              </>
            )}
          </div>
        </>
      )}

      {/* Layout dropdown */}
      {layoutOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setLayoutOpen(false)} />
          <div
            className="fixed z-50 min-w-[200px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800"
            style={{ top: layoutMenuPos.top, right: layoutMenuPos.right }}
          >
            <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
              Layout options
            </div>
            {([
              { mode: 'split' as const, label: 'Split view', icon: <LayoutGrid className="h-4 w-4" /> },
              { mode: 'editor' as const, label: 'Editor only', icon: <Pen className="h-4 w-4" /> },
              { mode: 'pdf' as const, label: 'PDF only', icon: <FileOutput className="h-4 w-4" /> },
            ]).map(({ mode, label, icon }) => {
              const isActive = (mode === 'editor' && (viewMode === 'code' || viewMode === 'editor')) || mode === viewMode
              return (
                <button
                  key={mode}
                  type="button"
                  onClick={() => { onToggleView(mode); setLayoutOpen(false) }}
                  className={`flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs transition-colors ${
                    isActive
                      ? 'bg-emerald-600 text-white'
                      : 'text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700/60'
                  }`}
                >
                  <span className={isActive ? 'text-white' : 'text-slate-400 dark:text-slate-500'}>{icon}</span>
                  <span className="flex-1">{label}</span>
                  {isActive && <Check className="h-3.5 w-3.5" />}
                </button>
              )
            })}
          </div>
        </>
      )}

      {/* Keyboard shortcuts modal */}
      {shortcutsOpen && (
        <>
          <div className="fixed inset-0 z-[60] bg-black/40" onClick={() => setShortcutsOpen(false)} />
          <div className="fixed left-1/2 top-1/2 z-[61] w-[420px] max-h-[80vh] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-slate-200 bg-white p-5 shadow-2xl dark:border-slate-700 dark:bg-slate-800">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Keyboard Shortcuts</h3>
              <button
                type="button"
                onClick={() => setShortcutsOpen(false)}
                className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-200"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M18 6 6 18M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="space-y-3 text-xs">
              {[
                ['Compile', `${modKey}Enter`],
                ['Save', `${modKey}S`],
                ['Bold', `${modKey}B`],
                ['Italic', `${modKey}I`],
                ['Undo', `${modKey}Z`],
                ['Redo', isMac ? `${modKey}\u21e7Z` : 'Ctrl+Y'],
                ['Find & Replace', `${modKey}F`],
                ['Select All', `${modKey}A`],
                ['Inline Math', `${modKey}M`],
                ['Toggle Comment', `${modKey}/`],
              ].map(([label, key]) => (
                <div key={label} className="flex items-center justify-between">
                  <span className="text-slate-600 dark:text-slate-300">{label}</span>
                  <kbd className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-500 dark:bg-slate-700 dark:text-slate-400">{key}</kbd>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  )
}
