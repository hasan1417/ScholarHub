import React, { useState, useEffect, useRef, useCallback } from 'react'
import {
  X, ChevronRight, ChevronDown, FileText, Plus, Upload,
  Image, Loader2, Trash2, FolderOpen, FileCode, BookTemplate, ListTree,
} from 'lucide-react'
import type { EditorView } from '@codemirror/view'
import type { Text as YText } from 'yjs'
import { researchPapersAPI, latexAPI } from '../../../services/api'
import type { SupportFile, ConferenceTemplate } from '../../../types'
import { FileContextMenu } from './FileContextMenu'

interface OutlineItem {
  title: string
  level: number
  from: number
}

interface FilePanelProps {
  paperId: string
  fileList: string[]
  activeFile: string
  onSelectFile: (file: string) => void
  onCreateFile: (filename: string) => void
  onDeleteFile: (file: string) => void
  readOnly: boolean
  editorViewRef?: React.RefObject<EditorView | null>
  canCreateFiles?: boolean
  /** Y.Text for the active file (realtime mode). When provided, template
   *  application writes to Y.Text directly instead of via CM dispatch,
   *  which avoids desync issues with full-document replacements. */
  yText?: YText | null
  outlineItems?: OutlineItem[]
  onScrollToSection?: (from: number) => void
}

interface FigureFile {
  filename: string
  size: number
}

// Collapsible section header
const SectionHeader: React.FC<{
  title: string
  count?: number
  expanded: boolean
  onToggle: () => void
  action?: React.ReactNode
}> = ({ title, count, expanded, onToggle, action }) => (
  <div className="flex items-center justify-between px-3 py-2">
    <button
      type="button"
      onClick={onToggle}
      className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"
    >
      {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
      <span>{title}</span>
      {count != null && count > 0 && (
        <span className="rounded-full bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
          {count}
        </span>
      )}
    </button>
    {action}
  </div>
)

const SUPPORT_EXTENSIONS = '.cls,.sty,.bst,.bib,.def,.fd'

// Indent px per outline level (section=2 -> 0, subsection=3 -> 1 indent, etc.)
const OUTLINE_INDENT_BASE = 2 // level for \section
const OUTLINE_INDENT_PX = 12

export const FilePanel: React.FC<FilePanelProps> = ({
  paperId,
  fileList,
  activeFile,
  onSelectFile,
  onCreateFile,
  onDeleteFile,
  readOnly,
  editorViewRef,
  canCreateFiles = true,
  yText,
  outlineItems,
  onScrollToSection,
}) => {
  // New file creation
  const [isCreating, setIsCreating] = useState(false)
  const [newFileName, setNewFileName] = useState('')

  const handleCreateSubmit = useCallback(() => {
    let name = newFileName.trim()
    if (!name) return
    if (!name.endsWith('.tex')) name += '.tex'
    if (fileList.includes(name)) {
      setNewFileName('')
      setIsCreating(false)
      return
    }
    onCreateFile(name)
    setNewFileName('')
    setIsCreating(false)
  }, [newFileName, fileList, onCreateFile])

  // Section expand states
  const [texExpanded, setTexExpanded] = useState(true)
  const [supportExpanded, setSupportExpanded] = useState(true)
  const [figuresExpanded, setFiguresExpanded] = useState(false)
  const [templatesExpanded, setTemplatesExpanded] = useState(false)
  const [outlineExpanded, setOutlineExpanded] = useState(true)

  // Support files state
  const [supportFiles, setSupportFiles] = useState<SupportFile[]>([])
  const [supportLoading, setSupportLoading] = useState(false)
  const [supportUploading, setSupportUploading] = useState(false)
  const supportInputRef = useRef<HTMLInputElement>(null)

  // Figures state
  const [figures, setFigures] = useState<FigureFile[]>([])
  const [figuresLoading, setFiguresLoading] = useState(false)
  const [figureUploading, setFigureUploading] = useState(false)
  const figureInputRef = useRef<HTMLInputElement>(null)

  // Templates state
  const [templates, setTemplates] = useState<ConferenceTemplate[]>([])
  const [templatesLoading, setTemplatesLoading] = useState(false)

  // Context menu state
  const [contextMenu, setContextMenu] = useState<{
    visible: boolean
    x: number
    y: number
    filename: string
  } | null>(null)

  // Rename state: which file is being renamed inline
  const [renamingFile, setRenamingFile] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')

  // Resize handle state for file list / outline split
  const [outlineHeight, setOutlineHeight] = useState(200)
  const resizingRef = useRef(false)
  const resizeStartRef = useRef({ y: 0, height: 0 })
  const containerRef = useRef<HTMLDivElement>(null)

  // Fetch support files
  const fetchSupportFiles = useCallback(async () => {
    setSupportLoading(true)
    try {
      const resp = await researchPapersAPI.listSupportFiles(paperId)
      setSupportFiles(resp.data.files)
    } catch (e) {
      console.error('Failed to load support files', e)
    } finally {
      setSupportLoading(false)
    }
  }, [paperId])

  // Fetch figures
  const fetchFigures = useCallback(async () => {
    setFiguresLoading(true)
    try {
      const resp = await researchPapersAPI.listFigures(paperId)
      setFigures(resp.data.files)
    } catch (e) {
      console.error('Failed to load figures', e)
    } finally {
      setFiguresLoading(false)
    }
  }, [paperId])

  // Fetch templates
  const fetchTemplates = useCallback(async () => {
    setTemplatesLoading(true)
    try {
      const resp = await latexAPI.getTemplates()
      setTemplates(resp.data.templates)
    } catch (e) {
      console.error('Failed to load templates', e)
    } finally {
      setTemplatesLoading(false)
    }
  }, [])

  // Load data on mount
  useEffect(() => {
    fetchSupportFiles()
    fetchFigures()
    fetchTemplates()
  }, [fetchSupportFiles, fetchFigures, fetchTemplates])

  // Upload support file
  const handleSupportUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setSupportUploading(true)
    try {
      await researchPapersAPI.uploadSupportFile(paperId, file)
      await fetchSupportFiles()
    } catch (err) {
      console.error('Support file upload failed', err)
    } finally {
      setSupportUploading(false)
      if (supportInputRef.current) supportInputRef.current.value = ''
    }
  }, [paperId, fetchSupportFiles])

  // Delete support file
  const handleSupportDelete = useCallback(async (filename: string) => {
    if (!confirm(`Delete ${filename}?`)) return
    try {
      await researchPapersAPI.deleteSupportFile(paperId, filename)
      setSupportFiles(prev => prev.filter(f => f.filename !== filename))
    } catch (err) {
      console.error('Failed to delete support file', err)
    }
  }, [paperId])

  // Upload figure
  const handleFigureUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setFigureUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      await researchPapersAPI.uploadFigure(paperId, formData)
      await fetchFigures()
    } catch (err) {
      console.error('Figure upload failed', err)
    } finally {
      setFigureUploading(false)
      if (figureInputRef.current) figureInputRef.current.value = ''
    }
  }, [paperId, fetchFigures])

  // Apply template — replaces everything up to and including \maketitle,
  // preserving user-written body content (sections after \maketitle).
  //
  // In realtime (Yjs) mode we read from and write to Y.Text directly.
  // Going through view.dispatch() for full-document replacements can fail
  // when the CM doc length and Y.Text length are out of sync, which causes
  // the template to be appended instead of replacing content.
  const handleApplyTemplate = useCallback((template: ConferenceTemplate) => {
    const view = editorViewRef?.current
    if (!view) return
    if (activeFile !== 'main.tex') {
      alert('Templates can only be applied to main.tex. Please switch to main.tex first.')
      return
    }
    if (!window.confirm(`Apply "${template.name}" template? This will replace your preamble and title block.`)) return

    // Read from the source of truth: Y.Text in realtime mode, CM doc otherwise
    const doc = (yText && yText.length >= 0) ? yText.toString() : view.state.doc.toString()
    let tpl = template.preamble_example.trimEnd()

    // Preserve the user's existing \title{...} and \date{...} if present
    const braceContent = /\{([^}]*(?:\{[^}]*\}[^}]*)*)\}/
    const userTitleMatch = doc.match(new RegExp('\\\\title' + braceContent.source))
    if (userTitleMatch) {
      tpl = tpl.replace(new RegExp('\\\\title' + braceContent.source), userTitleMatch[0])
    }
    const userDateMatch = doc.match(new RegExp('\\\\date' + braceContent.source))
    if (userDateMatch) {
      tpl = tpl.replace(new RegExp('\\\\date' + braceContent.source), userDateMatch[0])
    }

    let newContent: string
    if (doc.trim().length === 0) {
      // Empty doc: use template as-is, add \end{document}
      newContent = tpl + '\n\n\n\\end{document}\n'
    } else {
      // Find user's body content: everything after the last \maketitle
      // (that's where the actual sections/content begins)
      const maketitleIdx = doc.lastIndexOf('\\maketitle')
      const beginDocIdx = doc.lastIndexOf('\\begin{document}')

      let userBody = ''
      if (maketitleIdx >= 0) {
        userBody = doc.slice(maketitleIdx + '\\maketitle'.length)
      } else if (beginDocIdx >= 0) {
        userBody = doc.slice(beginDocIdx + '\\begin{document}'.length)
      }

      // If userBody is only whitespace + \end{document}, treat as empty
      const bodyWithoutEnd = userBody.replace(/\\end\{document\}\s*$/, '').trim()

      if (bodyWithoutEnd.length === 0) {
        newContent = tpl + '\n\n\n\\end{document}\n'
      } else {
        newContent = tpl + '\n' + userBody
      }
    }

    // Write to the source of truth
    if (yText && yText.doc) {
      // Realtime mode: atomic Y.Text replacement — yCollab observer will
      // sync the change to the CM view automatically.
      yText.doc.transact(() => {
        yText.delete(0, yText.length)
        yText.insert(0, newContent)
      })
    } else {
      // Non-realtime mode: direct CM dispatch
      view.dispatch({
        changes: { from: 0, to: doc.length, insert: newContent },
      })
    }
  }, [editorViewRef, activeFile, yText])

  // Context menu handlers
  const handleContextMenu = useCallback((e: React.MouseEvent, filename: string) => {
    e.preventDefault()
    setContextMenu({ visible: true, x: e.clientX, y: e.clientY, filename })
  }, [])

  const handleContextMenuClose = useCallback(() => {
    setContextMenu(null)
  }, [])

  const handleRenameFromMenu = useCallback((oldName: string, newName: string) => {
    // For .tex files, rename is done inline — trigger inline rename mode
    // The actual rename would need backend support; for now we just show
    // the inline input. The context menu calls this with a prompt result.
    // Since the prompt is handled inside FileContextMenu, we get both names here.
    // For now, we can handle rename by deleting old + creating new if content can be transferred.
    // This is a UI placeholder — full rename requires backend API.
    console.warn('Rename not yet implemented on backend:', oldName, '->', newName)
  }, [])

  const handleFinishRename = useCallback(() => {
    if (renamingFile && renameValue.trim() && renameValue !== renamingFile) {
      handleRenameFromMenu(renamingFile, renameValue.trim())
    }
    setRenamingFile(null)
    setRenameValue('')
  }, [renamingFile, renameValue, handleRenameFromMenu])

  // Resize handle for outline section
  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    resizingRef.current = true
    resizeStartRef.current = { y: e.clientY, height: outlineHeight }

    const handleMouseMove = (ev: MouseEvent) => {
      if (!resizingRef.current) return
      const delta = resizeStartRef.current.y - ev.clientY
      const newHeight = Math.max(60, Math.min(400, resizeStartRef.current.height + delta))
      setOutlineHeight(newHeight)
    }

    const handleMouseUp = () => {
      resizingRef.current = false
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [outlineHeight])

  // Sort fileList: main.tex first, rest alphabetically
  const sortedFiles = [...fileList].sort((a, b) => {
    if (a === 'main.tex') return -1
    if (b === 'main.tex') return 1
    return a.localeCompare(b)
  })

  return (
    <div ref={containerRef} className="flex h-full w-[240px] flex-shrink-0 flex-col overflow-hidden border-r border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2.5 dark:border-slate-700">
        <div className="flex items-center gap-2">
          <FolderOpen className="h-4 w-4 text-slate-500 dark:text-slate-400" />
          <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Files
          </span>
        </div>
      </div>

      {/* Scrollable file sections */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {/* Section 1: .tex Files */}
        <SectionHeader
          title="TeX Files"
          count={fileList.length}
          expanded={texExpanded}
          onToggle={() => setTexExpanded(p => !p)}
          action={!readOnly && canCreateFiles ? (
            <button
              type="button"
              onClick={() => setIsCreating(true)}
              className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
              title="New .tex file"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          ) : undefined}
        />
        {texExpanded && (
          <div className="px-1 pb-2">
            {sortedFiles.map(file => (
              renamingFile === file ? (
                <div key={file} className="px-2 py-1">
                  <input
                    type="text"
                    autoFocus
                    value={renameValue}
                    onChange={e => setRenameValue(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') handleFinishRename()
                      else if (e.key === 'Escape') { setRenamingFile(null); setRenameValue('') }
                    }}
                    onBlur={handleFinishRename}
                    className="w-full rounded border border-slate-300 bg-white px-1.5 py-0.5 text-xs outline-none focus:border-indigo-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
                  />
                </div>
              ) : (
                <button
                  key={file}
                  type="button"
                  onClick={() => onSelectFile(file)}
                  onContextMenu={(e) => handleContextMenu(e, file)}
                  className={`group flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-xs transition-colors ${
                    file === activeFile
                      ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300'
                      : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
                  }`}
                >
                  <FileText className="h-3 w-3 flex-shrink-0" />
                  <span className="flex-1 truncate">{file}</span>
                  {file !== 'main.tex' && !readOnly && (
                    <button
                      type="button"
                      title={`Delete ${file}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        if (confirm(`Delete ${file}?`)) onDeleteFile(file)
                      }}
                      className="hidden rounded p-0.5 text-slate-400 hover:bg-rose-100 hover:text-rose-500 group-hover:inline-flex dark:hover:bg-rose-900/30 dark:hover:text-rose-400"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  )}
                </button>
              )
            ))}
            {isCreating && (
              <div className="px-2 py-1">
                <input
                  type="text"
                  autoFocus
                  value={newFileName}
                  onChange={e => setNewFileName(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') handleCreateSubmit()
                    else if (e.key === 'Escape') { setIsCreating(false); setNewFileName('') }
                  }}
                  onBlur={() => {
                    if (newFileName.trim()) handleCreateSubmit()
                    else setIsCreating(false)
                  }}
                  placeholder="filename.tex"
                  className="w-full rounded border border-slate-300 bg-white px-1.5 py-0.5 text-xs outline-none focus:border-indigo-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
                />
              </div>
            )}
          </div>
        )}

        <div className="mx-3 border-t border-slate-200 dark:border-slate-700" />

        {/* Section 2: Support Files */}
        <SectionHeader
          title="Support Files"
          count={supportFiles.length}
          expanded={supportExpanded}
          onToggle={() => setSupportExpanded(p => !p)}
          action={!readOnly ? (
            <button
              type="button"
              onClick={() => supportInputRef.current?.click()}
              disabled={supportUploading}
              className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
              title="Upload support file"
            >
              {supportUploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
            </button>
          ) : undefined}
        />
        <input
          ref={supportInputRef}
          type="file"
          accept={SUPPORT_EXTENSIONS}
          onChange={handleSupportUpload}
          className="hidden"
        />
        {supportExpanded && (
          <div className="px-1 pb-2">
            {supportLoading ? (
              <div className="flex items-center justify-center py-3">
                <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
              </div>
            ) : supportFiles.length === 0 ? (
              <p className="px-3 py-2 text-[11px] text-slate-400 dark:text-slate-500">
                Upload .cls, .sty, .bst, .bib, .def, .fd files
              </p>
            ) : (
              <>
                {supportFiles.map(f => (
                  <div
                    key={f.filename}
                    className="group flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-slate-600 dark:text-slate-300"
                  >
                    <FileCode className="h-3 w-3 flex-shrink-0 text-slate-400" />
                    <span className="flex-1 truncate" title={f.filename}>{f.filename}</span>
                    {!readOnly && (
                      <button
                        type="button"
                        onClick={() => handleSupportDelete(f.filename)}
                        className="hidden rounded p-0.5 text-slate-400 hover:bg-rose-100 hover:text-rose-500 group-hover:inline-flex dark:hover:bg-rose-900/30 dark:hover:text-rose-400"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                ))}
                <p className="mt-1 px-3 text-[10px] text-slate-400 dark:text-slate-500">
                  Available during compilation
                </p>
              </>
            )}
          </div>
        )}

        <div className="mx-3 border-t border-slate-200 dark:border-slate-700" />

        {/* Section 3: Figures */}
        <SectionHeader
          title="Figures"
          count={figures.length}
          expanded={figuresExpanded}
          onToggle={() => setFiguresExpanded(p => !p)}
          action={!readOnly ? (
            <button
              type="button"
              onClick={() => figureInputRef.current?.click()}
              disabled={figureUploading}
              className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
              title="Upload figure"
            >
              {figureUploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
            </button>
          ) : undefined}
        />
        <input
          ref={figureInputRef}
          type="file"
          accept="image/*"
          onChange={handleFigureUpload}
          className="hidden"
        />
        {figuresExpanded && (
          <div className="px-1 pb-2">
            {figuresLoading ? (
              <div className="flex items-center justify-center py-3">
                <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
              </div>
            ) : figures.length === 0 ? (
              <p className="px-3 py-2 text-[11px] text-slate-400 dark:text-slate-500">
                No figures uploaded
              </p>
            ) : (
              figures.map(f => (
                <div
                  key={f.filename}
                  className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-slate-600 dark:text-slate-300"
                >
                  <Image className="h-3 w-3 flex-shrink-0 text-slate-400" />
                  <span className="flex-1 truncate" title={f.filename}>{f.filename}</span>
                </div>
              ))
            )}
          </div>
        )}

        <div className="mx-3 border-t border-slate-200 dark:border-slate-700" />

        {/* Section 4: Templates */}
        <SectionHeader
          title="Templates"
          expanded={templatesExpanded}
          onToggle={() => setTemplatesExpanded(p => !p)}
        />
        {templatesExpanded && (
          <div className="px-3 pb-2">
            {templatesLoading ? (
              <div className="flex items-center justify-center py-3">
                <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
              </div>
            ) : templates.length === 0 ? (
              <p className="py-2 text-[11px] text-slate-400 dark:text-slate-500">
                No templates available
              </p>
            ) : (
              <div className="space-y-1">
                {templates.map(t => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => handleApplyTemplate(t)}
                    disabled={readOnly}
                    className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-xs text-slate-600 transition-colors hover:bg-slate-100 disabled:opacity-50 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    <BookTemplate className="h-3 w-3 flex-shrink-0 text-slate-400" />
                    <div className="flex-1 min-w-0">
                      <div className="truncate font-medium">{t.name}</div>
                      {t.description && (
                        <div className="truncate text-[10px] text-slate-400 dark:text-slate-500">{t.description}</div>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Draggable resize handle between file list and outline */}
      {outlineItems !== undefined && (
        <div
          className="group flex h-2 cursor-row-resize items-center justify-center border-y border-slate-200 bg-slate-50 transition-colors hover:bg-indigo-50 dark:border-slate-700 dark:bg-slate-800/50 dark:hover:bg-slate-750"
          onMouseDown={handleResizeStart}
        >
          <div className="flex gap-0.5">
            <div className="h-0.5 w-0.5 rounded-full bg-slate-400 dark:bg-slate-500" />
            <div className="h-0.5 w-0.5 rounded-full bg-slate-400 dark:bg-slate-500" />
            <div className="h-0.5 w-0.5 rounded-full bg-slate-400 dark:bg-slate-500" />
            <div className="h-0.5 w-0.5 rounded-full bg-slate-400 dark:bg-slate-500" />
            <div className="h-0.5 w-0.5 rounded-full bg-slate-400 dark:bg-slate-500" />
          </div>
        </div>
      )}

      {/* Section 5: File Outline */}
      {outlineItems !== undefined && (
        <div
          className="flex flex-col overflow-hidden flex-shrink-0"
          style={{ height: outlineExpanded ? outlineHeight : 'auto' }}
        >
          <SectionHeader
            title="File Outline"
            count={outlineItems.length}
            expanded={outlineExpanded}
            onToggle={() => setOutlineExpanded(p => !p)}
            action={
              <ListTree className="h-3.5 w-3.5 text-slate-400" />
            }
          />
          {outlineExpanded && (
            <div className="flex-1 overflow-y-auto px-1 pb-2">
              {outlineItems.length === 0 ? (
                <p className="px-3 py-2 text-[11px] text-slate-400 dark:text-slate-500">
                  No sections found
                </p>
              ) : (
                outlineItems.map((item, i) => {
                  const indent = Math.max(0, item.level - OUTLINE_INDENT_BASE) * OUTLINE_INDENT_PX
                  return (
                    <button
                      key={`${item.from}-${i}`}
                      type="button"
                      onClick={() => onScrollToSection?.(item.from)}
                      className="flex w-full items-center gap-1 rounded-md px-2 py-0.5 text-left text-xs text-slate-600 transition-colors hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                      style={{ paddingLeft: `${8 + indent}px` }}
                    >
                      <span className="truncate">
                        {item.title || '(untitled)'}
                      </span>
                    </button>
                  )
                })
              )}
            </div>
          )}
        </div>
      )}

      {/* Context Menu */}
      {contextMenu?.visible && (
        <FileContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          filename={contextMenu.filename}
          isMainFile={contextMenu.filename === 'main.tex'}
          onRename={handleRenameFromMenu}
          onDelete={(filename) => {
            if (confirm(`Delete ${filename}?`)) onDeleteFile(filename)
          }}
          onNewFile={() => setIsCreating(true)}
          onClose={handleContextMenuClose}
        />
      )}
    </div>
  )
}
