import { useState } from 'react'
import {
  FileText,
  BookOpen,
  Calendar,
  Check,
  ChevronDown,
  Loader2,
} from 'lucide-react'
import {
  ChannelScopeConfig,
  ResearchPaper,
  ProjectReferenceSuggestion,
  MeetingSummary,
} from '../../types'

const ResourceScopePicker = ({
  scope,
  papers,
  references,
  meetings,
  onToggle,
  isLoading,
}: {
  scope: ChannelScopeConfig
  papers: ResearchPaper[]
  references: ProjectReferenceSuggestion[]
  meetings: MeetingSummary[]
  onToggle: (type: 'paper' | 'reference' | 'meeting', id: string) => void
  isLoading: boolean
}) => {
  const [expandedSections, setExpandedSections] = useState<string[]>(['papers', 'references', 'meetings'])

  const toggleSection = (section: string) => {
    setExpandedSections((prev) =>
      prev.includes(section) ? prev.filter((s) => s !== section) : [...prev, section]
    )
  }

  const selectedPaperIds = new Set(scope.paper_ids || [])
  const selectedReferenceIds = new Set(scope.reference_ids || [])
  const selectedMeetingIds = new Set(scope.meeting_ids || [])

  const totalSelected = selectedPaperIds.size + selectedReferenceIds.size + selectedMeetingIds.size

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-4">
        <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        <span className="ml-2 text-sm text-gray-500">Loading resources...</span>
      </div>
    )
  }

  return (
    <div className="divide-y divide-gray-100 dark:divide-slate-700">
      {totalSelected > 0 && (
        <div className="bg-indigo-50 px-3 py-2 text-xs text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300">
          {totalSelected} resource{totalSelected !== 1 ? 's' : ''} selected
        </div>
      )}

      {/* Papers Section */}
      {papers.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => toggleSection('papers')}
            className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-slate-800"
          >
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-blue-500" />
              <span className="text-sm font-medium text-gray-700 dark:text-slate-200">Papers</span>
              {selectedPaperIds.size > 0 && (
                <span className="rounded-full bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700 dark:bg-blue-500/20 dark:text-blue-300">
                  {selectedPaperIds.size}
                </span>
              )}
            </div>
            <ChevronDown className={`h-4 w-4 text-gray-400 transition ${expandedSections.includes('papers') ? 'rotate-180' : ''}`} />
          </button>
          {expandedSections.includes('papers') && (
            <div className="space-y-1 px-3 pb-2">
              {papers.map((paper) => (
                <label
                  key={paper.id}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-gray-50 dark:hover:bg-slate-800"
                >
                  <div className={`flex h-4 w-4 items-center justify-center rounded border ${
                    selectedPaperIds.has(paper.id)
                      ? 'border-indigo-500 bg-indigo-500'
                      : 'border-gray-300 dark:border-slate-600'
                  }`}>
                    {selectedPaperIds.has(paper.id) && <Check className="h-3 w-3 text-white" />}
                  </div>
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={selectedPaperIds.has(paper.id)}
                    onChange={() => onToggle('paper', paper.id)}
                  />
                  <span className="text-sm text-gray-700 dark:text-slate-300 truncate">{paper.title || 'Untitled Paper'}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      {/* References Section */}
      {references.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => toggleSection('references')}
            className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-slate-800"
          >
            <div className="flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-emerald-500" />
              <span className="text-sm font-medium text-gray-700 dark:text-slate-200">References</span>
              {selectedReferenceIds.size > 0 && (
                <span className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300">
                  {selectedReferenceIds.size}
                </span>
              )}
            </div>
            <ChevronDown className={`h-4 w-4 text-gray-400 transition ${expandedSections.includes('references') ? 'rotate-180' : ''}`} />
          </button>
          {expandedSections.includes('references') && (
            <div className="space-y-1 px-3 pb-2">
              {references.map((ref) => (
                <label
                  key={ref.reference_id}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-gray-50 dark:hover:bg-slate-800"
                >
                  <div className={`flex h-4 w-4 items-center justify-center rounded border ${
                    selectedReferenceIds.has(ref.reference_id)
                      ? 'border-indigo-500 bg-indigo-500'
                      : 'border-gray-300 dark:border-slate-600'
                  }`}>
                    {selectedReferenceIds.has(ref.reference_id) && <Check className="h-3 w-3 text-white" />}
                  </div>
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={selectedReferenceIds.has(ref.reference_id)}
                    onChange={() => onToggle('reference', ref.reference_id)}
                  />
                  <span className="text-sm text-gray-700 dark:text-slate-300 truncate">{ref.reference?.title || 'Untitled Reference'}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Meetings Section */}
      {meetings.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => toggleSection('meetings')}
            className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-slate-800"
          >
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-purple-500" />
              <span className="text-sm font-medium text-gray-700 dark:text-slate-200">Meetings</span>
              {selectedMeetingIds.size > 0 && (
                <span className="rounded-full bg-purple-100 px-1.5 py-0.5 text-xs text-purple-700 dark:bg-purple-500/20 dark:text-purple-300">
                  {selectedMeetingIds.size}
                </span>
              )}
            </div>
            <ChevronDown className={`h-4 w-4 text-gray-400 transition ${expandedSections.includes('meetings') ? 'rotate-180' : ''}`} />
          </button>
          {expandedSections.includes('meetings') && (
            <div className="space-y-1 px-3 pb-2">
              {meetings.map((meeting) => (
                <label
                  key={meeting.id}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-gray-50 dark:hover:bg-slate-800"
                >
                  <div className={`flex h-4 w-4 items-center justify-center rounded border ${
                    selectedMeetingIds.has(meeting.id)
                      ? 'border-indigo-500 bg-indigo-500'
                      : 'border-gray-300 dark:border-slate-600'
                  }`}>
                    {selectedMeetingIds.has(meeting.id) && <Check className="h-3 w-3 text-white" />}
                  </div>
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={selectedMeetingIds.has(meeting.id)}
                    onChange={() => onToggle('meeting', meeting.id)}
                  />
                  <span className="text-sm text-gray-700 dark:text-slate-300 truncate">{meeting.summary || `Meeting ${meeting.id.slice(0, 8)}`}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      {papers.length === 0 && references.length === 0 && meetings.length === 0 && (
        <div className="px-3 py-4 text-center text-sm text-gray-500 dark:text-slate-400">
          No resources available in this project yet.
        </div>
      )}
    </div>
  )
}

export default ResourceScopePicker
