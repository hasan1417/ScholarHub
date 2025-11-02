import React, { useState, useMemo } from 'react'
import { Conflict } from '../../services/branchService'
import { Check, ArrowRight, Plus, Minus, Edit3 } from 'lucide-react'

interface VisualDiffToolProps {
  conflicts: Conflict[]
  onResolveConflict: (conflictId: string, resolvedContent: string) => void
  onAutoResolve: (conflictId: string, strategy: 'source-wins' | 'target-wins') => void
  className?: string
}

interface DiffLine {
  type: 'unchanged' | 'added' | 'deleted' | 'modified'
  content: string
  lineNumber: number
  sourceLine?: number
  targetLine?: number
}

const VisualDiffTool: React.FC<VisualDiffToolProps> = ({
  conflicts,
  onResolveConflict,
  onAutoResolve,
  className = ''
}) => {
  const [selectedConflict, setSelectedConflict] = useState<Conflict | null>(null)
  const [resolvedContent, setResolvedContent] = useState<string>('')

  const generateDiff = (sourceContent: string, targetContent: string): DiffLine[] => {
    const sourceLines = sourceContent.split('\n')
    const targetLines = targetContent.split('\n')
    const diffLines: DiffLine[] = []
    
    let sourceIndex = 0
    let targetIndex = 0
    let lineNumber = 1

    while (sourceIndex < sourceLines.length || targetIndex < targetLines.length) {
      const sourceLine = sourceLines[sourceIndex]
      const targetLine = targetLines[targetIndex]

      if (sourceLine === targetLine) {
        // Unchanged line
        diffLines.push({
          type: 'unchanged',
          content: sourceLine || '',
          lineNumber: lineNumber++,
          sourceLine: sourceIndex + 1,
          targetLine: targetIndex + 1
        })
        sourceIndex++
        targetIndex++
      } else if (sourceLine && !targetLine) {
        // Deleted line
        diffLines.push({
          type: 'deleted',
          content: sourceLine,
          lineNumber: lineNumber++,
          sourceLine: sourceIndex + 1
        })
        sourceIndex++
      } else if (!sourceLine && targetLine) {
        // Added line
        diffLines.push({
          type: 'added',
          content: targetLine,
          lineNumber: lineNumber++,
          targetLine: targetIndex + 1
        })
        targetIndex++
      } else {
        // Modified line
        diffLines.push({
          type: 'modified',
          content: `- ${sourceLine}`,
          lineNumber: lineNumber++,
          sourceLine: sourceIndex + 1
        })
        diffLines.push({
          type: 'modified',
          content: `+ ${targetLine}`,
          lineNumber: lineNumber++,
          targetLine: targetIndex + 1
        })
        sourceIndex++
        targetIndex++
      }
    }

    return diffLines
  }

  const diffLines = useMemo(() => {
    if (!selectedConflict) return []
    return generateDiff(selectedConflict.sourceContent, selectedConflict.targetContent)
  }, [selectedConflict])

  const handleConflictSelect = (conflict: Conflict) => {
    setSelectedConflict(conflict)
    setResolvedContent(conflict.resolvedContent || conflict.targetContent)
  }

  const handleResolve = () => {
    if (selectedConflict && resolvedContent.trim()) {
      onResolveConflict(selectedConflict.id, resolvedContent)
      setSelectedConflict(null)
      setResolvedContent('')
    }
  }

  const getLineClass = (type: DiffLine['type']) => {
    switch (type) {
      case 'added':
        return 'bg-green-50 border-l-4 border-green-500 text-green-800'
      case 'deleted':
        return 'bg-red-50 border-l-4 border-red-500 text-red-800'
      case 'modified':
        return 'bg-yellow-50 border-l-4 border-yellow-500 text-yellow-800'
      default:
        return 'bg-gray-50 border-l-4 border-gray-300'
    }
  }

  const getLineIcon = (type: DiffLine['type']) => {
    switch (type) {
      case 'added':
        return <Plus size={16} className="text-green-600" />
      case 'deleted':
        return <Minus size={16} className="text-red-600" />
      case 'modified':
        return <Edit3 size={16} className="text-yellow-600" />
      default:
        return <span className="w-4 h-4" />
    }
  }

  if (conflicts.length === 0) {
    return (
      <div className={`p-6 text-center text-gray-500 ${className}`}>
        <Check className="w-12 h-12 mx-auto mb-4 text-green-500" />
        <h3 className="text-lg font-medium mb-2">No Conflicts Found</h3>
        <p>All changes can be merged automatically!</p>
      </div>
    )
  }

  return (
    <div className={`bg-white rounded-lg shadow-lg ${className}`}>
      {/* Conflict List */}
      <div className="border-b border-gray-200">
        <div className="px-6 py-4">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Conflicts to Resolve</h3>
          <div className="space-y-2">
            {conflicts.map((conflict) => (
              <div
                key={conflict.id}
                className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                  selectedConflict?.id === conflict.id
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
                onClick={() => handleConflictSelect(conflict)}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="font-medium text-gray-900">{conflict.section}</h4>
                    <p className="text-sm text-gray-600">
                      {conflict.status === 'resolved' ? 'Resolved' : 'Needs attention'}
                    </p>
                  </div>
                  <div className="flex items-center space-x-2">
                    {conflict.status === 'resolved' && (
                      <Check className="w-5 h-5 text-green-500" />
                    )}
                    <ArrowRight className="w-4 h-4 text-gray-400" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Diff Viewer */}
      {selectedConflict && (
        <div className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-lg font-medium text-gray-900">
              Resolving: {selectedConflict.section}
            </h4>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => onAutoResolve(selectedConflict.id, 'source-wins')}
                className="px-3 py-1 text-sm bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
              >
                Use Source
              </button>
              <button
                onClick={() => onAutoResolve(selectedConflict.id, 'target-wins')}
                className="px-3 py-1 text-sm bg-green-100 text-green-700 rounded hover:bg-green-200"
              >
                Use Target
              </button>
            </div>
          </div>

          {/* Diff Display */}
          <div className="bg-gray-50 rounded-lg p-4 mb-4">
            <div className="text-sm text-gray-600 mb-2">Visual Diff:</div>
            <div className="bg-white rounded border overflow-hidden">
              {diffLines.map((line, index) => (
                <div
                  key={index}
                  className={`flex items-start p-2 ${getLineClass(line.type)}`}
                >
                  <div className="flex items-center w-8 mr-3">
                    {getLineIcon(line.type)}
                  </div>
                  <div className="flex-1 font-mono text-sm">
                    <span className="text-gray-500 mr-3">
                      {line.sourceLine && `S:${line.sourceLine}`}
                    </span>
                    <span className="text-gray-500 mr-3">
                      {line.targetLine && `T:${line.targetLine}`}
                    </span>
                    {line.content}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Resolution Editor */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Resolved Content:
            </label>
            <textarea
              value={resolvedContent}
              onChange={(e) => setResolvedContent(e.target.value)}
              className="w-full h-32 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="Edit the content to resolve the conflict..."
            />
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end space-x-3">
            <button
              onClick={() => {
                setSelectedConflict(null)
                setResolvedContent('')
              }}
              className="px-4 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200"
            >
              Cancel
            </button>
            <button
              onClick={handleResolve}
              disabled={!resolvedContent.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Resolve Conflict
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default VisualDiffTool
