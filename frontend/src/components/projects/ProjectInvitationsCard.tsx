import React, { useEffect, useState, useCallback } from 'react'
import { projectsAPI } from '../../services/api'

interface ProjectInvitation {
  project_id: string
  project_title: string
  member_id: string
  role: string
  invited_at?: string | null
  invited_by?: string | null
}

const ProjectInvitationsCard: React.FC = () => {
  const [invites, setInvites] = useState<ProjectInvitation[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const resp = await projectsAPI.listPendingInvitations()
      setInvites(resp.data?.invitations || [])
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load project invitations')
      setInvites([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const accept = async (projectId: string, memberId: string) => {
    try {
      await projectsAPI.acceptInvitation(projectId, memberId)
      await load()
    } catch (e) {
      alert('Failed to accept project invitation')
    }
  }

  const decline = async (projectId: string, memberId: string) => {
    try {
      await projectsAPI.declineInvitation(projectId, memberId)
      await load()
    } catch (e) {
      alert('Failed to decline project invitation')
    }
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Project Invitations</h3>
        <div className="text-sm text-gray-600">Loading…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Project Invitations</h3>
        <div className="text-sm text-red-600">{error}</div>
      </div>
    )
  }

  if (invites.length === 0) {
    return null
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h3 className="text-lg font-medium text-gray-900 mb-4">Project Invitations</h3>
      <div className="space-y-3">
        {invites.map((inv) => (
          <div key={inv.member_id} className="flex items-center justify-between rounded-md bg-gray-50 p-3">
            <div className="min-w-0">
              <div className="font-medium text-gray-900 truncate">{inv.project_title}</div>
              <div className="text-xs text-gray-600">
                Role: {inv.role.toLowerCase()} {inv.invited_at && `• Invited ${new Date(inv.invited_at).toLocaleString()}`}
              </div>
              {inv.invited_by && (
                <div className="text-xs text-gray-500">Invited by {inv.invited_by}</div>
              )}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => accept(inv.project_id, inv.member_id)}
                className="px-3 py-1 bg-green-600 text-white rounded text-xs hover:bg-green-700"
              >
                Accept
              </button>
              <button
                onClick={() => decline(inv.project_id, inv.member_id)}
                className="px-3 py-1 bg-red-100 text-red-700 rounded text-xs hover:bg-red-200"
              >
                Decline
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default ProjectInvitationsCard
