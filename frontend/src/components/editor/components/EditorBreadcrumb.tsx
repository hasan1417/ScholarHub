import { FileText, ChevronRight } from 'lucide-react'

interface EditorBreadcrumbProps {
  activeFile: string
  currentSection?: string
}

export const EditorBreadcrumb: React.FC<EditorBreadcrumbProps> = ({
  activeFile,
  currentSection,
}) => {
  return (
    <div className="flex h-6 items-center gap-1.5 border-b border-slate-200 bg-slate-50 px-3 text-xs dark:border-slate-700/60 dark:bg-slate-800/60">
      <FileText className="h-3 w-3 flex-shrink-0 text-slate-400 dark:text-slate-500" />
      <span className="text-slate-600 dark:text-slate-300">{activeFile || 'main.tex'}</span>
      {currentSection && (
        <>
          <ChevronRight className="h-3 w-3 flex-shrink-0 text-slate-400 dark:text-slate-500" />
          <span className="truncate text-slate-500 dark:text-slate-400">
            {currentSection}
          </span>
        </>
      )}
    </div>
  )
}
