import React, { useState } from 'react'
import {
  ArrowLeft,
  ChevronDown,
  Eye,
  FileText,
  Globe,
  Lock,
  Pencil,
  Save,
  Settings,
  X,
} from 'lucide-react'

const EditDetailsShowcase: React.FC = () => {
  const [option3Status, setOption3Status] = useState('draft')
  const [option5Status, setOption5Status] = useState('draft')

  return (
    <div className="min-h-screen bg-gray-100 p-8">
      <div className="mx-auto max-w-5xl">
        <h1 className="mb-2 text-3xl font-bold text-gray-900">Edit Paper Details - UI Options</h1>
        <p className="mb-8 text-gray-600">Choose a design for the paper details editing experience</p>

        {/* Option 1: Card-Based Form */}
        <section className="mb-12">
          <h2 className="mb-4 text-xl font-semibold text-gray-800">Option 1: Card-Based Form</h2>
          <div className="rounded-2xl border border-gray-200 bg-white shadow-sm">
            {/* Header */}
            <div className="border-b border-gray-100 bg-gray-50/50 px-6 py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 text-sm text-gray-500">
                  <ArrowLeft className="h-4 w-4" />
                  Papers
                </div>
                <div className="flex items-center gap-2">
                  <button className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50">
                    <X className="h-4 w-4" />
                    Cancel
                  </button>
                  <button className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700">
                    <Save className="h-4 w-4" />
                    Save changes
                  </button>
                </div>
              </div>
            </div>
            {/* Edit Form */}
            <div className="p-6">
              <div className="rounded-xl border border-indigo-100 bg-indigo-50/30 p-6">
                <div className="mb-4 flex items-center gap-2 text-sm font-medium text-indigo-600">
                  <Pencil className="h-4 w-4" />
                  Editing Paper Details
                </div>
                <input
                  type="text"
                  defaultValue="Panoptic Segmentation"
                  className="mb-5 w-full rounded-lg border border-gray-200 bg-white px-4 py-3 text-xl font-semibold text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                />
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-700">
                      <div className="flex h-6 w-6 items-center justify-center rounded-md bg-amber-100">
                        <Settings className="h-3.5 w-3.5 text-amber-600" />
                      </div>
                      Status
                    </label>
                    <select className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20">
                      <option>Draft</option>
                      <option>In Progress</option>
                      <option>Completed</option>
                      <option>Published</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-700">
                      <div className="flex h-6 w-6 items-center justify-center rounded-md bg-blue-100">
                        <FileText className="h-3.5 w-3.5 text-blue-600" />
                      </div>
                      Type
                    </label>
                    <select className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20">
                      <option>Research</option>
                      <option>Literature Review</option>
                      <option>Case Study</option>
                      <option>Methodology</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-700">
                      <div className="flex h-6 w-6 items-center justify-center rounded-md bg-gray-100">
                        <Eye className="h-3.5 w-3.5 text-gray-600" />
                      </div>
                      Visibility
                    </label>
                    <select className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20">
                      <option>Private</option>
                      <option>Public</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Option 2: Side Panel */}
        <section className="mb-12">
          <h2 className="mb-4 text-xl font-semibold text-gray-800">Option 2: Side Panel / Modal</h2>
          <div className="flex rounded-2xl border border-gray-200 bg-white shadow-sm">
            {/* Main Content (dimmed) */}
            <div className="flex-1 p-6 opacity-50">
              <div className="flex items-center gap-3 text-sm text-gray-500">
                <ArrowLeft className="h-4 w-4" />
                Papers
              </div>
              <h1 className="mt-4 text-2xl font-semibold text-gray-900">Panoptic Segmentation</h1>
              <p className="mt-2 text-sm text-gray-500">Draft • Research • Last edited 1/21/2026</p>
            </div>
            {/* Side Panel */}
            <div className="w-80 border-l border-gray-200 bg-gray-50">
              <div className="border-b border-gray-200 bg-white px-5 py-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold text-gray-900">Edit Details</h3>
                  <button className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <div className="p-5">
                <div className="space-y-4">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700">Title</label>
                    <input
                      type="text"
                      defaultValue="Panoptic Segmentation"
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700">Status</label>
                    <select className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none">
                      <option>Draft</option>
                      <option>In Progress</option>
                      <option>Completed</option>
                      <option>Published</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700">Type</label>
                    <select className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none">
                      <option>Research</option>
                      <option>Literature Review</option>
                      <option>Case Study</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-gray-700">Visibility</label>
                    <select className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none">
                      <option>Private</option>
                      <option>Public</option>
                    </select>
                  </div>
                </div>
                <div className="mt-6 flex gap-2">
                  <button className="flex-1 rounded-lg border border-gray-200 bg-white py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
                    Cancel
                  </button>
                  <button className="flex-1 rounded-lg bg-indigo-600 py-2 text-sm font-medium text-white hover:bg-indigo-700">
                    Save
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Option 3: Inline with Color Previews */}
        <section className="mb-12">
          <h2 className="mb-4 text-xl font-semibold text-gray-800">Option 3: Inline with Color Previews</h2>
          <div className="rounded-2xl border border-gray-200 bg-white shadow-sm">
            <div className="p-6">
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-3 text-sm text-gray-500">
                  <ArrowLeft className="h-4 w-4" />
                  Papers
                </div>
                <div className="flex items-center gap-2">
                  <button className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-600">
                    <X className="h-4 w-4" />
                    Cancel
                  </button>
                  <button className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white">
                    <Save className="h-4 w-4" />
                    Save changes
                  </button>
                </div>
              </div>

              <input
                type="text"
                defaultValue="Panoptic Segmentation"
                className="mb-4 w-full border-b-2 border-indigo-500 bg-transparent pb-2 text-2xl font-semibold text-gray-900 focus:outline-none"
              />

              <div className="flex flex-wrap items-center gap-3">
                {/* Status with color dot */}
                <div className="relative">
                  <button
                    className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-sm hover:border-gray-300"
                    onClick={() => setOption3Status(option3Status === 'draft' ? 'in_progress' : 'draft')}
                  >
                    <span className={`h-2 w-2 rounded-full ${option3Status === 'draft' ? 'bg-amber-500' : 'bg-blue-500'}`} />
                    <span className="capitalize">{option3Status.replace('_', ' ')}</span>
                    <ChevronDown className="h-3.5 w-3.5 text-gray-400" />
                  </button>
                </div>

                {/* Type with color badge */}
                <button className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-sm hover:border-gray-300">
                  <span className="rounded bg-blue-100 px-1.5 py-0.5 text-xs font-medium text-blue-700">Research</span>
                  <ChevronDown className="h-3.5 w-3.5 text-gray-400" />
                </button>

                {/* Visibility with icon */}
                <button className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-sm hover:border-gray-300">
                  <Lock className="h-3.5 w-3.5 text-gray-500" />
                  Private
                  <ChevronDown className="h-3.5 w-3.5 text-gray-400" />
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* Option 4: Two-Column Grid */}
        <section className="mb-12">
          <h2 className="mb-4 text-xl font-semibold text-gray-800">Option 4: Two-Column Grid</h2>
          <div className="rounded-2xl border border-gray-200 bg-white shadow-sm">
            <div className="border-b border-gray-100 px-6 py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 text-sm text-gray-500">
                  <ArrowLeft className="h-4 w-4" />
                  Papers
                </div>
                <div className="flex items-center gap-2">
                  <button className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-600">
                    <X className="h-4 w-4" />
                    Cancel
                  </button>
                  <button className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white">
                    <Save className="h-4 w-4" />
                    Save changes
                  </button>
                </div>
              </div>
            </div>
            <div className="p-6">
              <div className="mb-6">
                <label className="mb-2 block text-sm font-medium text-gray-700">Paper Title</label>
                <input
                  type="text"
                  defaultValue="Panoptic Segmentation"
                  className="w-full rounded-xl border border-gray-200 px-4 py-3 text-lg font-semibold text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                />
              </div>

              <div className="grid grid-cols-2 gap-x-6 gap-y-4">
                <div>
                  <label className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-700">
                    <Settings className="h-4 w-4 text-amber-500" />
                    Status
                  </label>
                  <select className="w-full rounded-xl border border-gray-200 px-4 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20">
                    <option>Draft</option>
                    <option>In Progress</option>
                    <option>Completed</option>
                    <option>Published</option>
                  </select>
                </div>
                <div>
                  <label className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-700">
                    <FileText className="h-4 w-4 text-blue-500" />
                    Type
                  </label>
                  <select className="w-full rounded-xl border border-gray-200 px-4 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20">
                    <option>Research</option>
                    <option>Literature Review</option>
                    <option>Case Study</option>
                    <option>Methodology</option>
                  </select>
                </div>
                <div>
                  <label className="mb-2 flex items-center gap-2 text-sm font-medium text-gray-700">
                    <Eye className="h-4 w-4 text-gray-500" />
                    Visibility
                  </label>
                  <select className="w-full rounded-xl border border-gray-200 px-4 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20">
                    <option>Private</option>
                    <option>Public</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Option 5: Segmented Controls */}
        <section className="mb-12">
          <h2 className="mb-4 text-xl font-semibold text-gray-800">Option 5: Segmented Controls</h2>
          <div className="rounded-2xl border border-gray-200 bg-white shadow-sm">
            <div className="border-b border-gray-100 px-6 py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 text-sm text-gray-500">
                  <ArrowLeft className="h-4 w-4" />
                  Papers
                </div>
                <div className="flex items-center gap-2">
                  <button className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-600">
                    <X className="h-4 w-4" />
                    Cancel
                  </button>
                  <button className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white">
                    <Save className="h-4 w-4" />
                    Save changes
                  </button>
                </div>
              </div>
            </div>
            <div className="p-6">
              <input
                type="text"
                defaultValue="Panoptic Segmentation"
                className="mb-6 w-full rounded-xl border border-gray-200 px-4 py-3 text-xl font-semibold text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
              />

              <div className="space-y-4">
                {/* Status as segmented control */}
                <div>
                  <label className="mb-2 block text-sm font-medium text-gray-700">Status</label>
                  <div className="inline-flex rounded-xl border border-gray-200 bg-gray-50 p-1">
                    {['Draft', 'In Progress', 'Completed', 'Published'].map((status) => (
                      <button
                        key={status}
                        onClick={() => setOption5Status(status.toLowerCase().replace(' ', '_'))}
                        className={`rounded-lg px-4 py-2 text-sm font-medium transition-all ${
                          option5Status === status.toLowerCase().replace(' ', '_')
                            ? 'bg-white text-gray-900 shadow-sm'
                            : 'text-gray-500 hover:text-gray-700'
                        }`}
                      >
                        {status}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Type and Visibility in row */}
                <div className="flex gap-4">
                  <div className="flex-1">
                    <label className="mb-2 block text-sm font-medium text-gray-700">Type</label>
                    <select className="w-full rounded-xl border border-gray-200 px-4 py-2.5 text-sm focus:border-indigo-500 focus:outline-none">
                      <option>Research</option>
                      <option>Literature Review</option>
                      <option>Case Study</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-gray-700">Visibility</label>
                    <div className="inline-flex rounded-xl border border-gray-200 bg-gray-50 p-1">
                      <button className="flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-gray-900 shadow-sm">
                        <Lock className="h-4 w-4" />
                        Private
                      </button>
                      <button className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700">
                        <Globe className="h-4 w-4" />
                        Public
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

      </div>
    </div>
  )
}

export default EditDetailsShowcase
