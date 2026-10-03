// Simulated calendar: sim_day 0 is the Monday in scenario.json `calendar_start`.
// "Friday" on a call always means a simulated Friday, never the real one.
export const CALENDAR_START = '2026-10-05'

export function simDate(day: number): Date {
  const [y, m, d] = CALENDAR_START.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + day))
}
export const isoSimDate = (day: number) => simDate(day).toISOString().slice(0, 10)
export const formatSimDate = (day: number) =>
  simDate(day).toLocaleDateString('en-CA', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' })
