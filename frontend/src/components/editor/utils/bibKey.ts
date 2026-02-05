/**
 * Generate BibTeX key from reference
 * Format: {lastAuthorName}{year}{shortTitle}
 */
export function makeBibKey(ref: any): string {
  try {
    const first = (Array.isArray(ref.authors) && ref.authors.length > 0) ? String(ref.authors[0]) : ''
    const lastToken = first.split(/\s+/).filter(Boolean).slice(-1)[0] || ''
    const last = lastToken.toLowerCase()
    const yr = ref.year ? String(ref.year) : ''
    const base = (ref.title || '').toLowerCase().replace(/[^a-z0-9\s]/g, ' ')
    const parts = base.split(/\s+/).filter(Boolean)
    const short = (parts.slice(0, 3).join('')).slice(0, 12)
    const key = (last + yr + short) || ('ref' + yr)
    return key
  } catch {
    return 'ref'
  }
}
