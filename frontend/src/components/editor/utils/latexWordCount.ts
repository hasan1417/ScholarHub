/**
 * Count words and characters in LaTeX source, stripping commands,
 * comments, math environments, and preamble.
 */
export function countLatexWords(source: string): { words: number; characters: number } {
  let text = source

  // 1. Strip preamble (everything before \begin{document})
  const docStart = text.indexOf('\\begin{document}')
  if (docStart !== -1) {
    text = text.slice(docStart + '\\begin{document}'.length)
  }

  // 2. Strip everything after \end{document}
  const docEnd = text.indexOf('\\end{document}')
  if (docEnd !== -1) {
    text = text.slice(0, docEnd)
  }

  // 3. Strip %-line comments (not escaped \%)
  text = text.replace(/(?<!\\)%.*$/gm, '')

  // 4. Strip math environments: $$...$$, $...$, \[...\], \(...\)
  text = text.replace(/\$\$[\s\S]*?\$\$/g, '')
  text = text.replace(/\$[^$]*?\$/g, '')
  text = text.replace(/\\\[[\s\S]*?\\]/g, '')
  text = text.replace(/\\\([\s\S]*?\\\)/g, '')

  // 5. Strip named math environments: equation, align, math, etc.
  text = text.replace(/\\begin\{(equation|align|math)\*?\}[\s\S]*?\\end\{\1\*?\}/g, '')

  // 6. Strip \cite{...}, \ref{...}, \label{...} entirely
  text = text.replace(/\\(?:cite|ref|label)\{[^}]*\}/g, '')

  // 7. Strip \begin{...} and \end{...} tags
  text = text.replace(/\\(?:begin|end)\{[^}]*\}/g, '')

  // 8. Strip LaTeX command names but keep brace contents
  //    e.g. \textbf{important} -> important
  text = text.replace(/\\[a-zA-Z]+\*/g, '')
  text = text.replace(/\\[a-zA-Z]+/g, '')

  // 9. Strip remaining braces and backslashes
  text = text.replace(/[{}\\]/g, '')

  // 10. Count words: split on whitespace, filter empties
  const tokens = text.split(/\s+/).filter(t => t.length > 0)
  const words = tokens.length

  // 11. Characters = joined text without spaces
  const characters = tokens.join('').length

  return { words, characters }
}
