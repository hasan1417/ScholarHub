import { useState, useCallback, useRef, useLayoutEffect, useEffect, useMemo } from 'react'
import {
  Undo2, Redo2,
  Bold, Italic, Sigma, Link2, Library,
  Image, Table2, List, ListOrdered, Hash, Link,
  IndentIncrease, IndentDecrease, MessageSquare,
  MoreHorizontal, Locate, Search,
} from 'lucide-react'
import type { EditorView } from '@codemirror/view'
import { indentMore, indentLess, toggleComment } from '@codemirror/commands'
import { openSearchPanel, closeSearchPanel, searchPanelOpen } from '@codemirror/search'
import { AiToolsMenu } from './AiToolsMenu'
import { SectionHeadingDropdown } from './SectionHeadingDropdown'

interface FormattingItem {
  key: string
  label: string
  title: string
  icon: React.ReactNode
  action: () => void
}

interface FormattingGroup {
  label: string
  items: FormattingItem[]
}

/** Flat descriptor for a single toolbar button */
interface ToolbarItem {
  id: string
  icon: React.ReactNode
  /** Icon shown in overflow menu (defaults to icon) */
  overflowIcon?: React.ReactNode
  label: string
  action: () => void
  disabled?: boolean
  active?: boolean
  /** Show a vertical separator before this item */
  separator?: boolean
  /** This item uses a custom render in the toolbar (math/table dropdown trigger) */
  customRender?: boolean
}

interface EditorToolbarProps {
  viewMode: 'code' | 'split' | 'pdf'
  isMobile?: boolean
  readOnly: boolean
  undoEnabled: boolean
  redoEnabled: boolean
  onUndo: () => void
  onRedo: () => void
  hasTextSelected: boolean
  boldActive?: boolean
  italicActive?: boolean
  formattingGroups: FormattingGroup[]
  onInsertBold: () => void
  onInsertItalics: () => void
  onInsertInlineMath: () => void
  onInsertDisplayMath: () => void
  onInsertCite: () => void
  onInsertFigure: () => void
  onInsertTable: () => void
  onInsertTableWithSize: (cols: number, rows: number) => void
  onInsertItemize: () => void
  onInsertEnumerate: () => void
  onInsertRef: () => void
  onInsertLink: () => void
  onOpenReferences: (event: React.MouseEvent<HTMLButtonElement>) => void
  editorViewRef: React.RefObject<EditorView | null>
  aiActionLoading: string | null
  onAiAction: (action: string, tone?: string) => void
  symbolPaletteOpen?: boolean
  onToggleSymbolPalette?: () => void
  onForwardSync?: () => void
  visualMode?: boolean
  onToggleVisualMode?: () => void
}

/* ------------------------------------------------------------------ */
/*  TableSizeGrid                                                      */
/* ------------------------------------------------------------------ */
const TableSizeGrid: React.FC<{
  onSelect: (cols: number, rows: number) => void
}> = ({ onSelect }) => {
  const [hover, setHover] = useState<{ col: number; row: number }>({ col: 0, row: 0 })
  const maxCols = 8
  const maxRows = 6

  return (
    <div className="p-2">
      <div className="mb-1.5 text-center text-[10px] font-medium text-slate-500 dark:text-slate-400">
        {hover.col > 0 && hover.row > 0 ? `${hover.col} × ${hover.row}` : 'Select size'}
      </div>
      <table className="border-separate" style={{ borderSpacing: 2 }} onMouseLeave={() => setHover({ col: 0, row: 0 })}>
        <tbody>
          {Array.from({ length: maxRows }, (_, r) => (
            <tr key={r}>
              {Array.from({ length: maxCols }, (_, c) => (
                <td
                  key={c}
                  className={`h-3.5 w-3.5 cursor-pointer rounded-sm border transition-colors ${
                    hover.col > c && hover.row > r
                      ? 'border-indigo-400 bg-indigo-100 dark:border-indigo-500 dark:bg-indigo-900/50'
                      : 'border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-700'
                  }`}
                  onMouseEnter={() => setHover({ col: c + 1, row: r + 1 })}
                  onMouseUp={() => onSelect(c + 1, r + 1)}
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Shared styles                                                      */
/* ------------------------------------------------------------------ */
const btnCls = 'flex-shrink-0 rounded p-1.5 transition-colors disabled:opacity-30'
const btnDefault = `${btnCls} text-slate-500 hover:bg-slate-200 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-700/60 dark:hover:text-slate-200`
const btnActive = `${btnCls} bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300`
const sep = 'mx-1 h-4 w-px flex-shrink-0 bg-slate-300 dark:bg-slate-700'
const iconSz = 'h-3.5 w-3.5'
const ovItem = 'flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 disabled:opacity-40 dark:text-slate-200 dark:hover:bg-slate-700/60'
const ovIcon = 'h-3.5 w-3.5 flex-shrink-0 text-slate-400'
const ovSep = 'my-1 border-t border-slate-200 dark:border-slate-700'

/* ------------------------------------------------------------------ */
/*  EditorToolbar                                                      */
/* ------------------------------------------------------------------ */
export const EditorToolbar: React.FC<EditorToolbarProps> = ({
  viewMode,
  isMobile = false,
  readOnly,
  undoEnabled,
  redoEnabled,
  onUndo,
  onRedo,
  hasTextSelected,
  boldActive,
  italicActive,
  formattingGroups: _formattingGroups,
  onInsertBold,
  onInsertItalics,
  onInsertInlineMath,
  onInsertDisplayMath,
  onInsertCite,
  onInsertRef,
  onInsertLink,
  onInsertFigure,
  onInsertTable,
  onInsertTableWithSize,
  onInsertItemize,
  onInsertEnumerate,
  onOpenReferences,
  editorViewRef,
  aiActionLoading,
  onAiAction,
  symbolPaletteOpen,
  onToggleSymbolPalette,
  onForwardSync,
  visualMode,
  onToggleVisualMode,
}) => {
  void _formattingGroups

  const [openDropdown, setOpenDropdown] = useState<string | null>(null)
  const mathBtnRef = useRef<HTMLButtonElement>(null)
  const tableBtnRef = useRef<HTMLButtonElement>(null)
  const moreBtnRef = useRef<HTMLButtonElement>(null)
  const [mathMenuPos, setMathMenuPos] = useState({ top: 0, left: 0 })
  const [tableMenuPos, setTableMenuPos] = useState({ top: 0, left: 0 })
  const [moreMenuPos, setMoreMenuPos] = useState({ top: 0, left: 0 })

  const formattingDisabled = readOnly
  const showRow1Tools = viewMode !== 'pdf' && !readOnly

  const dispatchCmd = useCallback((cmd: (view: EditorView) => boolean) => {
    const view = editorViewRef.current
    if (view) { cmd(view); view.focus() }
  }, [editorViewRef])

  const closeAndRun = useCallback((fn: () => void) => () => {
    fn()
    setOpenDropdown(null)
  }, [])

  /* ---------------------------------------------------------------- */
  /*  Flat toolbar items list                                          */
  /* ---------------------------------------------------------------- */
  const items: ToolbarItem[] = useMemo(() => {
    const list: ToolbarItem[] = [
      { id: 'bold', icon: <Bold className={iconSz} />, overflowIcon: <Bold className={ovIcon} />, label: 'Bold', action: onInsertBold, disabled: formattingDisabled, active: boldActive, separator: true },
      { id: 'italic', icon: <Italic className={iconSz} />, overflowIcon: <Italic className={ovIcon} />, label: 'Italic', action: onInsertItalics, disabled: formattingDisabled, active: italicActive },
      { id: 'math', icon: <Sigma className={iconSz} />, overflowIcon: <Sigma className={ovIcon} />, label: 'Math', action: () => {/* handled via customRender */}, disabled: formattingDisabled, separator: true, customRender: true },
    ]
    if (onToggleSymbolPalette) {
      list.push({ id: 'symbol', icon: <span className="text-sm font-serif leading-none">&#937;</span>, overflowIcon: <span className={`${ovIcon} text-sm font-serif leading-none`}>&#937;</span>, label: 'Symbol Palette', action: onToggleSymbolPalette, active: symbolPaletteOpen })
    }
    list.push(
      { id: 'cite', icon: <Link2 className={iconSz} />, overflowIcon: <Link2 className={ovIcon} />, label: 'Citation', action: onInsertCite, disabled: formattingDisabled, separator: true },
      { id: 'library', icon: <Library className={iconSz} />, overflowIcon: <Library className={ovIcon} />, label: 'Insert from References', action: () => {/* needs mouse event, handled inline */} },
      { id: 'figure', icon: <Image className={iconSz} />, overflowIcon: <Image className={ovIcon} />, label: 'Figure', action: onInsertFigure, disabled: formattingDisabled, separator: true },
      { id: 'table', icon: <Table2 className={iconSz} />, overflowIcon: <Table2 className={ovIcon} />, label: 'Table', action: () => {/* handled via customRender */}, disabled: formattingDisabled, customRender: true },
      { id: 'itemize', icon: <List className={iconSz} />, overflowIcon: <List className={ovIcon} />, label: 'Bullet List', action: onInsertItemize, disabled: formattingDisabled },
      { id: 'enumerate', icon: <ListOrdered className={iconSz} />, overflowIcon: <ListOrdered className={ovIcon} />, label: 'Numbered List', action: onInsertEnumerate, disabled: formattingDisabled },
      { id: 'link', icon: <Link className={iconSz} />, overflowIcon: <Link className={ovIcon} />, label: 'Hyperlink', action: onInsertLink, disabled: formattingDisabled, separator: true },
      { id: 'ref', icon: <Hash className={iconSz} />, overflowIcon: <Hash className={ovIcon} />, label: 'Cross Reference', action: onInsertRef, disabled: formattingDisabled },
      { id: 'comment', icon: <MessageSquare className={iconSz} />, overflowIcon: <MessageSquare className={ovIcon} />, label: 'Toggle Comment', action: () => dispatchCmd(toggleComment), disabled: formattingDisabled, separator: true },
      { id: 'indent-less', icon: <IndentDecrease className={iconSz} />, overflowIcon: <IndentDecrease className={ovIcon} />, label: 'Decrease Indent', action: () => dispatchCmd(indentLess), disabled: formattingDisabled },
      { id: 'indent-more', icon: <IndentIncrease className={iconSz} />, overflowIcon: <IndentIncrease className={ovIcon} />, label: 'Increase Indent', action: () => dispatchCmd(indentMore), disabled: formattingDisabled },
    )
    return list
  }, [formattingDisabled, boldActive, italicActive, symbolPaletteOpen, onToggleSymbolPalette, onInsertBold, onInsertItalics, onInsertCite, onInsertFigure, onInsertItemize, onInsertEnumerate, onInsertLink, onInsertRef, dispatchCmd])

  /* ---------------------------------------------------------------- */
  /*  Responsive: IntersectionObserver detects clipped items           */
  /* ---------------------------------------------------------------- */
  const row1Ref = useRef<HTMLDivElement>(null)
  const toolbarContentRef = useRef<HTMLDivElement>(null)
  const itemRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const [hiddenItems, setHiddenItems] = useState<Set<string>>(new Set())

  useEffect(() => {
    const container = toolbarContentRef.current
    if (!container || typeof IntersectionObserver === 'undefined') return

    const observer = new IntersectionObserver(
      (entries) => {
        setHiddenItems(prev => {
          const next = new Set(prev)
          for (const entry of entries) {
            const id = entry.target.getAttribute('data-item')
            if (id) {
              if (entry.isIntersecting && entry.intersectionRatio > 0.9) {
                next.delete(id)
              } else {
                next.add(id)
              }
            }
          }
          if (next.size === prev.size && [...next].every(v => prev.has(v))) return prev
          return next
        })
      },
      { root: container, threshold: 0.9 }
    )

    Object.values(itemRefs.current).forEach(el => { if (el) observer.observe(el) })
    return () => observer.disconnect()
  }, [items])

  const hasOverflow = hiddenItems.size > 0

  // Close inline dropdowns if their trigger item gets hidden
  useEffect(() => {
    if (openDropdown === 'math' && hiddenItems.has('math')) setOpenDropdown(null)
    if (openDropdown === 'table' && hiddenItems.has('table')) setOpenDropdown(null)
  }, [hiddenItems, openDropdown])

  /* ---------------------------------------------------------------- */
  /*  Position fixed dropdown menus                                    */
  /* ---------------------------------------------------------------- */
  useLayoutEffect(() => {
    if (openDropdown === 'math' && mathBtnRef.current) {
      const rect = mathBtnRef.current.getBoundingClientRect()
      setMathMenuPos({ top: rect.bottom + 4, left: rect.left })
    }
    if (openDropdown === 'table' && tableBtnRef.current) {
      const rect = tableBtnRef.current.getBoundingClientRect()
      setTableMenuPos({ top: rect.bottom + 4, left: rect.left })
    }
    if (openDropdown === 'more' && moreBtnRef.current) {
      const rect = moreBtnRef.current.getBoundingClientRect()
      setMoreMenuPos({ top: rect.bottom + 4, left: rect.left })
    }
  }, [openDropdown])

  /* ---------------------------------------------------------------- */
  /*  Render a single toolbar button                                   */
  /* ---------------------------------------------------------------- */
  const renderToolbarButton = (item: ToolbarItem) => {
    // Math dropdown trigger
    if (item.id === 'math') {
      return (
        <button ref={mathBtnRef} type="button" disabled={item.disabled}
          onClick={() => setOpenDropdown(openDropdown === 'math' ? null : 'math')}
          className={openDropdown === 'math' ? btnActive : btnDefault}
          title="Insert math">
          {item.icon}
        </button>
      )
    }
    // Table dropdown trigger
    if (item.id === 'table') {
      return (
        <button ref={tableBtnRef} type="button" disabled={item.disabled}
          onClick={() => setOpenDropdown(openDropdown === 'table' ? null : 'table')}
          className={openDropdown === 'table' ? btnActive : btnDefault}
          title="Insert table">
          {item.icon}
        </button>
      )
    }
    // Library button needs mouse event forwarding
    if (item.id === 'library') {
      return (
        <button type="button" onClick={onOpenReferences}
          className={btnDefault} title="Insert from References">
          {item.icon}
        </button>
      )
    }
    // Generic button
    return (
      <button type="button" onClick={item.action} disabled={item.disabled}
        className={item.active ? btnActive : btnDefault}
        title={item.label}>
        {item.icon}
      </button>
    )
  }

  /* ================================================================ */
  /*  RENDER                                                           */
  /* ================================================================ */
  return (
    <>
      {/* ============================================================ */}
      {/* ROW 1 — Writing tools (responsive: collapses into overflow)  */}
      {/* ============================================================ */}
      <div
        ref={row1Ref}
        className="border-b border-slate-200 bg-slate-50 px-2 py-1 transition-colors dark:border-slate-700 dark:bg-slate-800"
      >
        <div className="flex items-center gap-0.5">
          {showRow1Tools && (
            <>
              {/* Always visible: toggle, undo/redo, heading */}
              <div className="flex items-center gap-0.5 flex-shrink-0">
                {/* Source / Visual toggle */}
                {onToggleVisualMode && (
                  <div className="mr-1 flex items-center rounded-full bg-slate-300 p-px dark:bg-slate-600">
                    <button
                      type="button"
                      onClick={() => visualMode && onToggleVisualMode()}
                      className={`whitespace-nowrap rounded-full px-2 py-px text-[11px] font-medium leading-tight transition-colors ${
                        !visualMode
                          ? 'bg-emerald-600 text-white'
                          : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                      }`}
                    >
                      Code Editor
                    </button>
                    <button
                      type="button"
                      onClick={() => !visualMode && onToggleVisualMode()}
                      className={`whitespace-nowrap rounded-full px-2 py-px text-[11px] font-medium leading-tight transition-colors ${
                        visualMode
                          ? 'bg-emerald-600 text-white'
                          : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                      }`}
                    >
                      Visual Editor
                    </button>
                  </div>
                )}

                <span className={sep} />

                {/* Undo / Redo */}
                <button type="button" onClick={onUndo} disabled={!undoEnabled}
                  className={btnDefault} title="Undo">
                  <Undo2 className={iconSz} />
                </button>
                <button type="button" onClick={onRedo} disabled={!redoEnabled}
                  className={btnDefault} title="Redo">
                  <Redo2 className={iconSz} />
                </button>

                {!isMobile && (
                  <>
                    <span className={sep} />
                    <SectionHeadingDropdown editorViewRef={editorViewRef} />
                  </>
                )}
              </div>

              {/* Collapsible items — overflow hidden clips from right */}
              {!isMobile && (
                <div ref={toolbarContentRef} className="flex items-center gap-0.5 overflow-hidden min-w-0">
                  {items.map(item => (
                    <div key={item.id} className="contents">
                      {item.separator && <span className={sep} />}
                      <div
                        ref={el => { itemRefs.current[item.id] = el }}
                        data-item={item.id}
                        className="flex-shrink-0"
                        style={hiddenItems.has(item.id) ? { visibility: 'hidden' } : undefined}
                      >
                        {renderToolbarButton(item)}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Overflow button — outside the overflow container */}
              {!isMobile && hasOverflow && (
                <div className="flex items-center gap-0.5 flex-shrink-0">
                  <span className={sep} />
                  <button
                    ref={moreBtnRef}
                    type="button"
                    onClick={() => setOpenDropdown(openDropdown === 'more' ? null : 'more')}
                    className={openDropdown === 'more' ? btnActive : btnDefault}
                    title="More formatting tools"
                  >
                    <MoreHorizontal className={iconSz} />
                  </button>
                </div>
              )}
            </>
          )}

          {/* Spacer */}
          <div className="flex-1" />

          {/* Right side of Row 1 */}
          <div className="flex items-center gap-0.5 shrink-0">
            {/* AI tools */}
            {viewMode !== 'pdf' && !readOnly && (
              <AiToolsMenu
                readOnly={readOnly}
                hasTextSelected={hasTextSelected}
                aiActionLoading={aiActionLoading}
                onAiAction={onAiAction}
              />
            )}

            {viewMode !== 'pdf' && !isMobile && <span className={sep} />}

            {/* Navigation */}
            {viewMode !== 'pdf' && !isMobile && onForwardSync && (
              <button type="button" onClick={onForwardSync}
                className={btnDefault} title="Go to PDF location">
                <Locate className={iconSz} />
              </button>
            )}

            {viewMode !== 'pdf' && !isMobile && (
              <button type="button"
                onClick={() => {
                  const v = editorViewRef.current
                  if (!v) return
                  if (searchPanelOpen(v.state)) {
                    closeSearchPanel(v)
                  } else {
                    openSearchPanel(v)
                  }
                }}
                className={btnDefault} title="Find and Replace">
                <Search className={iconSz} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/* FIXED DROPDOWN MENUS                                         */}
      {/* ============================================================ */}

      {openDropdown && (
        <div className="fixed inset-0 z-40" onClick={() => setOpenDropdown(null)} />
      )}

      {/* Math dropdown (only when math item is visible in toolbar) */}
      {openDropdown === 'math' && !hiddenItems.has('math') && (
        <div className="fixed z-50 min-w-[160px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800"
          style={{ top: mathMenuPos.top, left: mathMenuPos.left }}>
          <button onClick={closeAndRun(onInsertInlineMath)}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700/60">
            <span className="font-mono text-[10px]">$ $</span> Inline Math
          </button>
          <button onClick={closeAndRun(onInsertDisplayMath)}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700/60">
            <span className="font-mono text-[10px]">\[ \]</span> Display Math
          </button>
        </div>
      )}

      {/* Table dropdown (only when table item is visible in toolbar) */}
      {openDropdown === 'table' && !hiddenItems.has('table') && (
        <div className="fixed z-50 rounded-md border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-800"
          style={{ top: tableMenuPos.top, left: tableMenuPos.left }}>
          <TableSizeGrid onSelect={(cols, rows) => {
            onInsertTableWithSize(cols, rows)
            setOpenDropdown(null)
          }} />
          <div className="border-t border-slate-200 dark:border-slate-700">
            <button onClick={closeAndRun(onInsertTable)}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700/60">
              Default (3×2 booktabs)
            </button>
          </div>
        </div>
      )}

      {/* Per-item overflow menu */}
      {openDropdown === 'more' && hasOverflow && (
        <div className="fixed z-50 min-w-[190px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800"
          style={{ top: moreMenuPos.top, left: moreMenuPos.left }}>
          {items.filter(item => hiddenItems.has(item.id)).map((item, i) => {
            // Math: show expanded inline/display entries
            if (item.id === 'math') {
              return (
                <div key={item.id}>
                  {item.separator && i > 0 && <div className={ovSep} />}
                  <button onClick={closeAndRun(onInsertInlineMath)} disabled={formattingDisabled} className={ovItem}>
                    <Sigma className={ovIcon} /> Inline Math
                  </button>
                  <button onClick={closeAndRun(onInsertDisplayMath)} disabled={formattingDisabled} className={ovItem}>
                    <Sigma className={ovIcon} /> Display Math
                  </button>
                </div>
              )
            }
            // Table: show simple insert action
            if (item.id === 'table') {
              return (
                <div key={item.id}>
                  {item.separator && i > 0 && <div className={ovSep} />}
                  <button onClick={closeAndRun(onInsertTable)} disabled={formattingDisabled} className={ovItem}>
                    {item.overflowIcon} {item.label}
                  </button>
                </div>
              )
            }
            // Library: needs mouse event forwarding
            if (item.id === 'library') {
              return (
                <div key={item.id}>
                  {item.separator && i > 0 && <div className={ovSep} />}
                  <button onClick={(e) => { onOpenReferences(e as React.MouseEvent<HTMLButtonElement>); setOpenDropdown(null) }} className={ovItem}>
                    {item.overflowIcon} {item.label}
                  </button>
                </div>
              )
            }
            // Generic item
            return (
              <div key={item.id}>
                {item.separator && i > 0 && <div className={ovSep} />}
                <button onClick={() => { item.action(); setOpenDropdown(null) }} disabled={item.disabled} className={ovItem}>
                  {item.overflowIcon} {item.label}
                </button>
              </div>
            )
          })}
        </div>
      )}

    </>
  )
}
