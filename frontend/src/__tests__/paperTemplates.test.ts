import { describe, it, expect } from 'vitest'
import { PAPER_TEMPLATES } from '../constants/paperTemplates'
import type { PaperTemplateDefinition } from '../constants/paperTemplates'

describe('PAPER_TEMPLATES', () => {
  it('is a non-empty array', () => {
    expect(PAPER_TEMPLATES.length).toBeGreaterThan(0)
  })

  it('each template has required fields', () => {
    for (const template of PAPER_TEMPLATES) {
      expect(template.id).toBeTruthy()
      expect(template.label).toBeTruthy()
      expect(template.description).toBeTruthy()
      expect(template.sections.length).toBeGreaterThan(0)
      expect(template.latexTemplate).toBeTruthy()
    }
  })

  it('template ids are unique', () => {
    const ids = PAPER_TEMPLATES.map((t: PaperTemplateDefinition) => t.id)
    const uniqueIds = new Set(ids)
    expect(uniqueIds.size).toBe(ids.length)
  })

  it('includes a research paper template', () => {
    const research = PAPER_TEMPLATES.find((t: PaperTemplateDefinition) => t.id === 'research')
    expect(research).toBeDefined()
    expect(research!.sections).toContain('Abstract')
    expect(research!.sections).toContain('Introduction')
  })

  it('latex templates contain \\documentclass', () => {
    for (const template of PAPER_TEMPLATES) {
      expect(template.latexTemplate).toContain('\\documentclass')
    }
  })

  it('latex templates contain \\begin{document} and \\end{document}', () => {
    for (const template of PAPER_TEMPLATES) {
      expect(template.latexTemplate).toContain('\\begin{document}')
      expect(template.latexTemplate).toContain('\\end{document}')
    }
  })
})
