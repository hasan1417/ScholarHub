import { latex } from 'codemirror-lang-latex'
import { syntaxTree } from '@codemirror/language'
import type { LanguageSupport } from '@codemirror/language'
import type { Extension } from '@codemirror/state'
import { RangeSetBuilder } from '@codemirror/state'
import { ViewPlugin, Decoration, EditorView } from '@codemirror/view'
import type { DecorationSet, ViewUpdate } from '@codemirror/view'

/**
 * The codemirror-lang-latex parser recognises MaketitleCtrlSeq and several
 * other command nodes but doesn't assign them a highlight tag. This plugin
 * walks the syntax tree and adds a CSS class so they get coloured like
 * other backslash-commands (\begin, \section, etc.).
 */
const unstyledNodes = new Set([
  'MaketitleCtrlSeq',
  'CenteringCtrlSeq',
  'ItemCtrlSeq',
  'HLineCtrlSeq',
  'TopRuleCtrlSeq',
  'MidRuleCtrlSeq',
  'BottomRuleCtrlSeq',
  'MultiColumnCtrlSeq',
  'ParBoxCtrlSeq',
  'SetLengthCtrlSeq',
  'HboxCtrlSeq',
  'LeftCtrlSeq',
  'RightCtrlSeq',
  'InputCtrlSeq',
  'IncludeCtrlSeq',
  'IncludeGraphicsCtrlSeq',
  'CaptionCtrlSeq',
  'DefCtrlSeq',
  'LetCtrlSeq',
  'NewTheoremCtrlSeq',
  'TheoremStyleCtrlSeq',
  'AffilCtrlSeq',
  'AffiliationCtrlSeq',
  'TextColorCtrlSeq',
  'ColorBoxCtrlSeq',
  'HrefCtrlSeq',
  'UrlCtrlSeq',
  'MathTextCtrlSeq',
])

const ctrlSeqMark = Decoration.mark({ attributes: { style: 'color: var(--latex-editor-keyword)' } })

function buildDecorations(view: EditorView): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>()
  const tree = syntaxTree(view.state)
  const { from, to } = view.visibleRanges[0] ?? { from: 0, to: view.state.doc.length }
  const end = view.visibleRanges[view.visibleRanges.length - 1]?.to ?? to

  tree.iterate({
    from,
    to: end,
    enter(node) {
      if (unstyledNodes.has(node.name)) {
        builder.add(node.from, node.to, ctrlSeqMark)
      }
    },
  })
  return builder.finish()
}

const latexHighlightPlugin = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet
    constructor(view: EditorView) {
      this.decorations = buildDecorations(view)
    }
    update(update: ViewUpdate) {
      if (update.docChanged || update.viewportChanged || syntaxTree(update.startState) !== syntaxTree(update.state)) {
        this.decorations = buildDecorations(update.view)
      }
    }
  },
  { decorations: (v) => v.decorations }
)

export function latexHighlightFixes(): Extension {
  return latexHighlightPlugin
}

/**
 * Configured Lezer-based LaTeX language support.
 */
export function latexLanguageSetup(): LanguageSupport {
  return latex({
    autoCloseTags: true,
    enableLinting: false,
    enableTooltips: true,
    enableAutocomplete: false,
    autoCloseBrackets: false,
  })
}
