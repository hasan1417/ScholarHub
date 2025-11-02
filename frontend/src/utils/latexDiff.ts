export interface LatexSection {
  key: string // section path e.g., "1:Introduction" or "1.2:Background"
  title: string
  level: number // 1=section, 2=subsection, 3=subsubsection
  content: string
  lineStart?: number
  lineEnd?: number
}

export interface SectionDiffResult {
  added: LatexSection[]
  removed: LatexSection[]
  modified: Array<{ key: string; left: LatexSection; right: LatexSection }>
  unchanged: LatexSection[]
  reordered: string[] // keys reordered
  conflicts: Array<{ key: string; left: LatexSection; right: LatexSection }>
}

// Collapse whitespace inside inline ($...$) and display (\[...\], \begin{equation}...\end{equation}) math
export function normalizeMathWhitespace(src: string): string {
  try {
    let out = src
    // Inline math $...$
    out = out.replace(/\$(?:[^$\\]|\\.)*\$/gs, (m) => m.replace(/\s+/g, ' '))
    // Display math \[...\]
    out = out.replace(/\\\[(?:[^\\]|\\.)*?\\\]/gs, (m) => m.replace(/\s+/g, ' '))
    // equation/envs: \begin{...} ... \end{...}
    out = out.replace(/\\begin\{(equation\*?|align\*?|gather\*?|multline\*?)\}[\s\S]*?\\end\{\1\}/g, (m) => m.replace(/\s+/g, ' '))
    return out
  } catch {
    return src
  }
}

export function parseLatexSections(src: string): LatexSection[] {
  const sections: LatexSection[] = []
  const lines = src.split(/\n/)
  const buf: string[] = []
  let current: { key: string; title: string; level: number } | null = null
  let currentStartLine = 1
  let sectionIndex: number[] = [0, 0, 0]
  const pushCurrent = () => {
    if (current) {
      const lineEnd = currentStartLine + buf.length - 1
      sections.push({ key: current.key, title: current.title, level: current.level, content: buf.join('\n'), lineStart: currentStartLine, lineEnd })
      buf.length = 0
    }
  }
  const headerRegex = /(\\section|\\subsection|\\subsubsection)\s*\{([^}]*)\}/
  let lineNo = 1
  for (const line of lines) {
    const m = line.match(headerRegex)
    if (m) {
      pushCurrent()
      const level = m[1] === '\\section' ? 1 : m[1] === '\\subsection' ? 2 : 3
      sectionIndex[level - 1] += 1
      for (let i = level; i < sectionIndex.length; i++) sectionIndex[i] = 0
      const idx = sectionIndex.slice(0, level).join('.')
      const title = (m[2] || '').trim()
      current = { key: `${idx}:${title}`, title, level }
      currentStartLine = lineNo + 1 // content starts after header line
    } else {
      buf.push(line)
    }
    lineNo += 1
  }
  pushCurrent()
  // If no sections found, treat whole doc as a single section
  if (sections.length === 0) {
    const totalLines = lines.length
    sections.push({ key: '0:Document', title: 'Document', level: 1, content: src, lineStart: 1, lineEnd: totalLines })
  }
  return sections
}

export interface OutlineNode {
  key: string
  title: string
  level: number
  lineStart: number
  lineEnd: number
  children: OutlineNode[]
}

export function buildOutlineTree(sections: LatexSection[]): OutlineNode[] {
  const root: OutlineNode[] = []
  const stack: OutlineNode[] = []
  for (const s of sections) {
    const node: OutlineNode = {
      key: s.key,
      title: s.title,
      level: s.level,
      lineStart: s.lineStart || 1,
      lineEnd: s.lineEnd || (s.lineStart || 1),
      children: []
    }
    while (stack.length > 0 && stack[stack.length - 1].level >= node.level) stack.pop()
    if (stack.length === 0) root.push(node)
    else stack[stack.length - 1].children.push(node)
    stack.push(node)
  }
  return root
}

export function diffSections(leftSrc: string, rightSrc: string): SectionDiffResult {
  const left = parseLatexSections(leftSrc)
  const right = parseLatexSections(rightSrc)
  const leftMap = new Map(left.map(s => [s.key, s]))
  const rightMap = new Map(right.map(s => [s.key, s]))

  const added: LatexSection[] = []
  const removed: LatexSection[] = []
  const modified: Array<{ key: string; left: LatexSection; right: LatexSection }> = []
  const unchanged: LatexSection[] = []
  const conflicts: Array<{ key: string; left: LatexSection; right: LatexSection }> = []

  for (const [key, r] of rightMap) {
    const l = leftMap.get(key)
    if (!l) {
      added.push(r)
    } else {
      const lNorm = normalizeMathWhitespace(l.content).trim()
      const rNorm = normalizeMathWhitespace(r.content).trim()
      if (lNorm === rNorm) unchanged.push(r)
      else modified.push({ key, left: l, right: r })
    }
  }
  for (const [key, l] of leftMap) {
    if (!rightMap.has(key)) removed.push(l)
  }
  // Reorder detection: any key order differs between left and right
  const leftKeys = left.map(s => s.key)
  const rightKeys = right.map(s => s.key)
  const reordered: string[] = []
  if (leftKeys.length === rightKeys.length && leftKeys.some((k, i) => k !== rightKeys[i])) {
    // Record keys that moved
    leftKeys.forEach((k) => { if (rightKeys.indexOf(k) !== leftKeys.indexOf(k)) reordered.push(k) })
  }

  // Conflicts: heuristically, treat modified sections as conflicts; auto-merge later decides
  conflicts.push(...modified)

  return { added, removed, modified, unchanged, reordered, conflicts }
}

export function mergeLatex(
  _baseSrc: string,
  leftSrc: string,
  rightSrc: string,
  picks: Record<string, 'left' | 'right' | 'both'>
): string {
  const l = parseLatexSections(leftSrc)
  const r = parseLatexSections(rightSrc)
  const lMap = new Map(l.map(s => [s.key, s]))
  const rMap = new Map(r.map(s => [s.key, s]))
  const keys = Array.from(new Set([...l.map(s => s.key), ...r.map(s => s.key)])).sort((a,b)=>{
    // Keep numerical section order when possible
    const ai = parseFloat(a.split(':')[0])
    const bi = parseFloat(b.split(':')[0])
    return ai - bi
  })
  const out: string[] = []
  const emitHeader = (s: LatexSection) => {
    const head = s.level === 1 ? '\\section' : s.level === 2 ? '\\subsection' : '\\subsubsection'
    out.push(`${head}{${s.title}}`)
  }
  // Reconstruct merged doc in order of right (target) keys, falling back to left
  for (const k of keys) {
    const left = lMap.get(k)
    const right = rMap.get(k)
    if (left && !right) {
      // Present only in left — include
      emitHeader(left)
      out.push(left.content)
    } else if (!left && right) {
      emitHeader(right)
      out.push(right.content)
    } else if (left && right) {
      const choice = picks[k] || 'right'
      emitHeader(choice === 'left' ? left : right)
      if (choice === 'both') {
        out.push('% >>>>>> SOURCE')
        out.push(left.content)
        out.push('% ======')
        out.push(right.content)
        out.push('% <<<<<< TARGET')
      } else {
        out.push(choice === 'left' ? left.content : right.content)
      }
    }
  }
  return out.join('\n\n')
}
