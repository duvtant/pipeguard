import { describe, expect, it } from 'vitest'
import { csvCell, toCsv } from './exportCsv'

describe('csv export', () => {
  it('quotes commas, quotes and line breaks, and leaves plain text alone', () => {
    expect(csvCell('plain')).toBe('plain')
    expect(csvCell('a, b')).toBe('"a, b"')
    expect(csvCell('say "hi"')).toBe('"say ""hi"""')
    expect(csvCell('two\nlines')).toBe('"two\nlines"')
  })
  it('protects against spreadsheet formulas in text, but not in real numbers', () => {
    expect(csvCell('=HYPERLINK("http://x")')).toBe(`"'=HYPERLINK(""http://x"")"`)
    expect(csvCell('+1 555')).toBe("'+1 555"); expect(csvCell('@cmd')).toBe("'@cmd"); expect(csvCell('-5 days')).toBe("'-5 days")
    expect(csvCell(-20000)).toBe('-20000')
  })
  it('writes empty, boolean and non-finite values sensibly', () => {
    expect(csvCell(null)).toBe(''); expect(csvCell(undefined)).toBe(''); expect(csvCell(NaN)).toBe('')
    expect(csvCell(true)).toBe('Yes'); expect(csvCell(false)).toBe('No')
  })
  it('starts with a BOM, uses CRLF and has a header row', () => {
    const out = toCsv(['Unit', 'Days'], [['EDS-07', 22], ['EDS-14', 15]])
    expect(out.startsWith('﻿Unit,Days\r\nEDS-07,22\r\n')).toBe(true); expect(out.endsWith('\r\n')).toBe(true)
  })
})
