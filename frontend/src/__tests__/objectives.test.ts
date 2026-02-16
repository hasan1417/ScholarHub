import { describe, it, expect } from 'vitest'
import { parseObjectives } from '../utils/objectives'

describe('parseObjectives', () => {
  it('returns empty array for null input', () => {
    expect(parseObjectives(null)).toEqual([])
  })

  it('returns empty array for undefined input', () => {
    expect(parseObjectives(undefined)).toEqual([])
  })

  it('returns empty array for empty string', () => {
    expect(parseObjectives('')).toEqual([])
  })

  it('splits on newlines', () => {
    const result = parseObjectives('Objective one\nObjective two\nObjective three')
    expect(result).toEqual(['Objective one', 'Objective two', 'Objective three'])
  })

  it('splits on bullet characters', () => {
    const result = parseObjectives('First item\u2022Second item\u2022Third item')
    // \u2022 is the bullet character
    expect(result).toHaveLength(3)
  })

  it('strips numbered prefixes (1. 2. etc)', () => {
    const result = parseObjectives('1. First\n2. Second\n3. Third')
    expect(result).toEqual(['First', 'Second', 'Third'])
  })

  it('strips numbered prefixes with parentheses (1) 2) etc)', () => {
    const result = parseObjectives('1) First\n2) Second')
    expect(result).toEqual(['First', 'Second'])
  })

  it('strips numbered prefixes with dash (1- 2- etc)', () => {
    const result = parseObjectives('1- First\n2- Second')
    expect(result).toEqual(['First', 'Second'])
  })

  it('filters out empty lines', () => {
    const result = parseObjectives('First\n\n\nSecond\n\n')
    expect(result).toEqual(['First', 'Second'])
  })

  it('handles Windows-style line endings', () => {
    const result = parseObjectives('First\r\nSecond\r\nThird')
    expect(result).toEqual(['First', 'Second', 'Third'])
  })
})
