import { useState, useCallback } from 'react'
import { researchPapersAPI } from '../../../services/api'
import { makeBibKey } from '../utils/bibKey'

interface UseCitationHandlersOptions {
  paperId?: string
  readOnly: boolean
  insertSnippet: (snippet: string, placeholder?: string) => void
  insertAtDocumentEnd: (snippet: string, placeholder?: string) => void
}

export function useCitationHandlers({
  paperId, readOnly, insertSnippet, insertAtDocumentEnd,
}: UseCitationHandlersOptions) {
  const [citationDialogOpen, setCitationDialogOpen] = useState(false)
  const [citationAnchor, setCitationAnchor] = useState<HTMLElement | null>(null)

  const handleOpenReferencesToolbar = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    if (readOnly) return
    setCitationAnchor(event.currentTarget)
    setCitationDialogOpen(true)
  }, [readOnly])

  const handleCloseCitationDialog = useCallback(() => {
    setCitationDialogOpen(false)
  }, [])

  const handleInsertCitation = useCallback((citationKey: string, _references?: any[]) => {
    const cite = `\\cite{${citationKey}}`
    insertSnippet(cite, citationKey)
  }, [insertSnippet])

  const handleInsertBibliography = useCallback(async (style: string, bibFile: string, references: any[]) => {
    const bibContent = references.map(ref => {
      const key = makeBibKey(ref)
      const authors = ref.authors?.join(' and ') || ''
      const title = ref.title || ''
      const year = ref.year || ''
      const journal = ref.journal || ''
      const doi = ref.doi || ''

      return `@article{${key},
  author = {${authors}},
  title = {${title}},
  year = {${year}},
  journal = {${journal}},
  doi = {${doi}}
}`
    }).join('\n\n')

    try {
      const formData = new FormData()
      const bibFileObj = new File([bibContent], `${bibFile}.bib`, {
        type: 'application/x-bibtex'
      })
      formData.append('file', bibFileObj)
      await researchPapersAPI.uploadBib(paperId!, formData)
      const snippet = `\\clearpage\n% Bibliography\n\\bibliographystyle{${style}}\n\\bibliography{${bibFile}}\n`
      insertAtDocumentEnd(snippet, bibFile)
    } catch (error: any) {
      console.error('Failed to upload .bib file:', error)
      const detail = error.response?.data?.detail
      const message = Array.isArray(detail)
        ? detail.map((d: any) => `${d.loc?.join('.') || 'unknown'}: ${d.msg}`).join(', ')
        : (detail || error.message || 'Upload failed')
      alert(`Failed to upload bibliography file. ${message}`)
    }
  }, [paperId, insertAtDocumentEnd])

  return {
    citationDialogOpen,
    citationAnchor,
    handleOpenReferencesToolbar,
    handleCloseCitationDialog,
    handleInsertCitation,
    handleInsertBibliography,
  }
}
