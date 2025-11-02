import React, { useEffect, useState, useCallback } from 'react'
import { researchPapersAPI, teamAPI } from '../../services/api'
import { usePapers } from '../../contexts/PapersContext'

type PendingInvite = {
  id: string
  paper_id: string
  role: string
  invited_at: string
  paper_title: string
}

const PendingInvitationsCard: React.FC = () => {
  const [invites, setInvites] = useState<PendingInvite[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { refreshPapers } = usePapers()

  const load = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const resp = await researchPapersAPI.getPendingInvitations()
      setInvites(resp.data.pending_invitations || [])
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load invitations')
      setInvites([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const accept = async (paperId: string, memberId: string) => {
    try {
      await teamAPI.acceptInvitation(paperId, memberId)
      await load()
      // Refresh papers so the accepted paper appears in lists
      await refreshPapers()
    } catch (e) {
      alert('Failed to accept invitation')
    }
  }

  const decline = async (paperId: string, memberId: string) => {
    try {
      await teamAPI.declineInvitation(paperId, memberId)
      await load()
    } catch (e) {
      alert('Failed to decline invitation')
    }
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Pending Invitations</h3>
        <div className="text-sm text-gray-600">Loading...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Pending Invitations</h3>
        <div className="text-sm text-red-600">{error}</div>
      </div>
    )
  }

  if (!invites.length) {
    return null
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h3 className="text-lg font-medium text-gray-900 mb-4">Pending Invitations</h3>
      <div className="space-y-3">
        {invites.map((inv) => (
          <div key={inv.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-md">
            <div className="min-w-0">
              <div className="font-medium text-gray-900 truncate">{inv.paper_title}</div>
              <div className="text-xs text-gray-600">Role: {inv.role.toLowerCase()} • Invited {new Date(inv.invited_at).toLocaleString()}</div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={() => accept(inv.paper_id, inv.id)}
                className="px-3 py-1 bg-green-600 text-white rounded text-xs hover:bg-green-700"
              >
                Accept
              </button>
              <button
                onClick={() => decline(inv.paper_id, inv.id)}
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

export default PendingInvitationsCard
