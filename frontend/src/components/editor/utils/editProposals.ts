/** Proposed edit from AI - line-based for reliable matching */
export interface EditProposal {
  id: string
  description: string
  startLine: number
  endLine: number
  anchor: string
  proposed: string
  status: 'pending' | 'approved' | 'rejected' | 'expired'
  file?: string
}

/**
 * Parse <<<EDIT>>> blocks from AI text.
 * Format: <<<EDIT>>> description [<<<FILE>>> filename] <<<LINES>>> start-end <<<ANCHOR>>> text <<<PROPOSED>>> text <<<END>>>
 */
export function parseEditProposals(text: string): { cleanText: string; proposals: EditProposal[] } {
  const proposals: EditProposal[] = []
  const editRegex = /<<<EDIT>>>\s*([\s\S]*?)(?:<<<FILE>>>\s*([\s\S]*?))?\s*<<<LINES>>>\s*([\s\S]*?)<<<ANCHOR>>>\s*([\s\S]*?)<<<PROPOSED>>>\s*([\s\S]*?)<<<END>>>/g
  let match
  let cleanText = text

  while ((match = editRegex.exec(text)) !== null) {
    const fullMatch = match[0]
    const description = match[1]
    const file = match[2]?.trim() || undefined
    const linesStr = match[3]
    const anchor = match[4]
    const proposed = match[5]
    const linesParts = linesStr.trim().split('-')
    const startLine = parseInt(linesParts[0], 10) || 1
    const endLine = parseInt(linesParts[1] || linesParts[0], 10) || startLine

    proposals.push({
      id: `edit-${Date.now()}-${proposals.length}`,
      description: description.trim(),
      startLine,
      endLine,
      anchor: anchor.trim(),
      proposed: proposed.trim(),
      status: 'pending',
      file,
    })
    cleanText = cleanText.replace(fullMatch, '')
  }

  return { cleanText: cleanText.trim(), proposals }
}
