import { StateEffect, StateField, RangeSetBuilder } from '@codemirror/state'
import { Decoration, type DecorationSet, EditorView, WidgetType } from '@codemirror/view'
import type { Extension, Text } from '@codemirror/state'
import katex from 'katex'

/**
 * Visual mode for the LaTeX editor — incremental build.
 *
 * Architecture: Toggle via StateEffect dispatch (NOT extension reconfigure).
 * Decorations use StateField (NOT ViewPlugin) because line-spanning
 * replace decorations require StateField with `provide`.
 *
 * Title & author are EDITABLE: command syntax is hidden via targeted
 * replace decorations. The visible text is real CM6 content styled
 * via mark decorations.
 */

// ---------------------------------------------------------------------------
// Effects & fields
// ---------------------------------------------------------------------------

export const toggleVisualModeEffect = StateEffect.define<boolean>()
const togglePreambleEffect = StateEffect.define<void>()

export const visualModeField = StateField.define<boolean>({
  create: () => false,
  update(value, tr) {
    for (const e of tr.effects) {
      if (e.is(toggleVisualModeEffect)) return e.value
    }
    return value
  },
})

const preambleExpandedField = StateField.define<boolean>({
  create: () => false,
  update(value, tr) {
    for (const e of tr.effects) {
      if (e.is(togglePreambleEffect)) return !value
      if (e.is(toggleVisualModeEffect)) return false
    }
    return value
  },
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Find a \cmd{...} range. Handles nested braces. */
function findCmdRange(text: string, cmd: string, maxPos: number) {
  const prefix = `\\${cmd}{`
  const idx = text.indexOf(prefix)
  if (idx === -1 || idx >= maxPos) return null
  const contentStart = idx + prefix.length
  let depth = 1, i = contentStart
  while (i < text.length && depth > 0) {
    if (text[i] === '{') depth++
    else if (text[i] === '}') depth--
    i++
  }
  return {
    cmdStart: idx,
    contentStart,
    contentEnd: i - 1,
    cmdEnd: i,
  }
}

/**
 * Scan author content and collect [from, to] ranges that should be hidden:
 * - \commandName{ and matching }
 * - \\ (line break commands)
 * Returns sorted array.
 */
function collectInnerHideRanges(text: string, from: number, to: number): Array<[number, number]> {
  const ranges: Array<[number, number]> = []
  let i = from

  while (i < to) {
    if (text[i] === '\\') {
      // \\ (line break)
      if (i + 1 < to && text[i + 1] === '\\') {
        ranges.push([i, i + 2])
        i += 2
        continue
      }

      // \commandName
      if (i + 1 < to && /[a-zA-Z@]/.test(text[i + 1])) {
        let j = i + 1
        while (j < to && /[a-zA-Z@]/.test(text[j])) j++

        if (j < to && text[j] === '{') {
          // Hide \cmdName{
          ranges.push([i, j + 1])
          // Find matching } and hide it
          let depth = 1, k = j + 1
          while (k < to && depth > 0) {
            if (text[k] === '{') depth++
            else if (text[k] === '}') depth--
            k++
          }
          if (depth === 0) ranges.push([k - 1, k])
          i = j + 1
          continue
        }

        // \command without braces — hide it
        ranges.push([i, j])
        i = j
        continue
      }
    }
    i++
  }

  ranges.sort((a, b) => a[0] - b[0])
  return ranges
}

// ---------------------------------------------------------------------------
// Widgets
// ---------------------------------------------------------------------------

class PreambleBannerWidget extends WidgetType {
  toDOM(view: EditorView) {
    const banner = document.createElement('div')
    banner.className = 'cm-visual-preamble-banner'
    const arrow = document.createElement('span')
    arrow.className = 'cm-visual-preamble-arrow'
    arrow.textContent = '\u25B8'
    banner.appendChild(arrow)
    banner.appendChild(document.createTextNode(' Preamble'))
    banner.addEventListener('mousedown', (e) => {
      e.preventDefault()
      view.dispatch({ effects: togglePreambleEffect.of(undefined) })
    })
    return banner
  }
  eq() { return true }
  ignoreEvent() { return true }
}

class ExpandedPreambleBannerWidget extends WidgetType {
  toDOM(view: EditorView) {
    const banner = document.createElement('div')
    banner.className = 'cm-visual-preamble-banner cm-visual-preamble-banner-expanded'
    const label = document.createElement('span')
    label.textContent = 'Hide document preamble'
    banner.appendChild(label)
    const spacer = document.createElement('span')
    spacer.style.flex = '1'
    banner.appendChild(spacer)
    const chevron = document.createElement('span')
    chevron.className = 'cm-visual-preamble-chevron'
    chevron.textContent = '\u2303'
    banner.appendChild(chevron)
    banner.addEventListener('mousedown', (e) => {
      e.preventDefault()
      view.dispatch({ effects: togglePreambleEffect.of(undefined) })
    })
    return banner
  }
  eq() { return true }
  ignoreEvent() { return true }
}

class InlineMathWidget extends WidgetType {
  constructor(readonly math: string) { super() }
  toDOM() {
    const span = document.createElement('span')
    span.className = 'cm-visual-math'
    try {
      katex.render(this.math, span, { throwOnError: false, displayMode: false })
    } catch {
      span.textContent = `$${this.math}$`
    }
    return span
  }
  eq(other: InlineMathWidget) { return this.math === other.math }
  ignoreEvent() { return false }
}

class DisplayMathWidget extends WidgetType {
  constructor(readonly math: string) { super() }
  toDOM() {
    const div = document.createElement('div')
    div.className = 'cm-visual-display-math'
    try {
      katex.render(this.math, div, { throwOnError: false, displayMode: true })
    } catch {
      div.textContent = this.math
    }
    return div
  }
  eq(other: DisplayMathWidget) { return this.math === other.math }
  ignoreEvent() { return false }
}

class TextReplaceWidget extends WidgetType {
  constructor(readonly replacement: string) { super() }
  toDOM() {
    const span = document.createElement('span')
    span.textContent = this.replacement
    return span
  }
  eq(other: TextReplaceWidget) { return this.replacement === other.replacement }
  ignoreEvent() { return false }
}

class EndDocumentWidget extends WidgetType {
  toDOM() {
    const banner = document.createElement('div')
    banner.className = 'cm-visual-end-document'
    banner.textContent = 'End of document'
    return banner
  }
  eq() { return true }
  ignoreEvent() { return true }
}

// ---------------------------------------------------------------------------
// Decoration builder
// ---------------------------------------------------------------------------

function buildVisualDecorations(doc: Text, preambleExpanded: boolean): DecorationSet {
  const text = doc.toString()
  const builder = new RangeSetBuilder<Decoration>()
  const beginDocIdx = text.indexOf('\\begin{document}')

  // Body start: right after \begin{document}\n
  let bodyStart = 0
  if (beginDocIdx >= 0) {
    bodyStart = beginDocIdx + '\\begin{document}'.length
    if (text[bodyStart] === '\n') bodyStart++
  }

  // === PREAMBLE (added directly — these come first positionally) ===
  if (preambleExpanded && beginDocIdx > 0) {
    builder.add(0, 0, Decoration.widget({
      widget: new ExpandedPreambleBannerWidget(),
      block: true,
      side: -1,
    }))
    const endLine = doc.lineAt(beginDocIdx)
    for (let n = 1; n <= endLine.number; n++) {
      builder.add(doc.line(n).from, doc.line(n).from, Decoration.line({
        class: 'cm-visual-preamble-line',
      }))
    }
  } else if (beginDocIdx > 0) {
    const titleInfo = findCmdRange(text, 'title', beginDocIdx)
    const authorInfo = findCmdRange(text, 'author', beginDocIdx)

    if (titleInfo) {
      builder.add(0, titleInfo.contentStart, Decoration.replace({
        widget: new PreambleBannerWidget(),
        block: true,
        inclusiveStart: true,
      }))
      builder.add(titleInfo.contentStart, titleInfo.contentEnd, Decoration.mark({
        class: 'cm-visual-title',
      }))

      if (authorInfo && authorInfo.cmdStart > titleInfo.contentEnd) {
        builder.add(titleInfo.contentEnd, authorInfo.contentStart, Decoration.replace({}))
        const hideRanges = collectInnerHideRanges(text, authorInfo.contentStart, authorInfo.contentEnd)
        let cursor = authorInfo.contentStart
        for (const [hFrom, hTo] of hideRanges) {
          if (hFrom > cursor) {
            builder.add(cursor, hFrom, Decoration.mark({ class: 'cm-visual-author' }))
          }
          builder.add(hFrom, hTo, Decoration.replace({}))
          cursor = hTo
        }
        if (cursor < authorInfo.contentEnd) {
          builder.add(cursor, authorInfo.contentEnd, Decoration.mark({ class: 'cm-visual-author' }))
        }
        builder.add(authorInfo.contentEnd, bodyStart, Decoration.replace({}))
      } else {
        builder.add(titleInfo.contentEnd, bodyStart, Decoration.replace({}))
      }
    } else {
      builder.add(0, bodyStart, Decoration.replace({
        widget: new PreambleBannerWidget(),
        block: true,
        inclusiveStart: true,
      }))
    }
  }

  // === BODY DECORATIONS (collected, sorted, then added to builder) ===
  const postDecos: Array<{ from: number; to: number; deco: Decoration }> = []

  // \maketitle — hide entire line
  const maketitleIdx = text.indexOf('\\maketitle', bodyStart)
  if (maketitleIdx >= 0) {
    const mtLine = doc.lineAt(maketitleIdx)
    if (mtLine.text.trim() === '\\maketitle') {
      const to = mtLine.to < text.length ? mtLine.to + 1 : mtLine.to
      postDecos.push({ from: mtLine.from, to, deco: Decoration.replace({}) })
    } else {
      postDecos.push({ from: maketitleIdx, to: maketitleIdx + '\\maketitle'.length, deco: Decoration.replace({}) })
    }
  }

  // Section headings: \section{}, \subsection{}, \subsubsection{} (with optional *)
  const sectionRe = /\\((?:sub){0,2}section)\*?\{/g
  sectionRe.lastIndex = bodyStart
  let m: RegExpExecArray | null
  while ((m = sectionRe.exec(text)) !== null) {
    const cmdLevel = m[1]
    const contentStart = m.index + m[0].length
    let depth = 1, i = contentStart
    while (i < text.length && depth > 0) {
      if (text[i] === '{') depth++
      else if (text[i] === '}') depth--
      i++
    }
    if (depth !== 0) continue
    const contentEnd = i - 1
    const cssClass = cmdLevel === 'section' ? 'cm-visual-section'
      : cmdLevel === 'subsection' ? 'cm-visual-subsection'
      : 'cm-visual-subsubsection'

    // Hide \section{ (or \subsection*{ etc.)
    postDecos.push({ from: m.index, to: contentStart, deco: Decoration.replace({}) })
    // Style heading content
    if (contentEnd > contentStart) {
      postDecos.push({ from: contentStart, to: contentEnd, deco: Decoration.mark({ class: cssClass }) })
    }
    // Hide closing }
    postDecos.push({ from: contentEnd, to: i, deco: Decoration.replace({}) })
  }

  // Display math environments → rendered KaTeX block.
  // Collect their ranges so inline patterns (ligatures etc.) skip them.
  const mathEnvs = new Set([
    'equation', 'equation*', 'align', 'align*', 'gather', 'gather*',
    'multline', 'multline*', 'eqnarray', 'eqnarray*', 'displaymath',
    'math', 'flalign', 'flalign*',
  ])
  const displayRanges: Array<[number, number]> = []

  // Math environments: \begin{equation}...\end{equation}
  const mathEnvRe = /\\begin\{([^}]+)\}/g
  mathEnvRe.lastIndex = bodyStart
  while ((m = mathEnvRe.exec(text)) !== null) {
    if (!mathEnvs.has(m[1])) continue
    const endTag = `\\end{${m[1]}}`
    const endIdx = text.indexOf(endTag, m.index)
    if (endIdx < 0) continue
    const blockEnd = endIdx + endTag.length
    const mathContent = text.substring(m.index + m[0].length, endIdx).trim()
    const startLine = doc.lineAt(m.index)
    const endLine = doc.lineAt(blockEnd)
    const from = startLine.from
    const to = endLine.to < text.length ? endLine.to + 1 : endLine.to
    displayRanges.push([from, to])
    postDecos.push({
      from, to,
      deco: Decoration.replace({ widget: new DisplayMathWidget(mathContent), block: true }),
    })
  }

  // $$...$$ display math
  const dblDollarRe = /\$\$([\s\S]+?)\$\$/g
  dblDollarRe.lastIndex = bodyStart
  while ((m = dblDollarRe.exec(text)) !== null) {
    const mathContent = m[1].trim()
    const startLine = doc.lineAt(m.index)
    const endLine = doc.lineAt(m.index + m[0].length - 1)
    const from = startLine.from
    const to = endLine.to < text.length ? endLine.to + 1 : endLine.to
    displayRanges.push([from, to])
    postDecos.push({
      from, to,
      deco: Decoration.replace({ widget: new DisplayMathWidget(mathContent), block: true }),
    })
  }

  // \[...\] display math
  const bracketMathRe = /\\\[([\s\S]+?)\\\]/g
  bracketMathRe.lastIndex = bodyStart
  while ((m = bracketMathRe.exec(text)) !== null) {
    const mathContent = m[1].trim()
    const startLine = doc.lineAt(m.index)
    const endLine = doc.lineAt(m.index + m[0].length - 1)
    const from = startLine.from
    const to = endLine.to < text.length ? endLine.to + 1 : endLine.to
    displayRanges.push([from, to])
    postDecos.push({
      from, to,
      deco: Decoration.replace({ widget: new DisplayMathWidget(mathContent), block: true }),
    })
  }

  // Helper: check if position falls inside a display math block
  const inDisplayMath = (pos: number) =>
    displayRanges.some(([f, t]) => pos >= f && pos < t)

  // Environment delimiters — hide ALL \begin{...} / \end{...} lines universally.
  // Skip `document` (handled by preamble) and math envs (rendered above).
  const envRe = /\\(begin|end)\{([^}]+)\}/g
  envRe.lastIndex = bodyStart
  while ((m = envRe.exec(text)) !== null) {
    if (m[2] === 'document' || mathEnvs.has(m[2])) continue
    const lineObj = doc.lineAt(m.index)
    if (lineObj.text.trim() === m[0]) {
      const to = lineObj.to < text.length ? lineObj.to + 1 : lineObj.to
      postDecos.push({ from: lineObj.from, to, deco: Decoration.replace({}) })
    } else {
      postDecos.push({ from: m.index, to: m.index + m[0].length, deco: Decoration.replace({}) })
    }
  }

  // \item → bullet (•)
  const itemRe = /\\item\b/g
  itemRe.lastIndex = bodyStart
  while ((m = itemRe.exec(text)) !== null) {
    if (inDisplayMath(m.index)) continue
    postDecos.push({
      from: m.index,
      to: m.index + m[0].length,
      deco: Decoration.replace({ widget: new TextReplaceWidget('\u2022') }),
    })
  }

  // Inline math: $...$ → rendered KaTeX widget
  const mathRe = /\$([^$]+)\$/g
  mathRe.lastIndex = bodyStart
  while ((m = mathRe.exec(text)) !== null) {
    if (inDisplayMath(m.index)) continue
    // Skip display math ($$...$$)
    if (m.index > 0 && text[m.index - 1] === '$') continue
    if (m.index + m[0].length < text.length && text[m.index + m[0].length] === '$') continue
    postDecos.push({
      from: m.index,
      to: m.index + m[0].length,
      deco: Decoration.replace({ widget: new InlineMathWidget(m[1]) }),
    })
  }

  // LaTeX text ligatures (single pass to avoid overlapping matches)
  const ligRe = /---|--|``|''/g
  ligRe.lastIndex = bodyStart
  let lm: RegExpExecArray | null
  while ((lm = ligRe.exec(text)) !== null) {
    if (inDisplayMath(lm.index)) continue
    const ch = lm[0] === '---' ? '\u2014'  // em-dash —
      : lm[0] === '--' ? '\u2013'          // en-dash –
      : lm[0] === '``' ? '\u201C'          // left double quote "
      : '\u201D'                            // right double quote "
    postDecos.push({
      from: lm.index,
      to: lm.index + lm[0].length,
      deco: Decoration.replace({ widget: new TextReplaceWidget(ch) }),
    })
  }

  // \end{document} → "End of document" banner
  const endDocIdx = text.indexOf('\\end{document}', bodyStart)
  if (endDocIdx >= 0) {
    const edLine = doc.lineAt(endDocIdx)
    const to = edLine.to < text.length ? edLine.to + 1 : edLine.to
    postDecos.push({
      from: edLine.from, to,
      deco: Decoration.replace({ widget: new EndDocumentWidget(), block: true }),
    })
  }

  // Sort by position, then filter overlaps (later/smaller deco yields to earlier/larger one)
  postDecos.sort((a, b) => a.from - b.from || a.to - b.to)
  let lastTo = 0
  for (const d of postDecos) {
    if (d.from < lastTo) continue // skip overlapping decoration
    builder.add(d.from, d.to, d.deco)
    lastTo = d.to
  }

  return builder.finish()
}

// ---------------------------------------------------------------------------
// Decoration field
// ---------------------------------------------------------------------------

const visualDecoField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(decos, tr) {
    const active = tr.state.field(visualModeField, false)
    if (!active) return Decoration.none

    const toggled = tr.effects.some(e => e.is(toggleVisualModeEffect))
    const preambleToggled = tr.effects.some(e => e.is(togglePreambleEffect))
    if (!tr.docChanged && !toggled && !preambleToggled) return decos

    const expanded = tr.state.field(preambleExpandedField, false) ?? false
    try {
      return buildVisualDecorations(tr.state.doc, expanded)
    } catch (e) {
      console.error('[visual-mode] decoration build failed:', e)
      return Decoration.none
    }
  },
  provide: f => EditorView.decorations.from(f),
})

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------

const visualModeTheme = EditorView.baseTheme({
  '.cm-visual-preamble-banner': {
    display: 'flex',
    alignItems: 'center',
    padding: '7px 14px',
    fontSize: '13px',
    fontWeight: '500',
    fontFamily: 'system-ui, -apple-system, sans-serif',
    color: 'var(--latex-editor-gutter-fg, #64748b)',
    backgroundColor: 'var(--latex-editor-gutter-bg, #f1f5f9)',
    cursor: 'pointer',
    userSelect: 'none',
  },
  '.cm-visual-preamble-arrow': {
    fontSize: '11px',
    marginRight: '6px',
    opacity: '0.7',
  },
  '.cm-visual-preamble-chevron': {
    fontSize: '16px',
    lineHeight: '1',
    opacity: '0.5',
  },
  '.cm-visual-preamble-line': {
    backgroundColor: 'var(--latex-editor-gutter-bg, #f1f5f9)',
  },

  // Editable title
  '.cm-visual-title': {
    fontSize: '24px',
    fontWeight: '700',
    lineHeight: '1.4',
    fontFamily: 'system-ui, -apple-system, sans-serif',
    color: 'var(--latex-editor-fg, #1e293b)',
  },
  '& .cm-line:has(.cm-visual-title)': {
    textAlign: 'center',
    padding: '16px 12px 4px',
  },

  // Editable author
  '.cm-visual-author': {
    fontSize: '14px',
    lineHeight: '1.5',
    fontFamily: 'system-ui, -apple-system, sans-serif',
    color: 'var(--latex-editor-fg, #1e293b)',
  },
  '& .cm-line:has(.cm-visual-author)': {
    textAlign: 'center',
  },

  // Inline math
  '.cm-visual-math': {
    display: 'inline',
    verticalAlign: 'baseline',
  },
  '.cm-visual-math .katex': {
    fontSize: '1em',
  },

  // Display math
  '.cm-visual-display-math': {
    textAlign: 'center',
    padding: '8px 0',
    color: 'var(--latex-editor-fg, #1e293b)',
  },
  '.cm-visual-display-math .katex': {
    fontSize: '1.1em',
  },

  // Section headings
  '.cm-visual-section': {
    fontSize: '20px',
    fontWeight: '700',
    lineHeight: '1.4',
    fontFamily: 'system-ui, -apple-system, sans-serif',
    color: 'var(--latex-editor-fg, #1e293b)',
  },
  '.cm-visual-subsection': {
    fontSize: '17px',
    fontWeight: '600',
    lineHeight: '1.4',
    fontFamily: 'system-ui, -apple-system, sans-serif',
    color: 'var(--latex-editor-fg, #1e293b)',
  },
  '.cm-visual-subsubsection': {
    fontSize: '15px',
    fontWeight: '600',
    fontStyle: 'italic',
    lineHeight: '1.4',
    fontFamily: 'system-ui, -apple-system, sans-serif',
    color: 'var(--latex-editor-fg, #1e293b)',
  },

  // End of document banner
  '.cm-visual-end-document': {
    textAlign: 'center',
    padding: '8px 16px',
    margin: '16px 0 0',
    fontSize: '13px',
    fontWeight: '500',
    fontFamily: 'system-ui, -apple-system, sans-serif',
    color: 'var(--latex-editor-gutter-fg, #64748b)',
    backgroundColor: 'var(--latex-editor-gutter-bg, #f1f5f9)',
    borderRadius: '4px',
    userSelect: 'none',
  },

  // Visual mode body font: proportional serif (like Overleaf / Computer Modern)
  '&.cm-visual-mode .cm-content': {
    fontFamily: '"Computer Modern Serif", "Latin Modern Roman", "Crimson Pro", "Source Serif Pro", Georgia, "Times New Roman", serif',
    fontSize: '16px',
    lineHeight: '1.6',
  },
  '&.cm-visual-mode .cm-gutters': {
    fontFamily: 'var(--latex-editor-font-family)',
  },
})

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

// Add .cm-visual-mode class to the editor when visual mode is active
const visualModeEditorClass = EditorView.editorAttributes.compute([visualModeField], (state) => {
  return state.field(visualModeField) ? { class: 'cm-visual-mode' } : { class: '' }
})

export function latexVisualMode(): Extension {
  return [visualModeField, preambleExpandedField, visualDecoField, visualModeTheme, visualModeEditorClass]
}
