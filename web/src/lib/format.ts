/** $3.38 with unit M, or $720 with unit K: the number and its raised unit are separate so the unit can be styled. */
export function money(n: number): { value: string; unit: string } {
  const a = Math.abs(n), sign = n < 0 ? '−' : '' // a proper minus sign, placed before the dollar sign: −$20K, never $-20K
  if (a >= 1_000_000) return { value: `${sign}$${(a / 1_000_000).toFixed(a >= 10_000_000 ? 1 : 2)}`, unit: 'M' }
  if (a >= 1_000) return { value: `${sign}$${Math.round(a / 1_000)}`, unit: 'K' }
  return { value: `${sign}$${Math.round(a)}`, unit: '' }
}
export const moneyText = (n: number) => { const m = money(n); return `${m.value}${m.unit}` }
export const dollars = (n: number) => `${n < 0 ? '−' : ''}$${Math.abs(Math.round(n)).toLocaleString('en-US')}`
