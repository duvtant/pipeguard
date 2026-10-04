// CSV export for managers who want to analyse in Excel. Built in the browser from data the page already has.
// Excel-safe: UTF-8 with a BOM (accents and the minus sign survive), CRLF line ends, and formula protection: text that
// starts with = + - @ is prefixed with an apostrophe, so a technician's or the agent's words can never run as a formula.
export type Cell = string | number | boolean | null | undefined

const DANGEROUS = /^[=+\-@\t\r]/

export function csvCell(v: Cell): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'number') return Number.isFinite(v) ? String(v) : ''
  let s = typeof v === 'boolean' ? (v ? 'Yes' : 'No') : v
  if (DANGEROUS.test(s)) s = `'${s}`
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function toCsv(columns: string[], rows: Cell[][]): string {
  return '﻿' + [columns, ...rows].map((r) => r.map(csvCell).join(',')).join('\r\n') + '\r\n'
}

export interface CsvFile { filename: string; columns: string[]; rows: Cell[][] }

export function downloadCsv({ filename, columns, rows }: CsvFile) {
  const url = URL.createObjectURL(new Blob([toCsv(columns, rows)], { type: 'text/csv;charset=utf-8' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
}
