import { useState } from 'react'
import { FileText, Layers, LayoutDashboard, LogOut, Users, Loader2 } from 'lucide-react'
import { useAuth } from '../context/useAuth.ts'
import { BrandLogo } from './BrandLogo.tsx'
import { RoleProtectedRoute } from './ProtectedRoute.tsx'
import { CustomerDirectory } from './customers/CustomerDirectory.tsx'
import { ReportsView } from './reports/ReportsView.tsx'
import { SubscriptionWorkspace } from './SubscriptionWorkspace.tsx'
import { InvoiceWorkspace } from './invoices/InvoiceWorkspace.tsx'
import { CustomerPortal } from './portal/CustomerPortal.tsx'
import type { UserRole } from '../types/auth.ts'

type WorkspaceTab = 'overview' | 'customers' | 'subscriptions' | 'invoices'

const navigation: Array<{ id: WorkspaceTab; label: string; icon: typeof LayoutDashboard; roles: UserRole[] }> = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, roles: ['staff', 'admin'] },
  { id: 'subscriptions', label: 'Subscriptions', icon: Layers, roles: ['staff', 'admin'] },
  { id: 'invoices', label: 'Invoices', icon: FileText, roles: ['staff', 'admin'] },
  { id: 'customers', label: 'Customers', icon: Users, roles: ['staff', 'admin'] },
]

export function WorkspaceDashboard() {
  const { user, role, logout } = useAuth()
  const currentRole = (role || 'admin') as UserRole
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('overview')
  const [loggingOut, setLoggingOut] = useState(false)

  async function signOut() {
    setLoggingOut(true)
    try { await logout() } finally { setLoggingOut(false) }
  }

  if (currentRole === 'customer') return <CustomerPortal />

  const displayName = user?.full_name || user?.name || user?.email?.split('@')[0] || 'Team member'
  const visibleNavigation = navigation.filter(item => item.roles.includes(currentRole))

  return <div className="min-h-screen bg-slate-50 text-slate-900">
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-4 px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex shrink-0 items-center gap-4"><BrandLogo variant="light" size="md" showBadge/><span className="hidden h-6 w-px bg-slate-200 sm:block"/><span className="hidden text-sm font-medium text-slate-500 sm:block">Subscription workspace</span></div>
        <nav aria-label="Workspace" className="order-3 flex w-full items-center gap-1 overflow-x-auto border-t border-slate-100 pt-2 sm:order-2 sm:ml-4 sm:w-auto sm:flex-1 sm:border-0 sm:pt-0">
          {visibleNavigation.map(({ id, label, icon: Icon }) => <button key={id} type="button" onClick={() => setActiveTab(id)} aria-current={activeTab === id ? 'page' : undefined} className={`inline-flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${activeTab === id ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`}><Icon size={16}/>{label}</button>)}
        </nav>
        <div className="ml-auto flex shrink-0 items-center gap-3 sm:order-3">
          <div className="hidden text-right sm:block"><p className="text-sm font-semibold leading-5">{displayName}</p><p className="text-xs capitalize text-slate-500">{currentRole} access</p></div>
          <div className="grid h-9 w-9 place-items-center rounded-full bg-indigo-100 text-sm font-bold text-indigo-700">{displayName.charAt(0).toUpperCase()}</div>
          <button type="button" onClick={() => void signOut()} disabled={loggingOut} className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50" title="Sign out">{loggingOut ? <Loader2 size={16} className="animate-spin"/> : <LogOut size={16}/>}<span className="hidden md:inline">Sign out</span></button>
        </div>
      </div>
    </header>

    <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      {activeTab === 'overview' && <RoleProtectedRoute roles={['staff', 'admin']}><ReportsView/></RoleProtectedRoute>}
      {activeTab === 'subscriptions' && <RoleProtectedRoute roles={['staff', 'admin']}><SubscriptionWorkspace/></RoleProtectedRoute>}
      {activeTab === 'invoices' && <RoleProtectedRoute roles={['staff', 'admin']}><InvoiceWorkspace/></RoleProtectedRoute>}
      {activeTab === 'customers' && <RoleProtectedRoute roles={['staff', 'admin']}><CustomerDirectory/></RoleProtectedRoute>}
    </main>
  </div>
}
