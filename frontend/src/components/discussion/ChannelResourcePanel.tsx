import { ReactNode, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  DiscussionChannelResource,
  DiscussionChannelResourceCreate,
  DiscussionResourceType,
  MeetingSummary,
  ProjectReferenceSuggestion,
  ResearchPaper,
} from '../../types'
import {
  researchPapersAPI,
  projectReferencesAPI,
  projectMeetingsAPI,
} from '../../services/api'
import {
  Loader2,
  BookOpen,
  FileText,
  Bookmark,
  Plus,
  X,
  ChevronDown,
} from 'lucide-react'

interface ChannelResourcePanelProps {
  projectId: string
  loading: boolean
  error: Error | null
  resources: DiscussionChannelResource[]
  onCreateResource: (payload: DiscussionChannelResourceCreate) => void
  onRemoveResource: (resourceId: string) => void
  isSubmitting?: boolean
  isCollapsed?: boolean
  onToggleCollapse?: () => void
}

interface ResourceOption {
  id: string
  label: string
  subtitle?: string
  meta?: string[]
}

const resourceTypeLabels: Record<DiscussionResourceType, string> = {
  paper: 'Project paper',
  reference: 'Related paper',
  meeting: 'Transcript',
}

const iconForType = (type: DiscussionChannelResource['resource_type']): ReactNode => {
  switch (type) {
    case 'paper':
      return <FileText className="h-4 w-4 text-indigo-500" />
    case 'reference':
      return <Bookmark className="h-4 w-4 text-amber-500" />
    case 'meeting':
    default:
      return <BookOpen className="h-4 w-4 text-emerald-500" />
  }
}

const formatResourceLabel = (resource: DiscussionChannelResource): string => {
  return resource.details?.title ||
    (resource.resource_type === 'paper'
      ? 'Research paper'
      : resource.resource_type === 'reference'
        ? 'Related paper'
        : 'Transcript')
}

const resourceTypes: { label: string; value: DiscussionResourceType }[] = [
  { label: resourceTypeLabels.paper, value: 'paper' },
  { label: resourceTypeLabels.reference, value: 'reference' },
  { label: resourceTypeLabels.meeting, value: 'meeting' },
]

const truncate = (value: string, limit = 280): string => {
  if (value.length <= limit) return value
  return `${value.slice(0, limit - 3).trimEnd()}...`
}

const buildPaperOptions = (papers: ResearchPaper[] | undefined): ResourceOption[] => {
  if (!papers) return []
  return papers.map((paper) => ({
    id: paper.id,
    label: paper.title || 'Untitled paper',
    subtitle: paper.summary ? truncate(paper.summary) : paper.abstract ? truncate(paper.abstract) : undefined,
    meta: [paper.status, paper.year ? String(paper.year) : undefined].filter(Boolean) as string[],
  }))
}

const buildReferenceOptions = (
  references: ProjectReferenceSuggestion[] | undefined,
): ResourceOption[] => {
  if (!references) return []
  return references
    .filter((item) => Boolean(item.reference))
    .map((item) => {
      const reference = item.reference!
      const metaParts: string[] = []
      if (reference.year) metaParts.push(String(reference.year))
      if (reference.source) metaParts.push(reference.source)
      return {
        id: item.reference_id,
        label: reference.title || 'Reference',
        subtitle: reference.summary
          ? truncate(reference.summary)
          : reference.abstract
            ? truncate(reference.abstract)
            : undefined,
        meta: metaParts,
      }
    })
}

const buildMeetingOptions = (meetings: MeetingSummary[] | undefined): ResourceOption[] => {
  if (!meetings) return []
  return meetings.map((meeting) => {
    const createdAt = meeting.created_at ? new Date(meeting.created_at) : undefined
    const label = meeting.summary
      ? meeting.summary
      : createdAt
        ? `Meeting on ${createdAt.toLocaleDateString()}`
        : 'Meeting'
    const meta: string[] = []
    meta.push(meeting.status)
    if (meeting.transcript) {
      meta.push('Transcript available')
    }
    return {
      id: meeting.id,
      label,
      subtitle: meeting.summary ? truncate(meeting.summary) : undefined,
      meta,
    }
  })
}

const buildMetaTags = (resource: DiscussionChannelResource): string[] => {
  const details = resource.details || {}
  const tags: string[] = []

  if (resource.resource_type === 'paper') {
    if (details.status) tags.push(details.status)
  } else if (resource.resource_type === 'reference') {
    if (details.source) tags.push(details.source)
  }

  return tags
}

const ChannelResourcePanel = ({
  projectId,
  loading,
  error,
  resources,
  onCreateResource,
  onRemoveResource,
  isSubmitting = false,
  isCollapsed = false,
  onToggleCollapse,
}: ChannelResourcePanelProps) => {
  const [isAdding, setIsAdding] = useState(false)
  const [resourceType, setResourceType] = useState<DiscussionResourceType>('paper')
  const [selectedResourceIds, setSelectedResourceIds] = useState<string[]>([])
  const [filterQuery, setFilterQuery] = useState('')

  useEffect(() => {
    if (isCollapsed) {
      setIsAdding(false)
      setSelectedResourceIds([])
      setFilterQuery('')
    }
  }, [isCollapsed])

  const papersQuery = useQuery({
    queryKey: ['projectDiscussionPapers', projectId],
    queryFn: async () => {
      const response = await researchPapersAPI.getPapers({ projectId, limit: 200 })
      return response.data.papers as ResearchPaper[]
    },
    enabled: Boolean(projectId),
    staleTime: 60_000,
  })

  const referencesQuery = useQuery({
    queryKey: ['projectDiscussionReferences', projectId],
    queryFn: async () => {
      const response = await projectReferencesAPI.list(projectId, { status: 'approved' })
      return response.data.references as ProjectReferenceSuggestion[]
    },
    enabled: Boolean(projectId),
    staleTime: 60_000,
  })

  const meetingsQuery = useQuery({
    queryKey: ['projectDiscussionMeetings', projectId],
    queryFn: async () => {
      const response = await projectMeetingsAPI.listMeetings(projectId)
      return response.data.meetings as MeetingSummary[]
    },
    enabled: Boolean(projectId),
    staleTime: 60_000,
  })

  const resourceOptions: ResourceOption[] = useMemo(() => {
    if (resourceType === 'paper') return buildPaperOptions(papersQuery.data)
    if (resourceType === 'reference') return buildReferenceOptions(referencesQuery.data)
    return buildMeetingOptions(meetingsQuery.data)
  }, [resourceType, papersQuery.data, referencesQuery.data, meetingsQuery.data])

  const selectedOptions = useMemo(() => {
    if (!selectedResourceIds.length) return []
    const lookup = new Set(selectedResourceIds)
    return resourceOptions.filter((option) => lookup.has(option.id))
  }, [resourceOptions, selectedResourceIds])

  const linkedOptionIds = useMemo(() => {
    const record: Record<DiscussionResourceType, Set<string>> = {
      paper: new Set(),
      reference: new Set(),
      meeting: new Set(),
    }
    resources.forEach((resource) => {
      if (resource.paper_id) record.paper.add(resource.paper_id)
      if (resource.reference_id) record.reference.add(resource.reference_id)
      if (resource.meeting_id) record.meeting.add(resource.meeting_id)
    })
    return record
  }, [resources])

  const optionsLoading =
    resourceType === 'paper'
      ? papersQuery.isLoading
      : resourceType === 'reference'
        ? referencesQuery.isLoading
        : meetingsQuery.isLoading

  const optionsError =
    resourceType === 'paper'
      ? papersQuery.error
      : resourceType === 'reference'
        ? referencesQuery.error
        : meetingsQuery.error

  const canSubmit = useMemo(() => {
    if (isSubmitting) return false
    if (optionsLoading) return false
    return selectedResourceIds.length > 0
  }, [isSubmitting, optionsLoading, selectedResourceIds])

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!canSubmit) return

    selectedResourceIds.forEach((resourceId) => {
      const payload: DiscussionChannelResourceCreate = {
        resource_type: resourceType,
      }

      if (resourceType === 'paper') {
        payload.paper_id = resourceId
      } else if (resourceType === 'reference') {
        payload.reference_id = resourceId
      } else if (resourceType === 'meeting') {
        payload.meeting_id = resourceId
      }

      onCreateResource(payload)
    })

    setSelectedResourceIds([])
    setIsAdding(false)
  }

  const handleRemove = (resourceId: string) => {
    if (!window.confirm('Remove this resource from the channel?')) {
      return
    }
    onRemoveResource(resourceId)
  }

  const currentTypeLabel = resourceTypeLabels[resourceType]

  const filteredResources = useMemo(() => {
    const query = filterQuery.trim().toLowerCase()
    if (!query) return resources
    return resources.filter((resource) => {
      const label = formatResourceLabel(resource).toLowerCase()
      const summary = resource.details?.summary?.toLowerCase()
      const meta = buildMetaTags(resource).join(' ').toLowerCase()
      return label.includes(query) || (summary ? summary.includes(query) : false) || meta.includes(query)
    })
  }, [filterQuery, resources])

  const groupedResources = useMemo(() => {
    const grouped: Record<DiscussionResourceType, DiscussionChannelResource[]> = {
      paper: [],
      reference: [],
      meeting: [],
    }
    filteredResources.forEach((resource) => {
      grouped[resource.resource_type]?.push(resource)
    })
    return grouped
  }, [filteredResources])

  const hasAnyResources = filteredResources.length > 0

  const renderResourceItem = (resource: DiscussionChannelResource) => {
    const isReference = resource.resource_type === 'reference'
    const metaTags = isReference ? [] : buildMetaTags(resource)
    const label = formatResourceLabel(resource).trim()
    const summary = resource.details?.summary?.trim()
    const normalizedLabel = label.toLowerCase()
    const normalizedSummary = summary?.toLowerCase()
    const showSummary = !isReference && Boolean(summary) && normalizedSummary !== normalizedLabel
    const displayLabel = truncate(label, 80)

    return (
      <li
        key={resource.id}
        className="flex items-start gap-2.5 rounded-lg border border-gray-100 bg-gray-50/70 p-2.5 text-[13px] text-gray-700 transition-colors dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-200"
      >
        <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-full bg-white shadow dark:bg-slate-900">
          {iconForType(resource.resource_type)}
        </div>
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-[13px] font-semibold text-gray-900 dark:text-slate-100" title={label}>
            {displayLabel}
          </p>
          {showSummary && summary && (
            <p className="line-clamp-2 text-[11px] leading-relaxed text-gray-500 dark:text-slate-300">{truncate(summary, 140)}</p>
          )}
          {!isReference && (
            <div className="flex flex-wrap items-center gap-1.5 text-[10px] uppercase tracking-wide text-gray-400 dark:text-slate-400">
              <span className="font-medium text-indigo-500/90 dark:text-indigo-300">{resourceTypeLabels[resource.resource_type]}</span>
              {metaTags.map((tag) => (
                <span key={tag} className="rounded-full bg-gray-200 px-2 py-0.5 text-[10px] text-gray-500 dark:bg-slate-700 dark:text-slate-300">
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => handleRemove(resource.id)}
          className="rounded-full p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
          title="Unlink resource"
        >
          <X className="h-4 w-4" />
        </button>
      </li>
    )
  }

  return (
    <div className="flex flex-col rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-900/40">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {onToggleCollapse && (
            <button
              type="button"
              onClick={onToggleCollapse}
              className="rounded-full border border-gray-200 p-1 text-gray-500 transition hover:bg-gray-100 hover:text-gray-700 dark:border-slate-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
              aria-label={isCollapsed ? 'Expand resources panel' : 'Collapse resources panel'}
            >
              <ChevronDown
                className={clsx('h-4 w-4 transition-transform', isCollapsed ? '-rotate-90' : 'rotate-0')}
              />
            </button>
          )}
          <h3 className="text-sm font-semibold text-gray-900 dark:text-slate-100">Channel resources</h3>
        </div>
      <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-slate-400">
        <span>{resources.length}</span>
        <button
          type="button"
          onClick={() => {
            if (isCollapsed && onToggleCollapse) {
              onToggleCollapse()
            }
            setIsAdding((prev) => !prev)
            setSelectedResourceIds([])
          }}
          className="inline-flex items-center gap-1 rounded-full border border-indigo-200 px-2.5 py-1 text-xs font-medium text-indigo-600 transition hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
          disabled={isSubmitting}
        >
            <Plus className="h-3.5 w-3.5" />
            Link
          </button>
        </div>
      </div>

      {!isCollapsed && (
        <div className="mt-3 space-y-3 overflow-y-auto max-h-72">
        {isAdding && (
          <form className="mb-4 space-y-3 rounded-lg border border-indigo-100 bg-indigo-50/40 p-3 transition-colors dark:border-indigo-400/40 dark:bg-slate-800/60" onSubmit={handleSubmit}>
            <div className="flex flex-col gap-2">
              <label className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300" htmlFor="resource-type">
                Resource type
              </label>
              <select
                id="resource-type"
                value={resourceType}
                onChange={(event) => {
                  const nextType = event.target.value as DiscussionResourceType
                  setResourceType(nextType)
                  setSelectedResourceIds([])
                }}
                className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
              >
                {resourceTypes.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-xs font-medium uppercase tracking-wide text-gray-600 dark:text-slate-300" htmlFor="resource-value">
                {currentTypeLabel}
              </label>
              {optionsLoading ? (
                <div className="flex items-center gap-2 rounded-lg border border-dashed border-gray-300 bg-white px-3 py-2 text-sm text-gray-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-300">
                  <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
                  Loading {currentTypeLabel.toLowerCase()}s...
                </div>
              ) : optionsError ? (
                <div className="rounded-lg border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-200">
                  Unable to load {currentTypeLabel.toLowerCase()}s.
                </div>
              ) : resourceOptions.length === 0 ? (
                <div className="rounded-lg border border-dashed border-gray-300 bg-white px-3 py-2 text-xs text-gray-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-300">
                  No {currentTypeLabel.toLowerCase()}s available for this project.
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-[11px] uppercase tracking-wide text-gray-400 dark:text-slate-400">
                    <span>Select {currentTypeLabel.toLowerCase()}s</span>
                    {selectedResourceIds.length > 0 && (
                      <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-medium text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-200">
                        {selectedResourceIds.length} selected
                      </span>
                    )}
                  </div>
                  <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-gray-200 bg-white p-1 dark:border-slate-600 dark:bg-slate-900/60">
                    {resourceOptions.map((option) => {
                      const linkedSet = linkedOptionIds[resourceType]
                      const isAlreadyLinked = linkedSet.has(option.id)
                      const isChecked = selectedResourceIds.includes(option.id)
                      return (
                        <label
                          key={option.id}
                          className={clsx(
                            'flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-sm transition',
                            isAlreadyLinked
                              ? 'bg-gray-100 text-gray-400 dark:bg-slate-800/50 dark:text-slate-500'
                              : isChecked
                                ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-200'
                                : 'hover:bg-gray-100 dark:hover:bg-slate-800/60'
                          )}
                        >
                          <input
                            type="checkbox"
                            className="mt-0.5 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60"
                            disabled={isAlreadyLinked}
                            checked={isChecked}
                            onChange={() => {
                              setSelectedResourceIds((prev) =>
                                prev.includes(option.id)
                                  ? prev.filter((id) => id !== option.id)
                                  : [...prev, option.id]
                              )
                            }}
                          />
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center justify-between">
                              <span className="font-medium text-gray-900 dark:text-slate-100">{option.label}</span>
                              {isAlreadyLinked && (
                                <span className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-slate-500">Linked</span>
                              )}
                            </div>
                            {option.subtitle && (
                              <p className="mt-1 line-clamp-2 text-[11px] text-gray-500 dark:text-slate-300">{option.subtitle}</p>
                            )}
                            {option.meta && option.meta.length > 0 && (
                              <p className="mt-1 text-[10px] uppercase tracking-wide text-gray-400 dark:text-slate-500">
                                {option.meta.join(' • ')}
                              </p>
                            )}
                          </div>
                        </label>
                      )
                    })}
                  </div>
                </div>
              )}
              {selectedOptions.length > 0 && (
                <div className="space-y-1 text-xs text-gray-500 dark:text-slate-400">
                  <p className="font-medium text-gray-600 dark:text-slate-300">Selected</p>
                  <ul className="space-y-1">
                    {selectedOptions.map((option) => (
                      <li key={option.id} className="flex items-center justify-between gap-2 rounded-md bg-gray-100 px-2 py-1 dark:bg-slate-800/60">
                        <span className="truncate text-[11px] text-gray-600 dark:text-slate-300">{option.label}</span>
                        <button
                          type="button"
                          onClick={() =>
                            setSelectedResourceIds((prev) => prev.filter((id) => id !== option.id))
                          }
                          className="rounded-full p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-600 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                          aria-label={`Remove ${option.label}`}
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setIsAdding(false)
                  setSelectedResourceIds([])
                }}
                className="rounded-lg border border-gray-200 px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!canSubmit}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300 dark:disabled:bg-indigo-500/40"
              >
                {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                Link resource
              </button>
            </div>
          </form>
        )}

        {loading && (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-indigo-500" />
          </div>
        )}

        {error && !loading && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-200">
            Unable to load channel resources.
          </div>
        )}

        {!loading && !error && resources.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 p-4 text-xs text-gray-500 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-300">
            No linked resources yet. Attach project papers, related papers, or meeting transcripts to keep this conversation anchored.
          </div>
        )}

        {!loading && !error && resources.length > 0 && (
          <div className="space-y-3">
            <div className="sticky top-0 z-10 bg-white pb-2 dark:bg-slate-900/60">
              <label className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-gray-400 dark:text-slate-400" htmlFor="channel-resource-filter">
                Filter resources
              </label>
              <div className="flex items-center gap-2">
                <input
                  id="channel-resource-filter"
                  type="search"
                  value={filterQuery}
                  onChange={(event) => setFilterQuery(event.target.value)}
                  placeholder="Search by title or summary"
                  className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900/60 dark:text-slate-100"
                />
                {filterQuery.trim() && (
                  <button
                    type="button"
                    onClick={() => setFilterQuery('')}
                    className="rounded-lg border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>

            {!hasAnyResources && (
              <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 p-4 text-xs text-gray-500 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-300">
                No resources match your filter. Adjust the search to see more results.
              </div>
            )}

            {hasAnyResources && (
              <div className="space-y-4">
                {resourceTypes.map(({ value, label }) => {
                  const items = groupedResources[value]
                  if (!items || items.length === 0) return null
                  return (
                    <section key={value} className="space-y-2">
                      <div className="flex items-center justify-between text-[11px] uppercase tracking-wide text-gray-400 dark:text-slate-400">
                        <span>{label}</span>
                        <span className="rounded-full bg-gray-200 px-2 py-0.5 text-[10px] text-gray-600 dark:bg-slate-700 dark:text-slate-200">{items.length}</span>
                      </div>
                      <ul className="space-y-3">{items.map((resourceItem) => renderResourceItem(resourceItem))}</ul>
                    </section>
                  )
                })}
              </div>
            )}
          </div>
        )}
      </div>
      )}
    </div>
  )
}

export default ChannelResourcePanel
