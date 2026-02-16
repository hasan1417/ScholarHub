import { describe, it, expect } from 'vitest'
import { normalizePaperTitle, hasDuplicatePaperTitle } from '../utils/papers'

describe('normalizePaperTitle', () => {
  it('trims leading and trailing whitespace', () => {
    expect(normalizePaperTitle('  Hello World  ')).toBe('Hello World')
  })

  it('collapses multiple internal spaces', () => {
    expect(normalizePaperTitle('A   Study  on   AI')).toBe('A Study on AI')
  })

  it('handles empty string', () => {
    expect(normalizePaperTitle('')).toBe('')
  })

  it('handles single word', () => {
    expect(normalizePaperTitle('  AI  ')).toBe('AI')
  })
})

describe('hasDuplicatePaperTitle', () => {
  const existing = [
    { title: 'Machine Learning Basics', projectId: 'proj-1' },
    { title: 'Deep Dive Into NLP', projectId: 'proj-2' },
    { title: 'Standalone Paper', projectId: null },
  ]

  it('detects duplicate within same project', () => {
    expect(hasDuplicatePaperTitle(existing, 'Machine Learning Basics', 'proj-1')).toBe(true)
  })

  it('is case-insensitive', () => {
    expect(hasDuplicatePaperTitle(existing, 'machine learning basics', 'proj-1')).toBe(true)
  })

  it('ignores different projects', () => {
    expect(hasDuplicatePaperTitle(existing, 'Machine Learning Basics', 'proj-2')).toBe(false)
  })

  it('matches papers with null projectId when no project specified', () => {
    expect(hasDuplicatePaperTitle(existing, 'Standalone Paper')).toBe(true)
  })

  it('returns false for non-existing title', () => {
    expect(hasDuplicatePaperTitle(existing, 'Quantum Computing Survey', 'proj-1')).toBe(false)
  })

  it('handles extra whitespace in title', () => {
    expect(hasDuplicatePaperTitle(existing, '  Machine   Learning  Basics ', 'proj-1')).toBe(true)
  })

  it('returns false for empty title', () => {
    expect(hasDuplicatePaperTitle(existing, '')).toBe(false)
  })
})
