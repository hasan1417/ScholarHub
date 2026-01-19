import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { Loader2 } from 'lucide-react'
import { Logo } from '../../components/brand/Logo'

const AuthCallback = () => {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { refreshUser } = useAuth()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const handleCallback = async () => {
      const accessToken = searchParams.get('access_token')
      const errorParam = searchParams.get('error')

      if (errorParam) {
        setError('Authentication failed. Please try again.')
        setTimeout(() => navigate('/login'), 3000)
        return
      }

      if (!accessToken) {
        setError('No authentication token received.')
        setTimeout(() => navigate('/login'), 3000)
        return
      }

      // Store the token
      localStorage.setItem('access_token', accessToken)

      try {
        // Refresh user data
        await refreshUser()
        // Redirect to projects
        navigate('/projects', { replace: true })
      } catch (err) {
        console.error('Failed to fetch user after OAuth:', err)
        setError('Failed to complete authentication.')
        localStorage.removeItem('access_token')
        setTimeout(() => navigate('/login'), 3000)
      }
    }

    handleCallback()
  }, [searchParams, navigate, refreshUser])

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden">
      {/* Background */}
      <div className="fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-50 via-white to-purple-50 dark:opacity-0 transition-opacity duration-500" />
        <div className="absolute inset-0 opacity-0 dark:opacity-100 transition-opacity duration-500">
          <div className="absolute inset-0 bg-slate-950" />
          <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-indigo-500/20 rounded-full blur-[128px]" />
          <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-purple-500/20 rounded-full blur-[128px]" />
        </div>
      </div>

      <div className="w-full max-w-md px-4 py-10 sm:px-6 text-center">
        {/* Logo */}
        <div className="flex justify-center mb-8">
          <Logo iconClassName="h-11 w-11" textClassName="text-2xl font-bold" />
        </div>

        {/* Card */}
        <div className="relative">
          <div className="absolute -inset-1 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-3xl blur-xl opacity-20 dark:opacity-30" />

          <div className="relative bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl rounded-2xl border border-gray-200/50 dark:border-slate-700/50 shadow-2xl shadow-gray-200/50 dark:shadow-slate-900/50 p-8">
            {error ? (
              <>
                <div className="mb-4">
                  <div className="w-16 h-16 mx-auto rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                    <svg className="w-8 h-8 text-red-600 dark:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </div>
                </div>
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                  Authentication Failed
                </h2>
                <p className="text-gray-600 dark:text-slate-400">
                  {error}
                </p>
                <p className="text-sm text-gray-500 dark:text-slate-500 mt-4">
                  Redirecting to login...
                </p>
              </>
            ) : (
              <>
                <div className="mb-4">
                  <Loader2 className="w-12 h-12 mx-auto text-indigo-600 dark:text-indigo-400 animate-spin" />
                </div>
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                  Completing Sign In
                </h2>
                <p className="text-gray-600 dark:text-slate-400">
                  Please wait while we complete your authentication...
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default AuthCallback
