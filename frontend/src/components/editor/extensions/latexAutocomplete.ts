import {
  autocompletion,
  completionKeymap,
  type CompletionContext,
  type CompletionResult,
  type Completion,
} from '@codemirror/autocomplete'
import type { Extension } from '@codemirror/state'
import { researchPapersAPI } from '../../../services/api'
import { makeBibKey } from '../utils/bibKey'

// ---------------------------------------------------------------------------
// 1. LaTeX command completions — triggered by `\`
// ---------------------------------------------------------------------------

interface CmdEntry {
  label: string
  detail: string
  template?: string // snippet with | as cursor position
}

const LATEX_COMMANDS: CmdEntry[] = [
  // Sectioning
  { label: '\\part', detail: 'Part heading', template: '\\part{|}' },
  { label: '\\chapter', detail: 'Chapter heading', template: '\\chapter{|}' },
  { label: '\\section', detail: 'Section heading', template: '\\section{|}' },
  { label: '\\subsection', detail: 'Subsection heading', template: '\\subsection{|}' },
  { label: '\\subsubsection', detail: 'Subsubsection heading', template: '\\subsubsection{|}' },
  { label: '\\paragraph', detail: 'Paragraph heading', template: '\\paragraph{|}' },
  // Text formatting
  { label: '\\textbf', detail: 'Bold text', template: '\\textbf{|}' },
  { label: '\\textit', detail: 'Italic text', template: '\\textit{|}' },
  { label: '\\textsc', detail: 'Small caps', template: '\\textsc{|}' },
  { label: '\\texttt', detail: 'Monospace text', template: '\\texttt{|}' },
  { label: '\\emph', detail: 'Emphasised text', template: '\\emph{|}' },
  { label: '\\underline', detail: 'Underlined text', template: '\\underline{|}' },
  { label: '\\footnote', detail: 'Footnote', template: '\\footnote{|}' },
  { label: '\\textsuperscript', detail: 'Superscript', template: '\\textsuperscript{|}' },
  { label: '\\textsubscript', detail: 'Subscript', template: '\\textsubscript{|}' },
  // Math
  { label: '\\frac', detail: 'Fraction', template: '\\frac{|}{denominator}' },
  { label: '\\sqrt', detail: 'Square root', template: '\\sqrt{|}' },
  { label: '\\sum', detail: 'Summation' },
  { label: '\\int', detail: 'Integral' },
  { label: '\\lim', detail: 'Limit' },
  { label: '\\infty', detail: 'Infinity symbol' },
  { label: '\\alpha', detail: 'Greek alpha' },
  { label: '\\beta', detail: 'Greek beta' },
  { label: '\\gamma', detail: 'Greek gamma' },
  { label: '\\delta', detail: 'Greek delta' },
  { label: '\\epsilon', detail: 'Greek epsilon' },
  { label: '\\theta', detail: 'Greek theta' },
  { label: '\\lambda', detail: 'Greek lambda' },
  { label: '\\mu', detail: 'Greek mu' },
  { label: '\\pi', detail: 'Greek pi' },
  { label: '\\sigma', detail: 'Greek sigma' },
  { label: '\\omega', detail: 'Greek omega' },
  { label: '\\mathbb', detail: 'Blackboard bold', template: '\\mathbb{|}' },
  { label: '\\mathcal', detail: 'Calligraphic', template: '\\mathcal{|}' },
  { label: '\\mathrm', detail: 'Roman math text', template: '\\mathrm{|}' },
  // References
  { label: '\\cite', detail: 'Citation', template: '\\cite{|}' },
  { label: '\\ref', detail: 'Cross-reference', template: '\\ref{|}' },
  { label: '\\label', detail: 'Label', template: '\\label{|}' },
  { label: '\\eqref', detail: 'Equation reference', template: '\\eqref{|}' },
  { label: '\\autoref', detail: 'Auto-reference', template: '\\autoref{|}' },
  { label: '\\pageref', detail: 'Page reference', template: '\\pageref{|}' },
  { label: '\\bibliography', detail: 'Bibliography file', template: '\\bibliography{|}' },
  { label: '\\bibliographystyle', detail: 'Bibliography style', template: '\\bibliographystyle{|}' },
  // Environments
  { label: '\\begin', detail: 'Begin environment', template: '\\begin{|}' },
  // Floats
  { label: '\\includegraphics', detail: 'Include image', template: '\\includegraphics[width=|\\linewidth]{file}' },
  { label: '\\caption', detail: 'Caption', template: '\\caption{|}' },
  { label: '\\centering', detail: 'Center content' },
  // Layout
  { label: '\\newpage', detail: 'New page' },
  { label: '\\clearpage', detail: 'Clear page (flush floats)' },
  { label: '\\newline', detail: 'New line' },
  { label: '\\hspace', detail: 'Horizontal space', template: '\\hspace{|}' },
  { label: '\\vspace', detail: 'Vertical space', template: '\\vspace{|}' },
  { label: '\\noindent', detail: 'No paragraph indent' },
  // Misc
  { label: '\\usepackage', detail: 'Use package', template: '\\usepackage{|}' },
  { label: '\\input', detail: 'Input file', template: '\\input{|}' },
  { label: '\\include', detail: 'Include file', template: '\\include{|}' },
  { label: '\\documentclass', detail: 'Document class', template: '\\documentclass{|}' },
  { label: '\\title', detail: 'Title', template: '\\title{|}' },
  { label: '\\author', detail: 'Author', template: '\\author{|}' },
  { label: '\\date', detail: 'Date', template: '\\date{|}' },
  { label: '\\maketitle', detail: 'Render title block' },
  { label: '\\item', detail: 'List item' },
  { label: '\\toprule', detail: 'Booktabs top rule' },
  { label: '\\midrule', detail: 'Booktabs mid rule' },
  { label: '\\bottomrule', detail: 'Booktabs bottom rule' },
  { label: '\\hline', detail: 'Horizontal line' },
]

function applyTemplate(
  view: import('@codemirror/view').EditorView,
  _completion: Completion,
  from: number,
  to: number,
  template: string,
) {
  const cursorIdx = template.indexOf('|')
  const text = cursorIdx >= 0 ? template.slice(0, cursorIdx) + template.slice(cursorIdx + 1) : template
  const cursorPos = cursorIdx >= 0 ? from + cursorIdx : from + text.length
  view.dispatch({
    changes: { from, to, insert: text },
    selection: { anchor: cursorPos },
  })
}

const commandCompletions: Completion[] = LATEX_COMMANDS.map((cmd) => {
  const c: Completion = {
    label: cmd.label,
    detail: cmd.detail,
    type: 'keyword',
  }
  if (cmd.template) {
    c.apply = (view, completion, from, to) => applyTemplate(view, completion, from, to, cmd.template!)
  }
  return c
})

function latexCommandCompletions(context: CompletionContext): CompletionResult | null {
  // Match a backslash followed by word characters
  const word = context.matchBefore(/\\[a-zA-Z]*/)
  if (!word) return null
  // Don't trigger on 1-char "\" if not explicitly requested
  if (word.from === word.to && !context.explicit) return null

  // Skip if we're inside \begin{, \cite{, \ref{ etc. — those have their own sources
  const beforeText = context.state.doc.sliceString(Math.max(0, word.from - 10), word.from)
  if (/\\(?:begin|end)\{$/.test(beforeText + '\\')) return null

  return {
    from: word.from,
    options: commandCompletions,
    validFor: /^\\[a-zA-Z]*$/,
  }
}

// ---------------------------------------------------------------------------
// 2. Environment completions — triggered by `\begin{`
// ---------------------------------------------------------------------------

const ENVIRONMENTS = [
  { label: 'document', detail: 'Document root' },
  { label: 'abstract', detail: 'Abstract' },
  { label: 'figure', detail: 'Figure float' },
  { label: 'table', detail: 'Table float' },
  { label: 'tabular', detail: 'Tabular data' },
  { label: 'equation', detail: 'Numbered equation' },
  { label: 'align', detail: 'Aligned equations' },
  { label: 'align*', detail: 'Aligned (unnumbered)' },
  { label: 'gather', detail: 'Gathered equations' },
  { label: 'gather*', detail: 'Gathered (unnumbered)' },
  { label: 'itemize', detail: 'Bullet list' },
  { label: 'enumerate', detail: 'Numbered list' },
  { label: 'description', detail: 'Description list' },
  { label: 'quote', detail: 'Short quotation' },
  { label: 'quotation', detail: 'Long quotation' },
  { label: 'verbatim', detail: 'Verbatim text' },
  { label: 'center', detail: 'Centered content' },
  { label: 'flushleft', detail: 'Left-aligned content' },
  { label: 'flushright', detail: 'Right-aligned content' },
  { label: 'minipage', detail: 'Mini page' },
  { label: 'theorem', detail: 'Theorem' },
  { label: 'proof', detail: 'Proof' },
  { label: 'lemma', detail: 'Lemma' },
  { label: 'definition', detail: 'Definition' },
  { label: 'corollary', detail: 'Corollary' },
  { label: 'proposition', detail: 'Proposition' },
  { label: 'remark', detail: 'Remark' },
  { label: 'example', detail: 'Example' },
]

const envCompletions: Completion[] = ENVIRONMENTS.map((env) => ({
  label: env.label,
  detail: env.detail,
  type: 'type',
  apply: (view, _completion, from, to) => {
    const text = `${env.label}}\n  \n\\end{${env.label}}`
    const cursorPos = from + env.label.length + 2 // after "}\n  "
    view.dispatch({
      changes: { from, to, insert: text },
      selection: { anchor: cursorPos },
    })
  },
}))

function environmentCompletions(context: CompletionContext): CompletionResult | null {
  // Match text after \begin{
  const match = context.matchBefore(/\\begin\{[a-zA-Z*]*/)
  if (!match) return null

  const braceIdx = match.text.indexOf('{')
  const from = match.from + braceIdx + 1

  return {
    from,
    options: envCompletions,
    validFor: /^[a-zA-Z*]*$/,
  }
}

// ---------------------------------------------------------------------------
// 3. Citation completions — triggered by \cite{, \citep{, etc.
// ---------------------------------------------------------------------------

interface CiteCache {
  paperId: string
  completions: Completion[]
  fetching: boolean
}

let citeCache: CiteCache | null = null

function citeCompletions(paperId: string | undefined) {
  return function citationSource(context: CompletionContext): CompletionResult | null | Promise<CompletionResult | null> {
    if (!paperId) return null

    // Match text after \cite{, \citep{, \citet{, \autocite{, \parencite{, \textcite{
    const match = context.matchBefore(/\\(?:cite[pt]?|autocite|parencite|textcite)\{[^}]*/)
    if (!match) return null

    const braceIdx = match.text.indexOf('{')
    const from = match.from + braceIdx + 1
    // Handle multi-cite: \cite{key1,key2,<cursor>}
    const textAfterBrace = match.text.slice(braceIdx + 1)
    const lastComma = textAfterBrace.lastIndexOf(',')
    const effectiveFrom = lastComma >= 0 ? from + lastComma + 1 : from

    // Return cached results if available
    if (citeCache && citeCache.paperId === paperId && citeCache.completions.length > 0) {
      return {
        from: effectiveFrom,
        options: citeCache.completions,
        validFor: /^[a-zA-Z0-9_:-]*$/,
      }
    }

    // Avoid concurrent fetches
    if (citeCache?.fetching && citeCache?.paperId === paperId) return null

    // Fetch references asynchronously
    citeCache = { paperId, completions: [], fetching: true }

    return Promise.resolve(researchPapersAPI.listReferences(paperId))
      .then((resp) => {
        const refs: any[] = resp.data?.references || []
        const completions: Completion[] = refs.map((ref) => {
          const key = makeBibKey(ref)
          const authors = Array.isArray(ref.authors) ? ref.authors.join(', ') : ''
          const year = ref.year || ''
          const title = ref.title || ''
          const detail = `${authors} (${year})`
          return {
            label: key,
            detail,
            info: title,
            type: 'text',
          }
        })

        citeCache = { paperId, completions, fetching: false }

        return {
          from: effectiveFrom,
          options: completions,
          validFor: /^[a-zA-Z0-9_:-]*$/,
        }
      })
      .catch(() => {
        if (citeCache) citeCache.fetching = false
        return null
      })
  }
}

// ---------------------------------------------------------------------------
// 4. Label/Ref completions — triggered by \ref{, \eqref{, etc.
// ---------------------------------------------------------------------------

const LABEL_RE = /\\label\{([^}]+)\}/g

function refCompletions(context: CompletionContext): CompletionResult | null {
  // Match text after \ref{, \eqref{, \autoref{, \pageref{
  const match = context.matchBefore(/\\(?:ref|eqref|autoref|pageref)\{[^}]*/)
  if (!match) return null

  const braceIdx = match.text.indexOf('{')
  const from = match.from + braceIdx + 1

  // Scan the entire document for \label{...}
  const doc = context.state.doc.toString()
  const labels: Completion[] = []
  const seen = new Set<string>()
  let m: RegExpExecArray | null
  LABEL_RE.lastIndex = 0
  while ((m = LABEL_RE.exec(doc)) !== null) {
    const lbl = m[1]
    if (!seen.has(lbl)) {
      seen.add(lbl)
      labels.push({ label: lbl, type: 'variable', detail: 'label' })
    }
  }

  if (labels.length === 0) return null

  return {
    from,
    options: labels,
    validFor: /^[a-zA-Z0-9_:.-]*$/,
  }
}

// ---------------------------------------------------------------------------
// Exported extension factory
// ---------------------------------------------------------------------------

export { completionKeymap }

export function latexAutocompletion(paperId?: string): Extension {
  return autocompletion({
    override: [
      latexCommandCompletions,
      environmentCompletions,
      citeCompletions(paperId),
      refCompletions,
    ],
    activateOnTyping: true,
    defaultKeymap: true,
  })
}
