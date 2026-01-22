import React, { useEffect, useState } from 'react'
import { X, UserPlus, Mail, Shield, Edit, Eye } from 'lucide-react'
import { usersAPI } from '../../services/api'

interface TeamInviteModalProps {
  isOpen: boolean
  onClose: () => void
  onInvite: (email: string, role: string) => Promise<void>
  paperTitle: string
}

interface RoleOption {
  value: string
  label: string
  description: string
  icon: React.ReactNode
}

const TeamInviteModal: React.FC<TeamInviteModalProps> = ({
  isOpen,
  onClose,
  onInvite,
  paperTitle
}) => {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('viewer')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lookupStatus, setLookupStatus] = useState<'idle' | 'checking' | 'found' | 'not_found'>('idle')

  const roleOptions: RoleOption[] = [
    {
      value: 'admin',
      label: 'Admin',
      description: 'Full control: manage team, edit papers, approve references',
      icon: <Shield className="w-4 h-4" />
    },
    {
      value: 'editor',
      label: 'Editor',
      description: 'Edit papers, approve/reject references, add manual citations',
      icon: <Edit className="w-4 h-4" />
    },
    {
      value: 'viewer',
      label: 'Viewer',
      description: 'Read-only access to papers and discussions',
      icon: <Eye className="w-4 h-4" />
    }
  ]

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!email.trim()) {
      setError('Please enter an email address')
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      await onInvite(email.trim(), role)
      setEmail('')
      setRole('viewer')
      onClose()
    } catch (err: any) {
      // Surface actionable backend errors
      const detail = err?.response?.data?.detail
      if (detail === 'User not found') {
        setError('No account found for this email. Ask the user to register, then try again.')
      } else if (detail === 'Not authorized to invite team members') {
        setError('You do not have permission to invite members for this paper.')
      } else if (detail === 'User is already a team member' || detail === 'User is already a member of this project') {
        setError('This user is already a member of the project.')
      } else if (detail === 'An invitation has already been sent to this email') {
        setError('An invitation has already been sent to this email.')
      } else if (detail === 'Member already exists' || detail === 'Invitation already exists') {
        setError('This person has already been invited.')
      } else if (detail === 'Invalid role for invitation') {
        setError('Select a valid role: Admin, Editor, or Viewer.')
      } else {
        setError(err.message || 'Failed to send invitation')
      }
    } finally {
      setIsLoading(false)
    }
  }

  // Debounced user lookup by email
  useEffect(() => {
    let timer: number | undefined
    const run = async () => {
      const value = email.trim()
      // Only lookup when email looks valid
      const looksValid = /[^@\s]+@[^@\s]+\.[^@\s]+/.test(value)
      if (!value || !looksValid) {
        setLookupStatus('idle')
        return
      }
      try {
        setLookupStatus('checking')
        await usersAPI.lookupByEmail(value)
        setLookupStatus('found')
      } catch (e: any) {
        if (e?.response?.status === 404) {
          setLookupStatus('not_found')
        } else if (e?.response?.status >= 500) {
          // Be quiet on server errors (keep UX smooth)
          setLookupStatus('idle')
        } else {
          setLookupStatus('idle')
        }
      }
    }
    timer = window.setTimeout(run, 400)
    return () => {
      if (timer) window.clearTimeout(timer)
    }
  }, [email])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 dark:bg-black/70">
      <div className="mx-auto max-h-[90vh] w-full max-w-md overflow-y-auto rounded-lg bg-white shadow-xl transition-colors dark:bg-slate-800 dark:text-slate-100">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 p-6 dark:border-slate-700">
          <div className="min-w-0 flex items-center space-x-3">
            <UserPlus className="h-6 w-6 flex-shrink-0 text-blue-600 dark:text-blue-300" />
            <h2 className="truncate text-xl font-semibold text-gray-900 dark:text-slate-100">Invite Team Member</h2>
          </div>
          <button
            onClick={onClose}
            className="ml-3 flex-shrink-0 text-gray-400 transition-colors hover:text-gray-600 dark:text-slate-400 dark:hover:text-slate-200"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          <p className="mb-6 break-words text-gray-600 dark:text-slate-300">
            Invite someone to collaborate on <span className="font-medium text-gray-900 dark:text-slate-100">"{paperTitle}"</span>
          </p>

          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Email Input */}
            <div>
              <label htmlFor="email" className="mb-2 block text-sm font-medium text-gray-700 dark:text-slate-200">
                Email Address
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 transform text-gray-400 dark:text-slate-400" />
                <input
                  type="email"
                  id="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-md border border-gray-300 py-3 pl-10 pr-4 focus:border-transparent focus:ring-2 focus:ring-blue-500 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100"
                  placeholder="colleague@example.com"
                  disabled={isLoading}
                />
                {lookupStatus !== 'idle' && (
                  <div className="absolute right-3 top-1/2 -translate-y-1/2 text-xs">
                    {lookupStatus === 'checking' && <span className="text-gray-400 dark:text-slate-400">Checking...</span>}
                    {lookupStatus === 'found' && <span className="text-green-600 dark:text-emerald-300">User found</span>}
                    {lookupStatus === 'not_found' && <span className="text-blue-600 dark:text-blue-400">Will invite</span>}
                  </div>
                )}
              </div>
              {lookupStatus === 'not_found' && (
                <p className="mt-1 text-xs text-blue-600 dark:text-blue-400">This email is not registered. They'll receive an invite and will be auto-enrolled when they sign up.</p>
              )}
            </div>

            {/* Role Selection */}
            <div>
              <label className="mb-3 block text-sm font-medium text-gray-700 dark:text-slate-200">
                Role
              </label>
              <div className="space-y-3">
                {roleOptions.map((option) => (
                  <label
                    key={option.value}
                    className={`flex items-start space-x-3 p-3 border rounded-lg cursor-pointer transition-colors ${
                      role === option.value
                        ? 'border-blue-500 bg-blue-50 dark:border-blue-400 dark:bg-blue-500/10'
                        : 'border-gray-200 hover:border-gray-300 dark:border-slate-600 dark:hover:border-slate-500'
                    }`}
                  >
                    <input
                      type="radio"
                      name="role"
                      value={option.value}
                      checked={role === option.value}
                      onChange={(e) => setRole(e.target.value)}
                      className="mt-1 text-blue-600 focus:ring-blue-500 dark:text-blue-400"
                      disabled={isLoading}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center space-x-2 mb-1">
                        <span className="flex-shrink-0 text-blue-600 dark:text-blue-300">{option.icon}</span>
                        <span className="truncate font-medium text-gray-900 dark:text-slate-100">{option.label}</span>
                      </div>
                      <p className="break-words text-sm text-gray-600 dark:text-slate-300">{option.description}</p>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* Error Display */}
            {error && (
              <div className="rounded-md border border-red-200 bg-red-50 p-3 dark:border-red-500/40 dark:bg-red-500/10">
                <p className="text-sm text-red-700 dark:text-red-200">{error}</p>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex space-x-3 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 rounded-md border border-gray-300 px-4 py-2 text-gray-700 transition-colors hover:bg-gray-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700"
                disabled={isLoading}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading || !email.trim()}
                className="flex-1 rounded-md bg-blue-600 px-4 py-2 text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-blue-500 dark:hover:bg-blue-400"
              >
                {isLoading ? 'Sending...' : lookupStatus === 'not_found' ? 'Send Invite Link' : 'Send Invitation'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}

export default TeamInviteModal
