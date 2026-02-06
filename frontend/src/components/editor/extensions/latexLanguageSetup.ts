import { latex } from 'codemirror-lang-latex'
import type { LanguageSupport } from '@codemirror/language'

/**
 * Configured Lezer-based LaTeX language support.
 *
 * - autoCloseTags: auto-inserts \end{env} when typing \begin{env}
 * - enableLinting: disabled — we use custom backend error markers
 * - enableTooltips: hover docs for commands/environments
 * - enableAutocomplete: disabled — our custom latexAutocomplete.ts handles
 *   project-specific \cite{} completions via the backend
 * - autoCloseBrackets: disabled — we use CM's built-in closeBrackets()
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
