import React, { useEffect, useMemo, useState } from 'react'
import { diffSections, parseLatexSections, buildOutlineTree, OutlineNode } from '../../utils/latexDiff'
import { researchPapersAPI } from '../../services/api'
import { Lock, Unlock, GitCompare } from 'lucide-react'

interface ChangesSidebarProps {
  paperId: string
  content: string
  onClose: () => void
  onJumpToLine: (line: number) => void
  onReplaceLines: (fromLine: number, toLine: number, text: string) => void
  lockedKeys?: Record<string, { userName: string; expiresAt: string }>
  onLockToggle?: (sectionKey: string, lock: boolean) => void
  baseline?: string
  onRevertAll?: () => void
}

const ChangesSidebar: React.FC<ChangesSidebarProps> = ({ paperId, content, onClose, onJumpToLine, onReplaceLines, lockedKeys, onLockToggle, baseline, onRevertAll }) => {
  const sections = useMemo(() => parseLatexSections(content), [content])
  const outline = useMemo(() => buildOutlineTree(sections), [sections])
  const [baseContent, setBaseContent] = useState<string>('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    // Use provided baseline if available; otherwise load latest published
    (async () => {
      try {
        setLoading(true)
        if (typeof baseline === 'string') {
          setBaseContent(baseline)
        } else {
          const resp = await researchPapersAPI.getPaperVersions(paperId)
          const respData = resp?.data as { versions?: any[] } | undefined
          const list = (respData?.versions || []) as Array<Record<string, any>>
          const latest = list[0]
          const txt = (latest?.content_json && latest.content_json.latex_source)
            ? latest.content_json.latex_source
            : (latest?.content || '')
          setBaseContent(txt || '')
        }
      } catch (e) {
        // If no versions exist, use empty base (everything appears added)
        setBaseContent('')
      } finally {
        setLoading(false)
      }
    })()
  }, [paperId, baseline])

  const changedKeys = useMemo(() => {
    if (!baseContent) return new Set<string>()
    const d = diffSections(baseContent, content)
    const s = new Set<string>([...d.added.map(x=>x.key), ...d.removed.map(x=>x.key), ...d.modified.map(x=>x.key)])
    return s
  }, [baseContent, content])

  const renderNode = (node: OutlineNode) => {
    const locked = lockedKeys && lockedKeys[node.key]
    const changed = changedKeys.has(node.key)
    return (
      <div key={node.key} className="pl-2 border-l">
        <div className="flex items-center justify-between py-1">
          <div className="flex items-center gap-2">
            <button className="text-left text-sm hover:underline" onClick={()=> onJumpToLine(node.lineStart)}>
              {node.title}
            </button>
            {changed && <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-100 text-yellow-800">changed</span>}
            {locked && <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 text-red-700 flex items-center gap-1"><Lock className="w-3 h-3"/> {locked.userName}</span>}
          </div>
          <div className="flex items-center gap-1">
            <button title="Compare with HEAD" className="px-1.5 py-0.5 text-xs border rounded flex items-center gap-1" onClick={async ()=>{
              try {
                const baseSec = parseLatexSections(baseContent).find(s=>s.key===node.key)?.content || ''
                const curSec = parseLatexSections(content).find(s=>s.key===node.key)?.content || ''
                const w = window.open('', '_blank', 'width=700,height=500')
                if (w) {
                  w.document.write(`<pre style="white-space:pre-wrap;padding:8px;">--- HEAD\n${baseSec}\n\n--- Current\n${curSec}</pre>`) 
                }
              } catch {}
            }}><GitCompare className="w-3 h-3"/> Compare</button>
            <button title="Revert to HEAD" className="px-1.5 py-0.5 text-xs border rounded" onClick={async ()=>{
              try {
                const baseSec = parseLatexSections(baseContent).find(s=>s.key===node.key)
                if (!baseSec) return
                onReplaceLines(baseSec.lineStart || 1, baseSec.lineEnd || baseSec.lineStart || 1, baseSec.content || '')
              } catch {}
            }}>Revert</button>
            {onLockToggle && (
              <button title={locked ? 'Unlock' : 'Lock'} className="px-1.5 py-0.5 text-xs border rounded" onClick={()=> onLockToggle(node.key, !locked)}>
                {locked ? <Unlock className="w-3 h-3"/> : <Lock className="w-3 h-3"/>}
              </button>
            )}
          </div>
        </div>
        {node.children.length > 0 && (
          <div className="pl-3">
            {node.children.map(renderNode)}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 bg-black bg-opacity-30 flex items-center justify-end" onClick={onClose}>
      <div className="bg-white w-[420px] h-full p-3 overflow-auto" onClick={e=>e.stopPropagation()}>
        <div className="flex items-center justify-between mb-2">
          <div className="font-semibold">Changes vs Published</div>
          <div className="flex items-center gap-2">
            {onRevertAll && (
              <button className="text-sm px-2 py-1 border rounded" onClick={onRevertAll}>Revert All</button>
            )}
            <button className="text-sm px-2 py-1 border rounded" onClick={onClose}>Close</button>
          </div>
        </div>
        {loading && (<div className="text-xs text-gray-500 mb-2">Loading published…</div>)}
        <div className="space-y-1">
          {outline.map(renderNode)}
        </div>
      </div>
    </div>
  )
}

export default ChangesSidebar
