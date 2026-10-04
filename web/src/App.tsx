import { lazy, Suspense, type ReactElement } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from '@/components/shell/AppShell'
import Fleet from '@/pages/Fleet'
import Impact from '@/pages/Impact'
import Plan from '@/pages/Plan'
import DecisionLog from '@/pages/DecisionLog'
import Roster from '@/pages/Roster'
import WorkOrders from '@/pages/WorkOrders'
import Summary from '@/pages/Summary'
import Settings from '@/pages/Settings'
import SignIn from '@/pages/SignIn'
import Placeholder from '@/pages/Placeholder'
import { isSignedIn } from '@/lib/auth'

// Heavy or rarely used routes load on demand so the manager dashboard bundle stays small.
const Phone = lazy(() => import('@/pages/Phone'))
const TestMode = lazy(() => import('@/pages/TestMode'))
const Styleguide = lazy(() => import('@/pages/design/Styleguide'))
const VoiceSmoke = lazy(() => import('@/pages/dev/VoiceSmoke'))

// "Sign in" is a one-click demonstration gate for the manager's pages only (the phone page and Test mode have their own entry).
const RequireSignIn = ({ children }: { children: ReactElement }) => (isSignedIn() ? children : <Navigate to="/signin" replace />)

export default function App() {
  return (
    <Suspense fallback={null}>
      <Routes>
        {/* Dev-only voice smoke test (plan P1.11) */}
        {import.meta.env.DEV && <Route path="/dev/voice" element={<VoiceSmoke />} />}
        <Route path="/signin" element={<SignIn />} />
        <Route path="/design" element={<Styleguide />} />
        {/* Technician phone page: mobile-first, no manager nav */}
        <Route path="/field/:fieldPageId" element={<Phone />} />
        {/* Test mode: not in the manager's menu, needs the admin token */}
        <Route path="/test" element={<TestMode />} />
        <Route element={<RequireSignIn><AppShell /></RequireSignIn>}>
          <Route index element={<Fleet />} />
          <Route path="impact" element={<Impact />} />
          <Route path="plan" element={<Plan />} />
          <Route path="log" element={<DecisionLog />} />
          <Route path="roster" element={<Roster />} />
          <Route path="orders" element={<WorkOrders />} />
          <Route path="summary" element={<Summary />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Placeholder title="Page not found" />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
