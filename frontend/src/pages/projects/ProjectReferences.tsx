import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  BookOpen,
  Calendar,
  CheckCircle2,
  Download,
  ExternalLink,
  FileEdit,
  FileText,
  GitFork,
  List,
  Loader2,
  MessageSquare,
  MoreVertical,
  Plus,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react'
import { useProjectContext } from './ProjectLayout'
import { projectReferencesAPI, referencesAPI, usersAPI } from '../../services/api'
import { ProjectReferenceSuggestion } from '../../types'
import { useAuth } from '../../contexts/AuthContext'
import AddProjectReferenceModal from '../../components/projects/AddProjectReferenceModal'
import ConfirmationModal from '../../components/common/ConfirmationModal'
import ZoteroImportModal from '../../components/references/ZoteroImportModal'
import CitationGraph from '../../components/references/CitationGraph'
import { getProjectUrlId } from '../../utils/urlId'
import { useToast } from '../../hooks/useToast'

const ProjectReferences = () => {
  const { toast } = useToast()
  const { project } = useProjectContext()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [showAddModal, setShowAddModal] = useState(false)
  const [uploadTarget, setUploadTarget] = useState<string | null>(null)
  const [uploadingId, setUploadingId] = useState<string | null>(null)
  const [reindexingId, setReindexingId] = useState<string | null>(null)
  const [deleteContext, setDeleteContext] = useState<{
    projectReferenceId: string
    referenceId: string | null
    title: string
  } | null>(null)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [openMenuId, setOpenMenuId] = useState<string | null>(null)
  const [ingestFailedIds, setIngestFailedIds] = useState<Set<string>>(new Set())
  const [zoteroConfigured, setZoteroConfigured] = useState(false)
  const [showZoteroModal, setShowZoteroModal] = useState(false)
  const undoContextRef = useRef<{
    projectReferenceId: string
    referenceId: string | null
    title: string
  } | null>(null)
  const bibFileInputRef = useRef<HTMLInputElement | null>(null)
  const [bibImporting, setBibImporting] = useState(false)
  const [bibExporting, setBibExporting] = useState(false)
  const [viewMode, setViewMode] = useState<'list' | 'graph'>('list')
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    usersAPI.getApiKeys().then((res) => {
      setZoteroConfigured(res.data.zotero?.configured ?? false)
    }).catch(() => {})
  }, [])

  const suggestionsQuery = useQuery({
    queryKey: ['project', project.id, 'relatedReferences'],
    queryFn: async () => {
      try {
        const response = await projectReferencesAPI.list(project.id, { status: 'approved' })
        return response.data
      } catch (error) {
        const axiosError = error as { response?: { status?: number } }
        if (axiosError.response?.status === 404) {
          return { disabled: true, references: [] as ProjectReferenceSuggestion[] }
        }
        throw error
      }
    },
  })

  const payload = suggestionsQuery.data
  const featureDisabled = payload ? 'disabled' in payload && (payload as any).disabled : false
  const references = (payload as { references: ProjectReferenceSuggestion[] } | undefined)?.references ?? []
  const currentUserId = user?.id
  const isOwner = project.created_by === currentUserId
  const memberRecord = project.members?.find((member) => member.user_id === currentUserId)
  const normalizedRole = isOwner
    ? 'admin'
    : (memberRecord?.role || '').toLowerCase() === 'owner'
      ? 'admin'
      : (memberRecord?.role || '').toLowerCase()
  const canAddManual = ['admin', 'editor'].includes(normalizedRole)
  const canManageReferences = ['admin', 'editor'].includes(normalizedRole)

  const handleAddReference = async (payload: {
    title: string
    authors?: string[]
    year?: number
    doi?: string
    url?: string
    journal?: string
    abstract?: string
    pdfFile?: File | null
  }) => {
    const response = await referencesAPI.create({
      title: payload.title,
      authors: payload.authors,
      year: payload.year,
      doi: payload.doi,
      url: payload.url,
      journal: payload.journal,
      abstract: payload.abstract,
      source: 'manual',
      is_open_access: undefined,
    })

    const created = response.data as {
      id?: string
      reference_id?: string
      referenceId?: string
      reference?: { id?: string }
    } | null
    const referenceId: string = created?.id || created?.reference_id || created?.referenceId || created?.reference?.id || ''
    if (!referenceId) {
      throw new Error('Reference was created but returned no id.')
    }

    if (payload.pdfFile) {
      await referencesAPI.uploadPdf(referenceId, payload.pdfFile)
    }

    const suggestion = await projectReferencesAPI.createSuggestion(project.id, referenceId, 1)
    const suggestionData = suggestion.data as { id?: string } | null
    const suggestionId = suggestionData?.id
    if (suggestionId) {
      await projectReferencesAPI.approveSuggestion(project.id, suggestionId)
    }

    await queryClient.invalidateQueries({ queryKey: ['project', project.id, 'relatedReferences'] })
  }

  const handleUploadRequest = (referenceId: string) => {
    if (!canManageReferences) return
    setUploadTarget(referenceId)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
      fileInputRef.current.click()
    }
  }

  const handleFileSelection: React.ChangeEventHandler<HTMLInputElement> = async (event) => {
    if (!canManageReferences) {
      setUploadTarget(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }
    const file = event.target.files?.[0]
    if (!file || !uploadTarget) {
      setUploadTarget(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }

    try {
      setUploadingId(uploadTarget)
      await referencesAPI.uploadPdf(uploadTarget, file)
      await queryClient.invalidateQueries({ queryKey: ['project', project.id, 'relatedReferences'] })
    } catch (error) {
      console.error('Failed to upload PDF', error)
      toast.error('Failed to upload PDF. Please try again.')
    } finally {
      setUploadingId(null)
      setUploadTarget(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleIngestExisting = async (referenceId: string) => {
    if (!canManageReferences) return
    try {
      setReindexingId(referenceId)
      await referencesAPI.ingestPdf(referenceId)
      await queryClient.invalidateQueries({ queryKey: ['project', project.id, 'relatedReferences'] })
      // On success, remove from failed set if it was there
      setIngestFailedIds((prev) => {
        const next = new Set(prev)
        next.delete(referenceId)
        return next
      })
    } catch (error) {
      console.error('Failed to ingest existing PDF', error)
      // Mark this reference as needing manual upload
      setIngestFailedIds((prev) => new Set(prev).add(referenceId))
      toast.warning('Unable to fetch the PDF automatically. Please upload the PDF manually.')
    } finally {
      setReindexingId(null)
    }
  }

  const handleUndoDelete = async () => {
    if (!undoContextRef.current || !undoContextRef.current.referenceId) return
    try {
      const response = await projectReferencesAPI.createSuggestion(
        project.id,
        undoContextRef.current.referenceId,
        1
      )
      const suggestionData = response.data as { id?: string } | null
      const suggestionId = suggestionData?.id
      if (suggestionId) {
        await projectReferencesAPI.approveSuggestion(project.id, suggestionId)
        await queryClient.invalidateQueries({ queryKey: ['project', project.id, 'relatedReferences'] })
      }
      undoContextRef.current = null
    } catch (error) {
      console.error('Failed to undo delete', error)
      toast.error('Unable to restore the related paper. Please try again.')
    }
  }

  const handleDeleteReference = async () => {
    if (!deleteContext || !canManageReferences) return
    try {
      setDeleteLoading(true)
      undoContextRef.current = deleteContext
      await projectReferencesAPI.remove(project.id, deleteContext.projectReferenceId)
      await queryClient.invalidateQueries({ queryKey: ['project', project.id, 'relatedReferences'] })
      const baseMessage = deleteContext.title ? `Deleted "${deleteContext.title}"` : 'Related paper deleted'
      if (deleteContext.referenceId) {
        toast.success(`${baseMessage}.`, { label: 'Undo', onClick: handleUndoDelete })
      } else {
        toast.success(`${baseMessage}.`)
      }
    } catch (error) {
      console.error('Failed to remove related paper', error)
      toast.error('Unable to remove the related paper right now. Please try again.')
    } finally {
      setDeleteLoading(false)
      setDeleteModalOpen(false)
      setDeleteContext(null)
    }
  }

  const handleBibImport: React.ChangeEventHandler<HTMLInputElement> = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      setBibImporting(true)
      const response = await projectReferencesAPI.importBibtex(project.id, file)
      const { imported, skipped } = response.data
      await queryClient.invalidateQueries({ queryKey: ['project', project.id, 'relatedReferences'] })
      toast.success(`Imported ${imported} reference${imported !== 1 ? 's' : ''}${skipped ? `, ${skipped} skipped` : ''}.`)
    } catch {
      toast.error('Failed to import BibTeX file. Please check the format and try again.')
    } finally {
      setBibImporting(false)
      if (bibFileInputRef.current) bibFileInputRef.current.value = ''
    }
  }

  const handleBibExport = async () => {
    try {
      setBibExporting(true)
      const response = await projectReferencesAPI.exportBibtex(project.id)
      const blob = new Blob([response.data as BlobPart], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'references.bib'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Failed to export references.')
    } finally {
      setBibExporting(false)
    }
  }

  type BadgeTone = 'emerald' | 'amber' | 'slate' | 'sky' | 'purple'
  const toneClasses: Record<BadgeTone, string> = {
    emerald: 'border border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-400/40 dark:bg-emerald-500/20 dark:text-emerald-200',
    amber: 'border border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-400/40 dark:bg-amber-500/20 dark:text-amber-200',
    slate: 'border border-slate-200 bg-slate-100 text-slate-600 dark:border-slate-600/60 dark:bg-slate-800/60 dark:text-slate-300',
    sky: 'border border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-400/40 dark:bg-sky-500/20 dark:text-sky-200',
    purple: 'border border-purple-200 bg-purple-50 text-purple-700 dark:border-purple-400/40 dark:bg-purple-500/20 dark:text-purple-200',
  }

  const Badge = ({ label, tone, icon }: { label: string; tone: BadgeTone; icon?: ReactNode }) => (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${toneClasses[tone]}`}>
      {icon}
      {label}
    </span>
  )

  const formatDate = (value?: string | null) => {
    if (!value) return null
    try {
      return new Date(value).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    } catch (error) {
      return null
    }
  }

  if (suggestionsQuery.isLoading) {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm text-sm text-gray-600 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300">
        <Loader2 className="h-4 w-4 animate-spin text-indigo-600 dark:text-indigo-300" />
        Loading project intelligence…
      </div>
    )
  }

  if (featureDisabled) {
    return (
      <div className="rounded-2xl border border-dashed border-gray-200 bg-white p-6 text-sm text-gray-500 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300">
        <div className="flex items-center gap-2 text-gray-600 dark:text-slate-300">
          <AlertCircle className="h-4 w-4 text-amber-500" />
          Project reference intelligence is currently disabled for this environment.
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-900/50">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
            <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">Related papers</h2>

            {/* View mode toggle */}
            <div className="ml-3 inline-flex rounded-lg border border-gray-200 p-0.5 dark:border-slate-700">
              <button
                type="button"
                onClick={() => setViewMode('list')}
                className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  viewMode === 'list'
                    ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200'
                    : 'text-gray-500 hover:text-gray-700 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                <List className="h-3.5 w-3.5" />
                List
              </button>
              <button
                type="button"
                onClick={() => setViewMode('graph')}
                className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  viewMode === 'graph'
                    ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200'
                    : 'text-gray-500 hover:text-gray-700 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                <GitFork className="h-3.5 w-3.5" />
                Graph
              </button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {references.length > 0 && viewMode === 'list' && (
              <button
                type="button"
                onClick={handleBibExport}
                disabled={bibExporting}
                className="inline-flex items-center gap-1 rounded-full border border-gray-200 px-3 py-2 sm:py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                {bibExporting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                Export .bib
              </button>
            )}
            {canAddManual && viewMode === 'list' && (
              <button
                type="button"
                onClick={() => bibFileInputRef.current?.click()}
                disabled={bibImporting}
                className="inline-flex items-center gap-1 rounded-full border border-gray-200 px-3 py-2 sm:py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                {bibImporting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
                Import .bib
              </button>
            )}
            {canAddManual && viewMode === 'list' && (
              <button
                type="button"
                onClick={() => {
                  if (zoteroConfigured) {
                    setShowZoteroModal(true)
                  } else {
                    toast.warning('Connect your Zotero account first in Settings > Integrations.')
                  }
                }}
                className="inline-flex items-center gap-1 rounded-full border border-emerald-200 px-3 py-2 sm:py-1.5 text-xs font-medium text-emerald-600 hover:bg-emerald-50 dark:border-emerald-400/40 dark:text-emerald-200 dark:hover:bg-emerald-500/10"
              >
                <BookOpen className="h-3.5 w-3.5" />
                <span className="hidden xs:inline">Import from</span><span className="xs:hidden">From</span> Zotero
              </button>
            )}
            {canAddManual && viewMode === 'list' && (
              <button
                type="button"
                onClick={() => setShowAddModal(true)}
                className="inline-flex items-center gap-1 rounded-full border border-indigo-200 px-3 py-2 sm:py-1.5 text-xs font-medium text-indigo-600 hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
              >
                <Plus className="h-3.5 w-3.5" />
                Add paper
              </button>
            )}
          </div>
        </div>

        {viewMode === 'graph' ? (
          <CitationGraph projectId={project.id} />
        ) : references.length === 0 ? (
          <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-6 text-sm text-gray-500 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300">
            No approved related papers yet. Review suggestions from the Discovery tab to build this list.
          </div>
        ) : (
          <ul className="space-y-3">
            {references.map((item) => {
              const ref = item.reference
              // Only show analysis badge for completed statuses, not pending
              const analysisBadge = ref?.status && ref.status !== 'pending'
                ? {
                    tone: ref.status === 'analyzed' ? ('emerald' as const) : ('amber' as const),
                    label: ref.status === 'analyzed' ? 'Analyzed' : 'Processing',
                    icon: ref.status === 'analyzed' ? (
                      <Sparkles className="h-3 w-3" />
                    ) : (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ),
                  }
                : null

              const documentDownloadPath = ref?.document_download_url || null
              const decidedAt = formatDate(item.decided_at)
              const confidencePercent =
                typeof item.confidence === 'number'
                  ? Math.round(Math.min(Math.max(item.confidence, 0), 1) * 100)
                  : null
              const summary = ref?.summary || ref?.abstract
              const referenceId = ref?.id || item.reference_id || null
              const hasDocument = Boolean(ref?.document_id)
              const hasPdfStored = Boolean(hasDocument || documentDownloadPath)
              const isPdfProcessed = Boolean(ref?.pdf_processed)
              const hasPdfUrl = Boolean(ref?.pdf_url)
              const isOpenAccess = Boolean(ref?.is_open_access)
              // Can auto-fetch: OA paper with pdf_url but no stored PDF yet
              const canAutoFetch = hasPdfUrl && isOpenAccess && !hasPdfStored
              const ingestFailed = referenceId ? ingestFailedIds.has(referenceId) : false
              // Show "Analyze PDF" when:
              // - has stored PDF (and not yet processed), OR
              // - can auto-fetch (OA + pdf_url) and hasn't failed yet
              const showIngestButton = Boolean(canManageReferences && referenceId && !isPdfProcessed && (hasPdfStored || (canAutoFetch && !ingestFailed)))
              // Show "Upload PDF" when:
              // - no PDF stored AND either:
              //   - can't auto-fetch (not OA or no pdf_url), OR
              //   - OA but auto-fetch failed
              const showUploadButton = Boolean(canManageReferences && referenceId && !hasPdfStored && !isPdfProcessed && (!canAutoFetch || ingestFailed))

              return (
                <li
                  key={item.id}
                  className="group rounded-xl border border-gray-200 bg-white p-5 text-sm text-gray-700 shadow-sm transition hover:border-indigo-200 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-200"
                >
                  <div className="flex flex-col gap-3">
                    {/* Header row: Title + Actions */}
                    <div className="flex items-start justify-between gap-4">
                      <h3 className="font-semibold text-gray-900 leading-snug dark:text-slate-100">
                        {ref?.title ?? 'Untitled reference'}
                      </h3>

                      {/* Actions - always visible on touch, hover on desktop */}
                      <div className="relative flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
                        {/* PDF Status/Action Button */}
                        {isPdfProcessed ? (
                          <span className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 dark:border-emerald-400/40 dark:bg-emerald-500/20 dark:text-emerald-200">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            PDF analyzed
                          </span>
                        ) : showIngestButton && referenceId ? (
                          <button
                            type="button"
                            className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 transition hover:bg-emerald-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-emerald-400 disabled:cursor-not-allowed disabled:opacity-50 dark:border-emerald-400/40 dark:bg-emerald-500/20 dark:text-emerald-200 dark:hover:bg-emerald-500/30"
                            onClick={() => handleIngestExisting(referenceId)}
                            disabled={!!reindexingId}
                            title={canAutoFetch ? 'Fetch PDF from source and analyze' : 'Analyze stored PDF'}
                          >
                            {reindexingId === referenceId ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Sparkles className="h-3.5 w-3.5" />
                            )}
                            {reindexingId === referenceId
                              ? (canAutoFetch ? 'Fetching…' : 'Analyzing…')
                              : (canAutoFetch ? 'Fetch & Analyze' : 'Analyze PDF')}
                          </button>
                        ) : showUploadButton ? (
                          <button
                            type="button"
                            className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 transition hover:bg-amber-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-amber-400 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-400/40 dark:bg-amber-500/20 dark:text-amber-200 dark:hover:bg-amber-500/30"
                            onClick={() => referenceId && handleUploadRequest(referenceId)}
                            disabled={!!uploadingId}
                            title="Upload a PDF file for this paper"
                          >
                            {uploadingId === referenceId ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Upload className="h-3.5 w-3.5" />
                            )}
                            {uploadingId === referenceId ? 'Uploading…' : 'Upload PDF'}
                          </button>
                        ) : null}

                        {/* Overflow Menu */}
                        {canManageReferences && (
                          <div className="relative">
                            <button
                              type="button"
                              className="inline-flex h-11 w-11 sm:h-8 sm:w-8 items-center justify-center rounded-lg text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-indigo-500 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-300"
                              onClick={() => setOpenMenuId(openMenuId === item.id ? null : item.id)}
                              aria-label="More options"
                            >
                              <MoreVertical className="h-4 w-4" />
                            </button>

                            {openMenuId === item.id && (
                              <>
                                <div
                                  className="fixed inset-0 z-10"
                                  onClick={() => setOpenMenuId(null)}
                                />
                                <div className="absolute right-0 top-full z-20 mt-1 w-[calc(100vw-3rem)] sm:w-48 max-w-xs rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800">
                                  <button
                                    type="button"
                                    className="flex w-full items-center gap-2 px-4 py-3 sm:px-3 sm:py-2 text-sm sm:text-xs text-rose-600 transition hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-500/10"
                                    onClick={() => {
                                      setOpenMenuId(null)
                                      setDeleteContext({
                                        projectReferenceId: item.id,
                                        referenceId: referenceId,
                                        title: ref?.title ?? 'Related paper',
                                      })
                                      setDeleteModalOpen(true)
                                    }}
                                  >
                                    <Trash2 className="h-4 w-4 sm:h-3.5 sm:w-3.5" />
                                    Remove paper
                                  </button>
                                </div>
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Metadata badges row */}
                    <div className="flex flex-wrap items-center gap-2">
                      {ref?.year && (
                        <Badge label={String(ref.year)} tone="slate" icon={<Calendar className="h-3 w-3" />} />
                      )}
                      {ref?.source && (
                        <Badge label={ref.source} tone="slate" icon={<BookOpen className="h-3 w-3" />} />
                      )}
                      {ref?.is_open_access && (
                        <Badge label="Open access" tone="sky" icon={<ShieldCheck className="h-3 w-3" />} />
                      )}
                    </div>

                    {/* Authors and Journal */}
                    {(ref?.authors?.length || ref?.journal) && (
                      <div className="text-xs text-gray-500 dark:text-slate-400">
                        {ref?.authors && ref.authors.length > 0 && (
                          <p>{ref.authors.join(', ')}</p>
                        )}
                        {ref?.journal && <p className="italic">{ref.journal}</p>}
                      </div>
                    )}

                    {/* Abstract - truncated */}
                    {summary && (
                      <p className="text-xs text-gray-600 leading-relaxed line-clamp-2 dark:text-slate-300">
                        {summary}
                      </p>
                    )}

                    {/* Appears in */}
                    {item.papers && item.papers.length > 0 && (
                      <p className="text-xs text-gray-500 dark:text-slate-400">
                        <span className="font-medium">Appears in:</span>{' '}
                        {item.papers.map((paper) => paper.title ?? 'Untitled paper').join(', ')}
                      </p>
                    )}

                    {/* Status badges and links row */}
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-1 border-t border-gray-100 dark:border-slate-800">
                      {/* Analysis status - only show if processing (not pending and not already showing "PDF analyzed" in header) */}
                      {analysisBadge && ref?.status === 'processing' && (
                        <Badge label={analysisBadge.label} tone={analysisBadge.tone} icon={analysisBadge.icon} />
                      )}
                      {confidencePercent !== null && (
                        <Badge
                          label={`${confidencePercent}% match`}
                          tone="purple"
                          icon={<Sparkles className="h-3 w-3" />}
                        />
                      )}
                      {/* Divider */}
                      {((analysisBadge && ref?.status === 'processing') || confidencePercent !== null) && (ref?.doi || ref?.url || decidedAt) && (
                        <span className="text-gray-300 dark:text-slate-700">|</span>
                      )}

                      {/* Links */}
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-slate-400">
                        {ref?.doi && (
                          <a
                            href={ref.doi.startsWith('http') ? ref.doi : `https://doi.org/${ref.doi}`}
                            className="inline-flex items-center gap-1 hover:text-indigo-600 dark:hover:text-indigo-300"
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            <FileText className="h-3 w-3" />
                            DOI
                          </a>
                        )}
                        {ref?.url && (
                          <a
                            href={ref.url}
                            className="inline-flex items-center gap-1 hover:text-indigo-600 dark:hover:text-indigo-300"
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            <ExternalLink className="h-3 w-3" />
                            Source
                          </a>
                        )}
                        {decidedAt && (
                          <span className="inline-flex items-center gap-1 text-gray-400 dark:text-slate-500">
                            Added {decidedAt}
                          </span>
                        )}
                        {/* Cross-feature navigation */}
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 hover:text-indigo-600 dark:hover:text-indigo-300"
                          onClick={() => navigate(`/projects/${getProjectUrlId(project)}/discussion`)}
                          title={`Discuss "${ref?.title ?? 'this paper'}"`}
                        >
                          <MessageSquare className="h-3 w-3" />
                          Discuss
                        </button>
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 hover:text-indigo-600 dark:hover:text-indigo-300"
                          onClick={() => navigate(`/projects/${getProjectUrlId(project)}/papers`)}
                          title="Cite in a paper"
                        >
                          <FileEdit className="h-3 w-3" />
                          Cite in Paper
                        </button>
                      </div>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={handleFileSelection}
      />
      <input
        ref={bibFileInputRef}
        type="file"
        accept=".bib"
        className="hidden"
        onChange={handleBibImport}
      />

      {canAddManual && (
        <AddProjectReferenceModal
          isOpen={showAddModal}
          onClose={() => setShowAddModal(false)}
          onSubmit={handleAddReference}
          title="Add Related Paper"
        />
      )}

      <ZoteroImportModal
        isOpen={showZoteroModal}
        onClose={() => setShowZoteroModal(false)}
        onImportComplete={() => {
          queryClient.invalidateQueries({ queryKey: ['project', project.id, 'relatedReferences'] })
        }}
        projectId={project.id}
      />

      <ConfirmationModal
        isOpen={deleteModalOpen}
        onClose={() => {
          if (!deleteLoading) {
            setDeleteModalOpen(false)
            setDeleteContext(null)
          }
        }}
        onConfirm={handleDeleteReference}
        title="Delete this item?"
        description="This related paper will be removed from the project. You can undo this action for a short time after deletion."
        confirmLabel={deleteLoading ? 'Deleting…' : 'Delete'}
        cancelLabel="Cancel"
        confirmButtonColor="red"
        confirmTone="danger"
        isSubmitting={deleteLoading}
      />

    </div>
  )
}

export default ProjectReferences
