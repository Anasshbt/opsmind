import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { useAuthStore } from '@/store/auth'

import { LoginPage } from '@/pages/LoginPage'
import { LabPage } from '@/pages/LabPage'
// Lazy imports for code splitting
import { lazy, Suspense } from 'react'
import { Loader2 } from 'lucide-react'

const Dashboard = lazy(() => import('@/pages/Dashboard').then(m => ({ default: m.Dashboard })))
const CoursesPage = lazy(() => import('@/pages/CoursesPage').then(m => ({ default: m.CoursesPage })))
const LabsListPage = lazy(() => import('@/pages/LabsListPage').then(m => ({ default: m.LabsListPage })))
const EnterprisePage = lazy(() => import('@/pages/EnterprisePage').then(m => ({ default: m.EnterprisePage })))
const RegisterPage = lazy(() => import('@/pages/RegisterPage').then(m => ({ default: m.RegisterPage })))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
})

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-screen bg-gray-950">
      <Loader2 className="w-8 h-8 animate-spin text-brand-500" />
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            {/* Public */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />

            {/* Protected */}
            <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
            <Route path="/courses" element={<PrivateRoute><CoursesPage /></PrivateRoute>} />
            <Route path="/labs" element={<PrivateRoute><LabsListPage /></PrivateRoute>} />
            <Route path="/labs/:labId" element={<PrivateRoute><LabPage /></PrivateRoute>} />
            <Route path="/enterprise" element={<PrivateRoute><EnterprisePage /></PrivateRoute>} />

            {/* Fallbacks */}
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          style: { background: '#1f2937', color: '#f9fafb', border: '1px solid #374151' },
        }}
      />
    </QueryClientProvider>
  )
}
