import React, { useState, useRef } from 'react'
import { Upload, X, Loader2 } from 'lucide-react'
import { researchPapersAPI } from '../../services/api'

interface FigureUploadDialogProps {
  isOpen: boolean
  onClose: () => void
  onInsert: (imageUrl: string, caption: string, label: string, width: string) => void
  paperId: string
}

const FigureUploadDialog: React.FC<FigureUploadDialogProps> = ({
  isOpen,
  onClose,
  onInsert,
  paperId,
}) => {
  const [file, setFile] = useState<File | null>(null)
  const [caption, setCaption] = useState('')
  const [label, setLabel] = useState('')
  const [width, setWidth] = useState('0.8')
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (!selectedFile) return

    // Validate file type
    const validTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/svg+xml']
    if (!validTypes.includes(selectedFile.type)) {
      setError('Please select a valid image file (PNG, JPG, GIF, or SVG)')
      return
    }

    // Validate file size (10MB max)
    const maxSize = 10 * 1024 * 1024
    if (selectedFile.size > maxSize) {
      setError('File size must be less than 10MB')
      return
    }

    setFile(selectedFile)
    setError(null)

    // Create preview
    const reader = new FileReader()
    reader.onload = (event) => {
      setPreview(event.target?.result as string)
    }
    reader.readAsDataURL(selectedFile)
  }

  const handleUpload = async () => {
    if (!file) {
      setError('Please select a file')
      return
    }

    if (!caption.trim()) {
      setError('Please enter a caption')
      return
    }

    setUploading(true)
    setError(null)

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('caption', caption)
      formData.append('label', label || generateLabel(caption))

      const response = await researchPapersAPI.uploadFigure(paperId, formData)
      const data = (response?.data ?? response) as { url?: string }
      const imageUrl = data?.url || `figures/${file.name}`

      onInsert(imageUrl, caption, label || generateLabel(caption), width)
      handleClose()
    } catch (err: any) {
      console.error('Upload error:', err)
      const detail = err?.response?.data?.detail || err?.message || 'Failed to upload image'
      setError(detail)
    } finally {
      setUploading(false)
    }
  }

  const generateLabel = (caption: string): string => {
    return 'fig:' + caption
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .substring(0, 30)
  }

  const handleClose = () => {
    setFile(null)
    setCaption('')
    setLabel('')
    setWidth('0.8')
    setError(null)
    setPreview(null)
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-lg bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">Insert Figure</h2>
          <button
            onClick={handleClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            disabled={uploading}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-4 px-6 py-4">
          {/* File Upload */}
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-700">
              Image File
            </label>
            <div
              onClick={() => fileInputRef.current?.click()}
              className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-6 hover:border-gray-400 hover:bg-gray-100"
            >
              {preview ? (
                <img src={preview} alt="Preview" className="max-h-40 rounded" />
              ) : (
                <>
                  <Upload className="mb-2 h-8 w-8 text-gray-400" />
                  <p className="text-sm text-gray-600">Click to upload image</p>
                  <p className="mt-1 text-xs text-gray-500">PNG, JPG, GIF, SVG (max 10MB)</p>
                </>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleFileSelect}
              className="hidden"
            />
            {file && (
              <p className="mt-2 text-sm text-gray-600">
                Selected: <span className="font-medium">{file.name}</span>
              </p>
            )}
          </div>

          {/* Caption */}
          <div>
            <label htmlFor="caption" className="mb-2 block text-sm font-medium text-gray-700 dark:text-slate-200">
              Caption *
            </label>
            <input
              id="caption"
              type="text"
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              placeholder="Figure caption"
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
              disabled={uploading}
            />
          </div>

          {/* Label */}
          <div>
            <label htmlFor="label" className="mb-2 block text-sm font-medium text-gray-700 dark:text-slate-200">
              Label (optional)
            </label>
            <input
              id="label"
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="fig:my-figure"
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
              disabled={uploading}
            />
            <p className="mt-1 text-xs text-gray-500">
              Used for referencing with \ref{'{'}label{'}'}
            </p>
          </div>

          {/* Width */}
          <div>
            <label htmlFor="width" className="mb-2 block text-sm font-medium text-gray-700 dark:text-slate-200">
              Width (relative to line width)
            </label>
            <input
              id="width"
              type="number"
              min="0.1"
              max="1"
              step="0.1"
              value={width}
              onChange={(e) => setWidth(e.target.value)}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100 dark:placeholder:text-slate-400"
              disabled={uploading}
            />
            <p className="mt-1 text-xs text-gray-500">
              0.8 = 80% of text width (recommended)
            </p>
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t bg-gray-50 px-6 py-4">
          <button
            onClick={handleClose}
            className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
            disabled={uploading}
          >
            Cancel
          </button>
          <button
            onClick={handleUpload}
            disabled={!file || !caption.trim() || uploading}
            className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {uploading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Uploading...</span>
              </>
            ) : (
              'Insert Figure'
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

export default FigureUploadDialog
