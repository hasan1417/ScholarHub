import { EditorView } from '@codemirror/view'
import type { Extension } from '@codemirror/state'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { tags as t } from '@lezer/highlight'

// Overleaf-inspired theme colors are defined via CSS variables in styles/index.css
// so the editor can react to both light and dark modes without remounting.

const overleafHighlightStyle = HighlightStyle.define([
  { tag: t.comment, color: 'var(--latex-editor-comment)', fontStyle: 'italic' },
  { tag: [t.string, t.special(t.string)], color: 'var(--latex-editor-string)' },
  { tag: [t.tagName, t.macroName], color: 'var(--latex-editor-command)', fontWeight: '600' },
  { tag: t.keyword, color: 'var(--latex-editor-keyword)', fontWeight: '600' },
  { tag: [t.atom, t.bool], color: 'var(--latex-editor-math)' },
  { tag: [t.number, t.integer, t.float], color: 'var(--latex-editor-number)' },
  { tag: t.operator, color: 'var(--latex-editor-operator)' },
  { tag: t.bracket, color: 'var(--latex-editor-bracket)' },
  { tag: [t.variableName, t.definition(t.variableName)], color: 'var(--latex-editor-text)' },
  { tag: t.special(t.variableName), color: 'var(--latex-editor-math)' },
])

export const overleafLatexTheme: Extension = [
  EditorView.theme({
    '&': {
      backgroundColor: 'var(--latex-editor-bg)',
      color: 'var(--latex-editor-fg)',
      height: '100%',
    },
    '.cm-editor': {
      fontSize: 'var(--latex-editor-font-size)',
      height: '100%',
    },
    '.cm-scroller': {
      overflow: 'auto',
      fontFamily: 'var(--latex-editor-font-family)',
      lineHeight: '1.58',
      // Scroller background is gutter color - extends full height
      backgroundColor: 'var(--latex-editor-gutter-bg)',
      minHeight: '100%',
    },
    '.cm-content': {
      padding: '12px 16px',
      minHeight: '100%',
      maxHeight: 'none',
      fontFamily: 'var(--latex-editor-font-family)',
      backgroundColor: 'var(--latex-editor-bg)',
    },
    '.cm-gutters': {
      backgroundColor: 'transparent',
      color: 'var(--latex-editor-gutter-fg)',
      borderRight: '1px solid var(--latex-editor-gutter-border)',
    },
    '.cm-lineNumbers .cm-gutterElement': {
      padding: '0 12px',
    },
    '.cm-activeLineGutter': {
      backgroundColor: 'var(--latex-editor-active-line-bg)',
      color: 'var(--latex-editor-active-line-fg)',
      // Extend to cover the border gap
      marginRight: '-1px',
      paddingRight: '1px',
    },
    '.cm-activeLine': {
      backgroundColor: 'var(--latex-editor-active-line-bg)',
      // Extend highlight to cover the gap created by content padding
      marginLeft: '-16px',
      paddingLeft: '16px',
      marginRight: '-16px',
      paddingRight: '16px',
    },
    '&.cm-has-selection .cm-activeLine': {
      backgroundColor: 'transparent',
    },
    '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': {
      backgroundColor: 'var(--latex-editor-selection-bg) !important',
    },
    '&.cm-editor.cm-focused': {
      outline: '1px solid var(--latex-editor-focus-ring)',
      outlineOffset: '0',
    },
    '.cm-foldPlaceholder': {
      backgroundColor: 'var(--latex-editor-fold-bg)',
      color: 'var(--latex-editor-fold-fg)',
      border: '1px solid var(--latex-editor-fold-border)',
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
    },
    '&.cm-editor': {
      color: 'var(--latex-editor-fg)',
    },
    '.cm-selectionMatch': {
      backgroundColor: 'var(--latex-editor-selection-match)',
    },
    '.cm-content': {
      caretColor: 'var(--latex-editor-caret)',
    },
    '.cm-sel-spell-error': {
      textDecoration: 'underline wavy var(--latex-editor-spell)',
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
      fontWeight: 600,
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
