import { describe, it, expect } from 'vitest'
import { getProjectUrlId, getPaperUrlId, projectPath, paperPath } from '../utils/urlId'

describe('getProjectUrlId', () => {
  it('returns url_id when available', () => {
    const project = { id: 'uuid-123', url_id: 'my-project' }
    expect(getProjectUrlId(project)).toBe('my-project')
  })

  it('falls back to id when url_id is absent', () => {
    const project = { id: 'uuid-123' }
    expect(getProjectUrlId(project)).toBe('uuid-123')
  })

  it('falls back to id when url_id is empty string', () => {
    const project = { id: 'uuid-123', url_id: '' }
    expect(getProjectUrlId(project)).toBe('uuid-123')
  })
})

describe('getPaperUrlId', () => {
  it('returns url_id when available', () => {
    const paper = { id: 'uuid-456', url_id: 'my-paper' }
    expect(getPaperUrlId(paper)).toBe('my-paper')
  })

  it('falls back to id when url_id is absent', () => {
    const paper = { id: 'uuid-456' }
    expect(getPaperUrlId(paper)).toBe('uuid-456')
  })
})

describe('projectPath', () => {
  it('builds base project path', () => {
    const project = { id: 'uuid-1', url_id: 'cool-project' }
    expect(projectPath(project)).toBe('/projects/cool-project')
  })

  it('builds project path with subpath', () => {
    const project = { id: 'uuid-1', url_id: 'cool-project' }
    expect(projectPath(project, 'papers')).toBe('/projects/cool-project/papers')
  })

  it('uses id when url_id is not set', () => {
    const project = { id: 'uuid-1' }
    expect(projectPath(project, 'settings')).toBe('/projects/uuid-1/settings')
  })
})

describe('paperPath', () => {
  it('builds full paper path', () => {
    const project = { id: 'p1', url_id: 'proj-slug' }
    const paper = { id: 'r1', url_id: 'paper-slug' }
    expect(paperPath(project, paper)).toBe('/projects/proj-slug/papers/paper-slug')
  })

  it('builds paper path with subpath', () => {
    const project = { id: 'p1', url_id: 'proj-slug' }
    const paper = { id: 'r1', url_id: 'paper-slug' }
    expect(paperPath(project, paper, 'edit')).toBe('/projects/proj-slug/papers/paper-slug/edit')
  })

  it('falls back to ids when url_ids are missing', () => {
    const project = { id: 'p1' }
    const paper = { id: 'r1' }
    expect(paperPath(project, paper)).toBe('/projects/p1/papers/r1')
  })
})
