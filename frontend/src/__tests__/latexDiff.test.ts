import { describe, it, expect } from 'vitest'
import {
  normalizeMathWhitespace,
  parseLatexSections,
  buildOutlineTree,
  diffSections,
  mergeLatex,
} from '../utils/latexDiff'

describe('normalizeMathWhitespace', () => {
  it('collapses whitespace in inline math', () => {
    const input = '$a  +  b   = c$'
    expect(normalizeMathWhitespace(input)).toBe('$a + b = c$')
  })

  it('does not change text outside math', () => {
    const input = 'Some   text   here'
    expect(normalizeMathWhitespace(input)).toBe('Some   text   here')
  })

  it('collapses whitespace in display math', () => {
    const input = '\\[a  +  b\\]'
    expect(normalizeMathWhitespace(input)).toBe('\\[a + b\\]')
  })

  it('handles empty string', () => {
    expect(normalizeMathWhitespace('')).toBe('')
  })
})

describe('parseLatexSections', () => {
  it('parses sections from LaTeX source', () => {
    const src = [
      '\\section{Introduction}',
      'Some intro text.',
      '\\section{Methods}',
      'Describe methods here.',
    ].join('\n')

    const sections = parseLatexSections(src)
    expect(sections).toHaveLength(2)
    expect(sections[0].title).toBe('Introduction')
    expect(sections[0].level).toBe(1)
    expect(sections[0].key).toBe('1:Introduction')
    expect(sections[1].title).toBe('Methods')
    expect(sections[1].key).toBe('2:Methods')
  })

  it('handles subsections', () => {
    const src = [
      '\\section{Introduction}',
      'Intro.',
      '\\subsection{Background}',
      'Background text.',
      '\\subsection{Motivation}',
      'Motivation text.',
    ].join('\n')

    const sections = parseLatexSections(src)
    expect(sections).toHaveLength(3)
    expect(sections[1].level).toBe(2)
    expect(sections[1].key).toBe('1.1:Background')
    expect(sections[2].key).toBe('1.2:Motivation')
  })

  it('treats entire doc as single section when no headers found', () => {
    const src = 'Just a plain document with no sections.'
    const sections = parseLatexSections(src)
    expect(sections).toHaveLength(1)
    expect(sections[0].key).toBe('0:Document')
    expect(sections[0].content).toBe(src)
  })
})

describe('buildOutlineTree', () => {
  it('nests subsections under sections', () => {
    const src = [
      '\\section{Chapter 1}',
      'Text.',
      '\\subsection{Sub A}',
      'Sub text.',
      '\\subsection{Sub B}',
      'Sub text.',
      '\\section{Chapter 2}',
      'Text.',
    ].join('\n')

    const sections = parseLatexSections(src)
    const tree = buildOutlineTree(sections)

    expect(tree).toHaveLength(2)
    expect(tree[0].title).toBe('Chapter 1')
    expect(tree[0].children).toHaveLength(2)
    expect(tree[0].children[0].title).toBe('Sub A')
    expect(tree[0].children[1].title).toBe('Sub B')
    expect(tree[1].title).toBe('Chapter 2')
    expect(tree[1].children).toHaveLength(0)
  })
})

describe('diffSections', () => {
  it('detects added sections', () => {
    const left = '\\section{Intro}\nHello.'
    const right = '\\section{Intro}\nHello.\n\\section{Methods}\nNew content.'
    const diff = diffSections(left, right)
    expect(diff.added).toHaveLength(1)
    expect(diff.added[0].title).toBe('Methods')
    expect(diff.removed).toHaveLength(0)
  })

  it('detects removed sections', () => {
    const left = '\\section{Intro}\nHello.\n\\section{Methods}\nContent.'
    const right = '\\section{Intro}\nHello.'
    const diff = diffSections(left, right)
    expect(diff.removed).toHaveLength(1)
    expect(diff.removed[0].title).toBe('Methods')
  })

  it('detects modified sections', () => {
    const left = '\\section{Intro}\nOriginal text.'
    const right = '\\section{Intro}\nUpdated text.'
    const diff = diffSections(left, right)
    expect(diff.modified).toHaveLength(1)
    expect(diff.modified[0].key).toBe('1:Intro')
  })

  it('detects unchanged sections', () => {
    const left = '\\section{Intro}\nSame text.'
    const right = '\\section{Intro}\nSame text.'
    const diff = diffSections(left, right)
    expect(diff.unchanged).toHaveLength(1)
    expect(diff.modified).toHaveLength(0)
  })
})

describe('mergeLatex', () => {
  const base = '\\section{Intro}\nBase text.\n\\section{Methods}\nBase methods.'

  it('picks left content when choice is left', () => {
    const left = '\\section{Intro}\nLeft intro.\n\\section{Methods}\nLeft methods.'
    const right = '\\section{Intro}\nRight intro.\n\\section{Methods}\nRight methods.'
    const result = mergeLatex(base, left, right, {
      '1:Intro': 'left',
      '2:Methods': 'left',
    })
    expect(result).toContain('Left intro.')
    expect(result).toContain('Left methods.')
    expect(result).not.toContain('Right intro.')
    expect(result).not.toContain('Right methods.')
  })

  it('picks right content when choice is right', () => {
    const left = '\\section{Intro}\nLeft intro.\n\\section{Methods}\nLeft methods.'
    const right = '\\section{Intro}\nRight intro.\n\\section{Methods}\nRight methods.'
    const result = mergeLatex(base, left, right, {
      '1:Intro': 'right',
      '2:Methods': 'right',
    })
    expect(result).toContain('Right intro.')
    expect(result).toContain('Right methods.')
    expect(result).not.toContain('Left intro.')
    expect(result).not.toContain('Left methods.')
  })

  it('produces conflict markers when choice is both', () => {
    const left = '\\section{Intro}\nLeft version.'
    const right = '\\section{Intro}\nRight version.'
    const result = mergeLatex(base, left, right, { '1:Intro': 'both' })
    expect(result).toContain('% >>>>>> SOURCE')
    expect(result).toContain('Left version.')
    expect(result).toContain('% ======')
    expect(result).toContain('Right version.')
    expect(result).toContain('% <<<<<< TARGET')
  })

  it('includes sections present in only one side', () => {
    const left = '\\section{Intro}\nIntro text.\n\\section{Background}\nOnly in left.'
    const right = '\\section{Intro}\nIntro text.\n\\section{Results}\nOnly in right.'
    const result = mergeLatex(base, left, right, {})
    expect(result).toContain('\\section{Background}')
    expect(result).toContain('Only in left.')
    expect(result).toContain('\\section{Results}')
    expect(result).toContain('Only in right.')
  })
})
