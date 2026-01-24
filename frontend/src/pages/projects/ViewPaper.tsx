import React, { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { researchPapersAPI } from '../../services/api'
import { ResearchPaper } from '../../types'
import OOAdapter from '../../components/editor/adapters/OOAdapter'
import LatexPdfViewer from '../../components/editor/LatexPdfViewer'
import { getPaperUrlId } from '../../utils/urlId'

interface LatexPaperViewProps {
  paper: ResearchPaper
  latexSource: string
  onBack: () => void
}

const LatexPaperView: React.FC<LatexPaperViewProps> = ({ paper, latexSource, onBack }) => (
  <div className="fixed inset-0 flex flex-col bg-gray-50">
    <div className="flex items-center justify-between px-3 py-2 border-b bg-white">
      <button
        className="px-2 py-1 border border-gray-300 rounded-md text-xs hover:bg-gray-50 flex items-center gap-1"
        onClick={onBack}
        title="Back to Paper Details"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Back</span>
      </button>
      <div className="text-sm font-medium text-gray-700 truncate max-w-md" title={paper.title}>{paper.title}</div>
      <div className="w-24" />
    </div>
    <LatexPdfViewer latexSource={latexSource} paperId={paper.id} />
  </div>
)

interface OnlyOfficePaperViewProps {
  paper: ResearchPaper
  parsedContentJson: any
  onBack: () => void
}

const OnlyOfficePaperView: React.FC<OnlyOfficePaperViewProps> = ({ paper, parsedContentJson, onBack }) => (
  <div className="fixed inset-0">
    <OOAdapter
      paperId={paper.id}
      paperTitle={paper.title}
      content={paper.content || ''}
      contentJson={parsedContentJson}
      onContentChange={() => {}}
      onSelectionChange={() => {}}
      className="h-full w-full"
      readOnly={true}
      onNavigateBack={onBack}
    />
  </div>
)

const ViewPaper: React.FC = () => {
  const { projectId, paperId } = useParams<{ projectId?: string; paperId: string }>()
  const navigate = useNavigate()
  const [paper, setPaper] = useState<ResearchPaper | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const resolveProjectPath = (suffix = '') => {
    const id = projectId || paper?.project_id
    return id ? `/projects/${id}${suffix}` : `/projects${suffix}`
  }

  const parsedContentJson = useMemo(() => {
    const raw = paper?.content_json
    if (!raw) return null
    if (typeof raw === 'string') {
      try {
        return JSON.parse(raw)
      } catch (err) {
        console.warn('Failed to parse paper.content_json', err)
        return null
      }
    }
    return raw as Record<string, unknown>
  }, [paper?.content_json])

  useEffect(() => {
    if (paperId) {
      loadPaper()
    }
  }, [paperId])

  const loadPaper = async () => {
    if (!paperId) return
    try {
      setIsLoading(true)
      setError(null)
      const response = await researchPapersAPI.getPaper(paperId)
      setPaper(response.data)
    } catch (err) {
      console.error('Error loading paper:', err)
      setError('Failed to load paper')
    } finally {
      setIsLoading(false)
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-16 w-16 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600"></div>
          <p className="mt-6 text-lg font-medium text-gray-600">Loading paper...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center max-w-md">
          <div className="mb-4 rounded border border-red-300 bg-red-100 px-4 py-3 text-red-700">
            <p className="font-semibold">Error loading paper</p>
            <p className="text-sm">{error}</p>
          </div>
          <div className="space-x-3">
            <button
              onClick={loadPaper}
              className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
            >
              Try again
            </button>
            <button
              onClick={() => navigate(resolveProjectPath())}
              className="rounded-md bg-gray-600 px-4 py-2 text-white hover:bg-gray-700"
            >
              Back to papers
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!paper) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <h2 className="mb-2 text-xl font-semibold text-gray-900">Paper not found</h2>
          <p className="mb-4 text-gray-600">The paper you're looking for doesn't exist.</p>
          <button
            onClick={() => navigate(resolveProjectPath())}
            className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
          >
            Back to papers
          </button>
        </div>
      </div>
    )
  }

  const isLatexPaper = Boolean(
    parsedContentJson &&
    typeof parsedContentJson === 'object' &&
    (parsedContentJson as any).authoring_mode === 'latex'
  )
  const latexSource = isLatexPaper
    ? String((parsedContentJson as any)?.latex_source || '')
    : ''

  if (isLatexPaper) {
    return (
      <LatexPaperView
        paper={paper}
        latexSource={latexSource}
        onBack={() => navigate(resolveProjectPath(`/papers/${getPaperUrlId(paper)}`))}
      />
    )
  }

  return (
    <OnlyOfficePaperView
      paper={paper}
      parsedContentJson={parsedContentJson}
      onBack={() => navigate(resolveProjectPath())}
    />
  )
}

export default ViewPaper
