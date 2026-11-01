import React, { useState, useEffect } from 'react'
import { BrandLogo } from './components/BrandLogo.tsx'
import { SubscriptionIllustration } from './components/SubscriptionIllustration.tsx'
import { LoginForm } from './components/LoginForm.tsx'
import { SignupForm } from './components/SignupForm.tsx'
import { PasswordRecoveryForm } from './components/PasswordRecoveryForm.tsx'
import { WorkspaceDashboard } from './components/WorkspaceDashboard.tsx'
import { ProtectedRoute } from './components/ProtectedRoute.tsx'
import { AuthProvider } from './context/AuthContext.tsx'
import { useAuth } from './context/useAuth.ts'
import { CheckCircle2, ShieldCheck, Zap } from 'lucide-react'

type AuthScreen = 'login' | 'signup' | 'recovery'

function getInitialAuthScreen(): AuthScreen {
  if (typeof window === 'undefined') return 'login'
  const hashRoute = window.location.hash.slice(1).split('?')[0].toLowerCase()
  const search = window.location.search.toLowerCase()
  if (hashRoute === 'reset-password' || hashRoute === 'password-reset') return 'recovery'
  if (hashRoute.includes('signup') || search.includes('signup') || search.includes('register')) return 'signup'
  return 'login'
}

function getResetLinkParams() {
  if (typeof window === 'undefined') return { uid: '', token: '' }
  const query = window.location.hash.split('?').slice(1).join('?')
  const params = new URLSearchParams(query)
  return { uid: params.get('uid') || '', token: params.get('token') || '' }
}

const MainScreen: React.FC = () => {
  const { isAuthenticated, isLoading, logout } = useAuth()

  // Supports state-based switching with hash/path detection fallback
  const [currentScreen, setCurrentScreen] = useState<AuthScreen>(getInitialAuthScreen)

  // Sync hash when screen changes so users can bookmark or reload
  useEffect(() => {
    if (currentScreen === 'recovery') {
      // Keep the one-time uid and token in the hash while the reset form is open.
      const hash = window.location.hash.toLowerCase()
      if (hash.startsWith('#reset-password?')) return
      window.history.replaceState(null, '', '#password-reset')
    } else if (isAuthenticated) {
      window.history.replaceState(null, '', '#workspace')
    } else if (currentScreen === 'signup') {
      window.history.replaceState(null, '', '#signup')
    } else {
      window.history.replaceState(null, '', '#login')
    }
  }, [currentScreen, isAuthenticated])

  async function returnToLogin() {
    if (isAuthenticated) await logout()
    setCurrentScreen('login')
  }

  // If user is authenticated, render the protected workspace dashboard
  if (isAuthenticated && currentScreen !== 'recovery') {
    return (
      <ProtectedRoute>
        <WorkspaceDashboard />
      </ProtectedRoute>
    )
  }

  return (
    <div className="min-h-screen w-full flex flex-col lg:flex-row bg-[#F7F9FC] overflow-x-hidden">
      {/* ========================================================= */}
      {/* LEFT COLUMN: BRANDING & SUBSCRIPTION CYCLE VISUALS        */}
      {/* ========================================================= */}
      <section
        aria-label="BrightLoop Platform Highlights"
        className="relative lg:w-1/2 xl:w-[52%] bg-[#101828] text-white flex flex-col justify-between p-6 sm:p-10 lg:p-14 overflow-hidden border-b lg:border-b-0 lg:border-r border-[#1E2C48]"
      >
        {/* Subtle decorative radial gradients */}
        <div
          className="absolute -top-24 -left-24 w-96 h-96 rounded-full bg-[#4965F5]/25 blur-3xl pointer-events-none"
          aria-hidden="true"
        />
        <div
          className="absolute -bottom-24 -right-24 w-96 h-96 rounded-full bg-[#38BDF8]/20 blur-3xl pointer-events-none"
          aria-hidden="true"
        />

        {/* Top Header: BrightLoop Logo */}
        <header className="relative z-10 flex items-center justify-between">
          <BrandLogo variant="dark" size="md" showBadge />
          <div className="hidden sm:flex items-center gap-2 text-xs font-medium text-slate-400 bg-white/5 border border-white/10 px-3 py-1.5 rounded-full">
            <span>Subscriptions · Billing · Customer portal</span>
          </div>
        </header>

        {/* Center: Main Headline, Supporting Copy & Abstract Illustration */}
        <div className="relative z-10 my-8 lg:my-auto max-w-xl">
          <div className="space-y-4 mb-6 lg:mb-8 text-center lg:text-left">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#4965F5]/15 border border-[#4965F5]/30 text-xs font-semibold text-[#38BDF8]">
              <Zap className="w-3.5 h-3.5 text-[#38BDF8]" />
              <span>Subscription billing workspace</span>
            </div>

            <h2 className="text-3xl sm:text-4xl xl:text-5xl font-black text-white tracking-tight leading-[1.15]">
              Manage subscriptions.{' '}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-[#60A5FA] via-[#38BDF8] to-[#93C5FD]">
                Simplify growth.
              </span>
            </h2>

            <p className="text-sm sm:text-base text-slate-300 max-w-lg mx-auto lg:mx-0 leading-relaxed">
              Manage customer records, subscription changes, invoices, and recurring billing in one workspace.
            </p>
          </div>

          {/* Abstract Subscription Cycles Illustration */}
          <div className="hidden md:block">
            <SubscriptionIllustration />
          </div>

          {/* Quick highlight checklist on mobile/tablet */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-6 text-xs text-slate-300 md:hidden">
            <div className="flex items-center gap-2 bg-white/5 p-2.5 rounded-lg border border-white/10">
              <CheckCircle2 className="w-4 h-4 text-[#38BDF8] shrink-0" />
              <span>Scheduled billing scans</span>
            </div>
            <div className="flex items-center gap-2 bg-white/5 p-2.5 rounded-lg border border-white/10">
              <CheckCircle2 className="w-4 h-4 text-[#38BDF8] shrink-0" />
              <span>Customer lifecycle controls</span>
            </div>
          </div>
        </div>

        {/* Bottom Left Footer: Compliance & Security badges */}
        <footer className="relative z-10 pt-4 border-t border-white/10 flex flex-wrap items-center justify-between gap-4 text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-[#38BDF8]" />
            <span>Separate workspaces for staff and customers</span>
          </div>
        </footer>
      </section>

      {/* ========================================================= */}
      {/* RIGHT COLUMN: CLEAN MODERN AUTH CARD (LOGIN / SIGNUP)     */}
      {/* ========================================================= */}
      <main
        aria-label={currentScreen === 'signup' ? 'BrightLoop Sign Up' : currentScreen === 'recovery' ? 'Password recovery' : 'BrightLoop Sign In'}
        className="lg:w-1/2 xl:w-[48%] flex flex-col justify-center items-center p-6 sm:p-10 lg:p-14"
      >
        {/* Mobile branding header displayed on mobile devices */}
        <div className="lg:hidden mb-6 flex justify-center">
          <BrandLogo variant="light" size="md" />
        </div>

        {/* Conditional rendering between Login and Signup */}
        {isLoading ? (
          <div className="w-full max-w-[440px] mx-auto bg-white rounded-2xl border border-[#E5E7EB] p-8 text-center text-slate-500 text-sm flex items-center justify-center gap-2">
            <span className="w-4 h-4 border-2 border-[#4965F5] border-t-transparent rounded-full animate-spin" />
            <span>Verifying session...</span>
          </div>
        ) : currentScreen === 'signup' ? (
          <SignupForm onNavigateToLogin={() => setCurrentScreen('login')} />
        ) : currentScreen === 'recovery' ? (
          <PasswordRecoveryForm
            {...getResetLinkParams()}
            onNavigateToLogin={() => void returnToLogin()}
          />
        ) : (
          <LoginForm onNavigateToSignup={() => setCurrentScreen('signup')} onNavigateToRecovery={() => setCurrentScreen('recovery')} />
        )}
      </main>
    </div>
  )
}

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <MainScreen />
    </AuthProvider>
  )
}

export default App
