import React, { useState } from 'react'
import { Eye, EyeOff, Lock, Mail, User, Loader2, AlertCircle, CheckCircle2, Check, X } from 'lucide-react'
import { useAuth } from '../context/useAuth.ts'
import { formatApiError } from '../api/auth.ts'
import { hasPasswordPunctuation } from '../utils/password.ts'

interface SignupFormProps {
  onNavigateToLogin: () => void
}

interface ValidationErrors {
  fullName?: string
  email?: string
  password?: string
  confirmPassword?: string
  general?: string
}

export const SignupForm: React.FC<SignupFormProps> = ({ onNavigateToLogin }) => {
  const { register } = useAuth()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)

  const [errors, setErrors] = useState<ValidationErrors>({})
  const [touched, setTouched] = useState<{
    fullName?: boolean
    email?: boolean
    password?: boolean
    confirmPassword?: boolean
  }>({})

  const [isLoading, setIsLoading] = useState(false)
  const [signupSuccess, setSignupSuccess] = useState(false)

  // Password rules breakdown
  const hasMinLength = password.length >= 9
  const hasUppercase = /[A-Z]/.test(password)
  const hasLowercase = /[a-z]/.test(password)
  const hasSpecialChar = hasPasswordPunctuation(password)
  const isPasswordValid = hasMinLength && hasUppercase && hasLowercase && hasSpecialChar

  // Validation functions
  const validateFullName = (val: string): string | undefined => {
    if (!val.trim()) {
      return 'Full name is required.'
    }
    if (val.trim().length < 2) {
      return 'Please enter at least 2 characters.'
    }
    return undefined
  }

  const validateEmail = (val: string): string | undefined => {
    if (!val.trim()) {
      return 'Work email is required.'
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(val.trim())) {
      return 'Please enter a valid email address (e.g., name@company.com).'
    }
    return undefined
  }

  const validatePassword = (val: string): string | undefined => {
    if (!val) {
      return 'Password is required.'
    }
    if (val.length < 9) {
      return 'Password must be at least 9 characters.'
    }
    if (!/[A-Z]/.test(val)) {
      return 'Password must include at least one uppercase letter.'
    }
    if (!/[a-z]/.test(val)) {
      return 'Password must include at least one lowercase letter.'
    }
    if (!hasPasswordPunctuation(val)) {
      return 'Password must include at least one special character.'
    }
    return undefined
  }

  const validateConfirmPassword = (val: string, currentPassword: string): string | undefined => {
    if (!val) {
      return 'Please confirm your password.'
    }
    if (val !== currentPassword) {
      return 'Passwords do not match.'
    }
    return undefined
  }

  const handleBlur = (field: keyof typeof touched) => {
    setTouched((prev) => ({ ...prev, [field]: true }))
    let err: string | undefined

    if (field === 'fullName') err = validateFullName(fullName)
    if (field === 'email') err = validateEmail(email)
    if (field === 'password') err = validatePassword(password)
    if (field === 'confirmPassword') err = validateConfirmPassword(confirmPassword, password)

    setErrors((prev) => ({ ...prev, [field]: err }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    const nameErr = validateFullName(fullName)
    const emailErr = validateEmail(email)
    const passErr = validatePassword(password)
    const confirmErr = validateConfirmPassword(confirmPassword, password)

    setTouched({
      fullName: true,
      email: true,
      password: true,
      confirmPassword: true,
    })

    setErrors({
      fullName: nameErr,
      email: emailErr,
      password: passErr,
      confirmPassword: confirmErr,
    })

    if (nameErr || emailErr || passErr || confirmErr) {
      return
    }

    setIsLoading(true)
    setErrors({})

    try {
      await register({
        full_name: fullName.trim(),
        email: email.trim(),
        password,
      })
      setSignupSuccess(true)
    } catch (err: unknown) {
      const formatted = formatApiError(err)
      const newErrors: ValidationErrors = {
        general: formatted.message,
      }

      if (formatted.fieldErrors) {
        if (formatted.fieldErrors.full_name || formatted.fieldErrors.name) {
          newErrors.fullName = (formatted.fieldErrors.full_name || formatted.fieldErrors.name)?.[0]
        }
        if (formatted.fieldErrors.email) {
          newErrors.email = formatted.fieldErrors.email[0]
        }
        if (formatted.fieldErrors.password) {
          newErrors.password = formatted.fieldErrors.password[0]
        }
      }

      setErrors(newErrors)
      setSignupSuccess(false)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="w-full max-w-[440px] mx-auto">
      {/* Main Signup Card */}
      <div className="bg-white rounded-2xl border border-[#E5E7EB] shadow-xl shadow-slate-200/50 p-6 sm:p-8 transition-all">
        {/* Card Header */}
        <div className="mb-6">
          <h1 className="text-2xl sm:text-3xl font-extrabold text-[#172033] tracking-tight">
            Create an account
          </h1>
          <p className="text-sm text-slate-500 mt-1.5 leading-relaxed">
            Create an account to access your BrightLoop workspace.
          </p>
        </div>

        {/* Validation / Success Banner */}
        {signupSuccess ? (
          <div
            role="status"
            className="mb-6 p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 flex items-start gap-3 animate-in fade-in"
          >
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            <div className="flex-1 text-sm">
              <p className="font-semibold text-emerald-900">Account Created Successfully</p>
              <p className="text-emerald-700 mt-0.5 text-xs leading-relaxed">
                Your BrightLoop account has been registered. You can now sign in to your workspace.
              </p>
              <div className="mt-3 flex items-center gap-3">
                <button
                  type="button"
                  onClick={onNavigateToLogin}
                  className="text-xs font-semibold px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  Proceed to Login
                </button>
                <button
                  type="button"
                  onClick={() => setSignupSuccess(false)}
                  className="text-xs font-medium text-emerald-800 underline hover:text-emerald-950"
                >
                  Edit details
                </button>
              </div>
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
          {/* Full Name */}
          <div>
            <label
              htmlFor="signup-name-input"
              className="block text-xs font-semibold uppercase tracking-wider text-[#172033] mb-1.5"
            >
              Full Name
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                <User className="w-4 h-4" />
              </div>
              <input
                id="signup-name-input"
                name="fullName"
                type="text"
                autoComplete="name"
                disabled={isLoading}
                value={fullName}
                onChange={(e) => {
                  setFullName(e.target.value)
                  if (touched.fullName) {
                    setErrors((prev) => ({ ...prev, fullName: validateFullName(e.target.value) }))
                  }
                }}
                onBlur={() => handleBlur('fullName')}
                placeholder="Jane Doe"
                aria-invalid={Boolean(touched.fullName && errors.fullName)}
                aria-describedby={touched.fullName && errors.fullName ? 'name-error' : undefined}
                className={`w-full pl-10 pr-4 py-2.5 text-sm rounded-xl border bg-slate-50/50 text-[#172033] placeholder:text-slate-400 transition-colors focus:bg-white focus:outline-none focus:ring-2 focus:ring-offset-1 ${
                  touched.fullName && errors.fullName
                    ? 'border-red-400 focus:border-red-500 focus:ring-red-200'
                    : 'border-[#E5E7EB] focus:border-[#4965F5] focus:ring-blue-100'
                } ${isLoading ? 'opacity-60 cursor-not-allowed' : ''}`}
              />
            </div>
            {touched.fullName && errors.fullName && (
              <p id="name-error" role="alert" className="mt-1.5 text-xs text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.fullName}</span>
              </p>
            )}
          </div>

          {/* Email Address */}
          <div>
            <label
              htmlFor="signup-email-input"
              className="block text-xs font-semibold uppercase tracking-wider text-[#172033] mb-1.5"
            >
              Work Email
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                <Mail className="w-4 h-4" />
              </div>
              <input
                id="signup-email-input"
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
                onBlur={() => handleBlur('email')}
                placeholder="name@company.com"
                aria-invalid={Boolean(touched.email && errors.email)}
                aria-describedby={touched.email && errors.email ? 'signup-email-error' : undefined}
                className={`w-full pl-10 pr-4 py-2.5 text-sm rounded-xl border bg-slate-50/50 text-[#172033] placeholder:text-slate-400 transition-colors focus:bg-white focus:outline-none focus:ring-2 focus:ring-offset-1 ${
                  touched.email && errors.email
                    ? 'border-red-400 focus:border-red-500 focus:ring-red-200'
                    : 'border-[#E5E7EB] focus:border-[#4965F5] focus:ring-blue-100'
                } ${isLoading ? 'opacity-60 cursor-not-allowed' : ''}`}
              />
            </div>
            {touched.email && errors.email && (
              <p id="signup-email-error" role="alert" className="mt-1.5 text-xs text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.email}</span>
              </p>
            )}
          </div>

          {/* Password with show/hide toggle */}
          <div>
            <label
              htmlFor="signup-password-input"
              className="block text-xs font-semibold uppercase tracking-wider text-[#172033] mb-1.5"
            >
              Password
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                <Lock className="w-4 h-4" />
              </div>
              <input
                id="signup-password-input"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                disabled={isLoading}
                value={password}
                onChange={(e) => {
                  const val = e.target.value
                  setPassword(val)
                  if (touched.password) {
                    setErrors((prev) => ({ ...prev, password: validatePassword(val) }))
                  }
                  if (touched.confirmPassword && confirmPassword) {
                    setErrors((prev) => ({
                      ...prev,
                      confirmPassword: validateConfirmPassword(confirmPassword, val),
                    }))
                  }
                }}
                onBlur={() => handleBlur('password')}
                placeholder="Minimum 9 characters"
                aria-invalid={Boolean(touched.password && errors.password)}
                aria-describedby="password-requirements"
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

            {/* Live Password Requirements Checklist */}
            <div id="password-requirements" className="mt-2.5 p-2.5 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-[11px] font-semibold text-slate-600 block mb-1.5">
                Password must contain:
              </span>
              <div className="grid grid-cols-2 gap-1.5 text-[11px]">
                <div
                  className={`flex items-center gap-1.5 transition-colors ${
                    hasMinLength ? 'text-emerald-600 font-medium' : 'text-slate-500'
                  }`}
                >
                  <span
                    className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[9px] ${
                      hasMinLength ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-200 text-slate-400'
                    }`}
                  >
                    <Check className="w-2.5 h-2.5" />
                  </span>
                  <span>9+ characters</span>
                </div>

                <div
                  className={`flex items-center gap-1.5 transition-colors ${
                    hasUppercase ? 'text-emerald-600 font-medium' : 'text-slate-500'
                  }`}
                >
                  <span
                    className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[9px] ${
                      hasUppercase ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-200 text-slate-400'
                    }`}
                  >
                    <Check className="w-2.5 h-2.5" />
                  </span>
                  <span>Uppercase (A-Z)</span>
                </div>

                <div
                  className={`flex items-center gap-1.5 transition-colors ${
                    hasLowercase ? 'text-emerald-600 font-medium' : 'text-slate-500'
                  }`}
                >
                  <span
                    className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[9px] ${
                      hasLowercase ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-200 text-slate-400'
                    }`}
                  >
                    <Check className="w-2.5 h-2.5" />
                  </span>
                  <span>Lowercase (a-z)</span>
                </div>

                <div
                  className={`flex items-center gap-1.5 transition-colors ${
                    hasSpecialChar ? 'text-emerald-600 font-medium' : 'text-slate-500'
                  }`}
                >
                  <span
                    className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[9px] ${
                      hasSpecialChar ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-200 text-slate-400'
                    }`}
                  >
                    <Check className="w-2.5 h-2.5" />
                  </span>
                  <span>Special (!@#$)</span>
                </div>
              </div>
            </div>

            {touched.password && errors.password && !isPasswordValid && (
              <p role="alert" className="mt-1.5 text-xs text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.password}</span>
              </p>
            )}
          </div>

          {/* Confirm Password with show/hide toggle */}
          <div>
            <label
              htmlFor="signup-confirm-password-input"
              className="block text-xs font-semibold uppercase tracking-wider text-[#172033] mb-1.5"
            >
              Confirm Password
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                <Lock className="w-4 h-4" />
              </div>
              <input
                id="signup-confirm-password-input"
                name="confirmPassword"
                type={showConfirmPassword ? 'text' : 'password'}
                autoComplete="new-password"
                disabled={isLoading}
                value={confirmPassword}
                onChange={(e) => {
                  const val = e.target.value
                  setConfirmPassword(val)
                  if (touched.confirmPassword) {
                    setErrors((prev) => ({
                      ...prev,
                      confirmPassword: validateConfirmPassword(val, password),
                    }))
                  }
                }}
                onBlur={() => handleBlur('confirmPassword')}
                placeholder="Re-enter your password"
                aria-invalid={Boolean(touched.confirmPassword && errors.confirmPassword)}
                aria-describedby={touched.confirmPassword && errors.confirmPassword ? 'confirm-error' : undefined}
                className={`w-full pl-10 pr-10 py-2.5 text-sm rounded-xl border bg-slate-50/50 text-[#172033] placeholder:text-slate-400 transition-colors focus:bg-white focus:outline-none focus:ring-2 focus:ring-offset-1 ${
                  touched.confirmPassword && errors.confirmPassword
                    ? 'border-red-400 focus:border-red-500 focus:ring-red-200'
                    : 'border-[#E5E7EB] focus:border-[#4965F5] focus:ring-blue-100'
                } ${isLoading ? 'opacity-60 cursor-not-allowed' : ''}`}
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword((prev) => !prev)}
                className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-600 focus:outline-none focus:text-[#4965F5]"
                aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
              >
                {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {touched.confirmPassword && errors.confirmPassword && (
              <p id="confirm-error" role="alert" className="mt-1.5 text-xs text-red-600 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.confirmPassword}</span>
              </p>
            )}
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
                  <span>Creating your account...</span>
                </>
              ) : (
                <span>Create Account</span>
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
            Already have an account?
          </span>
        </div>

        {/* Link to existing Login screen */}
        <div className="text-center">
          <button
            type="button"
            onClick={onNavigateToLogin}
            className="w-full py-2.5 px-4 rounded-xl border border-[#E5E7EB] bg-slate-50/60 hover:bg-slate-100 text-[#172033] font-semibold text-xs sm:text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-[#4965F5]"
          >
            Sign in to existing workspace
          </button>
        </div>
      </div>

      {/* Trust & Security footer notice */}
      <p className="text-center text-[11px] text-slate-400 mt-5">
        Protected by enterprise-grade 256-bit encryption. SOC2 Type II Certified.
      </p>
    </div>
  )
}
