import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { ArrowLeft, Mail, Lock, User, Loader2, CheckCircle, ExternalLink } from 'lucide-react'
import { Logo } from '../../components/brand/Logo'
import GoogleSignInButton from '../../components/auth/GoogleSignInButton'

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

type RegistrationSuccess = {
  email: string
  message: string
  devVerificationUrl?: string
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
  const [registrationSuccess, setRegistrationSuccess] = useState<RegistrationSuccess | null>(null)

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
      const response = await register({
        email: formData.email,
        password: formData.password,
        first_name: formData.firstName,
        last_name: formData.lastName,
      })

      // Show verification pending screen
      setRegistrationSuccess({
        email: formData.email,
        message: response?.message || 'Please check your email to verify your account',
        devVerificationUrl: response?.dev_verification_url,
      })
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
        apiErrors.general = 'We couldn\'t create your account. Please review the details and try again.'
      }

      setFormErrors(apiErrors)
    } finally {
      setIsLoading(false)
    }
  }

  const getInputClasses = (hasError: boolean) =>
    `w-full pl-10 pr-4 py-3 rounded-xl border bg-white dark:bg-slate-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-slate-500 transition-all focus:outline-none focus:ring-2 ${
      hasError
        ? 'border-red-300 dark:border-red-800 focus:border-red-500 focus:ring-red-500/20'
        : 'border-gray-200 dark:border-slate-700 focus:border-indigo-500 focus:ring-indigo-500/20'
    }`

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden">
      {/* Animated Background */}
      <div className="fixed inset-0 -z-10">
        {/* Light mode gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-50 via-white to-purple-50 dark:opacity-0 transition-opacity duration-500" />
        {/* Dark mode gradient */}
        <div className="absolute inset-0 opacity-0 dark:opacity-100 transition-opacity duration-500">
          <div className="absolute inset-0 bg-slate-950" />
          <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-indigo-500/20 rounded-full blur-[128px]" />
          <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-purple-500/20 rounded-full blur-[128px]" />
        </div>
        {/* Grid pattern */}
        <div
          className="absolute inset-0 opacity-[0.02] dark:opacity-[0.05]"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%239C92AC' fill-opacity='0.4'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
          }}
        />
      </div>

      <div className="w-full max-w-md px-4 py-10 sm:px-6">
        {/* Logo */}
        <Link to="/" className="flex justify-center mb-8">
          <Logo iconClassName="h-11 w-11" textClassName="text-2xl font-bold" />
        </Link>

        {/* Card */}
        <div className="relative">
          {/* Glow effect */}
          <div className="absolute -inset-1 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-3xl blur-xl opacity-20 dark:opacity-30" />

          <div className="relative bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl rounded-2xl border border-gray-200/50 dark:border-slate-700/50 shadow-2xl shadow-gray-200/50 dark:shadow-slate-900/50 p-8">
            {/* Registration Success Screen */}
            {registrationSuccess ? (
              <div className="text-center">
                <div className="mx-auto w-16 h-16 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mb-6">
                  <CheckCircle className="w-8 h-8 text-green-600 dark:text-green-400" />
                </div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Check your email</h1>
                <p className="text-gray-600 dark:text-slate-400 mb-6">
                  We sent a verification link to<br />
                  <span className="font-medium text-gray-900 dark:text-white">{registrationSuccess.email}</span>
                </p>

                {/* Dev mode verification link */}
                {registrationSuccess.devVerificationUrl && (
                  <div className="mb-6 p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl">
                    <p className="text-sm font-medium text-amber-800 dark:text-amber-200 mb-2">
                      Development Mode
                    </p>
                    <p className="text-xs text-amber-700 dark:text-amber-300 mb-3">
                      Click below to verify your email (this link is only shown in development):
                    </p>
                    <a
                      href={registrationSuccess.devVerificationUrl}
                      className="inline-flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-lg transition-colors"
                    >
                      <ExternalLink className="w-4 h-4" />
                      Verify Email Now
                    </a>
                  </div>
                )}

                <p className="text-sm text-gray-500 dark:text-slate-500 mb-6">
                  Didn't receive the email? Check your spam folder or{' '}
                  <button
                    onClick={() => setRegistrationSuccess(null)}
                    className="text-indigo-600 dark:text-indigo-400 hover:underline"
                  >
                    try again
                  </button>
                </p>

                <Link
                  to="/login"
                  className="inline-flex items-center justify-center w-full py-3 px-4 rounded-xl border-2 border-gray-200 dark:border-slate-700 text-gray-700 dark:text-slate-300 font-semibold hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors"
                >
                  Back to Sign In
                </Link>
              </div>
            ) : (
            <>
            <div className="text-center mb-8">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Create your account</h1>
              <p className="mt-2 text-gray-600 dark:text-slate-400">Join the research community</p>
            </div>

            {formErrors.general && (
              <div className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800/50 dark:bg-red-500/10 dark:text-red-300">
                {formErrors.general}
              </div>
            )}

            <form onSubmit={handleSubmit} noValidate className="space-y-5">
              {/* Name Fields */}
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="firstName" className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                    First name
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <User className="h-5 w-5 text-gray-400 dark:text-slate-500" />
                    </div>
                    <input
                      id="firstName"
                      name="firstName"
                      type="text"
                      autoComplete="given-name"
                      required
                      aria-invalid={Boolean(formErrors.firstName)}
                      className={getInputClasses(Boolean(formErrors.firstName))}
                      placeholder="Ada"
                      value={formData.firstName}
                      onChange={handleChange}
                      disabled={isLoading}
                    />
                  </div>
                  {formErrors.firstName && (
                    <p className="mt-2 text-xs text-red-600 dark:text-red-400">{formErrors.firstName}</p>
                  )}
                </div>

                <div>
                  <label htmlFor="lastName" className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                    Last name
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <User className="h-5 w-5 text-gray-400 dark:text-slate-500" />
                    </div>
                    <input
                      id="lastName"
                      name="lastName"
                      type="text"
                      autoComplete="family-name"
                      required
                      aria-invalid={Boolean(formErrors.lastName)}
                      className={getInputClasses(Boolean(formErrors.lastName))}
                      placeholder="Lovelace"
                      value={formData.lastName}
                      onChange={handleChange}
                      disabled={isLoading}
                    />
                  </div>
                  {formErrors.lastName && (
                    <p className="mt-2 text-xs text-red-600 dark:text-red-400">{formErrors.lastName}</p>
                  )}
                </div>
              </div>

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
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    aria-invalid={Boolean(formErrors.email)}
                    className={getInputClasses(Boolean(formErrors.email))}
                    placeholder="you@university.edu"
                    value={formData.email}
                    onChange={handleChange}
                    disabled={isLoading}
                  />
                </div>
                {formErrors.email && (
                  <p className="mt-2 text-xs text-red-600 dark:text-red-400">{formErrors.email}</p>
                )}
              </div>

              {/* Password */}
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                  Password
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Lock className="h-5 w-5 text-gray-400 dark:text-slate-500" />
                  </div>
                  <input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="new-password"
                    required
                    aria-invalid={Boolean(formErrors.password)}
                    className={getInputClasses(Boolean(formErrors.password))}
                    placeholder="Create a secure password"
                    value={formData.password}
                    onChange={handleChange}
                    disabled={isLoading}
                  />
                </div>
                {formErrors.password && (
                  <p className="mt-2 text-xs text-red-600 dark:text-red-400">{formErrors.password}</p>
                )}
              </div>

              {/* Confirm Password */}
              <div>
                <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                  Confirm password
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Lock className="h-5 w-5 text-gray-400 dark:text-slate-500" />
                  </div>
                  <input
                    id="confirmPassword"
                    name="confirmPassword"
                    type="password"
                    autoComplete="new-password"
                    required
                    aria-invalid={Boolean(formErrors.confirmPassword)}
                    className={getInputClasses(Boolean(formErrors.confirmPassword))}
                    placeholder="Re-enter your password"
                    value={formData.confirmPassword}
                    onChange={handleChange}
                    disabled={isLoading}
                  />
                </div>
                {formErrors.confirmPassword && (
                  <p className="mt-2 text-xs text-red-600 dark:text-red-400">{formErrors.confirmPassword}</p>
                )}
              </div>

              {/* Terms notice */}
              <p className="text-xs text-gray-500 dark:text-slate-400">
                By creating an account you agree to keep your collaborators' data secure and follow your institution's sharing guidelines.
              </p>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isLoading}
                className="relative w-full group"
              >
                <div className="absolute -inset-0.5 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-xl blur opacity-60 group-hover:opacity-100 transition duration-200" />
                <div className="relative w-full py-3 px-4 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-semibold rounded-xl transition-all disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2">
                  {isLoading ? (
                    <>
                      <Loader2 className="h-5 w-5 animate-spin" />
                      Creating account...
                    </>
                  ) : (
                    'Create account'
                  )}
                </div>
              </button>
            </form>

            {/* Divider */}
            <div className="mt-8 flex items-center gap-4">
              <div className="flex-1 h-px bg-gray-200 dark:bg-slate-700" />
              <span className="text-sm text-gray-500 dark:text-slate-500">or continue with</span>
              <div className="flex-1 h-px bg-gray-200 dark:bg-slate-700" />
            </div>

            {/* Google Sign Up */}
            <div className="mt-6">
              <GoogleSignInButton mode="signup" disabled={isLoading} />
            </div>

            {/* Divider */}
            <div className="mt-8 flex items-center gap-4">
              <div className="flex-1 h-px bg-gray-200 dark:bg-slate-700" />
              <span className="text-sm text-gray-500 dark:text-slate-500">Already a member?</span>
              <div className="flex-1 h-px bg-gray-200 dark:bg-slate-700" />
            </div>

            {/* Sign In Link */}
            <div className="mt-6">
              <Link
                to="/login"
                className="w-full inline-flex items-center justify-center py-3 px-4 rounded-xl border-2 border-gray-200 dark:border-slate-700 text-gray-700 dark:text-slate-300 font-semibold hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors"
              >
                Sign in to your account
              </Link>
            </div>
            </>
            )}
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

export default Register
