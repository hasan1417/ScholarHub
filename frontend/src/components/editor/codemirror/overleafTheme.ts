import { EditorView } from '@codemirror/view'
import type { Extension } from '@codemirror/state'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { tags as t } from '@lezer/highlight'

// Overleaf textmate theme — colors defined via CSS variables in styles/index.css
// so the editor reacts to light/dark mode without remounting.

const overleafHighlightStyle = HighlightStyle.define([
  { tag: t.comment, color: 'var(--latex-editor-comment)', fontStyle: 'italic' },
  { tag: [t.string, t.special(t.string)], color: 'var(--latex-editor-string)' },
  // Lezer LaTeX: CtrlSeq/Csname → keyword, Begin/End → keyword
  { tag: [t.keyword, t.definitionKeyword], color: 'var(--latex-editor-keyword)' },
  // Legacy stex compat: tagName/macroName for command highlighting
  { tag: [t.tagName, t.macroName], color: 'var(--latex-editor-command)' },
  // Lezer: EnvName variants → className
  { tag: t.className, color: 'var(--latex-editor-command)' },
  // Lezer: section headings
  { tag: t.heading, color: 'var(--latex-editor-keyword)', fontWeight: 'bold' },
  // Lezer: \label, \ref → labelName
  { tag: t.labelName, color: 'var(--latex-editor-string)' },
  // Lezer: \cite → quote
  { tag: t.quote, color: 'var(--latex-editor-string)' },
  // Lezer: Dollar, MathSpecialChar → processingInstruction
  { tag: t.processingInstruction, color: 'var(--latex-editor-math)' },
  // Lezer: \textbf → strong, \textit/\emph → emphasis
  { tag: t.strong, color: 'var(--latex-editor-keyword)', fontWeight: 'bold' },
  { tag: t.emphasis, color: 'var(--latex-editor-keyword)', fontStyle: 'italic' },
  // Lezer: \texttt → monospace
  { tag: t.monospace, color: 'var(--latex-editor-keyword)' },
  // Lezer: verbatim/verb content → meta
  { tag: t.meta, color: 'var(--latex-editor-string)' },
  // NOTE: Do NOT style t.content — the Lezer LaTeX parser tags all normal text
  // as t.content (Normal node). Styling it wraps every word in a <span>, which
  // prevents browser spellcheck from seeing contiguous text nodes. The foreground
  // color is inherited from .cm-content / .cm-editor styles.
  { tag: [t.atom, t.bool], color: 'var(--latex-editor-math)' },
  { tag: [t.number, t.integer, t.float], color: 'var(--latex-editor-number)' },
  { tag: t.operator, color: 'var(--latex-editor-operator)' },
  { tag: t.bracket, color: 'var(--latex-editor-bracket)' },
  { tag: [t.variableName, t.definition(t.variableName)], color: 'var(--latex-editor-text)' },
  { tag: t.special(t.variableName), color: 'var(--latex-editor-math)' },
  // Lezer: invalid/trailing content
  { tag: t.invalid, color: 'var(--latex-editor-spell)' },
])

export const overleafLatexTheme: Extension = [
  EditorView.theme({
    '&': {
      backgroundColor: 'var(--latex-editor-bg)',
      color: 'var(--latex-editor-fg)',
      height: '100%',
      textRendering: 'optimizeSpeed',
      fontVariantNumeric: 'slashed-zero',
    },
    '.cm-editor': {
      fontSize: 'var(--latex-editor-font-size)',
      height: '100%',
    },
    '.cm-scroller': {
      overflow: 'auto',
      fontFamily: 'var(--latex-editor-font-family)',
      lineHeight: '1.58',
      backgroundColor: 'var(--latex-editor-bg)',
      minHeight: '100%',
    },
    '.cm-content': {
      padding: '4px 16px',
      minHeight: '100%',
      maxHeight: 'none',
      fontFamily: 'var(--latex-editor-font-family)',
    },
    '.cm-gutters': {
      backgroundColor: 'var(--latex-editor-gutter-bg)',
      color: 'var(--latex-editor-gutter-fg)',
      borderRight: 'none',
      flexShrink: '0',
    },
    '.cm-lineNumbers .cm-gutterElement': {
      padding: '0 8px 0 12px',
      userSelect: 'none',
    },
    '.cm-activeLineGutter': {
      backgroundColor: 'var(--latex-editor-active-line-gutter-bg)',
      color: 'var(--latex-editor-active-line-fg)',
    },
    '.cm-activeLine': {
      backgroundColor: 'var(--latex-editor-active-line-bg)',
      boxShadow: '-16px 0 0 var(--latex-editor-active-line-bg), 16px 0 0 var(--latex-editor-active-line-bg)',
    },
    // Hide active line highlight when selection exists
    '&.cm-has-selection .cm-activeLine': {
      backgroundColor: 'transparent',
      boxShadow: 'none',
    },
    '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': {
      backgroundColor: 'var(--latex-editor-selection-bg) !important',
    },
    '&.cm-editor.cm-focused': {
      outline: 'none',
    },
    '&.cm-editor.cm-focused:not(:focus-visible)': {
      outline: 'none',
    },
    // Matching brackets — Overleaf style: outline only, no background
    '&.cm-focused .cm-matchingBracket, &.cm-focused .cm-nonmatchingBracket': {
      outline: '1px solid rgb(192, 192, 192)',
      backgroundColor: 'transparent',
    },
    '.cm-foldPlaceholder': {
      backgroundColor: 'var(--latex-editor-fold-bg)',
      color: 'var(--latex-editor-fold-fg)',
      border: 'none',
      borderRadius: '3px',
      padding: '0 4px',
    },
    '.cm-tooltip': {
      backgroundColor: 'var(--latex-editor-tooltip-bg)',
      color: 'var(--latex-editor-tooltip-fg)',
      border: '1px solid var(--latex-editor-tooltip-border)',
    },
    '.cm-tooltip .cm-tooltip-arrow:before': {
      borderTopColor: 'var(--latex-editor-tooltip-bg)',
    },
    // ---- Search / Replace panel (Overleaf-inspired) ----
    // CM6 DOM: div.cm-search > [input[search], btn[next], btn[prev], btn[select],
    //   label>chk[case], label>chk[re], label>chk[word], br, input[replace],
    //   btn[replace], btn[replaceAll], btn[close]]
    // Grid: cols 1-4 = input area (labels overlay cols 2-4 inside search input),
    //        cols 5-6 = nav arrows, col 7 = select-all
    '.cm-panels': {
      backgroundColor: 'var(--latex-editor-search-bg)',
      color: 'var(--latex-editor-search-fg)',
      zIndex: '10',
    },
    '.cm-panels.cm-panels-top': {
      borderBottom: '1px solid var(--latex-editor-search-border)',
    },
    '.cm-panels.cm-panels-bottom': {
      borderTop: '1px solid var(--latex-editor-search-border)',
    },
    '.cm-panel.cm-search': {
      display: 'grid',
      gridTemplateColumns: 'minmax(200px, 1fr) auto auto auto auto auto auto',
      gridTemplateRows: 'auto auto',
      alignItems: 'center',
      gap: '4px 2px',
      padding: '6px 36px 6px 12px',
      backgroundColor: 'var(--latex-editor-search-bg)',
      fontSize: '13px',
      position: 'relative',
    },
    '.cm-panel.cm-search br': {
      display: 'none',
    },
    // ---- Text inputs ----
    '.cm-panel.cm-search input.cm-textfield': {
      backgroundColor: 'var(--latex-editor-search-input-bg)',
      color: 'var(--latex-editor-search-input-fg)',
      border: '1px solid var(--latex-editor-search-input-border)',
      borderRadius: '4px',
      padding: '5px 8px',
      fontSize: '13px',
      outline: 'none',
      fontFamily: 'inherit',
      margin: '0',
      minWidth: '0',
    },
    '.cm-panel.cm-search input.cm-textfield:focus': {
      borderColor: '#6366f1',
      boxShadow: '0 0 0 1px rgba(99,102,241,0.3)',
    },
    // Search input spans cols 1-4; right padding leaves room for overlaid toggles
    '.cm-panel.cm-search input.cm-textfield[name="search"]': {
      gridRow: '1',
      gridColumn: '1 / 5',
      paddingRight: '96px',
    },
    // Replace input spans same cols 1-4 → same width as search
    '.cm-panel.cm-search input.cm-textfield[name="replace"]': {
      gridRow: '2',
      gridColumn: '1 / 5',
    },
    // ---- Toggle labels (Aa, [.*], W) — overlaid inside the search input ----
    '.cm-panel.cm-search label': {
      gridRow: '1',
      zIndex: '1',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: '0',
      color: 'var(--latex-editor-search-fg)',
      opacity: '0.5',
      cursor: 'pointer',
      userSelect: 'none',
      width: '26px',
      height: '24px',
      borderRadius: '4px',
      backgroundColor: 'rgba(255,255,255,0.06)',
      border: '1px solid transparent',
      margin: '0',
      padding: '0',
    },
    '.cm-panel.cm-search label:hover': {
      opacity: '0.85',
      backgroundColor: 'rgba(255,255,255,0.12)',
    },
    '.cm-panel.cm-search label:has(input:checked)': {
      opacity: '1',
      backgroundColor: 'rgba(99,102,241,0.2)',
      borderColor: 'rgba(99,102,241,0.4)',
    },
    '.cm-panel.cm-search label input[type="checkbox"]': {
      display: 'none',
    },
    // Place each label in its grid column (2, 3, 4) to overlay on search input
    '.cm-panel.cm-search label:nth-of-type(1)': {
      gridColumn: '2',
    },
    '.cm-panel.cm-search label:nth-of-type(2)': {
      gridColumn: '3',
    },
    '.cm-panel.cm-search label:nth-of-type(3)': {
      gridColumn: '4',
    },
    // Icon symbols via ::after (match case → Aa, regexp → [.*], by word → W)
    '.cm-panel.cm-search label:nth-of-type(1)::after': {
      content: '"Aa"',
      fontSize: '11px',
      fontWeight: '700',
      lineHeight: '1',
    },
    '.cm-panel.cm-search label:nth-of-type(2)::after': {
      content: '"[.*]"',
      fontSize: '10px',
      fontWeight: '600',
      lineHeight: '1',
      fontFamily: 'monospace',
    },
    '.cm-panel.cm-search label:nth-of-type(3)::after': {
      content: '"W"',
      fontSize: '12px',
      fontWeight: '700',
      lineHeight: '1',
    },
    // ---- Action buttons: compact, borderless ----
    '.cm-panel.cm-search button.cm-button': {
      appearance: 'none',
      WebkitAppearance: 'none',
      background: 'transparent',
      backgroundColor: 'transparent',
      color: 'var(--latex-editor-search-fg)',
      border: 'none',
      borderRadius: '4px',
      padding: '4px 6px',
      fontSize: '12px',
      fontWeight: '500',
      cursor: 'pointer',
      backgroundImage: 'none',
      textTransform: 'none',
      whiteSpace: 'nowrap',
      opacity: '0.7',
      lineHeight: '1',
      margin: '0',
    },
    '.cm-panel.cm-search button.cm-button:hover': {
      backgroundColor: 'var(--latex-editor-search-btn-hover-bg)',
      opacity: '1',
    },
    // Nav buttons: prev (∧) & next (∨) arrows — grid row 1, cols 5-6
    '.cm-panel.cm-search button[name="prev"]': {
      gridRow: '1',
      gridColumn: '5',
      fontSize: '0',
      padding: '3px 5px',
    },
    '.cm-panel.cm-search button[name="prev"]::after': {
      content: '"\\2039"',
      fontSize: '18px',
      lineHeight: '1',
      transform: 'rotate(90deg)',
      display: 'inline-block',
    },
    '.cm-panel.cm-search button[name="next"]': {
      gridRow: '1',
      gridColumn: '6',
      fontSize: '0',
      padding: '3px 5px',
    },
    '.cm-panel.cm-search button[name="next"]::after': {
      content: '"\\203A"',
      fontSize: '18px',
      lineHeight: '1',
      transform: 'rotate(90deg)',
      display: 'inline-block',
    },
    '.cm-panel.cm-search button[name="select"]': {
      gridRow: '1',
      gridColumn: '7',
    },
    // Replace / Replace All — grid row 2, cols 5-6
    '.cm-panel.cm-search button[name="replace"]': {
      gridRow: '2',
      gridColumn: '5 / 7',
    },
    '.cm-panel.cm-search button[name="replaceAll"]': {
      gridRow: '2',
      gridColumn: '7',
    },
    // Close button: absolute top-right, aligned with row 1
    '.cm-panel.cm-search button[name="close"]': {
      position: 'absolute',
      right: '8px',
      top: '8px',
      backgroundColor: 'transparent',
      color: 'var(--latex-editor-search-fg)',
      border: 'none',
      fontSize: '16px',
      padding: '2px 6px',
      opacity: '0.5',
      borderRadius: '4px',
      cursor: 'pointer',
      margin: '0',
      lineHeight: '1',
    },
    '.cm-panel.cm-search button[name="close"]:hover': {
      opacity: '1',
      backgroundColor: 'var(--latex-editor-search-btn-hover-bg)',
    },
    // Search match highlights
    '.cm-searchMatch': {
      backgroundColor: 'rgba(255, 213, 0, 0.25)',
      borderRadius: '2px',
    },
    '.cm-searchMatch.cm-searchMatch-selected': {
      backgroundColor: 'rgba(99, 102, 241, 0.35)',
      outline: '1px solid rgba(99, 102, 241, 0.6)',
      borderRadius: '2px',
    },
  }),
  EditorView.baseTheme({
    '.cm-cursor, .cm-dropCursor': {
      borderLeftColor: 'var(--latex-editor-caret)',
      borderLeftWidth: '2px',
      marginLeft: '-1px',
    },
    '&.cm-editor': {
      color: 'var(--latex-editor-fg)',
    },
    '.cm-selectionMatch': {
      backgroundColor: 'var(--latex-editor-selection-match)',
      outline: '1px solid rgb(200, 200, 250)',
    },
    '.cm-content': {
      caretColor: 'var(--latex-editor-caret)',
    },
    '.cm-spell-error': {
      textDecoration: 'underline wavy var(--latex-editor-spell)',
      textDecorationSkipInk: 'none',
      textUnderlineOffset: '2px',
    },
    '.cm-content span.cm-comment': {
      color: 'var(--latex-editor-comment)',
      fontStyle: 'italic',
    },
    '.cm-content span.cm-string': {
      color: 'var(--latex-editor-string)',
    },
    '.cm-content span.cm-builtin, .cm-content span.cm-tag': {
      color: 'var(--latex-editor-command)',
    },
    '.cm-content span.cm-variableName': {
      color: 'var(--latex-editor-text)',
    },
    '.cm-content span.cm-keyword': {
      color: 'var(--latex-editor-keyword)',
    },
    '.cm-content span.cm-atom': {
      color: 'var(--latex-editor-math)',
    },
    '.cm-content span.cm-number': {
      color: 'var(--latex-editor-number)',
    },
    '.cm-content span.cm-bracket': {
      color: 'var(--latex-editor-bracket)',
    },
    '.cm-content span.cm-operator': {
      color: 'var(--latex-editor-operator)',
    },
  }),
  syntaxHighlighting(overleafHighlightStyle, { fallback: true }),
]
