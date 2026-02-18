import React, { useState, useEffect, useMemo, useRef } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { usersAPI, subscriptionAPI } from '../../services/api'
import {
  User,
  Mail,
  Lock,
  Eye,
  EyeOff,
  Calendar,
  CheckCircle,
  AlertCircle,
  Loader2,
  Save,
  Key,
  Camera,
  Trash2,
  UserCircle,
  Info,
  Check,
  Plug,
} from 'lucide-react'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const EditProfile = () => {
  const { user, updateUser } = useAuth()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: ''
  })
  const [passwordData, setPasswordData] = useState({
    current_password: '',
    new_password: '',
    confirm_password: ''
  })
  const [isLoading, setIsLoading] = useState(false)
  const [isPasswordLoading, setIsPasswordLoading] = useState(false)
  const [isAvatarLoading, setIsAvatarLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [showCurrentPassword, setShowCurrentPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [subscriptionTier, setSubscriptionTier] = useState<string>('free')

  // Integrations state
  const [openRouterKey, setOpenRouterKey] = useState('')
  const [openRouterKeyMasked, setOpenRouterKeyMasked] = useState<string | null>(null)
  const [openRouterKeyConfigured, setOpenRouterKeyConfigured] = useState(false)
  const [showOpenRouterKey, setShowOpenRouterKey] = useState(false)
  const [savingApiKey, setSavingApiKey] = useState(false)
  const [apiKeySaved, setApiKeySaved] = useState(false)
  const [zoteroApiKey, setZoteroApiKey] = useState('')
  const [zoteroUserId, setZoteroUserId] = useState('')
  const [zoteroConfigured, setZoteroConfigured] = useState(false)
  const [zoteroMaskedKey, setZoteroMaskedKey] = useState<string | null>(null)
  const [savingZotero, setSavingZotero] = useState(false)
  const [zoteroSaved, setZoteroSaved] = useState(false)

  // Fetch subscription tier
  useEffect(() => {
    const fetchSubscription = async () => {
      try {
        const res = await subscriptionAPI.getMySubscription()
        setSubscriptionTier(res.data?.subscription?.tier_id || 'free')
      } catch {
        setSubscriptionTier('free')
      }
    }
    fetchSubscription()
  }, [])

  // Load API keys
  useEffect(() => {
    usersAPI.getApiKeys().then((res) => {
      setOpenRouterKeyConfigured(res.data.openrouter.configured)
      setOpenRouterKeyMasked(res.data.openrouter.masked_key)
      setZoteroConfigured(res.data.zotero.configured)
      setZoteroMaskedKey(res.data.zotero.masked_key)
      setZoteroUserId(res.data.zotero.user_id || '')
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (user) {
      setFormData({
        first_name: user.first_name || '',
        last_name: user.last_name || ''
      })
    }
  }, [user])

  // Password strength calculation
  const passwordStrength = useMemo(() => {
    const password = passwordData.new_password
    if (!password) return { score: 0, label: '', color: '' }

    let score = 0
    if (password.length >= 8) score++
    if (password.length >= 12) score++
    if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score++
    if (/\d/.test(password)) score++
    if (/[^a-zA-Z0-9]/.test(password)) score++

    if (score <= 1) return { score: 1, label: 'Weak', color: 'bg-red-500' }
    if (score <= 2) return { score: 2, label: 'Fair', color: 'bg-orange-500' }
    if (score <= 3) return { score: 3, label: 'Good', color: 'bg-yellow-500' }
    if (score <= 4) return { score: 4, label: 'Strong', color: 'bg-emerald-500' }
    return { score: 5, label: 'Very Strong', color: 'bg-green-500' }
  }, [passwordData.new_password])

  const handleProfileUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError('')
    setMessage('')

    try {
      await usersAPI.updateUser(user!.id, formData)
      updateUser({ ...user!, ...formData })
      setMessage('Profile updated successfully!')
      setTimeout(() => setMessage(''), 3000)
    } catch (error: any) {
      setError(error.response?.data?.detail || 'Failed to update profile')
    } finally {
      setIsLoading(false)
    }
  }

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault()

    if (passwordData.new_password !== passwordData.confirm_password) {
      setError('New passwords do not match')
      return
    }

    if (passwordData.new_password.length < 8) {
      setError('New password must be at least 8 characters long')
      return
    }

    setIsPasswordLoading(true)
    setError('')
    setMessage('')

    try {
      await usersAPI.changePassword({
        current_password: passwordData.current_password,
        new_password: passwordData.new_password
      })
      setMessage('Password changed successfully!')
      setPasswordData({
        current_password: '',
        new_password: '',
        confirm_password: ''
      })
      setTimeout(() => setMessage(''), 3000)
    } catch (error: any) {
      setError(error.response?.data?.detail || 'Failed to change password')
    } finally {
      setIsPasswordLoading(false)
    }
  }

  const handleAvatarUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Validate file type
    if (!['image/jpeg', 'image/png', 'image/gif', 'image/webp'].includes(file.type)) {
      setError('Invalid file type. Please upload JPEG, PNG, GIF, or WebP.')
      return
    }

    // Validate file size (5MB)
    if (file.size > 5 * 1024 * 1024) {
      setError('File too large. Maximum size is 5MB.')
      return
    }

    setIsAvatarLoading(true)
    setError('')

    try {
      const response = await usersAPI.uploadAvatar(file)
      updateUser({ ...user!, avatar_url: response.data.avatar_url })
      setMessage('Avatar updated successfully!')
      setTimeout(() => setMessage(''), 3000)
    } catch (error: any) {
      setError(error.response?.data?.detail || 'Failed to upload avatar')
    } finally {
      setIsAvatarLoading(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleAvatarDelete = async () => {
    if (!user?.avatar_url) return

    setIsAvatarLoading(true)
    setError('')

    try {
      await usersAPI.deleteAvatar()
      updateUser({ ...user!, avatar_url: undefined })
      setMessage('Avatar removed successfully!')
      setTimeout(() => setMessage(''), 3000)
    } catch (error: any) {
      setError(error.response?.data?.detail || 'Failed to remove avatar')
    } finally {
      setIsAvatarLoading(false)
    }
  }

  const handleSaveOpenRouterKey = async () => {
    setSavingApiKey(true)
    setApiKeySaved(false)
    try {
      const res = await usersAPI.setOpenRouterKey(openRouterKey || null)
      setOpenRouterKeyConfigured(res.data.configured)
      setOpenRouterKeyMasked(openRouterKey ? `sk-or-...${openRouterKey.slice(-4)}` : null)
      setOpenRouterKey('')
      setApiKeySaved(true)
      setTimeout(() => setApiKeySaved(false), 2000)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to save API key')
      setTimeout(() => setError(''), 3000)
    } finally {
      setSavingApiKey(false)
    }
  }

  const handleSaveZoteroKey = async () => {
    setSavingZotero(true)
    setZoteroSaved(false)
    try {
      const res = await usersAPI.setZoteroKey(zoteroApiKey || null, zoteroUserId || null)
      setZoteroConfigured(res.data.configured)
      if (zoteroApiKey) setZoteroMaskedKey(`...${zoteroApiKey.slice(-4)}`)
      setZoteroApiKey('')
      setZoteroSaved(true)
      setTimeout(() => setZoteroSaved(false), 2000)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to save Zotero credentials')
      setTimeout(() => setError(''), 3000)
    } finally {
      setSavingZotero(false)
    }
  }

  const getInitials = () => {
    const first = formData.first_name?.charAt(0) || user?.email?.charAt(0) || '?'
    const last = formData.last_name?.charAt(0) || ''
    return (first + last).toUpperCase()
  }

  const getAvatarUrl = () => {
    if (!user?.avatar_url) return null
    if (user.avatar_url.startsWith('http')) return user.avatar_url
    return `${API_BASE_URL}${user.avatar_url}`
  }

  if (!user) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    )
  }

  const avatarUrl = getAvatarUrl()

  return (
    <div className="max-w-5xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
      {/* Header with Avatar */}
      <div className="mb-8">
        <div className="flex items-center gap-6">
          <div className="relative group">
            {/* Avatar */}
            {avatarUrl ? (
              <img
                src={avatarUrl}
                alt="Profile"
                className="h-24 w-24 rounded-full object-cover shadow-lg ring-4 ring-white dark:ring-gray-800"
              />
            ) : (
              <div className="h-24 w-24 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-3xl font-semibold shadow-lg ring-4 ring-white dark:ring-gray-800">
                {getInitials()}
              </div>
            )}

            {/* Upload overlay */}
            <div className="absolute inset-0 rounded-full bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
              {isAvatarLoading ? (
                <Loader2 className="h-6 w-6 text-white animate-spin" />
              ) : (
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="p-2 text-white hover:scale-110 transition-transform"
                  title="Upload photo"
                >
                  <Camera className="h-6 w-6" />
                </button>
              )}
            </div>

            {/* Verified badge */}
            <div className="absolute -bottom-1 -right-1 h-7 w-7 rounded-full bg-emerald-500 border-3 border-white dark:border-gray-800 flex items-center justify-center shadow-sm">
              <CheckCircle className="h-4 w-4 text-white" />
            </div>

            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/gif,image/webp"
              onChange={handleAvatarUpload}
              className="hidden"
            />
          </div>

          <div className="flex-1">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {formData.first_name || formData.last_name
                ? `${formData.first_name} ${formData.last_name}`.trim()
                : 'Your Profile'}
            </h1>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Manage your account settings and preferences
            </p>

            {/* Avatar actions */}
            <div className="mt-3 flex items-center gap-2">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isAvatarLoading}
                className="inline-flex items-center gap-1.5 text-sm font-medium text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300 disabled:opacity-50"
              >
                <Camera className="h-4 w-4" />
                {avatarUrl ? 'Change photo' : 'Upload photo'}
              </button>
              {avatarUrl && (
                <>
                  <span className="text-gray-300 dark:text-gray-600">|</span>
                  <button
                    type="button"
                    onClick={handleAvatarDelete}
                    disabled={isAvatarLoading}
                    className="inline-flex items-center gap-1.5 text-sm font-medium text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" />
                    Remove
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Messages */}
      {message && (
        <div className="mb-6 flex items-center gap-2 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 px-4 py-3 rounded-lg">
          <CheckCircle className="h-5 w-5 flex-shrink-0" />
          <span>{message}</span>
        </div>
      )}

      {error && (
        <div className="mb-6 flex items-center gap-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg">
          <AlertCircle className="h-5 w-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Profile & Password */}
        <div className="lg:col-span-2 space-y-6">
          {/* Profile Information Form */}
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-indigo-100 dark:bg-indigo-900/30">
                  <User className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Profile Information</h2>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Update your personal details</p>
                </div>
              </div>
            </div>

            <form onSubmit={handleProfileUpdate} className="p-6 space-y-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="first_name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                    First Name
                  </label>
                  <input
                    id="first_name"
                    type="text"
                    value={formData.first_name}
                    onChange={(e) => setFormData(prev => ({ ...prev, first_name: e.target.value }))}
                    className="w-full px-3.5 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                    placeholder="Enter your first name"
                  />
                </div>

                <div>
                  <label htmlFor="last_name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                    Last Name
                  </label>
                  <input
                    id="last_name"
                    type="text"
                    value={formData.last_name}
                    onChange={(e) => setFormData(prev => ({ ...prev, last_name: e.target.value }))}
                    className="w-full px-3.5 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                    placeholder="Enter your last name"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Email Address
                </label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <input
                    id="email"
                    type="email"
                    value={user.email}
                    disabled
                    className="w-full pl-10 pr-3.5 py-2.5 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-900/50 text-gray-500 dark:text-gray-400 cursor-not-allowed"
                  />
                </div>
                <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
                  <Lock className="h-3 w-3" />
                  Email cannot be changed
                </p>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  disabled={isLoading}
                  className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 text-white font-medium py-2.5 px-5 rounded-lg transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className="h-4 w-4" />
                      Save Changes
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>

          {/* Password Change Form */}
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-900/30">
                  <Key className="h-5 w-5 text-amber-600 dark:text-amber-400" />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Security</h2>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Update your password</p>
                </div>
              </div>
            </div>

            <form onSubmit={handlePasswordChange} className="p-6 space-y-5">
              <div>
                <label htmlFor="current_password" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Current Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <input
                    id="current_password"
                    type={showCurrentPassword ? 'text' : 'password'}
                    value={passwordData.current_password}
                    onChange={(e) => setPasswordData(prev => ({ ...prev, current_password: e.target.value }))}
                    className="w-full pl-10 pr-10 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                    placeholder="Enter current password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                  >
                    {showCurrentPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <div>
                <label htmlFor="new_password" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  New Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <input
                    id="new_password"
                    type={showNewPassword ? 'text' : 'password'}
                    value={passwordData.new_password}
                    onChange={(e) => setPasswordData(prev => ({ ...prev, new_password: e.target.value }))}
                    className="w-full pl-10 pr-10 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                    placeholder="Enter new password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                  >
                    {showNewPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>

                {/* Password Strength Indicator */}
                {passwordData.new_password && (
                  <div className="mt-2 space-y-1.5">
                    <div className="flex gap-1">
                      {[1, 2, 3, 4, 5].map((level) => (
                        <div
                          key={level}
                          className={`h-1 flex-1 rounded-full transition-colors ${
                            level <= passwordStrength.score
                              ? passwordStrength.color
                              : 'bg-gray-200 dark:bg-gray-700'
                          }`}
                        />
                      ))}
                    </div>
                    <p className={`text-xs ${
                      passwordStrength.score <= 2 ? 'text-red-600 dark:text-red-400' :
                      passwordStrength.score <= 3 ? 'text-yellow-600 dark:text-yellow-400' :
                      'text-emerald-600 dark:text-emerald-400'
                    }`}>
                      Password strength: {passwordStrength.label}
                    </p>
                  </div>
                )}
              </div>

              <div>
                <label htmlFor="confirm_password" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                  Confirm New Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <input
                    id="confirm_password"
                    type={showConfirmPassword ? 'text' : 'password'}
                    value={passwordData.confirm_password}
                    onChange={(e) => setPasswordData(prev => ({ ...prev, confirm_password: e.target.value }))}
                    className={`w-full pl-10 pr-10 py-2.5 border rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all ${
                      passwordData.confirm_password && passwordData.confirm_password !== passwordData.new_password
                        ? 'border-red-300 dark:border-red-600'
                        : passwordData.confirm_password && passwordData.confirm_password === passwordData.new_password
                        ? 'border-emerald-300 dark:border-emerald-600'
                        : 'border-gray-300 dark:border-gray-600'
                    }`}
                    placeholder="Confirm new password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                  >
                    {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                {passwordData.confirm_password && passwordData.confirm_password !== passwordData.new_password && (
                  <p className="mt-1.5 text-xs text-red-600 dark:text-red-400">Passwords do not match</p>
                )}
                {passwordData.confirm_password && passwordData.confirm_password === passwordData.new_password && (
                  <p className="mt-1.5 text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                    <CheckCircle className="h-3 w-3" />
                    Passwords match
                  </p>
                )}
              </div>

              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  disabled={isPasswordLoading || !passwordData.current_password || !passwordData.new_password || passwordData.new_password !== passwordData.confirm_password}
                  className="inline-flex items-center gap-2 bg-amber-600 hover:bg-amber-700 dark:bg-amber-500 dark:hover:bg-amber-600 text-white font-medium py-2.5 px-5 rounded-lg transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                >
                  {isPasswordLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Updating...
                    </>
                  ) : (
                    <>
                      <Key className="h-4 w-4" />
                      Update Password
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>

        </div>

        {/* Right Column - Account Info */}
        <div className="space-y-6">
          {/* Account Information */}
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30">
                  <Info className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Account</h2>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Account details</p>
                </div>
              </div>
            </div>

            <div className="p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Calendar className="h-4 w-4 text-gray-400" />
                  <span className="text-sm text-gray-600 dark:text-gray-400">Created</span>
                </div>
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {new Date(user.created_at).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric'
                  })}
                </span>
              </div>

              <div className="h-px bg-gray-100 dark:bg-gray-700" />

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Calendar className="h-4 w-4 text-gray-400" />
                  <span className="text-sm text-gray-600 dark:text-gray-400">Updated</span>
                </div>
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {new Date(user.updated_at).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric'
                  })}
                </span>
              </div>

              <div className="h-px bg-gray-100 dark:bg-gray-700" />

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <UserCircle className="h-4 w-4 text-gray-400" />
                  <span className="text-sm text-gray-600 dark:text-gray-400">Status</span>
                </div>
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                  user.is_active
                    ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'
                    : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                }`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${user.is_active ? 'bg-emerald-500' : 'bg-red-500'}`} />
                  {user.is_active ? 'Active' : 'Inactive'}
                </span>
              </div>
            </div>
          </div>

          {/* Quick Stats */}
          <div className="bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl shadow-sm p-6 text-white">
            <h3 className="text-sm font-medium text-indigo-100 mb-4">Account Summary</h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-indigo-100">Email verified</span>
                <CheckCircle className="h-4 w-4 text-emerald-300" />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-indigo-100">Account type</span>
                <span className={`text-sm font-medium ${
                  subscriptionTier === 'pro' ? 'text-amber-300' :
                  subscriptionTier === 'byok' ? 'text-emerald-300' : ''
                }`}>
                  {subscriptionTier === 'pro' ? 'Pro' : subscriptionTier === 'byok' ? 'BYOK' : 'Free'}
                </span>
              </div>
            </div>
          </div>

          {/* Integrations */}
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-emerald-100 dark:bg-emerald-900/30">
                  <Plug className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Integrations</h2>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Connect external services</p>
                </div>
              </div>
            </div>

            <div className="p-5 space-y-5">
              {/* OpenRouter */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">OpenRouter</label>
                  {openRouterKeyConfigured && (
                    <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                      <CheckCircle className="h-3 w-3" />
                      Connected
                    </span>
                  )}
                </div>
                <div className="relative">
                  <input
                    type={showOpenRouterKey ? 'text' : 'password'}
                    value={openRouterKey}
                    onChange={(e) => setOpenRouterKey(e.target.value)}
                    placeholder={openRouterKeyMasked || 'sk-or-...'}
                    className="w-full px-3 py-2 pr-9 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowOpenRouterKey(!showOpenRouterKey)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                  >
                    {showOpenRouterKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </button>
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer" className="text-xs text-indigo-600 hover:underline dark:text-indigo-400">
                    Get a key
                  </a>
                  <div className="flex items-center gap-2">
                    {openRouterKeyConfigured && (
                      <button
                        type="button"
                        onClick={async () => {
                          setSavingApiKey(true)
                          try {
                            await usersAPI.setOpenRouterKey(null)
                            setOpenRouterKeyConfigured(false)
                            setOpenRouterKeyMasked(null)
                            setOpenRouterKey('')
                          } catch (err: any) {
                            setError(err?.response?.data?.detail || 'Failed to remove key')
                            setTimeout(() => setError(''), 3000)
                          } finally {
                            setSavingApiKey(false)
                          }
                        }}
                        disabled={savingApiKey}
                        className="inline-flex items-center gap-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-medium py-1.5 px-3 rounded-lg text-xs transition-colors"
                      >
                        Remove
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={handleSaveOpenRouterKey}
                      disabled={savingApiKey}
                      className="inline-flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-medium py-1.5 px-3 rounded-lg text-xs transition-colors"
                    >
                      {savingApiKey ? <Loader2 className="h-3 w-3 animate-spin" /> : apiKeySaved ? <Check className="h-3 w-3" /> : null}
                      {savingApiKey ? 'Validating...' : apiKeySaved ? 'Saved' : 'Save'}
                    </button>
                  </div>
                </div>
              </div>

              <div className="h-px bg-gray-100 dark:bg-gray-700" />

              {/* Zotero */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Zotero</label>
                  {zoteroConfigured && (
                    <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                      <CheckCircle className="h-3 w-3" />
                      Connected
                    </span>
                  )}
                </div>
                <div className="space-y-2">
                  <input
                    type="password"
                    value={zoteroApiKey}
                    onChange={(e) => setZoteroApiKey(e.target.value)}
                    placeholder={zoteroMaskedKey || 'API key'}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                  />
                  <input
                    type="text"
                    value={zoteroUserId}
                    onChange={(e) => setZoteroUserId(e.target.value)}
                    placeholder="User ID (numeric)"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                  />
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <a href="https://www.zotero.org/settings/keys" target="_blank" rel="noopener noreferrer" className="text-xs text-indigo-600 hover:underline dark:text-indigo-400">
                    Get API key & user ID
                  </a>
                  <div className="flex items-center gap-2">
                    {zoteroConfigured && (
                      <button
                        type="button"
                        onClick={async () => {
                          setSavingZotero(true)
                          try {
                            await usersAPI.setZoteroKey(null, null)
                            setZoteroConfigured(false)
                            setZoteroMaskedKey(null)
                            setZoteroApiKey('')
                            setZoteroUserId('')
                          } catch (err: any) {
                            setError(err?.response?.data?.detail || 'Failed to remove Zotero credentials')
                            setTimeout(() => setError(''), 3000)
                          } finally {
                            setSavingZotero(false)
                          }
                        }}
                        disabled={savingZotero}
                        className="inline-flex items-center gap-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-medium py-1.5 px-3 rounded-lg text-xs transition-colors"
                      >
                        Remove
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={handleSaveZoteroKey}
                      disabled={savingZotero || (!zoteroApiKey && !zoteroUserId)}
                      className="inline-flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-medium py-1.5 px-3 rounded-lg text-xs transition-colors"
                    >
                      {savingZotero ? <Loader2 className="h-3 w-3 animate-spin" /> : zoteroSaved ? <Check className="h-3 w-3" /> : null}
                      {savingZotero ? 'Validating...' : zoteroSaved ? 'Saved' : 'Save'}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default EditProfile
