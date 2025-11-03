import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { ArrowLeft } from 'lucide-react'

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

  const inputBaseClasses =
    'w-full rounded-lg border px-3 py-2 transition-colors focus:outline-none sm:text-sm'

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-50 via-white to-purple-50 px-4 py-10 sm:px-6 lg:px-8 sm:py-16 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
      <div className="max-w-md w-full space-y-6 sm:space-y-8">
        <div className="bg-white/95 backdrop-blur rounded-2xl border border-gray-200/70 shadow-lg shadow-indigo-100/50 p-6 sm:p-8 dark:bg-gray-900/90 dark:border-gray-800 dark:shadow-indigo-950/40">
          <div className="text-center">
            <span className="text-3xl font-bold text-gray-900 dark:text-gray-100">ScholarHub</span>
          </div>

          <h1 className="mt-6 text-center text-2xl font-semibold text-gray-900 dark:text-gray-100">Welcome back</h1>

          {formErrors.general && (
            <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-400/40 dark:bg-red-500/10 dark:text-red-300">
              {formErrors.general}
            </div>
          )}

          <form className="mt-6 space-y-5" onSubmit={handleSubmit} noValidate>
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Email address
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                aria-invalid={Boolean(formErrors.email)}
                aria-describedby={formErrors.email ? 'email-error' : undefined}
                className={`${inputBaseClasses} ${
                  formErrors.email
                    ? 'border-red-400 focus:border-red-500 focus:ring-2 focus:ring-red-500'
                    : 'border-gray-300 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100'
                }`}
                placeholder="you@university.edu"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                disabled={isLoading}
              />
              {formErrors.email && (
                <p id="email-error" className="mt-1 text-xs text-red-600">
                  {formErrors.email}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="password" className="flex items-center justify-between text-sm font-medium text-gray-700 dark:text-gray-300">
                <span>Password</span>
                <Link to="/forgot-password" className="text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300">
                  Forgot password?
                </Link>
              </label>
              <input
                id="password"
                type="password"
                required
                autoComplete="current-password"
                aria-invalid={Boolean(formErrors.password)}
                aria-describedby={formErrors.password ? 'password-error' : undefined}
                className={`${inputBaseClasses} ${
                  formErrors.password
                    ? 'border-red-400 focus:border-red-500 focus:ring-2 focus:ring-red-500'
                    : 'border-gray-300 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100'
                }`}
                placeholder="Enter your password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={isLoading}
              />
              {formErrors.password && (
                <p id="password-error" className="mt-1 text-xs text-red-600">
                  {formErrors.password}
                </p>
              )}
            </div>

            <button
              type="submit"
              className="w-full rounded-lg bg-indigo-600 py-3 text-sm font-medium text-white transition-colors duration-200 hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={isLoading}
            >
              {isLoading ? (
                <div className="flex items-center justify-center gap-2">
                  <svg
                    className="h-5 w-5 animate-spin text-white"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Signing in…
                </div>
              ) : (
                'Sign in'
              )}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-gray-600 dark:text-gray-300">
            <span>Don&apos;t have an account? </span>
            <Link to="/register" className="font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300">
              Sign up
            </Link>
          </div>
        </div>

        <div className="flex justify-center">
          <Link
            to="/"
            className="inline-flex items-center gap-2 rounded-full border border-transparent px-4 py-2 text-sm font-medium text-gray-600 transition hover:border-gray-300 hover:bg-white dark:text-gray-300 dark:hover:bg-gray-900"
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
