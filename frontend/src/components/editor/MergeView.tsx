import React, { useEffect, useRef, useState } from 'react'
import { branchService, Branch, Commit as BranchCommit } from '../../services/branchService'
import { diffSections, mergeLatex, SectionDiffResult } from '../../utils/latexDiff'
import { EditorState } from '@codemirror/state'
import { EditorView } from '@codemirror/view'
import { StreamLanguage } from '@codemirror/language'
import { stex } from '@codemirror/legacy-modes/mode/stex'
import { GitMerge, GitPullRequest, AlertTriangle } from 'lucide-react'

interface MergeViewProps {
  paperId: string
  onMerged?: (merged: string) => void
}

const cmBaseExt = [
  StreamLanguage.define(stex),
  EditorView.lineWrapping,
  EditorView.theme({
    '&': { fontSize: '13px', backgroundColor: '#fff' },
    '.cm-content': { padding: '12px' },
    '.cm-scroller': { overflow: 'auto' },
  })
]

function createReadOnlyView(parent: HTMLElement, doc: string): EditorView {
  const state = EditorState.create({ doc: doc || '', extensions: [
    ...cmBaseExt,
    EditorView.editable.of(false)
  ]})
  return new EditorView({ state, parent })
}

const MergeView: React.FC<MergeViewProps> = ({ paperId, onMerged }) => {
  const [branches, setBranches] = useState<Branch[]>([])
  const [sourceBranchId, setSourceBranchId] = useState<string>('')
  const [targetBranchId, setTargetBranchId] = useState<string>('')
  const [sourceText, setSourceText] = useState<string>('')
  const [targetText, setTargetText] = useState<string>('')
  const [baseText, setBaseText] = useState<string>('')
  const [diff, setDiff] = useState<SectionDiffResult | null>(null)
  const [srcCommits, setSrcCommits] = useState<BranchCommit[]>([])
  const [tgtCommits, setTgtCommits] = useState<BranchCommit[]>([])
  const [picks, setPicks] = useState<Record<string, 'left' | 'right' | 'both'>>({})
  const leftRef = useRef<HTMLDivElement | null>(null)
  const rightRef = useRef<HTMLDivElement | null>(null)
  const leftViewRef = useRef<EditorView | null>(null)
  const rightViewRef = useRef<EditorView | null>(null)

  useEffect(() => {
    (async () => {
      const list = await branchService.getBranches(paperId)
      setBranches(list)
      const main = list.find(b => b.isMain) || list[0]
      if (main) setTargetBranchId(main.id)
    })()
  }, [paperId])

  // Load heads when branches change
  useEffect(() => {
    const load = async () => {
      if (!sourceBranchId || !targetBranchId) return
      const [srcList, tgtList] = await Promise.all([
        branchService.getCommitHistory(sourceBranchId),
        branchService.getCommitHistory(targetBranchId)
      ])
      setSrcCommits(srcList)
      setTgtCommits(tgtList)
      const srcHead = srcList[0]
      const tgtHead = tgtList[0]
      const srcText = (srcHead as any)?.content_json?.latex_source || srcHead?.content || ''
      const tgtText = (tgtHead as any)?.content_json?.latex_source || tgtHead?.content || ''
      setSourceText(srcText)
      setTargetText(tgtText)
      // Base: use older of the two heads if available; here we simply choose target as base for simplicity
      setBaseText(tgtText)
      setDiff(diffSections(srcText, tgtText))
    }
    load()
  }, [sourceBranchId, targetBranchId])

  useEffect(() => {
    // Create/destroy views
    if (leftRef.current) {
      try { leftViewRef.current?.destroy() } catch {}
      leftViewRef.current = createReadOnlyView(leftRef.current, sourceText)
    }
    if (rightRef.current) {
      try { rightViewRef.current?.destroy() } catch {}
      rightViewRef.current = createReadOnlyView(rightRef.current, targetText)
    }
    return () => {
      try { leftViewRef.current?.destroy() } catch {}
      try { rightViewRef.current?.destroy() } catch {}
    }
  }, [sourceText, targetText])

  const canMerge = Boolean(diff)
  const conflicts = diff?.conflicts || []

  const applyAutoMerge = () => {
    if (!diff) return
    const pickMap: Record<string, 'left' | 'right' | 'both'> = {}
    // Non-overlapping: auto pick whichever side has it
    diff.added.forEach(s => { pickMap[s.key] = 'right' })
    diff.removed.forEach(s => { pickMap[s.key] = 'left' })
    // Modified: leave for manual; default to right
    diff.modified.forEach(m => { if (!pickMap[m.key]) pickMap[m.key] = 'right' })
    setPicks(pickMap)
  }

  const buildMerged = () => {
    const merged = mergeLatex(baseText, sourceText, targetText, picks)
    onMerged?.(merged)
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-2 items-center mb-2">
        <GitMerge className="w-4 h-4" />
        <div className="font-medium">Merge Changes</div>
      </div>
      <div className="flex gap-3 items-end">
        <div className="flex-1">
          <label className="text-xs text-gray-600">Source Branch</label>
          <select className="w-full border rounded p-2" value={sourceBranchId} onChange={e => setSourceBranchId(e.target.value)}>
            <option value="">Select…</option>
            {branches.map(b => (<option key={b.id} value={b.id}>{b.name}</option>))}
          </select>
        </div>
        <div className="flex-1">
          <label className="text-xs text-gray-600">Target Branch</label>
          <select className="w-full border rounded p-2" value={targetBranchId} onChange={e => setTargetBranchId(e.target.value)}>
            <option value="">Select…</option>
            {branches.map(b => (<option key={b.id} value={b.id}>{b.name}</option>))}
          </select>
        </div>
        <button
          className="px-3 py-2 bg-blue-600 text-white rounded disabled:opacity-50"
          disabled={!sourceBranchId || !targetBranchId}
          onClick={applyAutoMerge}
        >Auto-merge non-overlapping</button>
        <button
          className="px-3 py-2 bg-green-600 text-white rounded disabled:opacity-50"
          disabled={!canMerge}
          onClick={buildMerged}
        >Apply Merge</button>
        <button
          className="px-3 py-2 bg-gray-700 text-white rounded disabled:opacity-50 flex items-center gap-1"
          disabled={!sourceBranchId || !targetBranchId}
          onClick={async () => {
            try {
              const src = branches.find(b => b.id === sourceBranchId)
              const tgt = branches.find(b => b.id === targetBranchId)
              await branchService.createMergeRequest(sourceBranchId, targetBranchId, `Merge ${src?.name} into ${tgt?.name}`, 'Proposed merge of changes')
              alert('Merge Request created')
            } catch (e) { console.error(e) }
          }}
        >
          <GitPullRequest className="w-4 h-4" /> Create MR
        </button>
      </div>

      {diff && (
        <div className="text-xs text-gray-700">
          <div className="flex gap-4 mb-1">
            <div>Added: <span className="font-semibold text-green-700">{diff.added.length}</span></div>
            <div>Removed: <span className="font-semibold text-red-700">{diff.removed.length}</span></div>
            <div>Modified: <span className="font-semibold text-yellow-700">{diff.modified.length}</span></div>
            <div>Reordered: <span className="font-semibold text-blue-700">{diff.reordered.length}</span></div>
            {conflicts.length > 0 && (
              <div className="flex items-center gap-1 text-red-700"><AlertTriangle className="w-4 h-4" /> Conflicts: {conflicts.length}</div>
            )}
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="border rounded p-2">
              <div className="font-medium text-green-700 mb-1">New sections</div>
              <ul className="space-y-0.5 max-h-24 overflow-auto">
                {diff.added.map(s => (<li key={s.key}>{s.key}</li>))}
                {diff.added.length === 0 && (<li className="text-gray-500">None</li>)}
              </ul>
            </div>
            <div className="border rounded p-2">
              <div className="font-medium text-red-700 mb-1">Removed sections</div>
              <ul className="space-y-0.5 max-h-24 overflow-auto">
                {diff.removed.map(s => (<li key={s.key}>{s.key}</li>))}
                {diff.removed.length === 0 && (<li className="text-gray-500">None</li>)}
              </ul>
            </div>
            <div className="border rounded p-2">
              <div className="font-medium text-blue-700 mb-1">Reordered</div>
              <ul className="space-y-0.5 max-h-24 overflow-auto">
                {diff.reordered.map(k => (<li key={k}>{k}</li>))}
                {diff.reordered.length === 0 && (<li className="text-gray-500">None</li>)}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Commit history summaries */}
      {(srcCommits.length > 0 || tgtCommits.length > 0) && (
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="border rounded">
            <div className="px-2 py-1 bg-gray-50 border-b">Source commits</div>
            <ul className="max-h-28 overflow-auto divide-y">
              {srcCommits.slice(0,5).map((c)=> (
                <li key={c.id} className="px-2 py-1">
                  <div className="font-medium">{c.message}</div>
                  <div className="text-gray-500">{new Date(c.timestamp).toLocaleString()}</div>
                </li>
              ))}
              {srcCommits.length === 0 && (<li className="px-2 py-2 text-gray-500">No commits</li>)}
            </ul>
          </div>
          <div className="border rounded">
            <div className="px-2 py-1 bg-gray-50 border-b">Target commits</div>
            <ul className="max-h-28 overflow-auto divide-y">
              {tgtCommits.slice(0,5).map((c)=> (
                <li key={c.id} className="px-2 py-1">
                  <div className="font-medium">{c.message}</div>
                  <div className="text-gray-500">{new Date(c.timestamp).toLocaleString()}</div>
                </li>
              ))}
              {tgtCommits.length === 0 && (<li className="px-2 py-2 text-gray-500">No commits</li>)}
            </ul>
          </div>
        </div>
      )}

      {/* Side-by-side views */}
      <div className="grid grid-cols-2 gap-3">
        <div className="border rounded overflow-hidden">
          <div className="px-2 py-1 text-xs bg-gray-50 border-b">Source preview</div>
          <div ref={leftRef} className="h-[300px]" />
        </div>
        <div className="border rounded overflow-hidden">
          <div className="px-2 py-1 text-xs bg-gray-50 border-b">Target preview</div>
          <div ref={rightRef} className="h-[300px]" />
        </div>
      </div>

      {/* Per-section picks for conflicts */}
      {conflicts.length > 0 && (
        <div className="mt-3">
          <div className="text-sm font-medium mb-2">Resolve Conflicts</div>
          <div className="space-y-2">
            {conflicts.map(c => (
              <div key={c.key} className="border rounded p-2">
                <div className="text-xs text-gray-600 mb-1">{c.key}</div>
                <div className="flex gap-2 text-xs">
                  <label className="inline-flex items-center gap-1">
                    <input type="radio" name={`pick-${c.key}`} checked={(picks[c.key]||'right')==='left'} onChange={()=>setPicks(p=>({...p,[c.key]:'left'}))} /> Source
                  </label>
                  <label className="inline-flex items-center gap-1">
                    <input type="radio" name={`pick-${c.key}`} checked={(picks[c.key]||'right')==='right'} onChange={()=>setPicks(p=>({...p,[c.key]:'right'}))} /> Target
                  </label>
                  <label className="inline-flex items-center gap-1">
                    <input type="radio" name={`pick-${c.key}`} checked={(picks[c.key]||'right')==='both'} onChange={()=>setPicks(p=>({...p,[c.key]:'both'}))} /> Both
                  </label>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default MergeView
