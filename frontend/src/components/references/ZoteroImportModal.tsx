import { useEffect, useState } from 'react'
import { ArrowLeft, BookOpen, Check, FolderOpen, Library, Loader2, X } from 'lucide-react'
import { zoteroAPI } from '../../services/api'

interface ZoteroCollection {
  key: string
  name: string
  num_items: number
}

interface ZoteroItem {
  key: string
  title: string
  authors: string[]
  year: number | null
  doi: string | null
  journal: string | null
  abstract: string | null
  url: string | null
  item_type: string
  already_imported: boolean
}

interface ZoteroImportModalProps {
  isOpen: boolean
  onClose: () => void
  onImportComplete: () => void
  projectId?: string
}

type Step = 'collections' | 'items'

const ZoteroImportModal: React.FC<ZoteroImportModalProps> = ({
  isOpen,
  onClose,
  onImportComplete,
  projectId,
}) => {
  const [step, setStep] = useState<Step>('collections')
  const [collections, setCollections] = useState<ZoteroCollection[]>([])
  const [items, setItems] = useState<ZoteroItem[]>([])
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const [, setSelectedCollection] = useState<string | null>(null)
  const [selectedCollectionName, setSelectedCollectionName] = useState<string>('')
  const [loadingCollections, setLoadingCollections] = useState(false)
  const [loadingItems, setLoadingItems] = useState(false)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ imported: number; skipped: number } | null>(null)

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setStep('collections')
      setCollections([])
      setItems([])
      setSelectedKeys(new Set())
      setSelectedCollection(null)
      setSelectedCollectionName('')
      setError(null)
      setResult(null)
      loadCollections()
    }
  }, [isOpen])

  const loadCollections = async () => {
    setLoadingCollections(true)
    setError(null)
    try {
      const res = await zoteroAPI.getCollections()
      setCollections(res.data.collections)
    } catch {
      setError('Failed to load Zotero collections. Check your credentials in Settings.')
    } finally {
      setLoadingCollections(false)
    }
  }

  const selectCollection = async (key: string | null, name: string) => {
    setSelectedCollection(key)
    setSelectedCollectionName(name)
    setStep('items')
    setLoadingItems(true)
    setError(null)
    setSelectedKeys(new Set())
    try {
      const params: { collection_key?: string; limit?: number } = { limit: 100 }
      if (key) params.collection_key = key
      const res = await zoteroAPI.getItems(params)
      setItems(res.data.items)
    } catch {
      setError('Failed to load items from Zotero.')
    } finally {
      setLoadingItems(false)
    }
  }

  const toggleItem = (key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const selectableItems = items.filter((i) => !i.already_imported)
  const allSelected = selectableItems.length > 0 && selectableItems.every((i) => selectedKeys.has(i.key))

  const toggleAll = () => {
    if (allSelected) {
      setSelectedKeys(new Set())
    } else {
      setSelectedKeys(new Set(selectableItems.map((i) => i.key)))
    }
  }

  const handleImport = async () => {
    if (selectedKeys.size === 0) return
    setImporting(true)
    setError(null)
    try {
      const res = await zoteroAPI.importItems({
        item_keys: Array.from(selectedKeys),
        project_id: projectId,
      })
      setResult({ imported: res.data.imported, skipped: res.data.skipped })
      onImportComplete()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      if (typeof detail === 'object' && detail?.error === 'limit_exceeded') {
        setError(detail.message || 'Reference limit reached. Upgrade your plan.')
      } else {
        setError(typeof detail === 'string' ? detail : 'Import failed. Please try again.')
      }
    } finally {
      setImporting(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 dark:bg-black/60">
      <div className="w-full max-w-xl overflow-hidden rounded-2xl bg-white shadow-2xl transition-colors dark:bg-slate-800">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4 dark:border-slate-700">
          <div className="flex items-center gap-2">
            {step === 'items' && (
              <button
                type="button"
                onClick={() => {
                  setStep('collections')
                  setResult(null)
                }}
                className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
              >
                <ArrowLeft className="h-4 w-4" />
              </button>
            )}
            <Library className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
            <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">
              {step === 'collections' ? 'Import from Zotero' : selectedCollectionName}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="max-h-[60vh] overflow-y-auto px-5 py-4">
          {error && (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
              {error}
            </div>
          )}

          {result && (
            <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300">
              Imported {result.imported} reference{result.imported !== 1 ? 's' : ''}
              {result.skipped > 0 && `, ${result.skipped} already existed`}.
            </div>
          )}

          {/* Collections step */}
          {step === 'collections' && (
            loadingCollections ? (
              <div className="flex items-center justify-center gap-2 py-12 text-sm text-gray-500 dark:text-slate-400">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading collections...
              </div>
            ) : (
              <div className="space-y-1">
                {/* All Items option */}
                <button
                  type="button"
                  onClick={() => selectCollection(null, 'All Items')}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition hover:bg-gray-100 dark:hover:bg-slate-700"
                >
                  <BookOpen className="h-4 w-4 text-indigo-500" />
                  <span className="flex-1 font-medium text-gray-900 dark:text-slate-100">All Items</span>
                </button>

                {collections.map((c) => (
                  <button
                    key={c.key}
                    type="button"
                    onClick={() => selectCollection(c.key, c.name)}
                    className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition hover:bg-gray-100 dark:hover:bg-slate-700"
                  >
                    <FolderOpen className="h-4 w-4 text-amber-500" />
                    <span className="flex-1 text-gray-900 dark:text-slate-100">{c.name}</span>
                    <span className="text-xs text-gray-400 dark:text-slate-500">{c.num_items}</span>
                  </button>
                ))}

                {collections.length === 0 && !loadingCollections && !error && (
                  <p className="py-8 text-center text-sm text-gray-500 dark:text-slate-400">
                    No collections found. Select "All Items" to browse your library.
                  </p>
                )}
              </div>
            )
          )}

          {/* Items step */}
          {step === 'items' && (
            loadingItems ? (
              <div className="flex items-center justify-center gap-2 py-12 text-sm text-gray-500 dark:text-slate-400">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading items...
              </div>
            ) : (
              <div className="space-y-1">
                {selectableItems.length > 0 && (
                  <button
                    type="button"
                    onClick={toggleAll}
                    className="mb-2 text-xs font-medium text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300"
                  >
                    {allSelected ? 'Deselect All' : 'Select All'}
                  </button>
                )}

                {items.map((item) => {
                  const disabled = item.already_imported
                  const checked = selectedKeys.has(item.key)
                  return (
                    <label
                      key={item.key}
                      className={`flex items-start gap-3 rounded-lg px-3 py-2.5 text-sm transition ${
                        disabled
                          ? 'cursor-not-allowed opacity-50'
                          : 'cursor-pointer hover:bg-gray-100 dark:hover:bg-slate-700'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked || disabled}
                        disabled={disabled}
                        onChange={() => !disabled && toggleItem(item.key)}
                        className="mt-0.5 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 disabled:opacity-50"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-gray-900 dark:text-slate-100 leading-snug">
                          {item.title}
                          {disabled && (
                            <span className="ml-2 inline-flex items-center gap-1 text-xs font-normal text-emerald-600 dark:text-emerald-400">
                              <Check className="h-3 w-3" /> Imported
                            </span>
                          )}
                        </p>
                        <p className="mt-0.5 text-xs text-gray-500 dark:text-slate-400 truncate">
                          {[
                            item.authors?.slice(0, 3).join(', '),
                            item.year,
                            item.journal,
                          ]
                            .filter(Boolean)
                            .join(' · ')}
                        </p>
                      </div>
                    </label>
                  )
                })}

                {items.length === 0 && !loadingItems && !error && (
                  <p className="py-8 text-center text-sm text-gray-500 dark:text-slate-400">
                    No items found in this collection.
                  </p>
                )}
              </div>
            )
          )}
        </div>

        {/* Footer */}
        {step === 'items' && (
          <div className="flex items-center justify-between border-t border-gray-200 px-5 py-3 dark:border-slate-700">
            <span className="text-xs text-gray-500 dark:text-slate-400">
              {selectedKeys.size} selected
            </span>
            <button
              type="button"
              onClick={handleImport}
              disabled={selectedKeys.size === 0 || importing}
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:bg-indigo-400 disabled:cursor-not-allowed"
            >
              {importing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {importing
                ? 'Importing...'
                : `Import ${selectedKeys.size} reference${selectedKeys.size !== 1 ? 's' : ''}`}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default ZoteroImportModal
