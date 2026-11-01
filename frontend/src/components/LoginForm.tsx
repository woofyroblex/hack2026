import React, { useState } from 'react'
import { Eye, EyeOff, Lock, Mail, Loader2, AlertCircle, X, CheckCircle2 } from 'lucide-react'
import { useAuth } from '../context/useAuth.ts'
import { formatApiError } from '../api/auth.ts'

interface LoginFormProps {
  onNavigateToSignup: () => void
  onNavigateToRecovery: () => void
}

export const LoginForm: React.FC<LoginFormProps> = ({ onNavigateToSignup, onNavigateToRecovery }) => {
  const { login } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  // Validation errors
  const [errors, setErrors] = useState<{ email?: string; password?: string; general?: string }>({})
  const [touched, setTouched] = useState<{ email?: boolean; password?: boolean }>({})

  // Form states
  const [isLoading, setIsLoading] = useState(false)
  const [loginSuccess, setLoginSuccess] = useState(false)

  // Validate email format
  const validateEmail = (value: string): string | undefined => {
    if (!value.trim()) {
      return 'Email address is required.'
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(value.trim())) {
      return 'Please enter a valid email address (e.g., name@company.com).'
    }
    return undefined
  }

  // Validate password
  const validatePassword = (value: string): string | undefined => {
    if (!value) {
      return 'Password is required.'
    }
    return undefined
  }

  // Handle email blur for instant feedback
  const handleEmailBlur = () => {
    setTouched((prev) => ({ ...prev, email: true }))
    const error = validateEmail(email)
    setErrors((prev) => ({ ...prev, email: error }))
  }

  // Handle password blur for instant feedback
  const handlePasswordBlur = () => {
    setTouched((prev) => ({ ...prev, password: true }))
    const error = validatePassword(password)
    setErrors((prev) => ({ ...prev, password: error }))
  }

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    const emailError = validateEmail(email)
    const passwordError = validatePassword(password)

    setTouched({ email: true, password: true })
    setErrors({
      email: emailError,
      password: passwordError,
    })

    if (emailError || passwordError) {
      return
    }

    setIsLoading(true)
    setErrors({})

    try {
      await login({
        email: email.trim(),
        password,
        remember_me: rememberMe,
      })
      setLoginSuccess(true)
    } catch (err: unknown) {
      const formatted = formatApiError(err)
      const newErrors: { email?: string; password?: string; general?: string } = {
        general: formatted.message,
      }

      if (formatted.fieldErrors) {
        if (formatted.fieldErrors.email) {
          newErrors.email = formatted.fieldErrors.email[0]
        }
        if (formatted.fieldErrors.password) {
          newErrors.password = formatted.fieldErrors.password[0]
        }
      }

      setErrors(newErrors)
      setLoginSuccess(false)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="w-full max-w-[440px] mx-auto">
      {/* Main Login Card */}
      <div className="bg-white rounded-2xl border border-[#E5E7EB] shadow-xl shadow-slate-200/50 p-6 sm:p-8 transition-all">
        {/* Card Header */}
        <div className="mb-6">
          <h1 className="text-2xl sm:text-3xl font-extrabold text-[#172033] tracking-tight">
            Welcome back
          </h1>
          <p className="text-sm text-slate-500 mt-1.5 leading-relaxed">
            Sign in with your account. BrightLoop opens the customer portal or staff workspace assigned to you.
          </p>
        </div>

        {/* Success Banner */}
        {loginSuccess ? (
          <div
            role="status"
            className="mb-6 p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 flex items-start gap-3 animate-in fade-in"
          >
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            <div className="flex-1 text-sm">
              <p className="font-semibold text-emerald-900">Signed In Successfully</p>
              <p className="text-emerald-700 mt-0.5 text-xs leading-relaxed">
                Loading your BrightLoop workspace session...
              </p>
            </div>
          </div>
        ) : null}

        {/* General Error Banner */}
        {errors.general && (
          <div
            role="alert"
            className="mb-6 p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-800 flex items-start gap-2.5 animate-in fade-in"
          >
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
            <div className="flex-1 text-xs sm:text-sm font-medium text-red-700 leading-snug">
              {errors.general}
            </div>
            <button
              type="button"
              onClick={() => setErrors((prev) => ({ ...prev, general: undefined }))}
              className="text-red-400 hover:text-red-700 p-0.5 rounded transition-colors"
              aria-label="Dismiss error"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Form Body */}
        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          {/* Email field */}
          <div>
            <label
              htmlFor="email-input"
              className="block text-xs font-semibold uppercase tracking-wider text-[#172033] mb-1.5"
            >
              Work Email
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                <Mail className="w-4 h-4" />
              </div>
              <input
                id="email-input"
                name="email"
                type="email"
                autoComplete="email"
                disabled={isLoading}
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                  if (touched.email) {
                    setErrors((prev) => ({ ...prev, email: validateEmail(e.target.value) }))
                  }
                }}
                onBlur={handleEmailBlur}
                placeholder="name@company.com"
                aria-invalid={Boolean(touched.email && errors.email)}
                aria-describedby={touched.email && errors.email ? 'email-error' : undefined}
                className={`w-full pl-10 pr-4 py-2.5 text-sm rounded-xl border bg-slate-50/50 text-[#172033] placeholder:text-slate-400 transition-colors focus:bg-white focus:outline-none focus:ring-2 focus:ring-offset-1 ${
                  touched.email && errors.email
                    ? 'border-red-400 focus:border-red-500 focus:ring-red-200'
                    : 'border-[#E5E7EB] focus:border-[#4965F5] focus:ring-blue-100'
                } ${isLoading ? 'opacity-60 cursor-not-allowed' : ''}`}
              />
            </div>
            {touched.email && errors.email && (
              <p id="email-error" role="alert" className="mt-1.5 text-xs text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.email}</span>
              </p>
            )}
          </div>

          {/* Password field with show/hide toggle */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label
                htmlFor="password-input"
                className="block text-xs font-semibold uppercase tracking-wider text-[#172033]"
              >
                Password
              </label>
              <button
                type="button"
                onClick={onNavigateToRecovery}
                className="text-xs font-semibold text-[#4965F5] hover:text-[#3852de] hover:underline focus:outline-none focus:ring-2 focus:ring-[#4965F5] rounded"
              >
                Forgot password?
              </button>
            </div>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                <Lock className="w-4 h-4" />
              </div>
              <input
                id="password-input"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                disabled={isLoading}
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value)
                  if (touched.password) {
                    setErrors((prev) => ({ ...prev, password: validatePassword(e.target.value) }))
                  }
                }}
                onBlur={handlePasswordBlur}
                placeholder="Enter your password"
                aria-invalid={Boolean(touched.password && errors.password)}
                aria-describedby={touched.password && errors.password ? 'password-error' : undefined}
                className={`w-full pl-10 pr-10 py-2.5 text-sm rounded-xl border bg-slate-50/50 text-[#172033] placeholder:text-slate-400 transition-colors focus:bg-white focus:outline-none focus:ring-2 focus:ring-offset-1 ${
                  touched.password && errors.password
                    ? 'border-red-400 focus:border-red-500 focus:ring-red-200'
                    : 'border-[#E5E7EB] focus:border-[#4965F5] focus:ring-blue-100'
                } ${isLoading ? 'opacity-60 cursor-not-allowed' : ''}`}
              />
              <button
                type="button"
                onClick={() => setShowPassword((prev) => !prev)}
                className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-600 focus:outline-none focus:text-[#4965F5]"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {touched.password && errors.password && (
              <p id="password-error" role="alert" className="mt-1.5 text-xs text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.password}</span>
              </p>
            )}
          </div>

          {/* Remember me checkbox */}
          <div className="flex items-center pt-1">
            <label className="relative flex items-center gap-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                disabled={isLoading}
                className="w-4 h-4 rounded border-slate-300 text-[#4965F5] focus:ring-[#4965F5] focus:ring-offset-0 cursor-pointer"
              />
              <span className="text-xs sm:text-sm text-slate-600 font-medium">
                Remember me on this device
              </span>
            </label>
          </div>

          {/* Submit Button */}
          <div className="pt-2">
            <button
              type="submit"
              disabled={isLoading}
              className={`w-full py-3 px-4 rounded-xl text-white font-semibold text-sm transition-all duration-200 shadow-md shadow-blue-500/25 flex items-center justify-center gap-2 ${
                isLoading
                  ? 'bg-[#4965F5]/80 cursor-wait'
                  : 'bg-[#4965F5] hover:bg-[#3852de] active:scale-[0.99] focus:outline-none focus:ring-4 focus:ring-blue-100'
              }`}
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Signing in...</span>
                </>
              ) : (
                <span>Sign in to BrightLoop</span>
              )}
            </button>
          </div>
        </form>

        {/* Divider */}
        <div className="relative my-6 text-center">
          <div className="absolute inset-0 flex items-center" aria-hidden="true">
            <div className="w-full border-t border-[#E5E7EB]" />
          </div>
          <span className="relative bg-white px-3 text-xs uppercase font-medium tracking-wider text-slate-400">
            New to BrightLoop?
          </span>
        </div>

        {/* Create an account link */}
        <div className="text-center">
          <button
            type="button"
            onClick={onNavigateToSignup}
            className="w-full py-2.5 px-4 rounded-xl border border-[#E5E7EB] bg-slate-50/60 hover:bg-slate-100 text-[#172033] font-semibold text-xs sm:text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-[#4965F5]"
          >
            Create an account
          </button>
        </div>
      </div>

      {/* Trust & Security footer notice */}
      <p className="text-center text-[11px] text-slate-400 mt-5">
        Secure sign-in with protected session cookies.
      </p>
    </div>
  )
}
