import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Search, X, BookOpen, Upload } from 'lucide-react'
import api, { projectReferencesAPI, researchPapersAPI } from '../../services/api'
import { makeBibKey } from './utils/bibKey'

interface ReferenceItem {
  id: string
  referenceId?: string
  title: string
  authors?: string[]
  year?: number
  doi?: string
  url?: string
  source?: string
  journal?: string
  abstract?: string
  pdfUrl?: string | null
  pdfProcessed?: boolean | null
  documentId?: string | null
  documentStatus?: string | null
  documentDownloadUrl?: string | null
}

interface CitationDialogProps {
  isOpen: boolean
  onClose: () => void
  paperId: string
  projectId?: string
  onInsertCitation: (citationKey: string, references: ReferenceItem[]) => void
  onInsertBibliography?: (style: string, bibFile: string, references: ReferenceItem[]) => void
  anchorElement: HTMLElement | null
}

const CitationDialog: React.FC<CitationDialogProps> = ({
  isOpen,
  onClose,
  paperId,
  projectId,
  onInsertCitation,
  onInsertBibliography,
  anchorElement,
}) => {
  const [references, setReferences] = useState<ReferenceItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null)
  const [bibliographyStyle, setBibliographyStyle] = useState('plain')
  const [bibFile] = useState('main')
  const [uploading, setUploading] = useState<Record<string, boolean>>({})
  const [uploadError, setUploadError] = useState<string | null>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)

  const bibliographyStyles = [
    { value: 'plain', label: 'Plain', description: 'Numbered [1], [2]' },
    { value: 'alpha', label: 'Alpha', description: 'Author-year [Knu84]' },
    { value: 'abbrv', label: 'Abbreviated', description: 'Short format' },
    { value: 'unsrt', label: 'Unsorted', description: 'Order of citation' },
    { value: 'ieee', label: 'IEEE', description: 'IEEE style [1]' },
    { value: 'acm', label: 'ACM', description: 'ACM style' },
    { value: 'apalike', label: 'APA-like', description: '(Author, Year)' },
    { value: 'chicago', label: 'Chicago', description: 'Chicago style' },
  ]

  const normalizeReferences = useCallback((refs: any[]): ReferenceItem[] => {
    return (refs || []).map((ref: any, index: number) => {
      const referenceId = String(ref.reference_id ?? ref.id ?? ref.referenceId ?? '')
      const id = String(ref.id ?? ref.reference_id ?? ref.referenceId ?? index)
      return {
        id,
        referenceId: referenceId || id,
        title: ref.title || ref.citation || ref.original_title || 'Untitled reference',
        authors: ref.authors,
        year: ref.year,
        doi: ref.doi,
        url: ref.url,
        source: ref.source,
        journal: ref.journal,
        abstract: ref.abstract,
        pdfUrl: ref.pdf_url ?? ref.pdfUrl ?? null,
        pdfProcessed: ref.pdf_processed ?? ref.pdfProcessed ?? null,
        documentId: ref.document_id ?? ref.documentId ?? null,
        documentStatus: ref.document_status ?? ref.documentStatus ?? null,
        documentDownloadUrl: ref.document_download_url ?? ref.documentDownloadUrl ?? null,
      }
    })
  }, [])

  const loadReferences = useCallback(async () => {
    setIsLoading(true)
    try {
      if (projectId) {
        const response = await projectReferencesAPI.listPaperReferences(projectId, paperId)
        const refs = normalizeReferences(response.data?.references || [])
        setReferences(refs)
      } else {
        const response = await researchPapersAPI.listReferences(paperId)
        const refs = normalizeReferences(response.data?.references || [])
        setReferences(refs)
      }
    } catch (error) {
      console.error('Failed to load references:', error)
    } finally {
      setIsLoading(false)
    }
  }, [normalizeReferences, paperId, projectId])

  // Load references
  useEffect(() => {
    if (!isOpen) return
    loadReferences()
  }, [isOpen, loadReferences])

  // Calculate position relative to anchor
  useEffect(() => {
    if (!isOpen || !anchorElement) {
      setPosition(null)
      return
    }

    const updatePosition = () => {
      const rect = anchorElement.getBoundingClientRect()
      const dialogWidth = 600
      const dialogHeight = 500
      const spacing = 8

      let top = rect.bottom + spacing
      let left = rect.left

      // Adjust if dialog goes off-screen
      if (left + dialogWidth > window.innerWidth) {
        left = window.innerWidth - dialogWidth - 20
      }
      if (top + dialogHeight > window.innerHeight) {
        top = rect.top - dialogHeight - spacing
      }

      setPosition({ top, left })
    }

    updatePosition()
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition)

    return () => {
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition)
    }
  }, [isOpen, anchorElement])

  // Focus search input when opened
  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      setTimeout(() => searchInputRef.current?.focus(), 100)
    }
  }, [isOpen])

  // Filter references based on search
  const filteredReferences = references.filter(ref => {
    if (!searchTerm.trim()) return true
    const search = searchTerm.toLowerCase()
    return (
      ref.title?.toLowerCase().includes(search) ||
      ref.authors?.some(a => a.toLowerCase().includes(search)) ||
      ref.year?.toString().includes(search) ||
      ref.journal?.toLowerCase().includes(search)
    )
  })

  const handleInsertCitation = (ref: ReferenceItem) => {
    const bibKey = makeBibKey(ref)
    onInsertCitation(bibKey, [ref])
    handleClose()
  }

  const handleClose = () => {
    setSearchTerm('')
    onClose()
  }

  const handleUploadPdf = async (ref: ReferenceItem, file: File | null) => {
    if (!file) return
    const referenceId = ref.referenceId || ref.id
    if (!referenceId) return
    setUploadError(null)
    setUploading((prev) => ({ ...prev, [referenceId]: true }))
    try {
      const formData = new FormData()
      formData.append('file', file)
      await api.post(`/references/${referenceId}/upload-pdf`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      await loadReferences()
    } catch (error: any) {
      console.error('Failed to upload PDF:', error)
      setUploadError(error?.message || 'Failed to upload PDF.')
    } finally {
      setUploading((prev) => ({ ...prev, [referenceId]: false }))
    }
  }

  const handleViewPdf = async (downloadUrl: string) => {
    try {
      const token = localStorage.getItem('access_token')
      if (!token) {
        alert('Please login again to download the PDF')
        return
      }
      // downloadUrl from backend is already /api/v1/documents/{id}/download
      // Use origin + path directly to avoid double /api/v1 from buildApiUrl
      const url = downloadUrl.startsWith('http')
        ? downloadUrl
        : `${window.location.origin}${downloadUrl.startsWith('/') ? downloadUrl : '/' + downloadUrl}`
      const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      if (!resp.ok) {
        throw new Error(`Download failed (${resp.status})`)
      }
      const blob = await resp.blob()
      const objectUrl = URL.createObjectURL(blob)
      window.open(objectUrl, '_blank')
      setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000)
    } catch (error) {
      console.error('Failed to open PDF', error)
      alert('Failed to open PDF')
    }
  }

  if (!isOpen || !position) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/20 dark:bg-black/40"
        onClick={handleClose}
      />

      {/* Dialog */}
      <div
        ref={dialogRef}
        className="fixed z-50 w-[600px] rounded-lg bg-white shadow-2xl border border-gray-200 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        style={{ top: position.top, left: position.left }}
      >
        {/* Header */}
        <div className="border-b border-gray-200 dark:border-slate-700">
          <div className="flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-2 text-gray-900 dark:text-slate-100">
              <BookOpen className="h-5 w-5 text-gray-700 dark:text-slate-200" />
              <h3 className="text-sm font-semibold">References</h3>
            </div>
            <button
              onClick={handleClose}
              className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Bibliography Style Selector */}
          <div className="flex items-center gap-2 border-t border-gray-100 bg-gray-50 px-4 py-2 dark:border-slate-700 dark:bg-slate-800">
            <label className="text-xs font-medium text-gray-600 dark:text-slate-300">Bibliography Style:</label>
            <select
              value={bibliographyStyle}
              onChange={(e) => setBibliographyStyle(e.target.value)}
              className="flex-1 rounded border border-gray-300 px-2 py-1 text-xs text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:focus:border-blue-400 dark:focus:ring-blue-400/40"
            >
              {bibliographyStyles.map((style) => (
                <option key={style.value} value={style.value}>
                  {style.label} - {style.description}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Search */}
        <div className="border-b border-gray-200 p-2 dark:border-slate-700">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400 dark:text-slate-500" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search references..."
              className="w-full rounded border border-gray-300 py-1.5 pl-8 pr-2 text-xs text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-blue-400 dark:focus:ring-blue-400/40"
            />
          </div>
        </div>

        {uploadError && (
          <div className="border-b border-gray-200 px-3 py-2 text-[11px] text-rose-600 dark:border-slate-700 dark:text-rose-300">
            {uploadError}
          </div>
        )}

        {/* Reference List */}
        <div className="max-h-[300px] overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-sm text-gray-500 dark:text-slate-400">Loading references...</div>
            </div>
          ) : filteredReferences.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <BookOpen className="mb-2 h-8 w-8 text-gray-300 dark:text-slate-600" />
              <p className="text-sm font-medium text-gray-900 dark:text-slate-100">
                {searchTerm ? 'No matching references' : 'No references yet'}
              </p>
              <p className="mt-1 text-xs text-gray-500 dark:text-slate-400">
                {searchTerm ? 'Try a different search term' : 'Add references to your project first'}
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-slate-700">
              {filteredReferences.map((ref) => {
                const uploadKey = ref.referenceId || ref.id
                const hasMetaPrefix = Boolean(ref.authors?.length || ref.year)
                const hasFullText = Boolean(
                  ref.pdfProcessed ||
                    ref.documentStatus === 'processed' ||
                    ref.documentId
                )
                const isProcessing = ref.documentStatus === 'processing' || ref.documentStatus === 'uploading'
                const hasPdfLink = Boolean(ref.pdfUrl)
                return (
                  <div
                    key={ref.id}
                    className="px-3 py-2 transition-colors hover:bg-gray-50 dark:hover:bg-slate-800"
                  >
                    <div className="flex items-start gap-2">
                      {/* Reference Info */}
                      <div className="flex-1 min-w-0">
                        <h4 className="text-xs font-medium text-gray-900 line-clamp-1 dark:text-slate-100">
                          {ref.title}
                        </h4>
                        <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[10px] text-gray-600 dark:text-slate-300">
                          {ref.authors && ref.authors.length > 0 && (
                            <span className="line-clamp-1">
                              {ref.authors[0]}
                              {ref.authors.length > 1 && ' et al.'}
                            </span>
                          )}
                          {ref.year && (
                            <>
                              <span className="text-gray-400 dark:text-slate-500">•</span>
                              <span>{ref.year}</span>
                            </>
                          )}
                          {hasMetaPrefix && <span className="text-gray-400 dark:text-slate-500">•</span>}
                          {hasFullText ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[9px] font-medium text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-200">
                              Full text ready
                            </span>
                          ) : isProcessing ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-1.5 py-0.5 text-[9px] font-medium text-amber-700 dark:bg-amber-500/20 dark:text-amber-200">
                              Processing
                            </span>
                          ) : hasPdfLink ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-sky-100 px-1.5 py-0.5 text-[9px] font-medium text-sky-700 dark:bg-sky-500/20 dark:text-sky-200">
                              PDF linked
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-1.5 py-0.5 text-[9px] font-medium text-amber-700 dark:bg-amber-500/20 dark:text-amber-200">
                              PDF missing
                            </span>
                          )}
                          {ref.documentDownloadUrl && (
                            <button
                              type="button"
                              onClick={() => handleViewPdf(ref.documentDownloadUrl as string)}
                              className="inline-flex items-center gap-1 rounded border border-indigo-200 bg-indigo-50 px-1.5 py-0.5 text-[9px] font-medium text-indigo-700 hover:bg-indigo-100 dark:border-indigo-400/40 dark:bg-indigo-500/10 dark:text-indigo-200"
                            >
                              View PDF
                            </button>
                          )}
                          {!hasFullText && (
                            <label
                              htmlFor={`upload-pdf-${ref.id}`}
                              className="inline-flex items-center gap-1 rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[9px] font-medium text-amber-700 hover:bg-amber-100 cursor-pointer dark:border-amber-400/40 dark:bg-amber-500/10 dark:text-amber-200"
                              onClick={(event) => event.stopPropagation()}
                            >
                              <Upload className="h-3 w-3" />
                              {uploading[uploadKey] ? 'Uploading...' : 'Upload PDF'}
                              <input
                                id={`upload-pdf-${ref.id}`}
                                type="file"
                                accept="application/pdf"
                                className="hidden"
                                disabled={uploading[uploadKey]}
                                onChange={(event) => {
                                  const file = event.target.files?.[0] || null
                                  void handleUploadPdf(ref, file)
                                  event.currentTarget.value = ''
                                }}
                              />
                            </label>
                          )}
                        </div>
                      </div>

                      {/* Insert Citation Button */}
                      <button
                        onClick={() => handleInsertCitation(ref)}
                        className="flex-shrink-0 rounded border border-gray-300 bg-white px-2 py-1 text-[10px] font-medium text-gray-700 hover:bg-gray-50 transition-colors dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
                        title="Insert citation"
                      >
                        Insert Citation
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-gray-200 bg-gray-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-800">
          <div className="text-[10px] text-gray-500 dark:text-slate-400">
            {filteredReferences.length} refs
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleClose}
              className="rounded border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-100 dark:border-slate-600 dark:text-slate-100 dark:hover:bg-slate-700"
            >
              Cancel
            </button>
            <button
              onClick={() => {
                if (onInsertBibliography) {
                  onInsertBibliography(bibliographyStyle, bibFile, references)
                  handleClose()
                }
              }}
              className="inline-flex items-center gap-1 rounded bg-blue-600 px-2 py-1 text-xs font-medium text-white hover:bg-blue-700"
            >
              <BookOpen className="h-3 w-3" />
              Insert Bibliography
            </button>
          </div>
        </div>
      </div>
    </>
  )
}

export default CitationDialog
