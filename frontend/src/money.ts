// Display formatting for rupee amounts; mirrors backend services/currency.rs. API amounts are decimal strings,
// and Intl formats strings as exact decimals (half-up), so no value passes through a float here.
const inr = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** ₹1,30,940.50 for "130940.5"; an em dash when the amount is missing or not a number. */
export function rupees(v: string | number | null | undefined): string {
  const s = String(v ?? '').trim()
  if (!/^-?(\d+\.?\d*|\.\d+)$/.test(s)) return '—'
  // Intl accepts decimal strings (ES2023); this TS lib only types the number overload.
  const out = inr.format(s.replace(/^-/, '') as unknown as number)
  return `${s.startsWith('-') && /[1-9]/.test(out) ? '-' : ''}₹${out}`
}

/** Exact paise for a typed amount ("1500.5" → 150050n); unparseable input counts as zero, as in the review forms. */
export function paise(v: string | null | undefined): bigint {
  const m = /^(-?)(\d*)(?:\.(\d*))?$/.exec((v ?? '').trim())
  if (!m || !(m[2] || m[3])) return 0n
  const frac = (m[3] ?? '').padEnd(3, '0')
  const p = BigInt(m[2] || '0') * 100n + BigInt(frac.slice(0, 2)) + (frac[2] >= '5' ? 1n : 0n)
  return m[1] ? -p : p
}

/** Paise back to a plain decimal string ("150050n" → "1500.50") for rupees() or comparison. */
export function fromPaise(p: bigint): string {
  const a = p < 0n ? -p : p
  return `${p < 0n ? '-' : ''}${a / 100n}.${String(a % 100n).padStart(2, '0')}`
}
