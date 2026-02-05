import React from 'react'

interface PdfPreviewPaneProps {
  iframeRef: React.Ref<HTMLIFrameElement>
  pdfViewerHtml: string
  compileStatus: 'idle' | 'compiling' | 'success' | 'error'
  compileError: string | null
  compileLogs: string[]
  lastCompileAt: number | null
}

export const PdfPreviewPane: React.FC<PdfPreviewPaneProps> = ({
  iframeRef,
  pdfViewerHtml,
  compileStatus,
  compileError,
  compileLogs,
  lastCompileAt,
}) => (
  <>
    <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-300">
      <span className="font-medium text-slate-600 dark:text-slate-200">PDF Preview</span>
      {compileStatus === 'compiling' && <span className="text-indigo-500 dark:text-indigo-300">Updating…</span>}
      {compileStatus === 'success' && lastCompileAt && <span className="text-slate-500 dark:text-slate-300">Updated {Math.max(1, Math.round((Date.now() - lastCompileAt) / 1000))}s ago</span>}
      {compileStatus === 'error' && compileError && <span className="text-rose-500 dark:text-rose-300" title={compileError}>Compile failed</span>}
    </div>
    <div className="overflow-hidden flex-1">
      <iframe
        ref={iframeRef}
        id="latex-preview-frame"
        title="Compiled PDF"
        srcDoc={pdfViewerHtml}
        data-loaded="false"
        className="h-full w-full"
      />
    </div>
    {compileLogs.length > 0 && (
      <div className="max-h-40 overflow-auto border-t border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-600 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300">
        {compileLogs.slice(-60).map((line, idx) => (
          <div key={idx} className="whitespace-pre-wrap">{line}</div>
        ))}
      </div>
    )}
  </>
)
