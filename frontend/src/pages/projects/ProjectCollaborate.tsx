import { Routes, Route, Navigate, useParams } from 'react-router-dom'
import { MessageCircle, Video } from 'lucide-react'
import ProjectDiscussion from './ProjectDiscussion'
import ProjectSyncSpace from './ProjectSyncSpace'
import SubTabs, { SubTab } from '../../components/navigation/SubTabs'

const COLLABORATE_TABS: SubTab[] = [
  {
    label: 'Discussion',
    path: 'chat',
    icon: MessageCircle,
    tooltip: 'Team discussions with channels and threads',
  },
  {
    label: 'Meetings',
    path: 'meetings',
    icon: Video,
    tooltip: 'Video calls with automatic transcription',
  },
]

const ProjectCollaborate = () => {
  const { projectId } = useParams<{ projectId: string }>()

  if (!projectId) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-200">
        <p>Project ID is required</p>
      </div>
    )
  }

  return (
    <div className="space-y-0 overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800/60">
      <SubTabs tabs={COLLABORATE_TABS} basePath={`/projects/${projectId}/collaborate`} />

      <div className="p-6 dark:bg-slate-900/10">
        <Routes>
          <Route index element={<Navigate to="chat" replace />} />
          <Route path="chat" element={<ProjectDiscussion />} />
          <Route path="meetings" element={<ProjectSyncSpace />} />
        </Routes>
      </div>
    </div>
  )
}

export default ProjectCollaborate
