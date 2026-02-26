import { useEffect, useState } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import { authAPI } from '../../services/api'
import { Loader2, CheckCircle, XCircle, ArrowLeft, Mail } from 'lucide-react'
import { Logo } from '../../components/brand/Logo'

type VerificationStatus = 'pending' | 'loading' | 'success' | 'error' | 'no-token'

const VerifyEmail = () => {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState<VerificationStatus>('pending')
  const [errorMessage, setErrorMessage] = useState<string>('')
  const [resendEmail, setResendEmail] = useState('')
  const [resendStatus, setResendStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')
  const token = searchParams.get('token')

  useEffect(() => {
    if (!token) {
      setStatus('no-token')
    }
  }, [token])

  const handleVerify = async () => {
    if (!token) return

    setStatus('loading')
    try {
      await authAPI.verifyEmail(token)
      setStatus('success')
      // Redirect to login after 3 seconds
      setTimeout(() => navigate('/login'), 3000)
    } catch (error: any) {
      setStatus('error')
      const detail = error?.response?.data?.detail
      if (typeof detail === 'string') {
        setErrorMessage(detail)
      } else {
        setErrorMessage('Failed to verify email. The link may be invalid or expired.')
      }
    }
  }

  const handleResendVerification = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!resendEmail.trim()) return

    setResendStatus('sending')
    try {
      await authAPI.resendVerification(resendEmail.trim())
      setResendStatus('sent')
    } catch {
      setResendStatus('error')
    }
  }

  const renderContent = () => {
    switch (status) {
      case 'pending':
        return (
          <>
            <div className="mb-4">
              <div className="w-16 h-16 mx-auto rounded-full bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center">
                <Mail className="w-8 h-8 text-indigo-600 dark:text-indigo-400" />
              </div>
            </div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              Verify Your Email
            </h2>
            <p className="text-gray-600 dark:text-slate-400 mb-6">
              Click the button below to verify your email address and activate your account.
            </p>
            <button
              onClick={handleVerify}
              className="w-full py-3 px-4 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white font-semibold rounded-xl transition-all shadow-lg shadow-indigo-500/25"
            >
              Verify My Email
            </button>
          </>
        )

      case 'loading':
        return (
          <>
            <div className="mb-4">
              <Loader2 className="w-12 h-12 mx-auto text-indigo-600 dark:text-indigo-400 animate-spin" />
            </div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              Verifying Your Email
            </h2>
            <p className="text-gray-600 dark:text-slate-400">
              Please wait while we verify your email address...
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
              Email Verified!
            </h2>
            <p className="text-gray-600 dark:text-slate-400 mb-4">
              Your email has been verified successfully. You can now sign in to your account.
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
              Verification Failed
            </h2>
            <p className="text-gray-600 dark:text-slate-400 mb-6">
              {errorMessage}
            </p>

            {/* Resend form */}
            <div className="border-t border-gray-200 dark:border-slate-700 pt-6">
              <p className="text-sm text-gray-600 dark:text-slate-400 mb-4">
                Need a new verification link?
              </p>
              <form onSubmit={handleResendVerification} className="space-y-3">
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Mail className="h-5 w-5 text-gray-400 dark:text-slate-500" />
                  </div>
                  <input
                    type="email"
                    placeholder="Enter your email"
                    value={resendEmail}
                    onChange={(e) => setResendEmail(e.target.value)}
                    className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:border-indigo-500 focus:ring-indigo-500/20"
                    disabled={resendStatus === 'sending' || resendStatus === 'sent'}
                  />
                </div>
                <button
                  type="submit"
                  disabled={resendStatus === 'sending' || resendStatus === 'sent' || !resendEmail.trim()}
                  className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-xl transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {resendStatus === 'sending' ? 'Sending...' : resendStatus === 'sent' ? 'Sent!' : 'Resend Verification'}
                </button>
              </form>
              {resendStatus === 'sent' && (
                <p className="text-sm text-green-600 dark:text-green-400 mt-2">
                  Check your inbox for the verification link.
                </p>
              )}
              {resendStatus === 'error' && (
                <p className="text-sm text-red-600 dark:text-red-400 mt-2">
                  Failed to send. Please try again.
                </p>
              )}
            </div>
          </>
        )

      case 'no-token':
        return (
          <>
            <div className="mb-4">
              <div className="w-16 h-16 mx-auto rounded-full bg-yellow-100 dark:bg-yellow-900/30 flex items-center justify-center">
                <Mail className="w-8 h-8 text-yellow-600 dark:text-yellow-400" />
              </div>
            </div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              Check Your Email
            </h2>
            <p className="text-gray-600 dark:text-slate-400 mb-6">
              We've sent a verification link to your email address. Click the link to verify your account.
            </p>

            {/* Resend form */}
            <div className="border-t border-gray-200 dark:border-slate-700 pt-6">
              <p className="text-sm text-gray-600 dark:text-slate-400 mb-4">
                Didn't receive the email?
              </p>
              <form onSubmit={handleResendVerification} className="space-y-3">
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Mail className="h-5 w-5 text-gray-400 dark:text-slate-500" />
                  </div>
                  <input
                    type="email"
                    placeholder="Enter your email"
                    value={resendEmail}
                    onChange={(e) => setResendEmail(e.target.value)}
                    className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:border-indigo-500 focus:ring-indigo-500/20"
                    disabled={resendStatus === 'sending' || resendStatus === 'sent'}
                  />
                </div>
                <button
                  type="submit"
                  disabled={resendStatus === 'sending' || resendStatus === 'sent' || !resendEmail.trim()}
                  className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-xl transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {resendStatus === 'sending' ? 'Sending...' : resendStatus === 'sent' ? 'Sent!' : 'Resend Verification'}
                </button>
              </form>
              {resendStatus === 'sent' && (
                <p className="text-sm text-green-600 dark:text-green-400 mt-2">
                  Check your inbox for the verification link.
                </p>
              )}
              {resendStatus === 'error' && (
                <p className="text-sm text-red-600 dark:text-red-400 mt-2">
                  Failed to send. Please try again.
                </p>
              )}
            </div>
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
        <div className="relative bg-white/80 dark:bg-slate-800/80 backdrop-blur-sm rounded-2xl border border-gray-200/80 dark:border-slate-600/50 shadow-lg shadow-indigo-500/5 dark:shadow-lg dark:shadow-black/20 p-8 text-center">
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

export default VerifyEmail
