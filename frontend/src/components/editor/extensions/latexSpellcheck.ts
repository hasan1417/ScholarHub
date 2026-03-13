import { EditorView, ViewPlugin, ViewUpdate, Decoration, type DecorationSet } from '@codemirror/view'
import { StateField, StateEffect, RangeSetBuilder } from '@codemirror/state'
import type { Extension } from '@codemirror/state'

/**
 * JS-based spell checker for the LaTeX editor.
 *
 * Browser native spellcheck doesn't work reliably with CM6 because CM6
 * frequently recreates DOM nodes (for syntax highlighting), which resets the
 * browser's spell-check state. Instead we load a dictionary (lazy, ~275 K
 * words) and underline misspelled words ourselves via CM6 Decorations.
 */

// ---------------------------------------------------------------------------
// Dictionary — lazy-loaded singleton
// ---------------------------------------------------------------------------

let dictionary: Set<string> | null = null
let dictionaryPromise: Promise<Set<string>> | null = null

function ensureDictionary(): Promise<Set<string>> {
  if (dictionary) return Promise.resolve(dictionary)
  if (!dictionaryPromise) {
    dictionaryPromise = import('an-array-of-english-words').then((mod) => {
      const words: string[] = (mod as any).default ?? mod
      dictionary = new Set(words.map((w: string) => w.toLowerCase()))
      return dictionary
    })
  }
  return dictionaryPromise
}

// ---------------------------------------------------------------------------
// LaTeX-aware skip regions
// ---------------------------------------------------------------------------

// Environments whose entire body should be skipped (not natural language)
const SKIP_ENVIRONMENTS = new Set([
  'thebibliography', 'verbatim', 'lstlisting', 'minted', 'equation',
  'equation*', 'align', 'align*', 'gather', 'gather*', 'multline', 'multline*',
  'tabular', 'tabular*',
])

// Commands whose brace arguments are NOT natural language (skip entire {arg})
const REF_COMMANDS = new Set([
  'cite', 'citep', 'citet', 'citeauthor', 'citeyear', 'citealt', 'citealp',
  'ref', 'eqref', 'pageref', 'autoref', 'cref', 'Cref',
  'label', 'input', 'include', 'includegraphics', 'usepackage', 'RequirePackage',
  'documentclass', 'bibliographystyle', 'bibliography',
  'begin', 'end', 'newcommand', 'renewcommand', 'DeclareMathOperator',
  'url', 'href', 'hyperref',
])

/** Return sorted array of [from, to) ranges that should NOT be spell-checked. */
function getSkipRanges(text: string): Array<[number, number]> {
  const ranges: Array<[number, number]> = []
  let i = 0
  const len = text.length

  while (i < len) {
    const ch = text[i]

    // Skip URLs and email addresses
    if (ch === 'h' && text.startsWith('http', i)) {
      const urlEnd = text.slice(i).search(/[\s})\]>]/)
      const end = urlEnd === -1 ? len : i + urlEnd
      ranges.push([i, end])
      i = end
      continue
    }
    if (ch === '@' || (i > 0 && /\S/.test(text[i - 1]) && ch === '.' && i + 1 < len && /[a-z]/i.test(text[i + 1]))) {
      // Find word boundaries around email-like patterns
      let start = i; while (start > 0 && /[^\s{}\\]/.test(text[start - 1])) start--
      let end = i + 1; while (end < len && /[^\s{}\\]/.test(text[end])) end++
      if (text.slice(start, end).includes('@')) {
        ranges.push([start, end])
        i = end
        continue
      }
    }

    // Comments: % to end of line
    if (ch === '%' && (i === 0 || text[i - 1] !== '\\')) {
      const eol = text.indexOf('\n', i)
      ranges.push([i, eol === -1 ? len : eol])
      i = eol === -1 ? len : eol
      continue
    }

    // Inline / display math: $...$ or $$...$$
    if (ch === '$') {
      const isDisplay = text[i + 1] === '$'
      const delim = isDisplay ? '$$' : '$'
      const searchStart = i + delim.length
      const closeIdx = text.indexOf(delim, searchStart)
      if (closeIdx !== -1) {
        const end = closeIdx + delim.length
        ranges.push([i, end])
        i = end
        continue
      }
    }

    // \( ... \) inline math
    if (ch === '\\' && text[i + 1] === '(') {
      const close = text.indexOf('\\)', i + 2)
      if (close !== -1) { ranges.push([i, close + 2]); i = close + 2; continue }
    }

    // \[ ... \] display math
    if (ch === '\\' && text[i + 1] === '[') {
      const close = text.indexOf('\\]', i + 2)
      if (close !== -1) { ranges.push([i, close + 2]); i = close + 2; continue }
    }

    // Skip entire environments that aren't natural language
    if (ch === '\\' && text.startsWith('\\begin{', i)) {
      const braceOpen = i + 7
      const braceClose = text.indexOf('}', braceOpen)
      if (braceClose !== -1) {
        const envName = text.slice(braceOpen, braceClose)
        if (SKIP_ENVIRONMENTS.has(envName)) {
          const endTag = `\\end{${envName}}`
          const endIdx = text.indexOf(endTag, braceClose + 1)
          if (endIdx !== -1) {
            const end = endIdx + endTag.length
            ranges.push([i, end])
            i = end
            continue
          }
        }
      }
    }

    // LaTeX commands
    if (ch === '\\' && i + 1 < len && /[a-zA-Z@]/.test(text[i + 1])) {
      let j = i + 1
      while (j < len && /[a-zA-Z@]/.test(text[j])) j++
      if (j < len && text[j] === '*') j++
      const cmdName = text.slice(i + 1, j).replace('*', '')

      if (REF_COMMANDS.has(cmdName)) {
        // Skip command + optional [...] + required {...}
        let k = j
        while (k < len && (text[k] === ' ' || text[k] === '\t')) k++
        while (k < len && text[k] === '[') {
          let depth = 1; k++
          while (k < len && depth > 0) { if (text[k] === '[') depth++; else if (text[k] === ']') depth--; k++ }
        }
        while (k < len && (text[k] === ' ' || text[k] === '\t')) k++
        if (k < len && text[k] === '{') {
          let depth = 1; k++
          while (k < len && depth > 0) { if (text[k] === '{') depth++; else if (text[k] === '}') depth--; k++ }
        }
        ranges.push([i, k])
        i = k
      } else {
        // Text commands like \textbf — only skip the command name
        ranges.push([i, j])
        i = j
      }
      continue
    }

    i++
  }

  return ranges
}

// ---------------------------------------------------------------------------
// Word extraction
// ---------------------------------------------------------------------------

interface WordEntry { word: string; from: number; to: number; adjacentHyphen: boolean; sentenceStart: boolean }

const WORD_RE = /[a-zA-Z'\u2019]+/g

function extractTextWords(text: string): WordEntry[] {
  const skipRanges = getSkipRanges(text)
  const words: WordEntry[] = []

  WORD_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = WORD_RE.exec(text)) !== null) {
    const wFrom = m.index
    const wTo = wFrom + m[0].length

    // Skip if overlapping any skip range
    let skip = false
    for (const [sf, st] of skipRanges) {
      if (wFrom < st && wTo > sf) { skip = true; break }
    }
    if (skip) continue

    // Trim leading/trailing apostrophes
    const word = m[0].replace(/^['\u2019]+|['\u2019]+$/g, '')
    if (word.length < 2) continue
    const trimStart = m[0].indexOf(word)
    const adjFrom = wFrom + trimStart
    const adjTo = adjFrom + word.length

    // Check if this word is adjacent to a hyphen in the source
    const adjacentHyphen = (adjFrom > 0 && text[adjFrom - 1] === '-') ||
      (adjTo < text.length && text[adjTo] === '-')

    // Check if this is a sentence start (first word after .!?: or start of text)
    let look = adjFrom - 1
    while (look >= 0 && ' \n\t'.includes(text[look])) look--
    const sentenceStart = look < 0 || '.!?:'.includes(text[look])

    words.push({ word, from: adjFrom, to: adjTo, adjacentHyphen, sentenceStart })
  }

  return words
}

// ---------------------------------------------------------------------------
// State field for spell-check decorations
// ---------------------------------------------------------------------------

const setSpellDecos = StateEffect.define<DecorationSet>()

const spellDecoField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(decos, tr) {
    for (const e of tr.effects) {
      if (e.is(setSpellDecos)) return e.value
    }
    return tr.docChanged ? decos.map(tr.changes) : decos
  },
  provide: (f) => EditorView.decorations.from(f),
})

// ---------------------------------------------------------------------------
// Suffix stripping — reduces false positives on derived words
// ---------------------------------------------------------------------------

const SUFFIXES = [
  'ing', 'tion', 'sion', 'ment', 'ness', 'ity', 'ous', 'ive', 'able', 'ible',
  'ful', 'less', 'ize', 'ise', 'ized', 'ised', 'izes', 'ises',
  'izing', 'ising', 'ation', 'ional', 'ally', 'ially',
  'ments', 'nesses', 'ities', 'ously', 'ively',
  'ed', 'es', 'er', 'ly', 'al', 'ty',
  's',
]

// Common abbreviations and academic terms missing from basic dictionaries
const ACADEMIC_ALLOW = new Set([
  'vs', 'etc', 'eg', 'ie', 'et', 'al', 'cf', 'wrt',
])

/** Check a word, trying suffix-stripped variants if the full form isn't found. */
function isKnownWord(word: string, dict: Set<string>): boolean {
  const lower = word.toLowerCase()
  if (dict.has(lower)) return true
  if (ACADEMIC_ALLOW.has(lower)) return true

  // Try stripping common suffixes
  for (const suffix of SUFFIXES) {
    if (lower.length > suffix.length + 2 && lower.endsWith(suffix)) {
      const stem = lower.slice(0, -suffix.length)
      if (dict.has(stem)) return true
      // Handle consonant doubling (e.g. "stopped" → "stop")
      if (stem.length > 2 && stem[stem.length - 1] === stem[stem.length - 2]) {
        if (dict.has(stem.slice(0, -1))) return true
      }
      // Handle "e" restoration (e.g. "operationalized" → "operationalize")
      if (dict.has(stem + 'e')) return true
    }
  }

  // Compound word detection: try splitting into two known words
  // Handles "datasets" (data+sets), "workflow" (work+flow), etc.
  for (let i = 3; i <= lower.length - 3; i++) {
    if (dict.has(lower.slice(0, i)) && dict.has(lower.slice(i))) return true
  }

  return false
}

// ---------------------------------------------------------------------------
// ViewPlugin — debounced spell check on visible text
// ---------------------------------------------------------------------------

const spellMark = Decoration.mark({ class: 'cm-spell-error' })

const spellcheckPlugin = ViewPlugin.fromClass(
  class {
    private timer: number | null = null
    private generation = 0

    constructor(private view: EditorView) {
      this.schedule()
    }

    update(update: ViewUpdate) {
      if (update.docChanged || update.viewportChanged) {
        this.schedule()
      }
    }

    private schedule() {
      if (this.timer !== null) clearTimeout(this.timer)
      this.timer = window.setTimeout(() => { this.timer = null; this.check() }, 500)
    }

    private async check() {
      const gen = ++this.generation
      const dict = await ensureDictionary()
      // If another check was scheduled while we were loading, bail
      if (gen !== this.generation) return

      const builder = new RangeSetBuilder<Decoration>()

      for (const { from, to } of this.view.visibleRanges) {
        const text = this.view.state.sliceDoc(from, to)
        const words = extractTextWords(text)

        for (const { word, from: wFrom, to: wTo, adjacentHyphen, sentenceStart } of words) {
          // Rule 1: Skip very short words (≤3 chars) — too many false positives
          if (word.length <= 3) continue
          // Rule 2: Skip ALL-CAPS acronyms (NLP, DARTS, etc.)
          if (/^[A-Z]+$/.test(word)) continue
          // Rule 3: Skip words with digits
          if (/\d/.test(word)) continue
          // Rule 4: Skip mixed case — any uppercase after position 0 (TransUNet, DeepLab, nnUNet)
          if (/[A-Z]/.test(word.slice(1))) continue
          // Rule 5: Capitalized word NOT at sentence start → proper noun (Zoph, Transformer)
          if (/^[A-Z]/.test(word) && !sentenceStart) continue
          // Rule 6: Adjacent to hyphen → part of compound term (Swin-UNet, self-configuring)
          // Accept if known, or if it looks intentional (capitalized, short, etc.)
          if (adjacentHyphen && (word.length <= 6 || /^[A-Z]/.test(word))) continue

          if (!isKnownWord(word, dict)) {
            builder.add(from + wFrom, from + wTo, spellMark)
          }
        }
      }

      // Only dispatch if this is still the latest check
      if (gen === this.generation) {
        this.view.dispatch({ effects: setSpellDecos.of(builder.finish()) })
      }
    }

    destroy() {
      if (this.timer !== null) clearTimeout(this.timer)
    }
  },
)

// ---------------------------------------------------------------------------
// Public extension
// ---------------------------------------------------------------------------

/**
 * JS-based spell check for the LaTeX editor. Loads an English dictionary
 * lazily and underlines misspelled words with a wavy red line. Skips LaTeX
 * commands, math, comments, and ref-like arguments.
 */
export function latexSpellcheck(): Extension {
  return [spellDecoField, spellcheckPlugin]
}
