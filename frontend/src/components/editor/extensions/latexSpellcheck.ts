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

interface WordEntry { word: string; from: number; to: number }

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
    let word = m[0].replace(/^['\u2019]+|['\u2019]+$/g, '')
    if (word.length < 2) continue
    const trimStart = m[0].indexOf(word)
    words.push({ word, from: wFrom + trimStart, to: wFrom + trimStart + word.length })
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

/** Check a word, trying suffix-stripped variants if the full form isn't found. */
function isKnownWord(word: string, dict: Set<string>): boolean {
  const lower = word.toLowerCase()
  if (dict.has(lower)) return true

  // Try stripping common suffixes
  for (const suffix of SUFFIXES) {
    if (lower.length > suffix.length + 2 && lower.endsWith(suffix)) {
      const stem = lower.slice(0, -suffix.length)
      if (dict.has(stem)) return true
      // Handle consonant doubling (e.g. "stopped" → "stop")
      if (stem.length > 2 && stem[stem.length - 1] === stem[stem.length - 2]) {
        if (dict.has(stem.slice(0, -1))) return true
      }
      // Handle "e" restoration (e.g. "operationalized" → "operationalize" → strip → "operational" + e)
      if (dict.has(stem + 'e')) return true
    }
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

        for (const { word, from: wFrom, to: wTo } of words) {
          if (word.length < 2) continue
          // Skip ALL-CAPS acronyms (NLP, ML, etc.)
          if (/^[A-Z]{2,}$/.test(word)) continue
          if (/\d/.test(word)) continue
          // Skip Roman numerals (i, ii, iii, iv, ... used in academic text)
          if (/^[ivxlcdm]+$/i.test(word) && /^(i{1,3}|iv|vi{0,3}|ix|xi{0,3}|xiv|xv|xvi{0,3}|xix|xx)$/i.test(word)) continue

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
