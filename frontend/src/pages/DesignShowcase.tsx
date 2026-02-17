import React, { useState } from 'react'
import { ArrowLeft, Eye, Edit, MoreHorizontal, FileText, BookOpen, Clock } from 'lucide-react'
import { useToast } from '../hooks/useToast'

const DesignShowcase: React.FC = () => {
  const { toast } = useToast()
  const [selectedOption, setSelectedOption] = useState<number | null>(null)

  // Mock data
  const paper = {
    title: 'Panoptic Segmentation',
    project: 'Climate Change Analysis',
    status: 'draft',
    type: 'Research',
    createdAt: '2026-01-21',
    updatedAt: '2026-01-21',
  }

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-slate-900 py-8 px-4">
      <div className="max-w-5xl mx-auto space-y-12">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">Paper Header Design Options</h1>
          <p className="text-gray-600 dark:text-slate-400">Click on an option to select it</p>
        </div>

        {/* Option 1: Hero Card Style */}
        <div
          className={`rounded-2xl border-2 transition-all cursor-pointer ${selectedOption === 1 ? 'border-indigo-500 ring-4 ring-indigo-100 dark:ring-indigo-900' : 'border-transparent'}`}
          onClick={() => setSelectedOption(1)}
        >
          <div className="p-4 bg-white dark:bg-slate-800 rounded-t-2xl border-b border-gray-100 dark:border-slate-700">
            <span className="text-sm font-semibold text-gray-500 dark:text-slate-400">Option 1: Hero Card Style</span>
          </div>
          <div className="bg-gray-50 dark:bg-slate-900 p-6 rounded-b-2xl">
            {/* Header */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700 overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-100 dark:border-slate-700">
                <button className="flex items-center gap-2 text-sm text-indigo-600 dark:text-indigo-400 hover:text-indigo-700">
                  <ArrowLeft className="h-4 w-4" />
                  {paper.project}
                </button>
              </div>
              <div className="p-6">
                <div className="flex items-start justify-between gap-6">
                  <div className="flex items-start gap-4">
                    <div className="flex items-center justify-center h-14 w-14 rounded-xl bg-indigo-100 dark:bg-indigo-900/30">
                      <FileText className="h-7 w-7 text-indigo-600 dark:text-indigo-400" />
                    </div>
                    <div>
                      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{paper.title}</h1>
                      <div className="flex items-center gap-3 mt-2 text-sm text-gray-500 dark:text-slate-400">
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 text-xs font-medium">
                          Draft
                        </span>
                        <span className="text-gray-300 dark:text-slate-600">•</span>
                        <span>{paper.type}</span>
                        <span className="text-gray-300 dark:text-slate-600">•</span>
                        <span>Created Jan 21</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-gray-200 dark:border-slate-600 text-sm font-medium text-gray-700 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700">
                      <Eye className="h-4 w-4" />
                      View
                    </button>
                    <button className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 text-sm font-medium text-white hover:bg-indigo-700">
                      <Edit className="h-4 w-4" />
                      Edit
                    </button>
                    <button className="p-2.5 rounded-lg border border-gray-200 dark:border-slate-600 text-gray-500 hover:bg-gray-50 dark:hover:bg-slate-700">
                      <MoreHorizontal className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Option 2: Split Layout with Visual Status */}
        <div
          className={`rounded-2xl border-2 transition-all cursor-pointer ${selectedOption === 2 ? 'border-indigo-500 ring-4 ring-indigo-100 dark:ring-indigo-900' : 'border-transparent'}`}
          onClick={() => setSelectedOption(2)}
        >
          <div className="p-4 bg-white dark:bg-slate-800 rounded-t-2xl border-b border-gray-100 dark:border-slate-700">
            <span className="text-sm font-semibold text-gray-500 dark:text-slate-400">Option 2: Split Layout with Visual Status</span>
          </div>
          <div className="bg-gray-50 dark:bg-slate-900 p-6 rounded-b-2xl">
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700">
              <div className="px-6 py-3 border-b border-gray-100 dark:border-slate-700">
                <button className="flex items-center gap-2 text-sm text-gray-500 dark:text-slate-400 hover:text-gray-700">
                  <ArrowLeft className="h-4 w-4" />
                  Back to project
                </button>
              </div>
              <div className="p-6">
                <div className="flex items-center gap-6">
                  {/* Status Block */}
                  <div className="flex flex-col items-center justify-center h-20 w-20 rounded-xl bg-amber-50 dark:bg-amber-900/20 border-2 border-amber-200 dark:border-amber-700">
                    <FileText className="h-6 w-6 text-amber-600 dark:text-amber-400" />
                    <span className="text-xs font-bold text-amber-700 dark:text-amber-300 mt-1 uppercase">Draft</span>
                  </div>
                  {/* Info */}
                  <div className="flex-1">
                    <h1 className="text-xl font-bold text-gray-900 dark:text-white">{paper.title}</h1>
                    <p className="text-sm text-indigo-600 dark:text-indigo-400 mt-0.5">{paper.project}</p>
                    <p className="text-sm text-gray-500 dark:text-slate-400 mt-1">
                      {paper.type} • Updated 2 hours ago
                    </p>
                  </div>
                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    <button className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 dark:border-slate-600 text-sm font-medium text-gray-700 dark:text-slate-300 hover:bg-gray-50">
                      <Eye className="h-4 w-4" />
                      View
                    </button>
                    <button className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 text-sm font-medium text-white hover:bg-indigo-700">
                      <Edit className="h-4 w-4" />
                      Edit
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Option 3: Minimal Modern (Recommended) */}
        <div
          className={`rounded-2xl border-2 transition-all cursor-pointer ${selectedOption === 3 ? 'border-indigo-500 ring-4 ring-indigo-100 dark:ring-indigo-900' : 'border-transparent'}`}
          onClick={() => setSelectedOption(3)}
        >
          <div className="p-4 bg-white dark:bg-slate-800 rounded-t-2xl border-b border-gray-100 dark:border-slate-700 flex items-center justify-between">
            <span className="text-sm font-semibold text-gray-500 dark:text-slate-400">Option 3: Minimal Modern</span>
            <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/30 px-2 py-1 rounded-full">Recommended</span>
          </div>
          <div className="bg-gray-50 dark:bg-slate-900 p-6 rounded-b-2xl">
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700 p-6">
              {/* Top row */}
              <div className="flex items-center justify-between mb-4">
                <button className="flex items-center gap-2 text-sm text-gray-500 dark:text-slate-400 hover:text-gray-700">
                  <ArrowLeft className="h-4 w-4" />
                  Papers
                </button>
                <div className="flex items-center gap-2">
                  <button className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 border border-gray-200 dark:border-slate-600">
                    <Eye className="h-4 w-4" />
                    View
                  </button>
                  <button className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-600 text-sm font-medium text-white hover:bg-indigo-700">
                    <Edit className="h-4 w-4" />
                    Write
                  </button>
                  <button className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100 dark:hover:bg-slate-700 border border-gray-200 dark:border-slate-600">
                    <MoreHorizontal className="h-4 w-4" />
                  </button>
                </div>
              </div>
              {/* Title */}
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{paper.title}</h1>
              {/* Meta */}
              <div className="flex items-center gap-2 mt-2 text-sm text-gray-500 dark:text-slate-400">
                <span className="text-amber-600 dark:text-amber-400 font-medium">Draft</span>
                <span>•</span>
                <span>{paper.type}</span>
              </div>
              {/* Last edited */}
              <p className="text-xs text-gray-400 dark:text-slate-500 mt-4">
                Last edited Jan 21, 2026
              </p>
            </div>
          </div>
        </div>

        {/* Option 4: Notion-style */}
        <div
          className={`rounded-2xl border-2 transition-all cursor-pointer ${selectedOption === 4 ? 'border-indigo-500 ring-4 ring-indigo-100 dark:ring-indigo-900' : 'border-transparent'}`}
          onClick={() => setSelectedOption(4)}
        >
          <div className="p-4 bg-white dark:bg-slate-800 rounded-t-2xl border-b border-gray-100 dark:border-slate-700">
            <span className="text-sm font-semibold text-gray-500 dark:text-slate-400">Option 4: Notion-style Properties</span>
          </div>
          <div className="bg-gray-50 dark:bg-slate-900 p-6 rounded-b-2xl">
            <div className="mb-4">
              <button className="flex items-center gap-2 text-sm text-gray-500 dark:text-slate-400 hover:text-gray-700">
                <ArrowLeft className="h-4 w-4" />
                {paper.project}
              </button>
            </div>
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700 p-6">
              {/* Title row */}
              <div className="flex items-start justify-between gap-4 mb-6">
                <div className="flex items-center gap-3">
                  <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-gray-100 dark:bg-slate-700">
                    <FileText className="h-5 w-5 text-gray-600 dark:text-slate-300" />
                  </div>
                  <h1 className="text-xl font-bold text-gray-900 dark:text-white">{paper.title}</h1>
                </div>
                <div className="flex items-center gap-2">
                  <button className="px-3 py-1.5 rounded-lg text-sm font-medium text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700">
                    Edit
                  </button>
                  <button className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100 dark:hover:bg-slate-700">
                    <MoreHorizontal className="h-4 w-4" />
                  </button>
                </div>
              </div>
              {/* Properties grid */}
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <p className="text-xs font-medium text-gray-400 dark:text-slate-500 uppercase tracking-wide mb-1">Status</p>
                  <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 font-medium">
                    <span className="h-2 w-2 rounded-full bg-amber-500"></span>
                    Draft
                  </span>
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-400 dark:text-slate-500 uppercase tracking-wide mb-1">Type</p>
                  <span className="text-gray-700 dark:text-slate-300">{paper.type}</span>
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-400 dark:text-slate-500 uppercase tracking-wide mb-1">Last edited</p>
                  <span className="text-gray-700 dark:text-slate-300">Jan 21, 2026</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Option 5: Compact with Progress */}
        <div
          className={`rounded-2xl border-2 transition-all cursor-pointer ${selectedOption === 5 ? 'border-indigo-500 ring-4 ring-indigo-100 dark:ring-indigo-900' : 'border-transparent'}`}
          onClick={() => setSelectedOption(5)}
        >
          <div className="p-4 bg-white dark:bg-slate-800 rounded-t-2xl border-b border-gray-100 dark:border-slate-700">
            <span className="text-sm font-semibold text-gray-500 dark:text-slate-400">Option 5: Compact with Color Accent</span>
          </div>
          <div className="bg-gray-50 dark:bg-slate-900 p-6 rounded-b-2xl">
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700 overflow-hidden">
              {/* Color bar */}
              <div className="h-1 bg-gradient-to-r from-amber-400 to-amber-500"></div>
              <div className="p-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <button className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-700 text-gray-400">
                      <ArrowLeft className="h-5 w-5" />
                    </button>
                    <div>
                      <p className="text-xs text-indigo-600 dark:text-indigo-400 font-medium mb-0.5">{paper.project}</p>
                      <h1 className="text-lg font-bold text-gray-900 dark:text-white">{paper.title}</h1>
                    </div>
                  </div>
                  <div className="flex items-center gap-6">
                    <div className="flex items-center gap-4 text-sm">
                      <div className="flex items-center gap-2">
                        <span className="h-2.5 w-2.5 rounded-full bg-amber-400"></span>
                        <span className="text-gray-600 dark:text-slate-300">Draft</span>
                      </div>
                      <div className="text-gray-400 dark:text-slate-500">|</div>
                      <div className="flex items-center gap-1.5 text-gray-500 dark:text-slate-400">
                        <BookOpen className="h-4 w-4" />
                        <span>{paper.type}</span>
                      </div>
                      <div className="text-gray-400 dark:text-slate-500">|</div>
                      <div className="flex items-center gap-1.5 text-gray-500 dark:text-slate-400">
                        <Clock className="h-4 w-4" />
                        <span>2h ago</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button className="px-4 py-2 rounded-lg border border-gray-200 dark:border-slate-600 text-sm font-medium text-gray-700 dark:text-slate-300 hover:bg-gray-50">
                        View
                      </button>
                      <button className="px-4 py-2 rounded-lg bg-indigo-600 text-sm font-medium text-white hover:bg-indigo-700">
                        Edit
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Selection indicator */}
        {selectedOption && (
          <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-indigo-600 text-white px-6 py-3 rounded-full shadow-lg flex items-center gap-3">
            <span>Option {selectedOption} selected</span>
            <button
              className="px-3 py-1 bg-white text-indigo-600 rounded-full text-sm font-semibold hover:bg-indigo-50"
              onClick={() => toast.info(`You selected Option ${selectedOption}. Let me know and I'll implement it!`)}
            >
              Apply
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default DesignShowcase
