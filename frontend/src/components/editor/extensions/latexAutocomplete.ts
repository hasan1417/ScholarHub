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
  { label: '\\section*', detail: 'Unnumbered section', template: '\\section*{|}' },
  { label: '\\subsection', detail: 'Subsection heading', template: '\\subsection{|}' },
  { label: '\\subsection*', detail: 'Unnumbered subsection', template: '\\subsection*{|}' },
  { label: '\\subsubsection', detail: 'Subsubsection heading', template: '\\subsubsection{|}' },
  { label: '\\paragraph', detail: 'Paragraph heading', template: '\\paragraph{|}' },
  { label: '\\subparagraph', detail: 'Sub-paragraph heading', template: '\\subparagraph{|}' },
  { label: '\\appendix', detail: 'Start appendices' },
  { label: '\\tableofcontents', detail: 'Table of contents' },
  { label: '\\listoffigures', detail: 'List of figures' },
  { label: '\\listoftables', detail: 'List of tables' },
  // Text formatting
  { label: '\\textbf', detail: 'Bold text', template: '\\textbf{|}' },
  { label: '\\textit', detail: 'Italic text', template: '\\textit{|}' },
  { label: '\\textsc', detail: 'Small caps', template: '\\textsc{|}' },
  { label: '\\texttt', detail: 'Monospace text', template: '\\texttt{|}' },
  { label: '\\textrm', detail: 'Roman text', template: '\\textrm{|}' },
  { label: '\\textsf', detail: 'Sans-serif text', template: '\\textsf{|}' },
  { label: '\\emph', detail: 'Emphasised text', template: '\\emph{|}' },
  { label: '\\underline', detail: 'Underlined text', template: '\\underline{|}' },
  { label: '\\footnote', detail: 'Footnote', template: '\\footnote{|}' },
  { label: '\\textsuperscript', detail: 'Superscript', template: '\\textsuperscript{|}' },
  { label: '\\textsubscript', detail: 'Subscript', template: '\\textsubscript{|}' },
  { label: '\\textcolor', detail: 'Colored text', template: '\\textcolor{|}{text}' },
  { label: '\\href', detail: 'Hyperlink', template: '\\href{|}{text}' },
  { label: '\\url', detail: 'URL', template: '\\url{|}' },
  // Math
  { label: '\\frac', detail: 'Fraction', template: '\\frac{|}{denominator}' },
  { label: '\\dfrac', detail: 'Display-style fraction', template: '\\dfrac{|}{denominator}' },
  { label: '\\tfrac', detail: 'Text-style fraction', template: '\\tfrac{|}{denominator}' },
  { label: '\\sqrt', detail: 'Square root', template: '\\sqrt{|}' },
  { label: '\\sum', detail: 'Summation' },
  { label: '\\prod', detail: 'Product' },
  { label: '\\int', detail: 'Integral' },
  { label: '\\iint', detail: 'Double integral' },
  { label: '\\oint', detail: 'Contour integral' },
  { label: '\\lim', detail: 'Limit' },
  { label: '\\max', detail: 'Maximum' },
  { label: '\\min', detail: 'Minimum' },
  { label: '\\sup', detail: 'Supremum' },
  { label: '\\inf', detail: 'Infimum' },
  { label: '\\log', detail: 'Logarithm' },
  { label: '\\ln', detail: 'Natural logarithm' },
  { label: '\\exp', detail: 'Exponential' },
  { label: '\\sin', detail: 'Sine' },
  { label: '\\cos', detail: 'Cosine' },
  { label: '\\tan', detail: 'Tangent' },
  { label: '\\infty', detail: 'Infinity symbol' },
  { label: '\\partial', detail: 'Partial derivative' },
  { label: '\\nabla', detail: 'Nabla / gradient' },
  { label: '\\forall', detail: 'For all' },
  { label: '\\exists', detail: 'Exists' },
  { label: '\\in', detail: 'Element of' },
  { label: '\\notin', detail: 'Not element of' },
  { label: '\\subset', detail: 'Subset' },
  { label: '\\subseteq', detail: 'Subset or equal' },
  { label: '\\cup', detail: 'Union' },
  { label: '\\cap', detail: 'Intersection' },
  { label: '\\emptyset', detail: 'Empty set' },
  { label: '\\cdot', detail: 'Center dot' },
  { label: '\\cdots', detail: 'Center dots' },
  { label: '\\ldots', detail: 'Lower dots' },
  { label: '\\times', detail: 'Times / cross' },
  { label: '\\pm', detail: 'Plus-minus' },
  { label: '\\leq', detail: 'Less or equal' },
  { label: '\\geq', detail: 'Greater or equal' },
  { label: '\\neq', detail: 'Not equal' },
  { label: '\\approx', detail: 'Approximately equal' },
  { label: '\\equiv', detail: 'Equivalent' },
  { label: '\\rightarrow', detail: 'Right arrow' },
  { label: '\\leftarrow', detail: 'Left arrow' },
  { label: '\\Rightarrow', detail: 'Double right arrow' },
  { label: '\\Leftarrow', detail: 'Double left arrow' },
  { label: '\\leftrightarrow', detail: 'Bidirectional arrow' },
  { label: '\\overline', detail: 'Overline', template: '\\overline{|}' },
  { label: '\\hat', detail: 'Hat accent', template: '\\hat{|}' },
  { label: '\\tilde', detail: 'Tilde accent', template: '\\tilde{|}' },
  { label: '\\bar', detail: 'Bar accent', template: '\\bar{|}' },
  { label: '\\vec', detail: 'Vector accent', template: '\\vec{|}' },
  { label: '\\dot', detail: 'Dot accent', template: '\\dot{|}' },
  // Greek letters
  { label: '\\alpha', detail: 'Greek alpha' },
  { label: '\\beta', detail: 'Greek beta' },
  { label: '\\gamma', detail: 'Greek gamma' },
  { label: '\\Gamma', detail: 'Greek Gamma (upper)' },
  { label: '\\delta', detail: 'Greek delta' },
  { label: '\\Delta', detail: 'Greek Delta (upper)' },
  { label: '\\epsilon', detail: 'Greek epsilon' },
  { label: '\\varepsilon', detail: 'Greek varepsilon' },
  { label: '\\zeta', detail: 'Greek zeta' },
  { label: '\\eta', detail: 'Greek eta' },
  { label: '\\theta', detail: 'Greek theta' },
  { label: '\\Theta', detail: 'Greek Theta (upper)' },
  { label: '\\iota', detail: 'Greek iota' },
  { label: '\\kappa', detail: 'Greek kappa' },
  { label: '\\lambda', detail: 'Greek lambda' },
  { label: '\\Lambda', detail: 'Greek Lambda (upper)' },
  { label: '\\mu', detail: 'Greek mu' },
  { label: '\\nu', detail: 'Greek nu' },
  { label: '\\xi', detail: 'Greek xi' },
  { label: '\\Xi', detail: 'Greek Xi (upper)' },
  { label: '\\pi', detail: 'Greek pi' },
  { label: '\\Pi', detail: 'Greek Pi (upper)' },
  { label: '\\rho', detail: 'Greek rho' },
  { label: '\\sigma', detail: 'Greek sigma' },
  { label: '\\Sigma', detail: 'Greek Sigma (upper)' },
  { label: '\\tau', detail: 'Greek tau' },
  { label: '\\upsilon', detail: 'Greek upsilon' },
  { label: '\\phi', detail: 'Greek phi' },
  { label: '\\varphi', detail: 'Greek varphi' },
  { label: '\\Phi', detail: 'Greek Phi (upper)' },
  { label: '\\chi', detail: 'Greek chi' },
  { label: '\\psi', detail: 'Greek psi' },
  { label: '\\Psi', detail: 'Greek Psi (upper)' },
  { label: '\\omega', detail: 'Greek omega' },
  { label: '\\Omega', detail: 'Greek Omega (upper)' },
  // Math fonts
  { label: '\\mathbb', detail: 'Blackboard bold', template: '\\mathbb{|}' },
  { label: '\\mathcal', detail: 'Calligraphic', template: '\\mathcal{|}' },
  { label: '\\mathrm', detail: 'Roman math text', template: '\\mathrm{|}' },
  { label: '\\mathbf', detail: 'Bold math', template: '\\mathbf{|}' },
  { label: '\\mathit', detail: 'Italic math', template: '\\mathit{|}' },
  { label: '\\mathsf', detail: 'Sans-serif math', template: '\\mathsf{|}' },
  { label: '\\text', detail: 'Text in math mode', template: '\\text{|}' },
  // References & citations
  { label: '\\cite', detail: 'Citation', template: '\\cite{|}' },
  { label: '\\citep', detail: 'Parenthetical citation', template: '\\citep{|}' },
  { label: '\\citet', detail: 'Textual citation', template: '\\citet{|}' },
  { label: '\\autocite', detail: 'Automatic citation', template: '\\autocite{|}' },
  { label: '\\parencite', detail: 'Parenthetical citation', template: '\\parencite{|}' },
  { label: '\\textcite', detail: 'In-text citation', template: '\\textcite{|}' },
  { label: '\\ref', detail: 'Cross-reference', template: '\\ref{|}' },
  { label: '\\label', detail: 'Label', template: '\\label{|}' },
  { label: '\\eqref', detail: 'Equation reference', template: '\\eqref{|}' },
  { label: '\\autoref', detail: 'Auto-reference', template: '\\autoref{|}' },
  { label: '\\pageref', detail: 'Page reference', template: '\\pageref{|}' },
  { label: '\\bibliography', detail: 'Bibliography file', template: '\\bibliography{|}' },
  { label: '\\bibliographystyle', detail: 'Bibliography style', template: '\\bibliographystyle{|}' },
  // Environments
  { label: '\\begin', detail: 'Begin environment', template: '\\begin{|}' },
  { label: '\\end', detail: 'End environment', template: '\\end{|}' },
  // Floats
  { label: '\\includegraphics', detail: 'Include image', template: '\\includegraphics[width=|\\linewidth]{file}' },
  { label: '\\caption', detail: 'Caption', template: '\\caption{|}' },
  { label: '\\centering', detail: 'Center content' },
  // Layout
  { label: '\\newpage', detail: 'New page' },
  { label: '\\clearpage', detail: 'Clear page (flush floats)' },
  { label: '\\newline', detail: 'New line' },
  { label: '\\linebreak', detail: 'Line break' },
  { label: '\\pagebreak', detail: 'Page break' },
  { label: '\\hspace', detail: 'Horizontal space', template: '\\hspace{|}' },
  { label: '\\vspace', detail: 'Vertical space', template: '\\vspace{|}' },
  { label: '\\noindent', detail: 'No paragraph indent' },
  { label: '\\phantom', detail: 'Invisible space', template: '\\phantom{|}' },
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
  { label: '\\cline', detail: 'Partial horizontal line', template: '\\cline{|-}' },
  { label: '\\multicolumn', detail: 'Multi-column cell', template: '\\multicolumn{|}{c}{text}' },
  { label: '\\multirow', detail: 'Multi-row cell', template: '\\multirow{|}{*}{text}' },
  { label: '\\newcommand', detail: 'Define new command', template: '\\newcommand{\\|}{definition}' },
  { label: '\\renewcommand', detail: 'Redefine command', template: '\\renewcommand{\\|}{definition}' },
  { label: '\\def', detail: 'Define macro', template: '\\def\\|{}' },
  { label: '\\left', detail: 'Left delimiter' },
  { label: '\\right', detail: 'Right delimiter' },
  { label: '\\bigl', detail: 'Big left delimiter' },
  { label: '\\bigr', detail: 'Big right delimiter' },
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
  { label: 'algorithm', detail: 'Algorithm' },
  { label: 'algorithmic', detail: 'Algorithmic pseudocode' },
  { label: 'lstlisting', detail: 'Code listing' },
  { label: 'cases', detail: 'Piecewise cases (math)' },
  { label: 'matrix', detail: 'Matrix (math)' },
  { label: 'bmatrix', detail: 'Bracketed matrix' },
  { label: 'pmatrix', detail: 'Parenthesized matrix' },
  { label: 'split', detail: 'Split equation' },
  { label: 'multline', detail: 'Multi-line equation' },
  { label: 'tikzpicture', detail: 'TikZ picture' },
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
