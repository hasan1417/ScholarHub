import React, { useMemo, useState } from 'react'
import { Users, Shield, Edit, Eye, Trash2, Settings, Crown, Clock, ChevronDown, X } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'

import { useProjectContext } from '../../pages/projects/ProjectLayout'
import { useAuth } from '../../contexts/AuthContext'
import { projectsAPI } from '../../services/api'
import TeamInviteModal from '../team/TeamInviteModal'

type RoleOption = 'admin' | 'editor' | 'viewer'

const normalizeRole = (role?: string | null): RoleOption => {
  const value = (role || '').toLowerCase()
  if (value === 'admin' || value === 'editor' || value === 'viewer') {
    return value as RoleOption
  }
  return 'viewer'
}

const rolePillClasses: Record<RoleOption, string> = {
  admin: 'bg-purple-100 text-purple-800 dark:bg-purple-500/20 dark:text-purple-100',
  editor: 'bg-green-100 text-green-800 dark:bg-emerald-500/20 dark:text-emerald-100',
  viewer: 'bg-gray-100 text-gray-800 dark:bg-slate-600/30 dark:text-slate-100',
}

const roleIcon = (role: RoleOption) => {
  switch (role) {
    case 'admin':
      return <Shield className="h-4 w-4 text-purple-600 dark:text-purple-300" />
    case 'editor':
      return <Edit className="h-4 w-4 text-green-600 dark:text-emerald-300" />
    default:
      return <Eye className="h-4 w-4 text-gray-500 dark:text-slate-300" />
  }
}

const ProjectTeamManager: React.FC = () => {
  const { project } = useProjectContext()
  const { user } = useAuth()
  const queryClient = useQueryClient()

  const [inviteOpen, setInviteOpen] = useState(false)
  const [activeMemberId, setActiveMemberId] = useState<string | null>(null)
  const [globalError, setGlobalError] = useState<string | null>(null)
  const [isManaging, setIsManaging] = useState<boolean>(false)
  const [membersModalOpen, setMembersModalOpen] = useState(false)
  const VISIBLE_MEMBERS_COUNT = 4

  const stringifyDetail = (detail: unknown): string => {
    if (!detail) return 'Unknown error'
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((item) => (item && typeof item === 'object' && 'msg' in item ? String((item as any).msg) : JSON.stringify(item)))
        .join('\n')
    }
    if (typeof detail === 'object' && 'msg' in (detail as any)) {
      return String((detail as any).msg)
    }
    try {
      return JSON.stringify(detail)
    } catch {
      return String(detail)
    }
  }

  const members = project.members ?? []
  const currentUserId = user?.id
  const isProjectOwner = project.created_by === currentUserId
  const membership = members.find((member) => member.user_id === currentUserId)
  const membershipStatus = membership?.status?.toLowerCase()
  const isMembershipAccepted = membershipStatus === 'accepted'
  const myRole: RoleOption = isProjectOwner ? 'admin' : normalizeRole(membership?.role)
  const canManageTeam = isMembershipAccepted && myRole === 'admin'
  const canAssignAdmin = isProjectOwner

  const sortedMembers = useMemo(() => {
    const priority: Record<RoleOption, number> = { admin: 0, editor: 1, viewer: 2 }
    return [...members].sort((a, b) => {
      const roleA = a.user_id === project.created_by ? 'admin' : normalizeRole(a.role)
      const roleB = b.user_id === project.created_by ? 'admin' : normalizeRole(b.role)
      if (priority[roleA] === priority[roleB]) {
        return (a.user?.email || '').localeCompare(b.user?.email || '')
      }
      return priority[roleA] - priority[roleB]
    })
  }, [members, project.created_by])

  // In manage mode, show all members inline; otherwise show limited
  const visibleMembers = isManaging
    ? sortedMembers
    : sortedMembers.slice(0, VISIBLE_MEMBERS_COUNT)
  const hasMoreMembers = sortedMembers.length > VISIBLE_MEMBERS_COUNT

  const invalidateProject = async () => {
    await queryClient.invalidateQueries({ queryKey: ['project', project.id] })
  }

  const handleInvite = async (email: string, role: string) => {
    if (!canManageTeam) {
      const error = new Error('Not authorized to invite members for this project.')
      setGlobalError(error.message)
      throw error
    }

    const normalized = normalizeRole(role)
    if (normalized === 'admin' && !canAssignAdmin) {
      const error = new Error('Only the creator can assign the admin role.')
      setGlobalError(error.message)
      throw error
    }

    try {
      setGlobalError(null)
      console.debug('Inviting project member by email', { projectId: project.id, email, role: normalized })

      // Use the new inviteByEmail endpoint that handles both registered and unregistered users
      const response = await projectsAPI.inviteByEmail(project.id, {
        email: email.trim(),
        role: normalized,
      })

      console.debug('Invite response:', response.data)
      await invalidateProject()
    } catch (error: any) {
      const detail = error?.response?.data?.detail
      if (detail) {
        console.error('Project invite failed', detail)
      } else {
        console.error('Project invite failed', error)
      }
      if (detail) {
        setGlobalError(stringifyDetail(detail))
      } else if (error instanceof Error) {
        setGlobalError(error.message)
      }
      throw error
    }
  }

  const handleRoleChange = async (memberId: string, role: RoleOption) => {
    if (!canManageTeam) return
    const current = members.find((member) => member.id === memberId)
    if (!current) return
    if (current.user_id === project.created_by) {
      return
    }
    if (normalizeRole(current.role) === role) {
      return
    }
    if (role === 'admin' && !canAssignAdmin) {
      alert('Only the owner can assign the admin role.')
      return
    }
    setActiveMemberId(memberId)
    try {
      await projectsAPI.updateMember(project.id, memberId, { role })
      await invalidateProject()
    } catch (error: any) {
      const detail = error?.response?.data?.detail
      if (detail) {
        alert(detail)
      } else {
        alert('Unable to update member role right now.')
      }
    } finally {
      setActiveMemberId(null)
    }
  }

  const handleRemove = async (memberId: string, email?: string | null) => {
    if (!canManageTeam) return
    const confirmed = window.confirm(`Remove ${email || 'this member'} from the project?`)
    if (!confirmed) return
    setActiveMemberId(memberId)
    try {
      await projectsAPI.removeMember(project.id, memberId)
      await invalidateProject()
    } catch (error: any) {
      const detail = error?.response?.data?.detail
      if (detail) {
        alert(detail)
      } else {
        alert('Unable to remove this member right now.')
      }
    } finally {
      setActiveMemberId(null)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
          <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">Team</h2>
        </div>
        {canManageTeam && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setInviteOpen(true)}
              className="inline-flex items-center rounded-full border border-indigo-200 px-3 py-1.5 text-xs font-medium text-indigo-600 transition-colors hover:bg-indigo-50 dark:border-indigo-400/40 dark:text-indigo-200 dark:hover:bg-indigo-500/10"
            >
              Invite member
            </button>
            <button
              type="button"
              onClick={() => setIsManaging((prev) => !prev)}
              className="inline-flex items-center gap-1 rounded-full border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-100 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              {!isManaging && <Settings className="h-3.5 w-3.5" />}
              {isManaging ? 'Done' : 'Manage'}
            </button>
          </div>
        )}
      </div>

      {globalError && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-200">
          {globalError}
        </div>
      )}

      <ul className="mt-4 space-y-3">
        {sortedMembers.length === 0 ? (
          <li className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-500 dark:border-slate-600 dark:bg-slate-800/50 dark:text-slate-400">
            No collaborators yet.
          </li>
        ) : (
          visibleMembers.map((member) => {
            const isProjectOwnerMember = member.user_id === project.created_by
            const effectiveRole: RoleOption = normalizeRole(member.role)
            const status = (member.status || 'accepted').toLowerCase()
            const isPending = status === 'invited'
            const isDeclined = status === 'declined'
            const isSelf = member.user_id === currentUserId
            const disableRoleSelect =
              !canManageTeam ||
              isProjectOwnerMember ||
              isPending ||
              (!canAssignAdmin && effectiveRole === 'admin')
            const disableRemove = !canManageTeam || isProjectOwnerMember || isSelf
            const displayName = member.user?.display_name
              || [member.user?.first_name, member.user?.last_name].filter(Boolean).join(' ').trim()
              || member.user?.email
              || member.user_id

            return (
              <li
                key={member.id}
                className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3 shadow-sm transition-colors sm:flex-row sm:items-center sm:justify-between dark:border-slate-700 dark:bg-slate-800/60"
              >
                <div className="flex items-start gap-3">
                  <div className="mt-1 flex h-8 w-8 items-center justify-center rounded-full bg-gray-100 dark:bg-slate-700">
                    {roleIcon(effectiveRole)}
                  </div>
                  <div className="min-w-0">
                    <p className="flex items-center gap-2 truncate text-sm font-semibold text-gray-900 dark:text-slate-100">
                      <span className="truncate">{displayName}</span>
                      {isSelf && (
                        <span className="text-[10px] uppercase tracking-wide text-indigo-500 dark:text-indigo-300">You</span>
                      )}
                    </p>
                    {member.user?.email && (
                      <p className="truncate text-xs text-gray-500 dark:text-slate-400">{member.user.email}</p>
                    )}
                    {status !== 'accepted' && (
                      <p
                        className={`mt-1 text-xs ${
                          isPending
                            ? 'text-amber-600'
                            : isDeclined
                            ? 'text-red-600'
                            : 'text-gray-500'
                        }`}
                      >
                        Status: {status}
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:gap-3">
                  <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${rolePillClasses[effectiveRole]}`}>
                    {roleIcon(effectiveRole)}
                    <span className="capitalize">{effectiveRole}</span>
                    {isProjectOwnerMember && (
                      <Crown className="h-3 w-3 text-yellow-500 dark:text-yellow-300" aria-label="Project creator" />
                    )}
                    {isPending && (
                      <Clock className="h-3 w-3 text-amber-500 dark:text-amber-300" aria-label="Invitation pending" />
                    )}
                  </span>

                  {canManageTeam && isManaging && (
                    <div className="flex items-center gap-2">
                      <select
                        className="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 transition-colors dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100"
                        value={effectiveRole}
                        disabled={disableRoleSelect || Boolean(activeMemberId)}
                        onChange={(event) => handleRoleChange(member.id, event.target.value as RoleOption)}
                      >
                        <option value="admin" disabled={!canAssignAdmin}>
                          Admin
                        </option>
                        <option value="editor">Editor</option>
                        <option value="viewer">Viewer</option>
                      </select>
                      <button
                        type="button"
                        onClick={() => handleRemove(member.id, member.user?.email)}
                        disabled={disableRemove || Boolean(activeMemberId)}
                        className="inline-flex items-center rounded-md p-1 text-gray-400 transition-colors hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-50 dark:text-slate-400 dark:hover:text-red-400"
                        title={disableRemove ? 'You cannot remove this member' : 'Remove member'}
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

      {hasMoreMembers && !isManaging && (
        <button
          onClick={() => setMembersModalOpen(true)}
          className="mt-3 flex items-center gap-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 transition-colors w-full justify-center"
        >
          <ChevronDown className="h-3.5 w-3.5" />
          View all {sortedMembers.length} members
        </button>
      )}

      {canManageTeam && (
        <TeamInviteModal
          isOpen={inviteOpen}
          onClose={() => setInviteOpen(false)}
          onInvite={handleInvite}
          paperTitle={project.title}
        />
      )}

      {/* All Members Modal */}
      {membersModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setMembersModalOpen(false)}
          />
          <div className="relative z-10 w-full max-w-lg mx-4 max-h-[80vh] flex flex-col rounded-2xl border border-gray-200 bg-white shadow-xl dark:border-slate-700 dark:bg-slate-800">
            {/* Header */}
            <div className="flex items-center justify-between p-5 border-b border-gray-200 dark:border-slate-700">
              <div className="flex items-center gap-2">
                <Users className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
                <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100">
                  Team Members ({sortedMembers.length})
                </h2>
              </div>
              <button
                onClick={() => setMembersModalOpen(false)}
                className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-slate-200 dark:hover:bg-slate-700 transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-5">
              <ul className="space-y-3">
                {sortedMembers.map((member) => {
                  const isProjectOwnerMember = member.user_id === project.created_by
                  const effectiveRole: RoleOption = normalizeRole(member.role)
                  const status = (member.status || 'accepted').toLowerCase()
                  const isPending = status === 'invited'
                  const isSelf = member.user_id === currentUserId
                  const displayName = member.user?.display_name
                    || [member.user?.first_name, member.user?.last_name].filter(Boolean).join(' ').trim()
                    || member.user?.email
                    || member.user_id

                  return (
                    <li
                      key={`modal-${member.id}`}
                      className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-800/60"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-100 dark:bg-slate-700 flex-shrink-0">
                          {roleIcon(effectiveRole)}
                        </div>
                        <div className="min-w-0">
                          <p className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-slate-100">
                            <span className="truncate">{displayName}</span>
                            {isSelf && (
                              <span className="text-[10px] uppercase tracking-wide text-indigo-500 dark:text-indigo-300">You</span>
                            )}
                          </p>
                          {member.user?.email && (
                            <p className="truncate text-xs text-gray-500 dark:text-slate-400">{member.user.email}</p>
                          )}
                        </div>
                      </div>
                      <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium flex-shrink-0 ${rolePillClasses[effectiveRole]}`}>
                        {roleIcon(effectiveRole)}
                        <span className="capitalize">{effectiveRole}</span>
                        {isProjectOwnerMember && (
                          <Crown className="h-3 w-3 text-yellow-500 dark:text-yellow-300" />
                        )}
                        {isPending && (
                          <Clock className="h-3 w-3 text-amber-500 dark:text-amber-300" />
                        )}
                      </span>
                    </li>
                  )
                })}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ProjectTeamManager
