import { useState } from 'react'
import {
  FileText,
  CreditCard,
  Layers,
  LayoutDashboard,
  Loader2,
  LogOut,
  Users,
} from 'lucide-react'
import { useAuth } from '../context/useAuth.ts'
import { BrandLogo } from './BrandLogo.tsx'
import { RoleProtectedRoute } from './ProtectedRoute.tsx'
import { CustomerDirectory } from './customers/CustomerDirectory.tsx'
import { ReportsView } from './reports/ReportsView.tsx'
import { SubscriptionWorkspace } from './SubscriptionWorkspace.tsx'
import { InvoiceWorkspace } from './invoices/InvoiceWorkspace.tsx'
import { PaymentsWorkspace } from './invoices/PaymentsWorkspace.tsx'
import { CustomerPortal } from './portal/CustomerPortal.tsx'
import type { UserRole } from '../types/auth.ts'

type WorkspaceTab = 'overview' | 'subscriptions' | 'invoices' | 'payments' | 'customers'

const navigation: Array<{
  id: WorkspaceTab
  label: string
  icon: typeof LayoutDashboard
  description: string
}> = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, description: 'Billing health and activity' },
  { id: 'subscriptions', label: 'Subscriptions', icon: Layers, description: 'Plans and billing schedules' },
  { id: 'invoices', label: 'Invoices', icon: FileText, description: 'Payments and balances' },
  { id: 'payments', label: 'Payments', icon: CreditCard, description: 'Receipts and references' },
  { id: 'customers', label: 'Customers', icon: Users, description: 'Customer records' },
]

export function WorkspaceDashboard() {
  const { user, role, logout } = useAuth()
  // Unknown roles receive the customer experience until the server confirms otherwise.
  const currentRole: UserRole = role || 'customer'
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('overview')
  const [loggingOut, setLoggingOut] = useState(false)

  async function signOut() {
    setLoggingOut(true)
    try {
      await logout()
    } finally {
      setLoggingOut(false)
    }
  }

  if (currentRole === 'customer') return <CustomerPortal />

  const displayName = user?.full_name || user?.name || user?.email?.split('@')[0] || 'Team member'
  const navButton = (item: (typeof navigation)[number], compact = false) => {
    const Icon = item.icon
    const active = activeTab === item.id
    return (
      <button
        key={item.id}
        type="button"
        onClick={() => setActiveTab(item.id)}
        aria-current={active ? 'page' : undefined}
        className={`group flex shrink-0 items-center gap-3 rounded-xl text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${compact ? 'px-3 py-2 text-sm' : 'w-full px-3 py-3'} ${active ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-950'}`}
      >
        <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${active ? 'bg-white text-indigo-700 shadow-sm' : 'bg-transparent text-slate-500 group-hover:text-slate-800'}`}>
          <Icon size={18} strokeWidth={1.9} />
        </span>
        <span className="min-w-0">
          <span className="block font-semibold">{item.label}</span>
          {!compact && <span className={`mt-0.5 block truncate text-xs ${active ? 'text-indigo-600/80' : 'text-slate-400'}`}>{item.description}</span>}
        </span>
      </button>
    )
  }

  return (
    <div className="min-h-screen bg-[#f6f7fb] text-slate-900">
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/95 backdrop-blur lg:hidden">
        <div className="flex min-h-16 items-center justify-between gap-3 px-4 sm:px-6">
          <BrandLogo variant="light" size="md" showBadge />
          <div className="flex items-center gap-2">
            <span className="hidden max-w-36 truncate text-sm font-medium text-slate-600 sm:block">{displayName}</span>
            <button
              type="button"
              onClick={() => void signOut()}
              disabled={loggingOut}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              title="Sign out"
            >
              {loggingOut ? <Loader2 size={16} className="animate-spin" /> : <LogOut size={16} />}
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>
        <nav aria-label="Workspace" className="flex gap-1 overflow-x-auto border-t border-slate-100 px-3 py-2">
          {navigation.map(item => navButton(item, true))}
        </nav>
      </header>

      <div className="mx-auto flex min-h-screen max-w-[1680px]">
        <aside className="sticky top-0 hidden h-screen w-[264px] shrink-0 flex-col border-r border-slate-200/80 bg-white px-4 py-6 lg:flex">
          <div className="px-2"><BrandLogo variant="light" size="md" showBadge /></div>
          <div className="mt-9 px-3 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400">Workspace</div>
          <nav aria-label="Workspace" className="mt-3 space-y-1">
            {navigation.map(item => navButton(item))}
          </nav>
          <div className="mt-auto rounded-2xl border border-slate-200 bg-slate-50 p-3">
            <div className="flex items-center gap-3">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-indigo-100 font-semibold text-indigo-700">
                {displayName.charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-slate-900">{displayName}</p>
                <p className="truncate text-xs capitalize text-slate-500">{currentRole} account</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => void signOut()}
              disabled={loggingOut}
              className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50"
            >
              {loggingOut ? <Loader2 size={16} className="animate-spin" /> : <LogOut size={16} />}
              Sign out
            </button>
          </div>
        </aside>

        <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-9" id="main-content" tabIndex={-1}>
          <div className="mx-auto max-w-[1320px]">
            {activeTab === 'overview' && <RoleProtectedRoute roles={['staff', 'admin']}><ReportsView /></RoleProtectedRoute>}
            {activeTab === 'subscriptions' && <RoleProtectedRoute roles={['staff', 'admin']}><SubscriptionWorkspace /></RoleProtectedRoute>}
            {activeTab === 'invoices' && <RoleProtectedRoute roles={['staff', 'admin']}><InvoiceWorkspace /></RoleProtectedRoute>}
            {activeTab === 'payments' && <RoleProtectedRoute roles={['staff', 'admin']}><PaymentsWorkspace /></RoleProtectedRoute>}
            {activeTab === 'customers' && <RoleProtectedRoute roles={['staff', 'admin']}><CustomerDirectory /></RoleProtectedRoute>}
          </div>
        </main>
      </div>
    </div>
  )
}
