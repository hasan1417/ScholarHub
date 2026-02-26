import { useState, useEffect } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import { authAPI } from '../../services/api'
import { ArrowLeft, Lock, Loader2, CheckCircle, XCircle } from 'lucide-react'
import { Logo } from '../../components/brand/Logo'

type ResetStatus = 'form' | 'loading' | 'success' | 'error' | 'invalid-token'

const ResetPassword = () => {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState<ResetStatus>('form')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [formErrors, setFormErrors] = useState<{ password?: string; confirmPassword?: string }>({})

  const token = searchParams.get('token')

  useEffect(() => {
    if (!token) {
      setStatus('invalid-token')
    }
  }, [token])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormErrors({})

    // Validate
    const errors: { password?: string; confirmPassword?: string } = {}
    if (password.length < 8) {
      errors.password = 'Password must be at least 8 characters'
    }
    if (password !== confirmPassword) {
      errors.confirmPassword = 'Passwords do not match'
    }

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors)
      return
    }

    if (!token) {
      setStatus('invalid-token')
      return
    }

    setStatus('loading')

    try {
      await authAPI.resetPassword(token, password)
      setStatus('success')
      // Redirect to login after 3 seconds
      setTimeout(() => navigate('/login'), 3000)
    } catch (error: any) {
      setStatus('error')
      const detail = error?.response?.data?.detail
      if (typeof detail === 'string') {
        setErrorMessage(detail)
      } else {
        setErrorMessage('Failed to reset password. The link may be invalid or expired.')
      }
    }
  }

  const renderContent = () => {
    switch (status) {
      case 'loading':
        return (
          <>
            <div className="mb-4">
              <Loader2 className="w-12 h-12 mx-auto text-indigo-600 dark:text-indigo-400 animate-spin" />
            </div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              Resetting Password
            </h2>
            <p className="text-gray-600 dark:text-slate-400">
              Please wait...
            </p>
          </>
        )

      case 'success':
        return (
          <>
            <div className="mb-4">
              <div className="w-16 h-16 mx-auto rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                <CheckCircle className="w-8 h-8 text-green-600 dark:text-green-400" />
              </div>
            </div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              Password Reset!
            </h2>
            <p className="text-gray-600 dark:text-slate-400 mb-4">
              Your password has been reset successfully. You can now sign in with your new password.
            </p>
            <p className="text-sm text-gray-500 dark:text-slate-500">
              Redirecting to login...
            </p>
          </>
        )

      case 'error':
        return (
          <>
            <div className="mb-4">
              <div className="w-16 h-16 mx-auto rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                <XCircle className="w-8 h-8 text-red-600 dark:text-red-400" />
              </div>
            </div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              Reset Failed
            </h2>
            <p className="text-gray-600 dark:text-slate-400 mb-6">
              {errorMessage}
            </p>
            <Link
              to="/forgot-password"
              className="inline-flex items-center justify-center py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-xl transition-colors"
            >
              Request New Reset Link
            </Link>
          </>
        )

      case 'invalid-token':
        return (
          <>
            <div className="mb-4">
              <div className="w-16 h-16 mx-auto rounded-full bg-yellow-100 dark:bg-yellow-900/30 flex items-center justify-center">
                <XCircle className="w-8 h-8 text-yellow-600 dark:text-yellow-400" />
              </div>
            </div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              Invalid Reset Link
            </h2>
            <p className="text-gray-600 dark:text-slate-400 mb-6">
              This password reset link is invalid or has expired. Please request a new one.
            </p>
            <Link
              to="/forgot-password"
              className="inline-flex items-center justify-center py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-xl transition-colors"
            >
              Request New Reset Link
            </Link>
          </>
        )

      case 'form':
        return (
          <>
            <div className="text-center mb-8">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Reset Password</h1>
              <p className="mt-2 text-gray-600 dark:text-slate-400">Enter your new password below</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              {/* New Password */}
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                  New Password
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Lock className="h-5 w-5 text-gray-400 dark:text-slate-500" />
                  </div>
                  <input
                    id="password"
                    type="password"
                    required
                    autoComplete="new-password"
                    aria-invalid={Boolean(formErrors.password)}
                    className={`w-full pl-10 pr-4 py-3 rounded-xl border bg-white dark:bg-slate-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-slate-500 transition-all focus:outline-none focus:ring-2 ${
                      formErrors.password
                        ? 'border-red-300 dark:border-red-800 focus:border-red-500 focus:ring-red-500/20'
                        : 'border-gray-200 dark:border-slate-700 focus:border-indigo-500 focus:ring-indigo-500/20'
                    }`}
                    placeholder="Enter new password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>
                {formErrors.password && (
                  <p className="mt-2 text-xs text-red-600 dark:text-red-400">{formErrors.password}</p>
                )}
              </div>

              {/* Confirm Password */}
              <div>
                <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                  Confirm Password
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Lock className="h-5 w-5 text-gray-400 dark:text-slate-500" />
                  </div>
                  <input
                    id="confirmPassword"
                    type="password"
                    required
                    autoComplete="new-password"
                    aria-invalid={Boolean(formErrors.confirmPassword)}
                    className={`w-full pl-10 pr-4 py-3 rounded-xl border bg-white dark:bg-slate-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-slate-500 transition-all focus:outline-none focus:ring-2 ${
                      formErrors.confirmPassword
                        ? 'border-red-300 dark:border-red-800 focus:border-red-500 focus:ring-red-500/20'
                        : 'border-gray-200 dark:border-slate-700 focus:border-indigo-500 focus:ring-indigo-500/20'
                    }`}
                    placeholder="Confirm new password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                  />
                </div>
                {formErrors.confirmPassword && (
                  <p className="mt-2 text-xs text-red-600 dark:text-red-400">{formErrors.confirmPassword}</p>
                )}
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                className="relative w-full group"
              >
                <div className="absolute -inset-0.5 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-xl blur opacity-60 group-hover:opacity-100 transition duration-200" />
                <div className="relative w-full py-3 px-4 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-semibold rounded-xl transition-all">
                  Reset Password
                </div>
              </button>
            </form>
          </>
        )
    }
  }

  return (
    <div className="min-h-screen bg-white dark:bg-[#0f172a] flex items-center justify-center relative overflow-hidden">
      {/* Background */}
      <div className="fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-50 via-white to-purple-50 dark:opacity-0 transition-opacity duration-500" />
        <div className="absolute inset-0 opacity-0 dark:opacity-100 transition-opacity duration-500">
          <div className="absolute inset-0 bg-[#0f172a]" />
        </div>
      </div>

      <div className="w-full max-w-md px-4 py-10 sm:px-6">
        {/* Logo */}
        <Link to="/" className="flex justify-center mb-8">
          <Logo iconClassName="h-11 w-11" textClassName="text-2xl font-bold" />
        </Link>

        {/* Card */}
        <div className="relative bg-white/80 dark:bg-slate-800/80 backdrop-blur-sm rounded-2xl border border-gray-200/80 dark:border-slate-600/50 shadow-lg shadow-indigo-500/5 dark:shadow-lg dark:shadow-black/20 p-8">
            {renderContent()}
          </div>

        {/* Back Link */}
        <div className="mt-8 flex justify-center">
          <Link
            to="/login"
            className="inline-flex items-center gap-2 text-sm font-medium text-gray-600 dark:text-slate-400 hover:text-gray-900 dark:hover:text-white transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to login
          </Link>
        </div>
      </div>
    </div>
  )
}

export default ResetPassword
