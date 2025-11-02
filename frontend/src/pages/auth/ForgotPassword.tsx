import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { authAPI } from '../../services/api'

const ForgotPassword = () => {
  const [email, setEmail] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setIsSubmitting(true)
    setStatusMessage(null)
    setErrorMessage(null)

    try {
      await authAPI.requestPasswordReset(email.trim())
      setStatusMessage('If an account exists for this email, we just sent reset instructions.')
    } catch (error: any) {
      const detail = error?.response?.data?.detail
      if (typeof detail === 'string') {
        setErrorMessage(detail)
      } else {
        setErrorMessage('We ran into an issue sending the reset link. Please try again shortly.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-50 via-white to-purple-50 px-4 py-10 sm:px-6 lg:px-8 sm:py-16">
      <div className="max-w-md w-full space-y-6 sm:space-y-8">
        <div className="bg-white/95 backdrop-blur rounded-2xl border border-gray-200/70 shadow-lg shadow-indigo-100/50 p-6 sm:p-8">
          <div className="text-center">
            <span className="text-3xl font-bold text-gray-900">ScholarHub</span>
            <p className="mt-1 text-sm text-gray-500">Reset access to your research workspace</p>
          </div>

          <h1 className="mt-6 text-center text-2xl font-semibold text-gray-900">Forgot password</h1>
          <p className="mt-2 text-center text-sm text-gray-600">
            Enter the email you use for ScholarHub and we&apos;ll send instructions to create a new password.
          </p>

          {statusMessage && (
            <div className="mt-6 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
              {statusMessage}
            </div>
          )}

          {errorMessage && (
            <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {errorMessage}
            </div>
          )}

          <form className="mt-6 space-y-5" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="reset-email" className="block text-sm font-medium text-gray-700">
                Email address
              </label>
              <input
                id="reset-email"
                type="email"
                required
                autoComplete="email"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="you@university.edu"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                disabled={isSubmitting}
              />
            </div>

            <button
              type="submit"
              className="w-full rounded-lg bg-indigo-600 py-3 text-sm font-medium text-white transition-colors duration-200 hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={isSubmitting || email.trim().length === 0}
            >
              {isSubmitting ? 'Sending reset link…' : 'Send reset link'}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-gray-600">
            Remember your password?{' '}
            <Link to="/login" className="font-medium text-indigo-600 hover:text-indigo-500">
              Return to sign in
            </Link>
          </div>
        </div>

        <div className="flex justify-center">
          <Link
            to="/"
            className="inline-flex items-center gap-2 rounded-full border border-transparent px-4 py-2 text-sm font-medium text-gray-600 transition hover:border-gray-300 hover:bg-white"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to home
          </Link>
        </div>
      </div>
    </div>
  )
}

export default ForgotPassword
