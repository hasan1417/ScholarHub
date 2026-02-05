import React, { useState, useCallback } from 'react'
import {
  ArrowLeft, Library, Save, Loader2, Undo2, Redo2, Sparkles,
  Type, FileText, Lightbulb, Book, Clock, ChevronDown, Bold,
  Italic, Sigma, List, ListOrdered, Image, Table, Link2,
} from 'lucide-react'

interface FormattingItem {
  key: string
  label: string
  title: string
  icon: React.ReactNode
  action: () => void
}

interface FormattingGroup {
  label: string
  items: FormattingItem[]
}

interface EditorToolbarProps {
  // View mode
  viewMode: 'code' | 'split' | 'pdf'
  onSetViewMode: (mode: 'code' | 'split' | 'pdf') => void

  // Navigation
  onNavigateBack?: () => void
  templateTitle?: string

  // Collaboration
  collaborationStatus?: string | null

  // Compile
  compileStatus: 'idle' | 'compiling' | 'success' | 'error'
  compileError: string | null
  lastCompileAt: number | null
  onCompile: () => void

  // Save
  readOnly: boolean
  disableSave?: boolean
  saveState: 'idle' | 'saving' | 'success' | 'error'
  saveError: string | null
  onSave: () => void

  // Undo/Redo
  undoEnabled: boolean
  redoEnabled: boolean
  onUndo: () => void
  onRedo: () => void

  // Text selection
  hasTextSelected: boolean

  // Formatting
  formattingGroups: FormattingGroup[]
  onInsertBold: () => void
  onInsertItalics: () => void
  onInsertInlineMath: () => void
  onInsertCite: () => void
  onInsertFigure: () => void
  onInsertTable: () => void
  onInsertItemize: () => void
  onInsertEnumerate: () => void

  // References
  paperId?: string
  onOpenReferences: (event: React.MouseEvent<HTMLButtonElement>) => void

  // History
  onOpenHistory: () => void

  // AI actions
  aiActionLoading: string | null
  onAiAction: (action: string, tone?: string) => void
}

export const EditorToolbar: React.FC<EditorToolbarProps> = ({
  viewMode,
  onSetViewMode,
  onNavigateBack,
  templateTitle,
  collaborationStatus,
  compileStatus,
  compileError,
  lastCompileAt,
  onCompile,
  readOnly,
  disableSave,
  saveState,
  saveError,
  onSave,
  undoEnabled,
  redoEnabled,
  onUndo,
  onRedo,
  hasTextSelected,
  formattingGroups,
  onInsertBold,
  onInsertItalics,
  onInsertInlineMath,
  onInsertCite,
  onInsertFigure,
  onInsertTable,
  onInsertItemize,
  onInsertEnumerate,
  paperId,
  onOpenReferences,
  onOpenHistory,
  aiActionLoading,
  onAiAction,
}) => {
  const [openDropdown, setOpenDropdown] = useState<string | null>(null)
  const [aiToolsMenuOpen, setAiToolsMenuOpen] = useState(false)
  const [toneMenuOpen, setToneMenuOpen] = useState(false)
  const [toneMenuAnchor, setToneMenuAnchor] = useState<HTMLElement | null>(null)

  const formattingDisabled = readOnly

  const handleToneButtonClick = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    if (readOnly || !hasTextSelected) return
    setToneMenuAnchor(event.currentTarget)
    setToneMenuOpen(true)
  }, [readOnly, hasTextSelected])

  const handleToneSelect = useCallback(async (tone: string) => {
    setToneMenuOpen(false)
    await onAiAction('tone', tone)
    setToneMenuAnchor(null)
  }, [onAiAction])

  return (
    <>
      {/* Header bar */}
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-3 py-2 text-slate-700 transition-colors dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-200">
        <div className="flex items-center gap-3">
          {onNavigateBack && (
            <button
              aria-label="Back to paper details"
              onClick={onNavigateBack}
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-300 bg-white text-slate-600 transition-colors hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
          )}
          <span className="text-sm font-semibold">{templateTitle || 'LaTeX Source'}</span>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500 dark:text-slate-300">
          {collaborationStatus && (
            <span className="inline-flex items-center gap-1 rounded border border-indigo-200 bg-indigo-50 px-2 py-1 font-medium text-indigo-600 dark:border-indigo-300/40 dark:bg-indigo-400/20 dark:text-indigo-100">
              {collaborationStatus}
            </span>
          )}
          {compileStatus === 'error' && compileError && (
            <span className="max-w-xs truncate text-rose-600 dark:text-rose-200" title={compileError}>{compileError}</span>
          )}
          {compileStatus === 'success' && lastCompileAt && (
            <span className="text-emerald-600 dark:text-emerald-200">Compiled {Math.max(1, Math.round((Date.now() - lastCompileAt) / 1000))}s ago</span>
          )}
          {saveState === 'saving' && <span className="text-indigo-500 dark:text-indigo-200">Saving…</span>}
          {saveState === 'success' && <span className="text-emerald-600 dark:text-emerald-200">Draft saved</span>}
          {saveState === 'error' && saveError && <span className="max-w-xs truncate text-rose-600 dark:text-rose-200" title={saveError}>{saveError}</span>}
        </div>
      </div>

      {/* Toolbar row */}
      <div className="border-b border-slate-200 bg-slate-50 px-2 py-1.5 transition-colors dark:border-slate-700 dark:bg-slate-800/90">
        <div className="flex items-center gap-1">
          {/* View Mode Toggle */}
          <div className="inline-flex items-center rounded-md bg-slate-200/80 p-0.5 dark:bg-slate-700">
            {(['code', 'split', 'pdf'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => onSetViewMode(mode)}
                className={`rounded px-3 py-1 text-xs font-medium transition-all ${
                  viewMode === mode
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white'
                }`}
              >
                {mode === 'code' ? 'Code' : mode === 'split' ? 'Split' : 'PDF'}
              </button>
            ))}
          </div>

          <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

          {viewMode !== 'pdf' && !readOnly && (
            <>
              {/* Undo/Redo */}
              <button
                type="button"
                onClick={onUndo}
                disabled={!undoEnabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 disabled:hover:bg-transparent dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Undo"
              >
                <Undo2 className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={onRedo}
                disabled={!redoEnabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 disabled:hover:bg-transparent dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Redo"
              >
                <Redo2 className="h-4 w-4" />
              </button>

              <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

              {/* Structure Dropdown */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setOpenDropdown(openDropdown === 'structure' ? null : 'structure')}
                  disabled={formattingDisabled}
                  className={`inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition-colors ${
                    formattingDisabled
                      ? 'cursor-not-allowed text-slate-400'
                      : openDropdown === 'structure'
                      ? 'bg-slate-200 text-slate-900 dark:bg-slate-600 dark:text-white'
                      : 'text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700'
                  }`}
                >
                  <span>Normal text</span>
                  <ChevronDown className="h-3 w-3" />
                </button>
                {openDropdown === 'structure' && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setOpenDropdown(null)} />
                    <div className="absolute left-0 top-full z-50 mt-1 min-w-[160px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-600 dark:bg-slate-800">
                      <button
                        onClick={() => { setOpenDropdown(null) }}
                        className="flex w-full items-center px-3 py-1.5 text-left text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                      >
                        Normal text
                      </button>
                      {formattingGroups.find(g => g.label === 'Structure')?.items.map(item => (
                        <button
                          key={item.key}
                          onClick={() => { item.action(); setOpenDropdown(null) }}
                          className={`flex w-full items-center px-3 py-1.5 text-left hover:bg-slate-100 dark:hover:bg-slate-700 ${
                            item.key === 'section' ? 'text-lg font-bold text-slate-800 dark:text-slate-100' :
                            item.key === 'subsection' ? 'text-base font-semibold text-slate-700 dark:text-slate-200' :
                            'text-sm font-medium text-slate-600 dark:text-slate-300'
                          }`}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>

              <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

              {/* Text Formatting Icons */}
              <button
                type="button"
                onClick={onInsertBold}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Bold (\\textbf)"
              >
                <Bold className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={onInsertItalics}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Italic (\\textit)"
              >
                <Italic className="h-4 w-4" />
              </button>

              <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

              {/* Math */}
              <button
                type="button"
                onClick={onInsertInlineMath}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Inline math ($...$)"
              >
                <Sigma className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={onInsertCite}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Citation (\\cite)"
              >
                <Link2 className="h-4 w-4" />
              </button>

              <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

              {/* Insert Elements */}
              <button
                type="button"
                onClick={onInsertFigure}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Insert figure"
              >
                <Image className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={onInsertTable}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Insert table"
              >
                <Table className="h-4 w-4" />
              </button>

              <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

              {/* Lists */}
              <button
                type="button"
                onClick={onInsertItemize}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Bullet list"
              >
                <List className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={onInsertEnumerate}
                disabled={formattingDisabled}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="Numbered list"
              >
                <ListOrdered className="h-4 w-4" />
              </button>

              <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

              {/* More formatting dropdown */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setOpenDropdown(openDropdown === 'more' ? null : 'more')}
                  disabled={formattingDisabled}
                  className={`rounded p-1.5 transition-colors ${
                    formattingDisabled
                      ? 'cursor-not-allowed text-slate-400'
                      : openDropdown === 'more'
                      ? 'bg-slate-200 text-slate-900 dark:bg-slate-600 dark:text-white'
                      : 'text-slate-500 hover:bg-slate-200 dark:text-slate-400 dark:hover:bg-slate-700'
                  }`}
                  title="More formatting"
                >
                  <ChevronDown className="h-4 w-4" />
                </button>
                {openDropdown === 'more' && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setOpenDropdown(null)} />
                    <div className="absolute left-0 top-full z-50 mt-1 min-w-[180px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-600 dark:bg-slate-800">
                      <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Text</div>
                      {formattingGroups.find(g => g.label === 'Text')?.items.filter(i => !['bold', 'italic'].includes(i.key)).map(item => (
                        <button
                          key={item.key}
                          onClick={() => { item.action(); setOpenDropdown(null) }}
                          className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                        >
                          {item.icon}
                          <span>{item.label}</span>
                        </button>
                      ))}
                      <div className="my-1 border-t border-slate-200 dark:border-slate-600" />
                      <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">Math</div>
                      {formattingGroups.find(g => g.label === 'Math')?.items.filter(i => i.key !== 'math-inline').map(item => (
                        <button
                          key={item.key}
                          onClick={() => { item.action(); setOpenDropdown(null) }}
                          className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                        >
                          {item.icon}
                          <span>{item.label}</span>
                        </button>
                      ))}
                      <div className="my-1 border-t border-slate-200 dark:border-slate-600" />
                      <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">References</div>
                      {formattingGroups.find(g => g.label === 'References')?.items.map(item => (
                        <button
                          key={item.key}
                          onClick={() => { item.action(); setOpenDropdown(null) }}
                          className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                        >
                          {item.icon}
                          <span>{item.label}</span>
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>

              <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />

              <button
                type="button"
                onClick={onOpenReferences}
                disabled={readOnly || !paperId}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="References & Citations"
              >
                <Library className="h-4 w-4" />
              </button>

              {/* AI Text Tools Dropdown */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => !aiActionLoading && setAiToolsMenuOpen(!aiToolsMenuOpen)}
                  disabled={readOnly || (!hasTextSelected && !aiActionLoading)}
                  className={`rounded p-1.5 transition-colors disabled:opacity-30 ${
                    aiToolsMenuOpen || aiActionLoading
                      ? 'bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-300'
                      : 'text-slate-500 hover:bg-slate-200 dark:text-slate-400 dark:hover:bg-slate-700'
                  }`}
                  title={aiActionLoading ? `Processing: ${aiActionLoading}...` : hasTextSelected ? 'AI text tools' : 'Select text first'}
                >
                  {aiActionLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="h-4 w-4" />
                  )}
                </button>
                {(aiToolsMenuOpen || aiActionLoading) && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => !aiActionLoading && setAiToolsMenuOpen(false)} />
                    <div className="absolute right-0 top-full z-50 mt-1 min-w-[150px] rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-600 dark:bg-slate-800">
                      <button
                        onClick={() => { if (!aiActionLoading) { onAiAction('paraphrase') } }}
                        disabled={!!aiActionLoading}
                        className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs ${aiActionLoading === 'paraphrase' ? 'bg-violet-50 text-violet-700 dark:bg-violet-500/20 dark:text-violet-300' : aiActionLoading ? 'opacity-40 cursor-not-allowed text-slate-400 dark:text-slate-500' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700'}`}
                      >
                        {aiActionLoading === 'paraphrase' ? <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-500" /> : <Sparkles className="h-3.5 w-3.5 text-violet-500" />}
                        Paraphrase
                      </button>
                      <button
                        onClick={() => { if (!aiActionLoading) { onAiAction('summarize') } }}
                        disabled={!!aiActionLoading}
                        className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs ${aiActionLoading === 'summarize' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300' : aiActionLoading ? 'opacity-40 cursor-not-allowed text-slate-400 dark:text-slate-500' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700'}`}
                      >
                        {aiActionLoading === 'summarize' ? <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-500" /> : <FileText className="h-3.5 w-3.5 text-emerald-500" />}
                        Summarize
                      </button>
                      <button
                        onClick={() => { if (!aiActionLoading) { onAiAction('explain') } }}
                        disabled={!!aiActionLoading}
                        className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs ${aiActionLoading === 'explain' ? 'bg-amber-50 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300' : aiActionLoading ? 'opacity-40 cursor-not-allowed text-slate-400 dark:text-slate-500' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700'}`}
                      >
                        {aiActionLoading === 'explain' ? <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-500" /> : <Lightbulb className="h-3.5 w-3.5 text-amber-500" />}
                        Explain
                      </button>
                      <button
                        onClick={() => { if (!aiActionLoading) { onAiAction('synonyms') } }}
                        disabled={!!aiActionLoading}
                        className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs ${aiActionLoading === 'synonyms' ? 'bg-blue-50 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300' : aiActionLoading ? 'opacity-40 cursor-not-allowed text-slate-400 dark:text-slate-500' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700'}`}
                      >
                        {aiActionLoading === 'synonyms' ? <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" /> : <Book className="h-3.5 w-3.5 text-blue-500" />}
                        Synonyms
                      </button>
                      <div className="my-1 border-t border-slate-200 dark:border-slate-600" />
                      <button
                        onClick={(e) => { if (!aiActionLoading) handleToneButtonClick(e) }}
                        disabled={!!aiActionLoading}
                        className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs ${aiActionLoading?.startsWith('tone_') ? 'bg-rose-50 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300' : aiActionLoading ? 'opacity-40 cursor-not-allowed text-slate-400 dark:text-slate-500' : 'text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700'}`}
                      >
                        {aiActionLoading?.startsWith('tone_') ? <Loader2 className="h-3.5 w-3.5 animate-spin text-rose-500" /> : <Type className="h-3.5 w-3.5 text-rose-500" />}
                        Change Tone...
                      </button>
                    </div>
                  </>
                )}
              </div>
            </>
          )}

          {/* Spacer */}
          <div className="flex-1" />

          {/* Right side: History, Compile, Save */}
          <div className="flex items-center gap-1">
            {paperId && (
              <button
                type="button"
                onClick={onOpenHistory}
                className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                title="History"
              >
                <Clock className="h-4 w-4" />
              </button>
            )}

            {!(disableSave || readOnly) && (
              <button
                type="button"
                className={`rounded p-1.5 transition-colors ${
                  saveState === 'saving'
                    ? 'text-indigo-500'
                    : saveState === 'success'
                    ? 'text-emerald-500'
                    : saveState === 'error'
                    ? 'text-rose-500'
                    : 'text-slate-500 hover:bg-slate-200 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-700'
                }`}
                onClick={onSave}
                disabled={!!(disableSave || readOnly)}
                title={saveState === 'saving' ? 'Saving...' : saveState === 'success' ? 'Saved' : 'Save'}
              >
                {saveState === 'saving' ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
              </button>
            )}

            <button
              type="button"
              className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-semibold transition-colors ${
                compileStatus === 'compiling'
                  ? 'cursor-wait bg-slate-400 text-white'
                  : compileStatus === 'success'
                  ? 'bg-emerald-600 text-white hover:bg-emerald-700'
                  : compileStatus === 'error'
                  ? 'bg-rose-600 text-white hover:bg-rose-700'
                  : 'bg-emerald-600 text-white hover:bg-emerald-700'
              }`}
              onClick={onCompile}
              disabled={compileStatus === 'compiling'}
              title="Recompile"
            >
              {compileStatus === 'compiling' ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Compiling</span>
                </>
              ) : (
                <span>Recompile</span>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Tone Selector Menu */}
      {(toneMenuOpen || aiActionLoading?.startsWith('tone_')) && toneMenuAnchor && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => {
              if (!aiActionLoading) {
                setToneMenuOpen(false)
                setToneMenuAnchor(null)
              }
            }}
          />
          <div
            className="fixed z-50 min-w-[160px] rounded-lg border border-slate-200 bg-white shadow-xl dark:border-slate-600 dark:bg-slate-800"
            style={{
              top: `${toneMenuAnchor.getBoundingClientRect().bottom + 8}px`,
              left: `${toneMenuAnchor.getBoundingClientRect().left}px`,
            }}
          >
            <div className="p-2">
              <div className="mb-2 px-2 text-xs font-semibold text-slate-600 dark:text-slate-400">
                {aiActionLoading?.startsWith('tone_') ? 'Processing...' : 'Select Tone'}
              </div>
              {['formal', 'casual', 'academic', 'friendly', 'professional'].map((tone) => (
                <button
                  key={tone}
                  onClick={() => !aiActionLoading && handleToneSelect(tone)}
                  disabled={!!aiActionLoading}
                  className={`flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm transition-colors ${
                    aiActionLoading === `tone_${tone}`
                      ? 'bg-rose-50 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300'
                      : aiActionLoading
                      ? 'cursor-not-allowed text-slate-400 opacity-40 dark:text-slate-500'
                      : 'text-slate-600 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700'
                  }`}
                >
                  {aiActionLoading === `tone_${tone}` && <Loader2 className="h-3.5 w-3.5 animate-spin text-rose-500" />}
                  {tone.charAt(0).toUpperCase() + tone.slice(1)}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  )
}
