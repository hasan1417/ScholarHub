import { useState, useCallback, useRef, useLayoutEffect, useEffect } from 'react'
import {
  Undo2, Redo2,
  Bold, Italic, Sigma, Link2, Library,
  Image, Table2, List, ListOrdered, Hash, Link,
  IndentIncrease, IndentDecrease, MessageSquare,
  MoreHorizontal, Locate, Search,
} from 'lucide-react'
import type { EditorView } from '@codemirror/view'
import { indentMore, indentLess, toggleComment } from '@codemirror/commands'
import { openSearchPanel } from '@codemirror/search'
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
/*  Responsive toolbar layout constants                                */
/* ------------------------------------------------------------------ */
// Collapsible group widths (approximate px, each includes trailing separator)
// Groups collapse from end: comment → linkref → insert → cite → math → bold
const GROUP_WIDTHS: number[] = [65, 65, 65, 125, 65, 95]
//                    0:BI 1:math 2:cite 3:insert 4:linkref 5:comment
const FIXED_LEFT = 325   // source/visual toggle + undo + redo + sep + heading-dropdown + sep
const FIXED_RIGHT = 40   // search button area
const OVERFLOW_BTN_W = 38 // sep + ··· button

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

  /* ---------------------------------------------------------------- */
  /*  Responsive: measure row 1 and compute visible groups             */
  /* ---------------------------------------------------------------- */
  const row1Ref = useRef<HTMLDivElement>(null)
  const [visibleCount, setVisibleCount] = useState(GROUP_WIDTHS.length)

  useEffect(() => {
    const el = row1Ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([entry]) => {
      const avail = entry.contentRect.width - FIXED_LEFT - FIXED_RIGHT
      let used = 0
      let count = 0
      for (let i = 0; i < GROUP_WIDTHS.length; i++) {
        const remaining = GROUP_WIDTHS.length - count - 1
        const extra = remaining > 0 ? OVERFLOW_BTN_W : 0
        if (used + GROUP_WIDTHS[i] + extra > avail) break
        used += GROUP_WIDTHS[i]
        count++
      }
      setVisibleCount(count)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const showG = (idx: number) => visibleCount > idx
  const hasOverflow = visibleCount < GROUP_WIDTHS.length

  // Close inline dropdowns if their parent group gets hidden
  useEffect(() => {
    if (openDropdown === 'math' && !showG(1)) setOpenDropdown(null)
    if (openDropdown === 'table' && !showG(3)) setOpenDropdown(null)
  }, [visibleCount]) // eslint-disable-line react-hooks/exhaustive-deps

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

  const dispatchCmd = useCallback((cmd: (view: EditorView) => boolean) => {
    const view = editorViewRef.current
    if (view) { cmd(view); view.focus() }
  }, [editorViewRef])

  const closeAndRun = useCallback((fn: () => void) => () => {
    fn()
    setOpenDropdown(null)
  }, [])

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

              {/* Undo / Redo — always visible */}
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
                  {/* Section Heading Dropdown — always visible */}
                  <span className={sep} />
                  <SectionHeadingDropdown editorViewRef={editorViewRef} />

                  {/* Group 0: Bold / Italic */}
                  {showG(0) && (
                    <>
                      <span className={sep} />
                      <button type="button" onClick={onInsertBold} disabled={formattingDisabled}
                        className={boldActive ? btnActive : btnDefault}
                        title="Bold (\\textbf)">
                        <Bold className={iconSz} />
                      </button>
                      <button type="button" onClick={onInsertItalics} disabled={formattingDisabled}
                        className={italicActive ? btnActive : btnDefault}
                        title="Italic (\\textit)">
                        <Italic className={iconSz} />
                      </button>
                    </>
                  )}

                  {/* Group 1: Math / Symbol */}
                  {showG(1) && (
                    <>
                      <span className={sep} />
                      <button ref={mathBtnRef} type="button" disabled={formattingDisabled}
                        onClick={() => setOpenDropdown(openDropdown === 'math' ? null : 'math')}
                        className={openDropdown === 'math' ? btnActive : btnDefault}
                        title="Insert math">
                        <Sigma className={iconSz} />
                      </button>
                      {onToggleSymbolPalette && (
                        <button type="button" onClick={onToggleSymbolPalette}
                          className={symbolPaletteOpen ? btnActive : btnDefault}
                          title="Symbol palette (Ω)">
                          <span className="text-sm font-serif leading-none">&#937;</span>
                        </button>
                      )}
                    </>
                  )}

                  {/* Group 2: Citation / Library */}
                  {showG(2) && (
                    <>
                      <span className={sep} />
                      <button type="button" onClick={onInsertCite} disabled={formattingDisabled}
                        className={btnDefault} title="Citation (\\cite)">
                        <Link2 className={iconSz} />
                      </button>
                      <button type="button" onClick={onOpenReferences}
                        className={btnDefault} title="Insert from References">
                        <Library className={iconSz} />
                      </button>
                    </>
                  )}

                  {/* Group 3: Figure / Table / Lists */}
                  {showG(3) && (
                    <>
                      <span className={sep} />
                      <button type="button" onClick={onInsertFigure} disabled={formattingDisabled}
                        className={btnDefault} title="Insert figure">
                        <Image className={iconSz} />
                      </button>
                      <button ref={tableBtnRef} type="button" disabled={formattingDisabled}
                        onClick={() => setOpenDropdown(openDropdown === 'table' ? null : 'table')}
                        className={openDropdown === 'table' ? btnActive : btnDefault}
                        title="Insert table">
                        <Table2 className={iconSz} />
                      </button>
                      <button type="button" onClick={onInsertItemize} disabled={formattingDisabled}
                        className={btnDefault} title="Bullet list">
                        <List className={iconSz} />
                      </button>
                      <button type="button" onClick={onInsertEnumerate} disabled={formattingDisabled}
                        className={btnDefault} title="Numbered list">
                        <ListOrdered className={iconSz} />
                      </button>
                    </>
                  )}

                  {/* Group 4: Link / Cross Reference */}
                  {showG(4) && (
                    <>
                      <span className={sep} />
                      <button type="button" onClick={onInsertLink} disabled={formattingDisabled}
                        className={btnDefault} title="Hyperlink">
                        <Link className={iconSz} />
                      </button>
                      <button type="button" onClick={onInsertRef} disabled={formattingDisabled}
                        className={btnDefault} title="Cross Reference (\\ref)">
                        <Hash className={iconSz} />
                      </button>
                    </>
                  )}

                  {/* Group 5: Comment / Indent */}
                  {showG(5) && (
                    <>
                      <span className={sep} />
                      <button type="button" onClick={() => dispatchCmd(toggleComment)} disabled={formattingDisabled}
                        className={btnDefault} title="Toggle Comment">
                        <MessageSquare className={iconSz} />
                      </button>
                      <button type="button" onClick={() => dispatchCmd(indentLess)} disabled={formattingDisabled}
                        className={btnDefault} title="Decrease Indent">
                        <IndentDecrease className={iconSz} />
                      </button>
                      <button type="button" onClick={() => dispatchCmd(indentMore)} disabled={formattingDisabled}
                        className={btnDefault} title="Increase Indent">
                        <IndentIncrease className={iconSz} />
                      </button>
                    </>
                  )}

                  {/* Overflow ··· button (only when items are hidden) */}
                  {hasOverflow && (
                    <>
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
                    </>
                  )}
                </>
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
                onClick={() => { const v = editorViewRef.current; if (v) openSearchPanel(v) }}
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

      {/* Math dropdown (only when group 1 is inline) */}
      {openDropdown === 'math' && showG(1) && (
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

      {/* Table dropdown (only when group 3 is inline) */}
      {openDropdown === 'table' && showG(3) && (
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

      {/* Dynamic overflow menu — shows items from hidden groups */}
      {openDropdown === 'more' && hasOverflow && (
        <div className="fixed z-50 min-w-[190px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800"
          style={{ top: moreMenuPos.top, left: moreMenuPos.left }}>

          {/* Bold/Italic (group 0) */}
          {!showG(0) && (
            <>
              <button onClick={closeAndRun(onInsertBold)} disabled={formattingDisabled} className={ovItem}>
                <Bold className={ovIcon} /> Bold
              </button>
              <button onClick={closeAndRun(onInsertItalics)} disabled={formattingDisabled} className={ovItem}>
                <Italic className={ovIcon} /> Italic
              </button>
              <div className={ovSep} />
            </>
          )}

          {/* Math/Symbol (group 1) */}
          {!showG(1) && (
            <>
              <button onClick={closeAndRun(onInsertInlineMath)} disabled={formattingDisabled} className={ovItem}>
                <Sigma className={ovIcon} /> Inline Math
              </button>
              <button onClick={closeAndRun(onInsertDisplayMath)} disabled={formattingDisabled} className={ovItem}>
                <Sigma className={ovIcon} /> Display Math
              </button>
              {onToggleSymbolPalette && (
                <button onClick={() => { onToggleSymbolPalette(); setOpenDropdown(null) }} className={ovItem}>
                  <span className={`${ovIcon} text-sm font-serif leading-none`}>&#937;</span> Symbol Palette
                </button>
              )}
              <div className={ovSep} />
            </>
          )}

          {/* Cite/Library (group 2) */}
          {!showG(2) && (
            <>
              <button onClick={closeAndRun(onInsertCite)} disabled={formattingDisabled} className={ovItem}>
                <Link2 className={ovIcon} /> Citation
              </button>
              <button onClick={(e) => { onOpenReferences(e as any); setOpenDropdown(null) }} className={ovItem}>
                <Library className={ovIcon} /> Insert from References
              </button>
              <div className={ovSep} />
            </>
          )}

          {/* Insert (group 3) */}
          {!showG(3) && (
            <>
              <button onClick={closeAndRun(onInsertFigure)} disabled={formattingDisabled} className={ovItem}>
                <Image className={ovIcon} /> Figure
              </button>
              <button onClick={closeAndRun(onInsertTable)} disabled={formattingDisabled} className={ovItem}>
                <Table2 className={ovIcon} /> Table
              </button>
              <button onClick={closeAndRun(onInsertItemize)} disabled={formattingDisabled} className={ovItem}>
                <List className={ovIcon} /> Bullet List
              </button>
              <button onClick={closeAndRun(onInsertEnumerate)} disabled={formattingDisabled} className={ovItem}>
                <ListOrdered className={ovIcon} /> Numbered List
              </button>
              <div className={ovSep} />
            </>
          )}

          {/* Link/Ref (group 4) */}
          {!showG(4) && (
            <>
              <button onClick={closeAndRun(onInsertLink)} disabled={formattingDisabled} className={ovItem}>
                <Link className={ovIcon} /> Hyperlink
              </button>
              <button onClick={closeAndRun(onInsertRef)} disabled={formattingDisabled} className={ovItem}>
                <Hash className={ovIcon} /> Cross Reference
              </button>
              {showG(5) || <div className={ovSep} />}
            </>
          )}

          {/* Comment/Indent (group 5) */}
          {!showG(5) && (
            <>
              {showG(4) && <div className={ovSep} />}
              <button onClick={() => { dispatchCmd(toggleComment); setOpenDropdown(null) }} disabled={formattingDisabled} className={ovItem}>
                <MessageSquare className={ovIcon} /> Toggle Comment
              </button>
              <button onClick={() => { dispatchCmd(indentLess); setOpenDropdown(null) }} disabled={formattingDisabled} className={ovItem}>
                <IndentDecrease className={ovIcon} /> Decrease Indent
              </button>
              <button onClick={() => { dispatchCmd(indentMore); setOpenDropdown(null) }} disabled={formattingDisabled} className={ovItem}>
                <IndentIncrease className={ovIcon} /> Increase Indent
              </button>
            </>
          )}
        </div>
      )}

    </>
  )
}
