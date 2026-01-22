import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Users, Shield, Edit, Eye, Trash2, Clock } from 'lucide-react'
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

type RoleOption = 'admin' | 'editor' | 'viewer'

const rolePillClasses: Record<RoleOption, string> = {
  admin: 'bg-purple-100 text-purple-800 dark:bg-purple-500/20 dark:text-purple-100',
  editor: 'bg-green-100 text-green-800 dark:bg-emerald-500/20 dark:text-emerald-100',
  viewer: 'bg-gray-100 text-gray-800 dark:bg-slate-600/30 dark:text-slate-100',
}

const roleIconBgClasses: Record<RoleOption, string> = {
  admin: 'bg-purple-100 dark:bg-purple-500/20',
  editor: 'bg-green-100 dark:bg-emerald-500/20',
  viewer: 'bg-gray-100 dark:bg-slate-700',
}

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

  const normalizeRole = useCallback((role: string): RoleOption => {
    const value = (role || '').toLowerCase()
    if (value === 'reviewer') return 'viewer'
    if (value === 'owner') return 'admin'
    if (value === 'admin' || value === 'editor' || value === 'viewer') {
      return value as RoleOption
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

  const getRoleIcon = useCallback((role: RoleOption) => {
    switch (role) {
      case 'admin':
        return <Shield className="h-4 w-4 text-purple-600 dark:text-purple-300" />
      case 'editor':
        return <Edit className="h-4 w-4 text-green-600 dark:text-emerald-300" />
      default:
        return <Eye className="h-4 w-4 text-gray-500 dark:text-slate-300" />
    }
  }, [])

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
          'w-full rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800/60',
          className,
        )}
      >
        <div className="animate-pulse space-y-3">
          <div className="h-6 w-1/3 rounded bg-gray-200 dark:bg-slate-700" />
          <div className="space-y-3">
            <div className="h-16 rounded-lg bg-gray-100 dark:bg-slate-700" />
            <div className="h-16 rounded-lg bg-gray-100 dark:bg-slate-700" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div
      className={clsx(
        'w-full rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800/60',
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
          <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">Team</h2>
        </div>
        {!isProjectScope && onInviteMember && (
          <button
            onClick={onInviteMember}
            className="rounded-full border border-indigo-200 px-3 py-1.5 text-xs font-medium text-indigo-600 transition-colors hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
          >
            Invite member
          </button>
        )}
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-200">
          {error}
        </div>
      )}

      <ul className="mt-4 space-y-3">
        {members.length === 0 ? (
          <li className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-500 dark:border-slate-600 dark:bg-slate-800/50 dark:text-slate-400">
            No collaborators yet.
            {!isProjectScope && onInviteMember && (
              <button
                onClick={onInviteMember}
                className="ml-2 text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300"
              >
                Invite your first collaborator
              </button>
            )}
          </li>
        ) : (
          members.map((member) => {
            const normalizedRole = normalizeRole(member.role)
            const displayName = member.first_name && member.last_name
              ? `${member.first_name} ${member.last_name}`
              : member.first_name || member.last_name || member.email
            const isSelf = member.user_id === user?.id
            const isPending = (member.status || 'accepted').toLowerCase() === 'invited'

            return (
              <li
                key={member.id}
                className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3 shadow-sm transition-colors sm:flex-row sm:items-center sm:justify-between dark:border-slate-700 dark:bg-slate-800/60"
              >
                <div className="flex items-start gap-3">
                  <div className={clsx(
                    'mt-0.5 flex h-8 w-8 items-center justify-center rounded-full',
                    roleIconBgClasses[normalizedRole]
                  )}>
                    {getRoleIcon(normalizedRole)}
                  </div>
                  <div className="min-w-0">
                    <p className="flex items-center gap-2 truncate text-sm font-semibold text-gray-900 dark:text-slate-100">
                      <span className="truncate">{displayName}</span>
                      {isSelf && (
                        <span className="text-[10px] uppercase tracking-wide text-indigo-500 dark:text-indigo-300">You</span>
                      )}
                    </p>
                    {member.email && (
                      <p className="truncate text-xs text-gray-500 dark:text-slate-400">{member.email}</p>
                    )}
                  </div>
                </div>

                <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:gap-3">
                  <span className={clsx(
                    'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium',
                    rolePillClasses[normalizedRole]
                  )}>
                    {getRoleIcon(normalizedRole)}
                    <span className="capitalize">{normalizedRole}</span>
                    {isPending && (
                      <Clock className="h-3 w-3 text-amber-500 dark:text-amber-300" aria-label="Invitation pending" />
                    )}
                  </span>

                  {canManageTeam && !member.is_owner && (
                    <div className="flex items-center gap-2">
                      <select
                        className="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 transition-colors dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100"
                        value={normalizedRole}
                        disabled={Boolean(updatingMemberId) || Boolean(removingMemberId)}
                        onChange={(e) => handleRoleChange(member, e.target.value)}
                      >
                        <option value="admin">Admin</option>
                        <option value="editor">Editor</option>
                        <option value="viewer">Viewer</option>
                      </select>
                      <button
                        type="button"
                        onClick={() => handleRemoveMember(member)}
                        disabled={Boolean(updatingMemberId) || Boolean(removingMemberId)}
                        className="inline-flex items-center rounded-md p-1 text-gray-400 transition-colors hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-50 dark:text-slate-400 dark:hover:text-red-400"
                        title="Remove member"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  )}
                </div>
              </li>
            )
          })
        )}
      </ul>
    </div>
  )
}

export default TeamMembersList
