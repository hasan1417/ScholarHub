import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { ArrowLeft, Mail, Lock, Loader2 } from 'lucide-react'
import { Logo } from '../../components/brand/Logo'
import GoogleSignInButton from '../../components/auth/GoogleSignInButton'

type LoginErrors = {
  general?: string
  email?: string
  password?: string
}

const Login = () => {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [formErrors, setFormErrors] = useState<LoginErrors>({})
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setFormErrors({})

    try {
      await login(email, password)
      navigate('/projects')
    } catch (error: any) {
      console.error('Login error:', error)
      const detail = error?.response?.data?.detail
      const nextErrors: LoginErrors = {}

      if (Array.isArray(detail)) {
        detail.forEach((err: any) => {
          const loc = Array.isArray(err?.loc) ? err.loc : []
          const field = loc[loc.length - 1]
          const message = err?.msg || err?.message
          if (field === 'email' && message) nextErrors.email = message
          else if (field === 'password' && message) nextErrors.password = message
        })
      } else if (typeof detail === 'object' && detail !== null) {
        const message = detail.msg || detail.message
        if (message) nextErrors.general = message
      } else if (typeof detail === 'string') {
        nextErrors.general = detail
      }

      if (!nextErrors.general && !nextErrors.email && !nextErrors.password) {
        nextErrors.general = 'Unable to sign in. Double-check your credentials and try again.'
      }

      setFormErrors(nextErrors)
    } finally {
      setIsLoading(false)
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
            <div className="text-center mb-8">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Welcome back</h1>
              <p className="mt-2 text-gray-600 dark:text-slate-400">Sign in to continue to your workspace</p>
            </div>

            {formErrors.general && (
              <div className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800/50 dark:bg-red-500/10 dark:text-red-300">
                {formErrors.general}
              </div>
            )}

            <form onSubmit={handleSubmit} noValidate className="space-y-5">
              {/* Email */}
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                  Email address
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Mail className="h-5 w-5 text-gray-400 dark:text-slate-500" />
                  </div>
                  <input
                    id="email"
                    type="email"
                    required
                    autoComplete="email"
                    aria-invalid={Boolean(formErrors.email)}
                    className={`w-full pl-10 pr-4 py-3 rounded-xl border bg-white dark:bg-slate-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-slate-500 transition-all focus:outline-none focus:ring-2 ${
                      formErrors.email
                        ? 'border-red-300 dark:border-red-800 focus:border-red-500 focus:ring-red-500/20'
                        : 'border-gray-200 dark:border-slate-700 focus:border-indigo-500 focus:ring-indigo-500/20'
                    }`}
                    placeholder="you@university.edu"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    disabled={isLoading}
                  />
                </div>
                {formErrors.email && (
                  <p className="mt-2 text-xs text-red-600 dark:text-red-400">{formErrors.email}</p>
                )}
              </div>

              {/* Password */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-slate-300">
                    Password
                  </label>
                  <Link
                    to="/forgot-password"
                    className="text-sm font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300"
                  >
                    Forgot password?
                  </Link>
                </div>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Lock className="h-5 w-5 text-gray-400 dark:text-slate-500" />
                  </div>
                  <input
                    id="password"
                    type="password"
                    required
                    autoComplete="current-password"
                    aria-invalid={Boolean(formErrors.password)}
                    className={`w-full pl-10 pr-4 py-3 rounded-xl border bg-white dark:bg-slate-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-slate-500 transition-all focus:outline-none focus:ring-2 ${
                      formErrors.password
                        ? 'border-red-300 dark:border-red-800 focus:border-red-500 focus:ring-red-500/20'
                        : 'border-gray-200 dark:border-slate-700 focus:border-indigo-500 focus:ring-indigo-500/20'
                    }`}
                    placeholder="Enter your password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={isLoading}
                  />
                </div>
                {formErrors.password && (
                  <p className="mt-2 text-xs text-red-600 dark:text-red-400">{formErrors.password}</p>
                )}
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3 px-4 text-white font-semibold bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-all shadow-lg shadow-indigo-500/25 hover:shadow-xl hover:shadow-indigo-500/30 hover:-translate-y-0.5 disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:translate-y-0 flex items-center justify-center gap-2"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-5 w-5 animate-spin" />
                    Signing in...
                  </>
                ) : (
                  'Sign in'
                )}
              </button>
            </form>

            {/* Divider */}
            <div className="mt-8 flex items-center gap-4">
              <div className="flex-1 h-px bg-gray-200 dark:bg-slate-700" />
              <span className="text-sm text-gray-500 dark:text-slate-500">or continue with</span>
              <div className="flex-1 h-px bg-gray-200 dark:bg-slate-700" />
            </div>

            {/* Google Sign In */}
            <div className="mt-6">
              <GoogleSignInButton mode="signin" disabled={isLoading} />
            </div>

            {/* Divider */}
            <div className="mt-8 flex items-center gap-4">
              <div className="flex-1 h-px bg-gray-200 dark:bg-slate-700" />
              <span className="text-sm text-gray-500 dark:text-slate-500">New to ScholarHub?</span>
              <div className="flex-1 h-px bg-gray-200 dark:bg-slate-700" />
            </div>

            {/* Sign Up Link */}
            <div className="mt-6">
              <Link
                to="/register"
                className="w-full inline-flex items-center justify-center py-3 px-4 rounded-xl border-2 border-gray-200 dark:border-slate-700 text-gray-700 dark:text-slate-300 font-semibold hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors"
              >
                Create an account
              </Link>
            </div>
          </div>

        {/* Back Link */}
        <div className="mt-8 flex justify-center">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-sm font-medium text-gray-600 dark:text-slate-400 hover:text-gray-900 dark:hover:text-white transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to home
          </Link>
        </div>
      </div>
    </div>
  )
}

export default Login
