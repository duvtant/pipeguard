// A simple two-tone phone ring made with Web Audio. Browsers only allow sound after a tap, so the AudioContext is created
// by the "I'm on shift" button (a user gesture) and reused for every ring afterwards.
let ctx: AudioContext | null = null
let timer: ReturnType<typeof setInterval> | null = null
// Browsers block vibration (and log an error) until the person has tapped the page.
const vibrate = (p: number | number[]) => { if (navigator.userActivation?.hasBeenActive) navigator.vibrate?.(p) }

export async function unlockAudio() {
  try {
    ctx ??= new (window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)()
    if (ctx.state === 'suspended') await ctx.resume()
  } catch { /* no audio: the page still works visually and with vibration */ }
}

function burst() {
  if (!ctx || ctx.state !== 'running') return
  const t = ctx.currentTime
  for (const [f, at] of [[440, 0], [480, 0], [440, 0.45], [480, 0.45]] as const) {
    const o = ctx.createOscillator(), g = ctx.createGain()
    o.type = 'sine'; o.frequency.value = f
    g.gain.setValueAtTime(0.0001, t + at); g.gain.exponentialRampToValueAtTime(0.18, t + at + 0.03); g.gain.exponentialRampToValueAtTime(0.0001, t + at + 0.4)
    o.connect(g).connect(ctx.destination); o.start(t + at); o.stop(t + at + 0.42)
  }
  vibrate([300, 150, 300])
}

export function startRinging() { stopRinging(); burst(); timer = setInterval(burst, 2500) }
export function stopRinging() { if (timer) { clearInterval(timer); timer = null; vibrate(0) } }
