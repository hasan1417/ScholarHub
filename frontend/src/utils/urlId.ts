/**
 * Utility functions for URL-friendly IDs.
 */

import type { ProjectSummary, ProjectDetail, ResearchPaper } from '../types'

/**
 * Get the URL-friendly ID for a project.
 * Falls back to regular ID if url_id is not available.
 */
export function getProjectUrlId(project: ProjectSummary | ProjectDetail | { id: string; url_id?: string }): string {
  return project.url_id || project.id
}

/**
 * Get the URL-friendly ID for a paper.
 * Falls back to regular ID if url_id is not available.
 */
export function getPaperUrlId(paper: ResearchPaper | { id: string; url_id?: string }): string {
  return paper.url_id || paper.id
}

/**
 * Build a project URL path.
 */
export function projectPath(project: { id: string; url_id?: string }, subpath?: string): string {
  const urlId = project.url_id || project.id
  return subpath ? `/projects/${urlId}/${subpath}` : `/projects/${urlId}`
}

/**
 * Build a paper URL path within a project.
 */
export function paperPath(
  project: { id: string; url_id?: string },
  paper: { id: string; url_id?: string },
  subpath?: string
): string {
  const projectUrlId = project.url_id || project.id
  const paperUrlId = paper.url_id || paper.id
  const base = `/projects/${projectUrlId}/papers/${paperUrlId}`
  return subpath ? `${base}/${subpath}` : base
}
