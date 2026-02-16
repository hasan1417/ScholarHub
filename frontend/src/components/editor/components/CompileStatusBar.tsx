import React from 'react'

interface CompileStatusBarProps {
  collaborationStatus?: string | null
  compileStatus: 'idle' | 'compiling' | 'success' | 'error'
  compileError: string | null
  lastCompileAt: number | null
  saveState: 'idle' | 'saving' | 'success' | 'error'
  saveError: string | null
  wordCount?: number | null
}

export const CompileStatusBar: React.FC<CompileStatusBarProps> = ({
  collaborationStatus,
  compileStatus,
  compileError,
  lastCompileAt,
  saveState,
  saveError,
  wordCount,
}) => {
  return (
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
      {typeof wordCount === 'number' && wordCount > 0 && (
        <span className="text-slate-400 dark:text-slate-400">{wordCount.toLocaleString()} words</span>
      )}
    </div>
  )
}
