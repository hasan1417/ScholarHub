import { Routes, Route, Navigate, useParams } from 'react-router-dom'
import { Search, BookOpen } from 'lucide-react'
import ProjectDiscovery from './ProjectDiscovery'
import ProjectReferences from './ProjectReferences'
import SubTabs, { SubTab } from '../../components/navigation/SubTabs'
import { useQuery } from '@tanstack/react-query'
import { projectDiscoveryAPI } from '../../services/api'
import { useProjectContext } from './ProjectLayout'

const ProjectLibrary = () => {
  const { projectId } = useParams<{ projectId: string }>()
  const { currentRole } = useProjectContext()

  // Get pending discovery count for badge
  const pendingDiscovery = useQuery({
    queryKey: ['project', projectId, 'discoveryPendingCount'],
    queryFn: async () => {
      if (!projectId) return 0
      const response = await projectDiscoveryAPI.getPendingCount(projectId)
      return response.data.pending
    },
    enabled: Boolean(projectId) && currentRole !== 'viewer',
    refetchInterval: 60000,
  })

  const pendingCount = pendingDiscovery.data ?? 0

  const LIBRARY_TABS: SubTab[] = [
    {
      label: 'Discover',
      path: 'discover',
      icon: Search,
      tooltip: 'Search for papers with AI-powered discovery',
      badge: pendingCount,
    },
    {
      label: 'References',
      path: 'references',
      icon: BookOpen,
      tooltip: 'Your collected papers for this project',
    },
  ]

  if (!projectId) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-200">
        <p>Project ID is required</p>
      </div>
    )
  }

  return (
    <div className="space-y-0 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800/60">
      <SubTabs tabs={LIBRARY_TABS} basePath={`/projects/${projectId}/library`} />

      <div className="p-6 dark:bg-slate-900/10">
        <Routes>
          <Route index element={<Navigate to="discover" replace />} />
          <Route path="discover" element={<ProjectDiscovery />} />
          <Route path="references" element={<ProjectReferences />} />
        </Routes>
      </div>
    </div>
  )
}

export default ProjectLibrary
