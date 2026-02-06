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
