export interface EditorAdapterHandle {
  getSelection: () => Promise<string>
  insertText: (text: string) => Promise<void>
  replaceSelection?: (text: string) => Promise<void>
  setContent?: (html: string, options?: { overwriteRealtime?: boolean }) => Promise<void>
  insertHTML?: (html: string) => Promise<void>
  insertBibliography?: (heading: string, items: string[]) => Promise<void>
  save: () => Promise<void>
  focus: () => void
  getCurrentCommitId?: () => Promise<string | null>
  scrollToLine?: (line: number) => Promise<void>
  replaceLines?: (fromLine: number, toLine: number, text: string) => Promise<void>
}

export interface EditorAdapterProps {
  content: string | any
  contentJson?: any
  onContentChange: (html: string, json?: any) => void
  onSelectionChange?: (selectionText: string) => void
  onReady?: (saveFn: () => Promise<void>) => void
  onDirtyChange?: (dirty: boolean) => void
  className?: string
  paperId?: string
  projectId?: string
  paperTitle?: string
  theme?: 'light' | 'dark'
  lockedSectionKeys?: string[]
  branchName?: 'draft' | 'published'
  readOnly?: boolean
  onNavigateBack?: () => void
  onOpenReferences?: () => void
  onOpenAiAssistant?: (anchor: HTMLElement | null) => void
  onInsertBibliographyShortcut?: () => void
  realtime?: {
    doc: any
    awareness?: any
    provider?: any
    status?: 'idle' | 'connecting' | 'connected' | 'disconnected'
    peers?: Array<{ id: string; name: string; email: string; color?: string }>
    synced?: boolean
    enabled?: boolean
  }
  collaborationStatus?: string | null
}
