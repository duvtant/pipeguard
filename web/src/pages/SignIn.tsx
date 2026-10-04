import { useNavigate } from 'react-router-dom'
import { signIn } from '@/lib/auth'
import ArrowRight from '~icons/ph/arrow-right'

export default function SignIn() {
  const navigate = useNavigate()
  const go = () => { signIn(); navigate('/', { replace: true }) }
  return (
    <div className="grid min-h-[100dvh] bg-canvas lg:grid-cols-[minmax(420px,520px)_1fr]">
      <main className="flex flex-col justify-between px-8 py-8 sm:px-14">
        <div className="flex items-center gap-2.5 text-[17px] [font-weight:var(--w-strong)] text-ink"><img src="/logo-mark.svg" width={32} height={32} alt="" />PipeGuard</div>
        <div className="py-12">
          <p className="m-0 mb-3 text-sm text-muted">Prairie Gas Transmission · Maintenance</p>
          <h1 className="m-0 max-w-[420px] text-[40px] leading-[46px] tracking-[-0.02em] text-ink [font-weight:var(--w-body)]">Fix it before it fails.</h1>
          <p className="m-0 mt-4 max-w-[400px] text-[16px] leading-6 text-muted">Predictive maintenance for gas compressor stations, with a voice agent that calls your crew and replans the work.</p>
          <button type="button" onClick={go} className="mt-8 inline-flex min-h-11 items-center gap-2 rounded-full bg-accent px-6 text-[15px] text-white transition-[background-color,transform] duration-150 ease-[var(--ease-out)] hover:bg-accent-ink active:scale-[0.98] [font-weight:var(--w-strong)]">
            Sign in as Maintenance Manager <ArrowRight width={16} height={16} aria-hidden />
          </button>
          <p className="m-0 mt-3 text-[13px] text-muted">No password: this is a demonstration with simulated data.</p>
        </div>
        <p className="m-0 max-w-[420px] text-[13px] text-muted">Prairie Gas Transmission is a simulated company. Turbine data: NASA C-MAPSS FD001 (stand-in). Costs are illustrative.</p>
      </main>
      <div aria-hidden className="relative hidden overflow-hidden lg:block" style={{ backgroundImage: 'url(/brand/mesh-insight.webp)', backgroundSize: 'cover', backgroundPosition: 'center' }}>
        <img src="/brand/sign-in.webp" width={1600} height={1000} alt="" className="absolute inset-x-0 top-1/2 w-full -translate-y-1/2 mix-blend-multiply" />
      </div>
    </div>
  )
}
