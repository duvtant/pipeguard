import { Link, Route, Routes } from 'react-router-dom'
import Placeholder from '@/pages/Placeholder'
import VoiceSmoke from '@/pages/dev/VoiceSmoke'

// Manager dashboard routes + the technician phone page. Pages are stubs: see
// docs/delegation/03_DAVID_dashboard-voice-pitch.md section 3.4 for what each one shows.
const NAV = [
  ['/', 'Fleet'],
  ['/impact', 'Impact'],
  ['/plan', 'Plan'],
  ['/log', 'Decision log'],
  ['/roster', 'Roster'],
  ['/orders', 'Work orders'],
  ['/settings', 'Settings'],
] as const

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <Routes>
        {/* Dev-only voice smoke test (plan P1.11); removed or hidden before the freeze */}
        {import.meta.env.DEV && <Route path="/dev/voice" element={<VoiceSmoke />} />}
        {/* Technician phone page: mobile-first, no manager nav */}
        <Route path="/field/:fieldPageId" element={<Placeholder title="Technician phone page" />} />
        {/* Test mode: not in the manager's nav, needs the admin token */}
        <Route path="/test" element={<Placeholder title="Test mode" />} />
        <Route
          path="*"
          element={
            <>
              <header className="flex items-center gap-6 border-b bg-white px-6 py-3">
                <strong>PipeGuard</strong>
                <nav className="flex gap-4 text-sm">
                  {NAV.map(([to, label]) => (
                    <Link key={to} to={to} className="hover:underline">{label}</Link>
                  ))}
                </nav>
              </header>
              <main className="p-6">
                <Routes>
                  {NAV.map(([to, label]) => (
                    <Route key={to} path={to} element={<Placeholder title={label} />} />
                  ))}
                </Routes>
              </main>
              <footer className="px-6 py-4 text-xs text-slate-500">
                Prairie Gas Transmission is a simulated company. Turbine data: NASA C-MAPSS FD001 (stand-in). Costs are illustrative.
              </footer>
            </>
          }
        />
      </Routes>
    </div>
  )
}
