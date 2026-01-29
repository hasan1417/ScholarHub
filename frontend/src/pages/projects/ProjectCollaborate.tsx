import { Routes, Route, Navigate, useParams } from 'react-router-dom'
import { Video, Sparkles } from 'lucide-react'
import ProjectDiscussion from './ProjectDiscussion'
import ProjectDiscussionOR from './ProjectDiscussionOR'
import ProjectSyncSpace from './ProjectSyncSpace'
import SubTabs, { SubTab } from '../../components/navigation/SubTabs'

const COLLABORATE_TABS: SubTab[] = [
  // Normal Discussion hidden - using Beta only for now
  // {
  //   label: 'Discussion',
  //   path: 'chat',
  //   icon: MessageCircle,
  //   tooltip: 'Team discussions with channels and threads',
  // },
  {
    label: 'Discussion AI',
    path: 'chat-beta',
    icon: Sparkles,
    tooltip: 'Multi-model AI chat (GPT, Claude, Gemini, DeepSeek)',
    badge: 'Beta',
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
          <Route index element={<Navigate to="chat-beta" replace />} />
          <Route path="chat" element={<ProjectDiscussion />} />
          <Route path="chat-beta" element={<ProjectDiscussionOR />} />
          <Route path="meetings" element={<ProjectSyncSpace />} />
        </Routes>
      </div>
    </div>
  )
}

export default ProjectCollaborate
