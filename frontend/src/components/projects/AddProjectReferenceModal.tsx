import React, { useState, useRef } from 'react'
import { X, Upload, FileText, Link2, BookOpen, ChevronDown, ChevronUp, Search, Loader2, CheckCircle2 } from 'lucide-react'

type AddProjectReferenceModalProps = {
  isOpen: boolean
  onClose: () => void
  onSubmit: (payload: {
    title: string
    authors?: string[]
    year?: number
    doi?: string
    url?: string
    journal?: string
    abstract?: string
    pdfFile?: File | null
  }) => Promise<void>
  title?: string
}

const AddProjectReferenceModal: React.FC<AddProjectReferenceModalProps> = ({ isOpen, onClose, onSubmit, title: heading = 'Add Reference' }) => {
  const [title, setTitle] = useState('')
  const [authors, setAuthors] = useState('')
  const [year, setYear] = useState('')
  const [doi, setDoi] = useState('')
  const [url, setUrl] = useState('')
  const [journal, setJournal] = useState('')
  const [abstractText, setAbstractText] = useState('')
  const [pdfFile, setPdfFile] = useState<File | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showOptional, setShowOptional] = useState(false)
  const [isLookingUp, setIsLookingUp] = useState(false)
  const [lookupSuccess, setLookupSuccess] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const resetForm = () => {
    setTitle('')
    setAuthors('')
    setYear('')
    setDoi('')
    setUrl('')
    setJournal('')
    setAbstractText('')
    setPdfFile(null)
    setError(null)
    setShowOptional(false)
    setLookupSuccess(false)
  }

  const handleClose = () => {
    if (isSubmitting) return
    resetForm()
    onClose()
  }

  const handleDoiLookup = async () => {
    if (!doi.trim()) return

    setIsLookingUp(true)
    setError(null)
    setLookupSuccess(false)

    try {
      // Clean up DOI - extract just the DOI part if full URL is provided
      let cleanDoi = doi.trim()
      if (cleanDoi.includes('doi.org/')) {
        cleanDoi = cleanDoi.split('doi.org/')[1]
      }

      const response = await fetch(`https://api.crossref.org/works/${encodeURIComponent(cleanDoi)}`)
      if (!response.ok) throw new Error('DOI not found')

      const data = await response.json()
      const work = data.message

      if (work.title?.[0]) setTitle(work.title[0])
      if (work.author) {
        const authorNames = work.author.map((a: { given?: string; family?: string }) =>
          [a.given, a.family].filter(Boolean).join(' ')
        ).filter(Boolean)
        setAuthors(authorNames.join(', '))
      }
      if (work.published?.['date-parts']?.[0]?.[0]) {
        setYear(String(work.published['date-parts'][0][0]))
      } else if (work['published-print']?.['date-parts']?.[0]?.[0]) {
        setYear(String(work['published-print']['date-parts'][0][0]))
      }
      if (work['container-title']?.[0]) setJournal(work['container-title'][0])
      if (work.abstract) {
        // Clean HTML from abstract
        const cleanAbstract = work.abstract.replace(/<[^>]*>/g, '').trim()
        setAbstractText(cleanAbstract)
      }
      if (work.URL) setUrl(work.URL)
      setDoi(cleanDoi)

      setLookupSuccess(true)
      setTimeout(() => setLookupSuccess(false), 3000)
    } catch (err) {
      setError('Could not find paper with this DOI. Please enter details manually.')
    } finally {
      setIsLookingUp(false)
    }
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!title.trim()) {
      setError('Title is required')
      return
    }

    setIsSubmitting(true)
    setError(null)
    try {
      await onSubmit({
        title: title.trim(),
        authors: authors
          .split(',')
          .map((a) => a.trim())
          .filter(Boolean),
        year: year ? Number(year) : undefined,
        doi: doi || undefined,
        url: url || undefined,
        journal: journal || undefined,
        abstract: abstractText || undefined,
        pdfFile,
      })
      resetForm()
      onClose()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      if (typeof detail === 'string') {
        setError(detail)
      } else if (detail?.message) {
        setError(detail.message)
      } else {
        setError(err.message || 'Unable to add reference right now.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file && file.type === 'application/pdf') {
      setPdfFile(file)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 dark:bg-black/60">
      <div className="w-full max-w-xl overflow-hidden rounded-2xl bg-white shadow-2xl transition-colors dark:bg-slate-800">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4 dark:border-slate-700">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-100 dark:bg-indigo-500/20">
              <BookOpen className="h-5 w-5 text-indigo-600 dark:text-indigo-300" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">{heading}</h2>
              <p className="text-xs text-gray-500 dark:text-slate-400">Add a paper to your library</p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-full p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
            title="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="max-h-[70vh] overflow-y-auto">
          <div className="space-y-5 px-6 py-5">
            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-200">
                {error}
              </div>
            )}

            {/* Quick DOI Lookup */}
            <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-4 dark:border-indigo-500/30 dark:bg-indigo-950/30">
              <div className="flex items-center gap-2 text-sm font-medium text-indigo-700 dark:text-indigo-300">
                <Search className="h-4 w-4" />
                Quick add with DOI
              </div>
              <p className="mt-1 text-xs text-indigo-600/70 dark:text-indigo-400/70">
                Enter a DOI to auto-fill paper details
              </p>
              <div className="mt-3 flex gap-2">
                <input
                  type="text"
                  value={doi}
                  onChange={(e) => setDoi(e.target.value)}
                  placeholder="10.1234/example or https://doi.org/..."
                  className="flex-1 rounded-lg border border-indigo-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-indigo-500/40 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
                  disabled={isSubmitting || isLookingUp}
                />
                <button
                  type="button"
                  onClick={handleDoiLookup}
                  disabled={!doi.trim() || isLookingUp || isSubmitting}
                  className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isLookingUp ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : lookupSuccess ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    <Search className="h-4 w-4" />
                  )}
                  {isLookingUp ? 'Looking up...' : lookupSuccess ? 'Found!' : 'Lookup'}
                </button>
              </div>
            </div>

            {/* Divider */}
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200 dark:border-slate-700" />
              </div>
              <div className="relative flex justify-center">
                <span className="bg-white px-3 text-xs text-gray-500 dark:bg-slate-800 dark:text-slate-400">
                  or enter details manually
                </span>
              </div>
            </div>

            {/* Title - Required */}
            <div>
              <label className="text-xs font-medium text-gray-700 dark:text-slate-300" htmlFor="ref-title">
                Paper title <span className="text-red-500">*</span>
              </label>
              <input
                id="ref-title"
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="mt-1.5 w-full rounded-lg border border-gray-200 bg-gray-50/50 px-4 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-800/50 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:bg-slate-800"
                placeholder="Enter the paper title"
                disabled={isSubmitting}
                required
              />
            </div>

            {/* Authors & Year */}
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="sm:col-span-2">
                <label className="text-xs font-medium text-gray-700 dark:text-slate-300" htmlFor="ref-authors">
                  Authors
                </label>
                <input
                  id="ref-authors"
                  type="text"
                  value={authors}
                  onChange={(e) => setAuthors(e.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-gray-200 bg-gray-50/50 px-4 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-800/50 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:bg-slate-800"
                  placeholder="John Smith, Jane Doe"
                  disabled={isSubmitting}
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-700 dark:text-slate-300" htmlFor="ref-year">
                  Year
                </label>
                <input
                  id="ref-year"
                  type="number"
                  value={year}
                  onChange={(e) => setYear(e.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-gray-200 bg-gray-50/50 px-4 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-800/50 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:bg-slate-800"
                  placeholder="2024"
                  disabled={isSubmitting}
                  min="1900"
                  max="2100"
                />
              </div>
            </div>

            {/* PDF Upload */}
            <div>
              <label className="text-xs font-medium text-gray-700 dark:text-slate-300">
                PDF attachment
              </label>
              <div
                className={`mt-1.5 rounded-lg border-2 border-dashed transition-colors ${
                  isDragging
                    ? 'border-indigo-400 bg-indigo-50 dark:border-indigo-500 dark:bg-indigo-950/50'
                    : pdfFile
                      ? 'border-emerald-300 bg-emerald-50/50 dark:border-emerald-500/50 dark:bg-emerald-950/30'
                      : 'border-gray-200 hover:border-gray-300 dark:border-slate-600 dark:hover:border-slate-500'
                }`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                {pdfFile ? (
                  <div className="flex items-center justify-between px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-100 dark:bg-emerald-500/20">
                        <FileText className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-900 dark:text-slate-100 truncate max-w-[200px]">
                          {pdfFile.name}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-slate-400">
                          {(pdfFile.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setPdfFile(null)}
                      className="rounded-full p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ) : (
                  <label className="flex cursor-pointer flex-col items-center px-4 py-6">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gray-100 dark:bg-slate-700">
                      <Upload className="h-6 w-6 text-gray-400 dark:text-slate-500" />
                    </div>
                    <p className="mt-2 text-sm text-gray-600 dark:text-slate-300">
                      <span className="font-medium text-indigo-600 dark:text-indigo-400">Click to upload</span> or drag and drop
                    </p>
                    <p className="mt-1 text-xs text-gray-400 dark:text-slate-500">PDF files only</p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="application/pdf"
                      className="hidden"
                      disabled={isSubmitting}
                      onChange={(e) => {
                        const file = e.target.files?.[0]
                        setPdfFile(file ?? null)
                      }}
                    />
                  </label>
                )}
              </div>
            </div>

            {/* Optional Fields Toggle */}
            <button
              type="button"
              onClick={() => setShowOptional(!showOptional)}
              className="flex w-full items-center justify-between rounded-lg border border-gray-200 px-4 py-2.5 text-sm text-gray-600 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-400 dark:hover:bg-slate-700/50"
            >
              <span className="flex items-center gap-2">
                <Link2 className="h-4 w-4" />
                Additional details (URL, Journal, Abstract)
              </span>
              {showOptional ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>

            {/* Optional Fields */}
            {showOptional && (
              <div className="space-y-4 rounded-lg border border-gray-100 bg-gray-50/50 p-4 dark:border-slate-700 dark:bg-slate-800/30">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="text-xs font-medium text-gray-600 dark:text-slate-400" htmlFor="ref-url">
                      URL
                    </label>
                    <input
                      id="ref-url"
                      type="url"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      className="mt-1.5 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
                      placeholder="https://..."
                      disabled={isSubmitting}
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600 dark:text-slate-400" htmlFor="ref-journal">
                      Journal / Venue
                    </label>
                    <input
                      id="ref-journal"
                      type="text"
                      value={journal}
                      onChange={(e) => setJournal(e.target.value)}
                      className="mt-1.5 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
                      placeholder="Nature, NeurIPS, etc."
                      disabled={isSubmitting}
                    />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-600 dark:text-slate-400" htmlFor="ref-abstract">
                    Abstract
                  </label>
                  <textarea
                    id="ref-abstract"
                    value={abstractText}
                    onChange={(e) => setAbstractText(e.target.value)}
                    className="mt-1.5 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
                    rows={3}
                    placeholder="Paper abstract or summary..."
                    disabled={isSubmitting}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 border-t border-gray-100 bg-gray-50/50 px-6 py-4 dark:border-slate-700 dark:bg-slate-800/50">
            <button
              type="button"
              onClick={handleClose}
              className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={isSubmitting || !title.trim()}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Adding...
                </>
              ) : (
                <>
                  <BookOpen className="h-4 w-4" />
                  Add Paper
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddProjectReferenceModal
