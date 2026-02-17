import { useState, useEffect, useCallback } from 'react'
import { X, ChevronDown, Check, AlertTriangle, Loader2, Package, Download, Info } from 'lucide-react'
import { latexAPI } from '../../../services/api'
import { useToast } from '../../../hooks/useToast'

interface VenueConfig {
  name: string
  abstract_max_words: number | null
  sections: string[] | null
  reference_style: string
  file_structure: string[]
  document_class: string
  required_packages: string[]
  page_limit: number | null
  font_size: string
}

interface ValidationIssue {
  type: string
  severity: string
  message: string
  passed: boolean
}

interface SubmissionBuilderProps {
  isOpen: boolean
  onClose: () => void
  getLatexSource: () => string
  paperId?: string
  getExtraFiles?: () => Record<string, string> | null
}

export default function SubmissionBuilder({
  isOpen,
  onClose,
  getLatexSource,
  paperId,
  getExtraFiles,
}: SubmissionBuilderProps) {
  const { toast } = useToast()

  const [venues, setVenues] = useState<Record<string, VenueConfig>>({})
  const [selectedVenue, setSelectedVenue] = useState<string>('')
  const [venuesLoading, setVenuesLoading] = useState(false)

  const [validationIssues, setValidationIssues] = useState<ValidationIssue[] | null>(null)
  const [validating, setValidating] = useState(false)

  const [building, setBuilding] = useState(false)

  // Fetch venues on open
  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    setVenuesLoading(true)
    ;(async () => {
      try {
        const resp = await latexAPI.getSubmissionVenues()
        if (cancelled) return
        setVenues(resp.data.venues)
        const keys = Object.keys(resp.data.venues)
        if (keys.length > 0 && !selectedVenue) {
          setSelectedVenue(keys[0])
        }
      } catch {
        if (!cancelled) toast.error('Failed to load submission venues.')
      } finally {
        if (!cancelled) setVenuesLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isOpen]) // eslint-disable-line react-hooks/exhaustive-deps

  // Reset validation when venue changes
  useEffect(() => {
    setValidationIssues(null)
  }, [selectedVenue])

  const handleValidate = useCallback(async () => {
    if (!selectedVenue) return
    setValidating(true)
    setValidationIssues(null)
    try {
      const source = getLatexSource()
      const resp = await latexAPI.validateSubmission({
        latex_source: source,
        venue: selectedVenue,
        paper_id: paperId,
      })
      setValidationIssues(resp.data.issues)
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Validation failed.'
      toast.error(msg)
    } finally {
      setValidating(false)
    }
  }, [selectedVenue, getLatexSource, paperId, toast])

  const handleBuild = useCallback(async () => {
    if (!selectedVenue) return
    setBuilding(true)
    try {
      const source = getLatexSource()
      const extraFiles = getExtraFiles?.() ?? undefined
      const resp = await latexAPI.buildSubmission({
        latex_source: source,
        venue: selectedVenue,
        paper_id: paperId,
        latex_files: extraFiles ?? undefined,
        include_bibtex: true,
      })
      const blob = new Blob([resp.data as BlobPart], { type: 'application/zip' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `submission-${selectedVenue}.zip`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Submission package downloaded.')
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Failed to build submission package.'
      toast.error(msg)
    } finally {
      setBuilding(false)
    }
  }, [selectedVenue, getLatexSource, getExtraFiles, paperId, toast])

  if (!isOpen) return null

  const cfg = selectedVenue ? venues[selectedVenue] : null
  const passedCount = validationIssues?.filter((i) => i.passed).length ?? 0
  const totalCount = validationIssues?.length ?? 0
  const failedCount = totalCount - passedCount

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />

      {/* Dialog */}
      <div className="relative z-10 mx-4 w-full max-w-lg rounded-xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-700">
          <div className="flex items-center gap-2">
            <Package className="h-5 w-5 text-indigo-500" />
            <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">
              Submission Package Builder
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">
          {venuesLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
            </div>
          ) : (
            <>
              {/* Venue selector */}
              <label className="mb-1.5 block text-xs font-medium text-slate-600 dark:text-slate-400">
                Target Venue
              </label>
              <div className="relative mb-4">
                <select
                  value={selectedVenue}
                  onChange={(e) => setSelectedVenue(e.target.value)}
                  className="w-full appearance-none rounded-lg border border-slate-300 bg-white py-2.5 pl-3 pr-10 text-sm text-slate-800 transition-colors focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:focus:border-indigo-400 dark:focus:ring-indigo-900"
                >
                  {Object.entries(venues).map(([key, v]) => (
                    <option key={key} value={key}>
                      {v.name}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              </div>

              {/* Venue info */}
              {cfg && (
                <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs dark:border-slate-700 dark:bg-slate-800/60">
                  <div className="mb-2 flex items-center gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-200">
                    <Info className="h-3.5 w-3.5 text-slate-400" />
                    {cfg.name} Requirements
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-slate-600 dark:text-slate-400">
                    <div>
                      <span className="font-medium text-slate-700 dark:text-slate-300">Document class:</span>{' '}
                      <code className="rounded bg-slate-200 px-1 py-0.5 font-mono text-[10px] dark:bg-slate-700">{cfg.document_class.replace(/\\/g, '\\')}</code>
                    </div>
                    <div>
                      <span className="font-medium text-slate-700 dark:text-slate-300">Font size:</span> {cfg.font_size}
                    </div>
                    <div>
                      <span className="font-medium text-slate-700 dark:text-slate-300">Abstract limit:</span>{' '}
                      {cfg.abstract_max_words ? `${cfg.abstract_max_words} words` : 'None'}
                    </div>
                    <div>
                      <span className="font-medium text-slate-700 dark:text-slate-300">Ref. style:</span> {cfg.reference_style}
                    </div>
                    {cfg.required_packages.length > 0 && (
                      <div className="col-span-2">
                        <span className="font-medium text-slate-700 dark:text-slate-300">Packages:</span>{' '}
                        {cfg.required_packages.join(', ')}
                      </div>
                    )}
                    {cfg.sections && (
                      <div className="col-span-2">
                        <span className="font-medium text-slate-700 dark:text-slate-300">Sections:</span>{' '}
                        {cfg.sections.join(', ')}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Validation results */}
              {validationIssues && (
                <div className="mb-4">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                      Compliance Check
                    </span>
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      {passedCount}/{totalCount} passed
                      {failedCount > 0 && (
                        <span className="ml-1 text-amber-600 dark:text-amber-400">
                          ({failedCount} issue{failedCount > 1 ? 's' : ''})
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="max-h-52 space-y-1 overflow-y-auto rounded-lg border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-800/50">
                    {validationIssues.map((issue, idx) => (
                      <div
                        key={idx}
                        className="flex items-start gap-2 rounded px-2 py-1.5 text-xs"
                      >
                        {issue.passed ? (
                          <Check className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-emerald-500" />
                        ) : (
                          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-amber-500" />
                        )}
                        <span
                          className={
                            issue.passed
                              ? 'text-slate-600 dark:text-slate-400'
                              : 'text-slate-800 dark:text-slate-200'
                          }
                        >
                          {issue.message}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-3 dark:border-slate-700">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-2 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleValidate}
            disabled={validating || !selectedVenue || venuesLoading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            {validating ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Check className="h-3.5 w-3.5" />
            )}
            Validate
          </button>
          <button
            type="button"
            onClick={handleBuild}
            disabled={building || !selectedVenue || venuesLoading}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
          >
            {building ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
            Build Package
          </button>
        </div>
      </div>
    </div>
  )
}
