import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { ArrowLeft } from 'lucide-react'

type RegisterForm = {
  firstName: string
  lastName: string
  email: string
  password: string
  confirmPassword: string
}

type RegisterErrors = {
  general?: string
  firstName?: string
  lastName?: string
  email?: string
  password?: string
  confirmPassword?: string
}

const Register = () => {
  const [formData, setFormData] = useState<RegisterForm>({
    email: '',
    password: '',
    confirmPassword: '',
    firstName: '',
    lastName: '',
  })
  const [isLoading, setIsLoading] = useState(false)
  const [formErrors, setFormErrors] = useState<RegisterErrors>({})

  const { register } = useAuth()
  const navigate = useNavigate()

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    const nextErrors: RegisterErrors = {}

    if (formData.password !== formData.confirmPassword) {
      nextErrors.confirmPassword = 'Passwords do not match.'
    }

    if (Object.keys(nextErrors).length > 0) {
      setFormErrors(nextErrors)
      return
    }

    setIsLoading(true)
    setFormErrors({})

    try {
      await register({
        email: formData.email,
        password: formData.password,
        first_name: formData.firstName,
        last_name: formData.lastName,
      })
      navigate('/projects')
    } catch (error: any) {
      const detail = error?.response?.data?.detail
      const apiErrors: RegisterErrors = {}

      if (Array.isArray(detail)) {
        detail.forEach((err: any) => {
          const loc = Array.isArray(err?.loc) ? err.loc : []
          const field = loc[loc.length - 1]
          const message = err?.msg || err?.message
          if (message && typeof field === 'string') {
            if (field === 'first_name') apiErrors.firstName = message
            else if (field === 'last_name') apiErrors.lastName = message
            else if (field === 'email') apiErrors.email = message
            else if (field === 'password') apiErrors.password = message
          }
        })
      } else if (typeof detail === 'object' && detail !== null) {
        const message = detail.msg || detail.message
        if (message) apiErrors.general = message
      } else if (typeof detail === 'string') {
        apiErrors.general = detail
      }

      if (Object.keys(apiErrors).length === 0) {
        apiErrors.general = 'We couldn’t create your account. Please review the details and try again.'
      }

      setFormErrors(apiErrors)
    } finally {
      setIsLoading(false)
    }
  }

  const inputBaseClasses =
    'w-full rounded-lg border px-3 py-2 transition-colors focus:outline-none sm:text-sm'

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-50 via-white to-purple-50 px-4 py-10 sm:px-6 lg:px-8 sm:py-16">
      <div className="max-w-md w-full space-y-6 sm:space-y-8">
        <div className="bg-white/95 backdrop-blur rounded-2xl border border-gray-200/70 shadow-lg shadow-indigo-100/50 p-6 sm:p-8">
          <div className="text-center">
            <span className="text-3xl font-bold text-gray-900">ScholarHub</span>
          </div>

          <h1 className="mt-6 text-center text-2xl font-semibold text-gray-900">Create your account</h1>

          {formErrors.general && (
            <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {formErrors.general}
            </div>
          )}

          <form className="mt-6 space-y-5" onSubmit={handleSubmit} noValidate>
            <div className="grid gap-4 sm:grid-cols-2 sm:gap-3">
              <div>
                <label htmlFor="firstName" className="block text-sm font-medium text-gray-700">
                  First name
                </label>
                <input
                  id="firstName"
                  name="firstName"
                  type="text"
                  autoComplete="given-name"
                  required
                  aria-invalid={Boolean(formErrors.firstName)}
                  aria-describedby={formErrors.firstName ? 'firstName-error' : undefined}
                  className={`${inputBaseClasses} ${
                    formErrors.firstName
                      ? 'border-red-400 focus:border-red-500 focus:ring-2 focus:ring-red-500'
                      : 'border-gray-300 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500'
                  }`}
                  placeholder="Ada"
                  value={formData.firstName}
                  onChange={handleChange}
                  disabled={isLoading}
                />
                {formErrors.firstName && (
                  <p id="firstName-error" className="mt-1 text-xs text-red-600">
                    {formErrors.firstName}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor="lastName" className="block text-sm font-medium text-gray-700">
                  Last name
                </label>
                <input
                  id="lastName"
                  name="lastName"
                  type="text"
                  autoComplete="family-name"
                  required
                  aria-invalid={Boolean(formErrors.lastName)}
                  aria-describedby={formErrors.lastName ? 'lastName-error' : undefined}
                  className={`${inputBaseClasses} ${
                    formErrors.lastName
                      ? 'border-red-400 focus:border-red-500 focus:ring-2 focus:ring-red-500'
                      : 'border-gray-300 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500'
                  }`}
                  placeholder="Lovelace"
                  value={formData.lastName}
                  onChange={handleChange}
                  disabled={isLoading}
                />
                {formErrors.lastName && (
                  <p id="lastName-error" className="mt-1 text-xs text-red-600">
                    {formErrors.lastName}
                  </p>
                )}
              </div>
            </div>

            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                Email address
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                aria-invalid={Boolean(formErrors.email)}
                aria-describedby={formErrors.email ? 'email-error' : undefined}
                className={`${inputBaseClasses} ${
                  formErrors.email
                    ? 'border-red-400 focus:border-red-500 focus:ring-2 focus:ring-red-500'
                    : 'border-gray-300 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500'
                }`}
                placeholder="you@lab.org"
                value={formData.email}
                onChange={handleChange}
                disabled={isLoading}
              />
              {formErrors.email && (
                <p id="email-error" className="mt-1 text-xs text-red-600">
                  {formErrors.email}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="new-password"
                required
                aria-invalid={Boolean(formErrors.password)}
                aria-describedby={formErrors.password ? 'password-error' : undefined}
                className={`${inputBaseClasses} ${
                  formErrors.password
                    ? 'border-red-400 focus:border-red-500 focus:ring-2 focus:ring-red-500'
                    : 'border-gray-300 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500'
                }`}
                placeholder="Create a secure password"
                value={formData.password}
                onChange={handleChange}
                disabled={isLoading}
              />
              {formErrors.password && (
                <p id="password-error" className="mt-1 text-xs text-red-600">
                  {formErrors.password}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700">
                Confirm password
              </label>
              <input
                id="confirmPassword"
                name="confirmPassword"
                type="password"
                autoComplete="new-password"
                required
                aria-invalid={Boolean(formErrors.confirmPassword)}
                aria-describedby={formErrors.confirmPassword ? 'confirmPassword-error' : undefined}
                className={`${inputBaseClasses} ${
                  formErrors.confirmPassword
                    ? 'border-red-400 focus:border-red-500 focus:ring-2 focus:ring-red-500'
                    : 'border-gray-300 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500'
                }`}
                placeholder="Re-enter your password"
                value={formData.confirmPassword}
                onChange={handleChange}
                disabled={isLoading}
              />
              {formErrors.confirmPassword && (
                <p id="confirmPassword-error" className="mt-1 text-xs text-red-600">
                  {formErrors.confirmPassword}
                </p>
              )}
            </div>

            <p className="text-xs text-gray-500">
              By creating an account you agree to keep your collaborators’ data secure and follow your institution’s sharing guidelines.
            </p>

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
                  Creating account…
                </div>
              ) : (
                'Create account'
              )}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-gray-600">
            <span>Already have an account? </span>
            <Link to="/login" className="font-medium text-indigo-600 hover:text-indigo-500">
              Sign in
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

export default Register
