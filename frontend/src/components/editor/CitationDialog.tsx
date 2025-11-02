import React, { useState, useEffect, useRef } from 'react'
import { Search, X, BookOpen } from 'lucide-react'
import { projectReferencesAPI, researchPapersAPI } from '../../services/api'

interface ReferenceItem {
  id: string
  title: string
  authors?: string[]
  year?: number
  doi?: string
  url?: string
  source?: string
  journal?: string
  abstract?: string
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

// Generate BibTeX key from reference
function makeBibKey(ref: ReferenceItem): string {
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

  // Load references
  useEffect(() => {
    if (!isOpen) return

    const loadReferences = async () => {
      setIsLoading(true)
      try {
        if (projectId) {
          const response = await projectReferencesAPI.listPaperReferences(projectId, paperId)
          const refs = response.data?.references || []
          setReferences(refs)
        } else {
          const response = await researchPapersAPI.listReferences(paperId)
          const refs = response.data?.references || []
          setReferences(refs)
        }
      } catch (error) {
        console.error('Failed to load references:', error)
      } finally {
        setIsLoading(false)
      }
    }

    loadReferences()
  }, [isOpen, paperId, projectId])

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

  if (!isOpen || !position) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/20"
        onClick={handleClose}
      />

      {/* Dialog */}
      <div
        ref={dialogRef}
        className="fixed z-50 w-[600px] rounded-lg bg-white shadow-2xl"
        style={{ top: position.top, left: position.left }}
      >
        {/* Header */}
        <div className="border-b border-gray-200">
          <div className="flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-gray-700" />
              <h3 className="text-sm font-semibold text-gray-900">References</h3>
            </div>
            <button
              onClick={handleClose}
              className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Bibliography Style Selector */}
          <div className="flex items-center gap-2 border-t border-gray-100 bg-gray-50 px-4 py-2">
            <label className="text-xs font-medium text-gray-600">Bibliography Style:</label>
            <select
              value={bibliographyStyle}
              onChange={(e) => setBibliographyStyle(e.target.value)}
              className="flex-1 rounded border border-gray-300 px-2 py-1 text-xs text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
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
        <div className="border-b border-gray-200 p-2">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search references..."
              className="w-full rounded border border-gray-300 py-1.5 pl-8 pr-2 text-xs text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
        </div>

        {/* Reference List */}
        <div className="max-h-[300px] overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-sm text-gray-500">Loading references...</div>
            </div>
          ) : filteredReferences.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <BookOpen className="mb-2 h-8 w-8 text-gray-300" />
              <p className="text-sm font-medium text-gray-900">
                {searchTerm ? 'No matching references' : 'No references yet'}
              </p>
              <p className="mt-1 text-xs text-gray-500">
                {searchTerm ? 'Try a different search term' : 'Add references to your project first'}
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {filteredReferences.map((ref) => (
                  <div
                    key={ref.id}
                    className="px-3 py-2 transition-colors hover:bg-gray-50"
                  >
                    <div className="flex items-start gap-2">
                      {/* Reference Info */}
                      <div className="flex-1 min-w-0">
                        <h4 className="text-xs font-medium text-gray-900 line-clamp-1">
                          {ref.title}
                        </h4>
                        <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[10px] text-gray-600">
                          {ref.authors && ref.authors.length > 0 && (
                            <span className="line-clamp-1">
                              {ref.authors[0]}
                              {ref.authors.length > 1 && ' et al.'}
                            </span>
                          )}
                          {ref.year && (
                            <>
                              <span className="text-gray-400">•</span>
                              <span>{ref.year}</span>
                            </>
                          )}
                        </div>
                      </div>

                      {/* Insert Citation Button */}
                      <button
                        onClick={() => handleInsertCitation(ref)}
                        className="flex-shrink-0 rounded border border-gray-300 bg-white px-2 py-1 text-[10px] font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                        title="Insert citation"
                      >
                        Insert Citation
                      </button>
                    </div>
                  </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-gray-200 bg-gray-50 px-3 py-2">
          <div className="text-[10px] text-gray-500">
            {filteredReferences.length} refs
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleClose}
              className="rounded border border-gray-300 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-100"
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
