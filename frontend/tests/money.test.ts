import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fromPaise, paise, rupees } from '../src/money.ts'

test('rupees uses Indian grouping and keeps paise', () => {
  const cases: [string | number | null | undefined, string][] = [
    ['0', '₹0.00'], ['1', '₹1.00'], ['100', '₹100.00'], ['999', '₹999.00'], ['1000', '₹1,000.00'],
    ['5000', '₹5,000.00'], ['10000', '₹10,000.00'], ['100000', '₹1,00,000.00'], ['130940.50', '₹1,30,940.50'],
    ['130940.5', '₹1,30,940.50'], ['97069.62', '₹97,069.62'], ['4447.80', '₹4,447.80'],
    ['15000000', '₹1,50,00,000.00'], ['1234567890.12', '₹1,23,45,67,890.12'],
    ['-4447.80', '-₹4,447.80'], ['-100000', '-₹1,00,000.00'],
    // half-up on the exact decimal: 1.005 would round down as a float
    ['1.005', '₹1.01'], ['0.004', '₹0.00'], ['-0.004', '₹0.00'], ['999.995', '₹1,000.00'], ['99999.994', '₹99,999.99'],
    [5000, '₹5,000.00'], [130940.5, '₹1,30,940.50'],
    [null, '—'], [undefined, '—'], ['', '—'], ['abc', '—'], ['1,000', '—'],
  ]
  for (const [v, want] of cases) assert.equal(rupees(v), want, `rupees(${JSON.stringify(v)})`)
})

test('paise sums exactly', () => {
  assert.equal(fromPaise(['0.1', '0.2'].reduce((s, x) => s + paise(x), 0n)), '0.30')
  assert.equal(fromPaise(paise('130940.5')), '130940.50')
  assert.equal(fromPaise(paise('-4447.805')), '-4447.81')
  assert.equal(paise(null), 0n)
  assert.equal(paise('abc'), 0n)
})
