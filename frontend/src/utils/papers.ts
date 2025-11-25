export const normalizePaperTitle = (value: string) => {
  return value.trim().replace(/\s+/g, ' ')
}

export const hasDuplicatePaperTitle = (
  existingTitles: Array<{ title?: string | null; projectId?: string | null }>,
  titleToCheck: string,
  projectId?: string | null,
) => {
  const normalizedTarget = normalizePaperTitle(titleToCheck).toLowerCase()
  if (!normalizedTarget) return false

  return existingTitles.some((item) => {
    const normalizedExisting = normalizePaperTitle(item.title ?? '').toLowerCase()
    if (!normalizedExisting) return false
    if (projectId) {
      return normalizedExisting === normalizedTarget && item.projectId === projectId
    }
    return normalizedExisting === normalizedTarget && (!item.projectId || item.projectId === null)
  })
}
