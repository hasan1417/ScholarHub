import React, { useState } from 'react'
import { X, Upload } from 'lucide-react'

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

const AddProjectReferenceModal: React.FC<AddProjectReferenceModalProps> = ({ isOpen, onClose, onSubmit, title: heading = 'Add Manual Reference' }) => {
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
  }

  const handleClose = () => {
    if (isSubmitting) return
    resetForm()
    onClose()
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

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 dark:bg-black/60">
      <div className="w-full max-w-2xl overflow-hidden rounded-xl bg-white shadow-xl transition-colors dark:bg-slate-800">
        <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4 dark:border-slate-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">{heading}</h2>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-full p-1 text-gray-400 transition-colors hover:text-gray-600 dark:text-slate-300 dark:hover:text-slate-100"
            title="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 px-5 py-4 text-gray-700 dark:text-slate-200">
          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-200">
              {error}
            </div>
          )}

          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700 dark:text-slate-200" htmlFor="ref-title">Title *</label>
            <input
              id="ref-title"
              type="text"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
              placeholder="Enter paper title"
              disabled={isSubmitting}
              required
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-slate-200" htmlFor="ref-authors">Authors</label>
              <input
                id="ref-authors"
                type="text"
                value={authors}
                onChange={(event) => setAuthors(event.target.value)}
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
                placeholder="Comma-separated list"
                disabled={isSubmitting}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-slate-200" htmlFor="ref-year">Year</label>
              <input
                id="ref-year"
                type="number"
                value={year}
                onChange={(event) => setYear(event.target.value)}
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
                placeholder="2024"
                disabled={isSubmitting}
                min="0"
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-slate-200" htmlFor="ref-doi">DOI</label>
              <input
                id="ref-doi"
                type="text"
                value={doi}
                onChange={(event) => setDoi(event.target.value)}
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
                placeholder="10.1234/abcd.5678"
                disabled={isSubmitting}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-slate-200" htmlFor="ref-url">URL</label>
              <input
                id="ref-url"
                type="url"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
                placeholder="https://example.com"
                disabled={isSubmitting}
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-slate-200" htmlFor="ref-journal">Journal / Source</label>
              <input
                id="ref-journal"
                type="text"
                value={journal}
                onChange={(event) => setJournal(event.target.value)}
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
                placeholder="Journal name"
                disabled={isSubmitting}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-slate-200" htmlFor="ref-pdf">Attach PDF (optional)</label>
              <label className={`flex cursor-pointer items-center justify-between rounded-md border border-dashed border-gray-300 px-3 py-2 text-sm text-gray-600 transition-colors ${isSubmitting ? 'opacity-60' : 'hover:border-indigo-400 hover:text-indigo-600 dark:border-slate-600 dark:text-slate-300 dark:hover:border-indigo-400/70 dark:hover:text-indigo-200'}`}>
                <span className="truncate">{pdfFile ? pdfFile.name : 'Choose file'}</span>
                <span className="flex items-center gap-1 text-indigo-600">
                  <Upload className="h-4 w-4" />
                  Browse
                </span>
                <input
                  id="ref-pdf"
                  type="file"
                  accept="application/pdf"
                  className="hidden"
                  disabled={isSubmitting}
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    setPdfFile(file ?? null)
                  }}
                />
              </label>
              <p className="text-xs text-gray-400">PDF is optional and helps AI enrichment.</p>
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700" htmlFor="ref-abstract">Abstract</label>
            <textarea
              id="ref-abstract"
              value={abstractText}
              onChange={(event) => setAbstractText(event.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              rows={4}
              placeholder="Optional short abstract or summary"
              disabled={isSubmitting}
            />
          </div>

          <div className="flex items-center justify-end gap-3 border-t border-gray-100 pt-4">
            <button
              type="button"
              onClick={handleClose}
              className="inline-flex items-center rounded-full border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100"
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="inline-flex items-center rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Saving…' : 'Add related paper'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AddProjectReferenceModal
