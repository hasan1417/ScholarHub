import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Users, Shield, Edit, Eye, Trash2, UserCheck, UserX, Clock } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../../contexts/AuthContext'
import { teamAPI } from '../../services/api'
import { ProjectMember } from '../../types'

interface TeamMember {
  id: string
  user_id: string
  email: string
  first_name?: string
  last_name?: string
  role: string
  status: string
  joined_at?: string
  is_owner: boolean
}

interface TeamMembersListProps {
  paperId?: string
  projectMembers?: ProjectMember[]
  projectOwnerId?: string
  onInviteMember?: () => void
  refreshKey?: number
  className?: string
}

const emptyMembers: TeamMember[] = []

const TeamMembersList: React.FC<TeamMembersListProps> = ({
  paperId,
  projectMembers,
  projectOwnerId,
  onInviteMember,
  refreshKey,
  className,
}) => {
  const { user } = useAuth()
  const isProjectScope = Array.isArray(projectMembers)

  const mappedProjectMembers = useMemo<TeamMember[]>(() => {
    if (!projectMembers) {
      return emptyMembers
    }

    return projectMembers.map((member) => ({
      id: member.id || member.user_id,
      user_id: member.user_id,
      email: member.user?.email ?? 'unknown@scholarhub.dev',
      first_name: member.user?.first_name ?? undefined,
      last_name: member.user?.last_name ?? undefined,
      role: member.role,
      status: member.status,
      joined_at: member.joined_at ?? undefined,
      is_owner: Boolean(projectOwnerId && member.user_id === projectOwnerId),
    }))
  }, [projectMembers, projectOwnerId])

  const [members, setMembers] = useState<TeamMember[]>(() => (isProjectScope ? mappedProjectMembers : emptyMembers))
  const [isLoading, setIsLoading] = useState<boolean>(!isProjectScope)
  const [error, setError] = useState<string | null>(null)
  const [updatingMemberId, setUpdatingMemberId] = useState<string | null>(null)
  const [removingMemberId, setRemovingMemberId] = useState<string | null>(null)

  const normalizeRole = useCallback((role: string) => {
    const value = (role || '').toLowerCase()
    if (value === 'reviewer') return 'viewer'
    if (value === 'owner') return 'admin'
    if (value === 'admin' || value === 'editor' || value === 'viewer') {
      return value
    }
    return 'viewer'
  }, [])

  const loadTeamMembers = useCallback(async () => {
    if (!paperId) {
      setMembers(emptyMembers)
      setIsLoading(false)
      return
    }

    try {
      setIsLoading(true)
      setError(null)

      const response = await teamAPI.getTeamMembers(paperId)
      const data = response.data as TeamMember[] | { members?: TeamMember[] } | null
      const entries = Array.isArray(data)
        ? data
        : Array.isArray(data?.members)
          ? data.members
          : []
      setMembers(entries)
    } catch (err) {
      console.error('Error loading team members:', err)
      setMembers(emptyMembers)
      setError('Unable to load team members right now.')
    } finally {
      setIsLoading(false)
    }
  }, [paperId])

  useEffect(() => {
    if (isProjectScope) {
      setMembers(mappedProjectMembers)
      setIsLoading(false)
      setError(null)
      return
    }

    loadTeamMembers()
  }, [isProjectScope, mappedProjectMembers, loadTeamMembers, refreshKey])

  const getRoleIcon = useCallback((role: string) => {
    const normalized = normalizeRole(role)
    const size = 'h-4 w-4'
    switch (normalized) {
      case 'admin':
        return <Shield className={`${size} text-purple-500 dark:text-white/80`} />
      case 'editor':
        return <Edit className={`${size} text-emerald-500 dark:text-white/80`} />
      case 'viewer':
        return <Eye className={`${size} text-slate-500 dark:text-white/80`} />
      default:
        return <Users className={`${size} text-slate-500 dark:text-white/80`} />
    }
  }, [normalizeRole])

  const getRoleBadgeClasses = useCallback((role: string) => {
    const normalized = normalizeRole(role)
    switch (normalized) {
      case 'admin':
        return 'bg-purple-100 text-purple-700 dark:bg-white/20 dark:text-white'
      case 'editor':
        return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-100'
      case 'viewer':
        return 'bg-slate-200 text-slate-700 dark:bg-slate-500/20 dark:text-slate-200'
      default:
        return 'bg-slate-200 text-slate-700 dark:bg-slate-500/20 dark:text-slate-200'
    }
  }, [normalizeRole])

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'accepted':
        return <UserCheck className="h-4 w-4 text-emerald-500 dark:text-emerald-300" />
      case 'invited':
        return <Clock className="h-4 w-4 text-amber-500 dark:text-amber-300" />
      case 'declined':
        return <UserX className="h-4 w-4 text-rose-500 dark:text-rose-300" />
      default:
        return <Users className="h-4 w-4 text-slate-400 dark:text-slate-300" />
    }
  }

  const canManageTeam = useMemo(() => {
    if (isProjectScope) return false
    const viewerRole = normalizeRole(members.find((m) => m.user_id === user?.id)?.role || 'viewer')
    return viewerRole === 'admin'
  }, [isProjectScope, members, normalizeRole, user?.id])

  const handleRoleChange = async (member: TeamMember, nextRole: string) => {
    if (isProjectScope || !paperId) return
    if (normalizeRole(member.role) === nextRole) return
    try {
      setUpdatingMemberId(member.id)
      await teamAPI.updateMemberRole(paperId, member.id, nextRole)
      await loadTeamMembers()
    } catch (err) {
      console.error('Failed to update member role', err)
      alert('Unable to update member role right now.')
    } finally {
      setUpdatingMemberId(null)
    }
  }

  const handleRemoveMember = async (member: TeamMember) => {
    if (isProjectScope || !paperId) return
    if (removingMemberId || member.is_owner) return
    const confirmed = window.confirm(`Remove ${member.email} from this paper?`)
    if (!confirmed) return
    try {
      setRemovingMemberId(member.id)
      await teamAPI.removeTeamMember(paperId, member.id)
      await loadTeamMembers()
    } catch (err) {
      console.error('Failed to remove member', err)
      alert('Unable to remove this member right now.')
    } finally {
      setRemovingMemberId(null)
    }
  }

  if (isLoading) {
    return (
      <div
        className={clsx(
          'w-full rounded-2xl border border-gray-200 bg-white p-4 backdrop-blur dark:border-white/10 dark:bg-white/5',
          className,
        )}
      >
        <div className="animate-pulse space-y-3">
          <div className="h-6 w-1/3 rounded bg-gray-200 dark:bg-white/20" />
          <div className="space-y-3">
            <div className="h-12 rounded-lg bg-gray-100 dark:bg-white/10" />
            <div className="h-12 rounded-lg bg-gray-100 dark:bg-white/10" />
            <div className="h-12 rounded-lg bg-gray-100 dark:bg-white/10" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div
      className={clsx(
        'w-full rounded-2xl border border-gray-200 bg-white p-4 text-slate-900 shadow-sm backdrop-blur dark:border-white/10 dark:bg-white/5 dark:text-slate-100',
        className,
      )}
    >
      <div className="mb-4 flex items-center justify-between">
        <h3 className="flex min-w-0 items-center text-lg font-semibold text-slate-900 dark:text-slate-100">
          <Users className="mr-2 h-5 w-5 flex-shrink-0 text-indigo-500 dark:text-indigo-300" />
          <span className="truncate">Team Members ({members.length})</span>
        </h3>
        {!isProjectScope && onInviteMember && (
          <button
            onClick={onInviteMember}
            className="rounded-full border border-indigo-200 px-3 py-1 text-xs font-medium text-indigo-600 transition-colors hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
          >
            Invite member
          </button>
        )}
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-400/30 dark:bg-rose-500/10 dark:text-rose-100">
          {error}
        </div>
      )}

      <div className="space-y-3">
        {members.map((member) => {
          const displayName = member.first_name && member.last_name
            ? `${member.first_name} ${member.last_name}`
            : member.email
          const normalizedRole = normalizeRole(member.role)

          return (
            <div
              key={member.id}
              className="flex items-center justify-between rounded-xl border border-gray-100 bg-gray-50 p-3 transition-colors dark:border-white/10 dark:bg-white/5"
            >
              <div className="flex min-w-0 flex-1 items-center space-x-3">
                <div className="flex-shrink-0 text-slate-500 dark:text-white/70">
                  {getRoleIcon(member.role)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="truncate font-medium text-slate-900 dark:text-slate-100">{displayName}</span>
                    {member.user_id === user?.id && (
                      <span className="text-xs text-slate-500 dark:text-white/70">(You)</span>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-300">
                    <span className="truncate">{member.email}</span>
                    <span className={clsx('rounded-full px-2 py-0.5 font-medium capitalize', getRoleBadgeClasses(member.role))}>
                      {normalizedRole}
                    </span>
                    <span className="flex items-center gap-1">
                      {getStatusIcon(member.status)}
                      <span className="capitalize">{member.status}</span>
                    </span>
                    {member.joined_at && (
                      <span className="text-slate-400 dark:text-slate-400/80">Joined {new Date(member.joined_at).toLocaleDateString()}</span>
                    )}
                    {member.is_owner && <span className="text-slate-600 dark:text-white/80">Owner</span>}
                  </div>
                </div>
              </div>

              {canManageTeam && !member.is_owner ? (
                <div className="ml-3 flex items-center gap-2 text-xs">
                  <select
                    className="rounded border border-gray-300 bg-white px-2 py-1 text-slate-700 transition-colors dark:border-white/20 dark:bg-white/10 dark:text-slate-100"
                    value={normalizedRole}
                    onChange={(e) => handleRoleChange(member, e.target.value)}
                    disabled={Boolean(updatingMemberId) || Boolean(removingMemberId)}
                  >
                    <option value="admin">Admin</option>
                    <option value="editor">Editor</option>
                    <option value="viewer">Viewer</option>
                  </select>
                  <button
                    className="p-1 text-rose-500 transition-colors hover:text-rose-600 dark:text-rose-200 dark:hover:text-rose-100"
                    onClick={() => handleRemoveMember(member)}
                    disabled={Boolean(updatingMemberId) || Boolean(removingMemberId)}
                    title="Remove member"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ) : null}
            </div>
          )
        })}
      </div>

      {members.length === 0 && !error && (
        <div className="py-8 text-center text-sm text-slate-500 dark:text-slate-300">
          <Users className="mx-auto mb-3 h-10 w-10 text-slate-300 dark:text-white/40" />
          <p>No team members yet.</p>
          {!isProjectScope && onInviteMember && (
            <button
              onClick={onInviteMember}
              className="mt-3 inline-flex items-center rounded-full border border-indigo-200 px-3 py-1 text-xs font-medium text-indigo-600 transition-colors hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
            >
              Invite your first collaborator
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export default TeamMembersList
