import React from 'react'
import { Files, Search, ToggleLeft, ToggleRight, FileSearch, Loader2, ClipboardCheck } from 'lucide-react'

interface EditorSideRailProps {
  activePanel: 'files' | 'search' | null
  onTogglePanel: (panel: 'files' | 'search') => void
  // Track changes
  trackChangesEnabled?: boolean
  onToggleTrackChanges?: () => void
  trackChangesPanelOpen?: boolean
  onToggleTrackChangesPanel?: () => void
  hasTrackedChanges?: boolean
  // Writing analysis
  writingAnalysisPanelOpen?: boolean
  onToggleWritingAnalysis?: () => void
  writingAnalysisLoading?: boolean
}

const RailButton: React.FC<{
  active?: boolean
  title: string
  onClick: () => void
  children: React.ReactNode
  className?: string
}> = ({ active, title, onClick, children, className }) => (
  <button
    type="button"
    title={title}
    onClick={onClick}
    className={`relative flex h-9 w-full items-center justify-center transition-colors ${
      active
        ? 'text-slate-900 dark:text-white before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-indigo-500 dark:before:bg-indigo-400'
        : 'text-slate-400 hover:text-slate-700 dark:text-slate-500 dark:hover:text-slate-300'
    } ${className || ''}`}
  >
    {children}
  </button>
)

export const EditorSideRail: React.FC<EditorSideRailProps> = ({
  activePanel,
  onTogglePanel,
  trackChangesEnabled,
  onToggleTrackChanges,
  trackChangesPanelOpen,
  onToggleTrackChangesPanel,
  hasTrackedChanges,
  writingAnalysisPanelOpen,
  onToggleWritingAnalysis,
  writingAnalysisLoading,
}) => {
  return (
    <div className="flex h-full w-9 flex-shrink-0 flex-col border-r border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-900">
      {/* Top icons */}
      <div className="flex flex-col">
        <RailButton
          active={activePanel === 'files'}
          title="File tree"
          onClick={() => onTogglePanel('files')}
        >
          <Files className="h-5 w-5" />
        </RailButton>
        <RailButton
          active={activePanel === 'search'}
          title="Search (coming soon)"
          onClick={() => onTogglePanel('search')}
        >
          <Search className="h-5 w-5" />
        </RailButton>
      </div>

      {/* Divider */}
      <div className="mx-1.5 border-t border-slate-200 dark:border-slate-700" />

      {/* Review & analysis */}
      <div className="flex flex-col">
        {onToggleWritingAnalysis && (
          <RailButton
            active={writingAnalysisPanelOpen}
            title="Writing quality analysis"
            onClick={onToggleWritingAnalysis}
          >
            {writingAnalysisLoading
              ? <Loader2 className="h-5 w-5 animate-spin" />
              : <FileSearch className="h-5 w-5" />}
          </RailButton>
        )}

        {onToggleTrackChanges && (
          <RailButton
            active={trackChangesEnabled}
            title={trackChangesEnabled ? 'Track changes ON' : 'Track changes OFF'}
            onClick={onToggleTrackChanges}
            className={trackChangesEnabled ? '!text-amber-600 dark:!text-amber-400' : ''}
          >
            {trackChangesEnabled
              ? <ToggleRight className="h-5 w-5" />
              : <ToggleLeft className="h-5 w-5" />}
          </RailButton>
        )}

        {onToggleTrackChangesPanel && hasTrackedChanges && (
          <RailButton
            active={trackChangesPanelOpen}
            title="Review tracked changes"
            onClick={onToggleTrackChangesPanel}
            className={trackChangesPanelOpen ? '!text-amber-600 dark:!text-amber-400' : ''}
          >
            <ClipboardCheck className="h-5 w-5" />
          </RailButton>
        )}
      </div>
    </div>
  )
}
