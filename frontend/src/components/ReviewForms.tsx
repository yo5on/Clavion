import { FileText, Plus, Save, Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import {
  CATEGORY_LABELS,
  rupees,
  type BillLineItem,
  type HospitalBill,
  type PolicyDocument,
  type SettlementLetter,
} from '../api'
import { Field, btn, input } from './ui'

type Editor<T> = { value: T; onSave: (v: T) => Promise<void>; text: string }

// Sum shown for review only; the audit recomputes every total in Python with Decimal.
const displaySum = (xs: (string | null)[]) => xs.reduce((s, x) => s + (Number(x) || 0), 0).toFixed(2)

function useDraft<T>(value: T) {
  const [draft, setDraft] = useState<T>(value)
  const [saving, setSaving] = useState(false)
  const set = <K extends keyof T>(k: K, v: T[K]) => setDraft((d) => ({ ...d, [k]: v }))
  return { draft, setDraft, set, saving, setSaving }
}

function text(v: string | null | undefined) {
  return v ?? ''
}
function nullable(v: string) {
  return v.trim() === '' ? null : v
}

function SaveBar({ saving, onSave, raw }: { saving: boolean; onSave: () => void; raw: string }) {
  const [show, setShow] = useState(false)
  return (
    <div className="mt-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button type="button" className={btn.ghost} onClick={() => setShow((s) => !s)}>
          <FileText className="size-3.5" /> {show ? 'Hide' : 'Show'} extracted text
        </button>
        <button type="button" className={btn.primary} onClick={onSave} disabled={saving}>
          <Save className="size-4" /> {saving ? 'Saving…' : 'Save corrections'}
        </button>
      </div>
      {show && (
        <pre className="max-h-80 overflow-auto rounded-lg bg-navy-950 p-3 text-xs leading-relaxed text-slate-200">{raw}</pre>
      )}
    </div>
  )
}

function Grid({ children }: { children: ReactNode }) {
  return <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
}

function TextField<T>({ label, obj, k, set }: { label: string; obj: T; k: keyof T; set: (k: keyof T, v: never) => void }) {
  return (
    <Field label={label}>
      <input className={input} value={text(obj[k] as string | null)} onChange={(e) => set(k, nullable(e.target.value) as never)} />
    </Field>
  )
}

const th = 'px-2 py-1.5 text-left text-xs font-medium text-slate-500'
const td = 'px-1 py-1'

export function BillEditor({ value, onSave, text: raw }: Editor<HospitalBill>) {
  const { draft, set, saving, setSaving } = useDraft(value)
  const items = draft.line_items
  const setItem = (i: number, patch: Partial<BillLineItem>) =>
    set('line_items', items.map((it, j) => (j === i ? { ...it, ...patch } : it)))
  const sum = displaySum(items.map((i) => i.amount))
  const save = async () => {
    setSaving(true)
    await onSave(draft).finally(() => setSaving(false))
  }

  return (
    <div>
      <Grid>
        <TextField label="Hospital" obj={draft} k="hospital_name" set={set} />
        <TextField label="Patient" obj={draft} k="patient_name" set={set} />
        <TextField label="Bill number" obj={draft} k="bill_number" set={set} />
        <TextField label="Bill date" obj={draft} k="bill_date" set={set} />
        <TextField label="Stated bill total (₹)" obj={draft} k="total_amount" set={set} />
      </Grid>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className={th}>#</th>
              <th className={th}>Description</th>
              <th className={th}>Category</th>
              <th className={th}>Qty</th>
              <th className={th}>Rate (₹)</th>
              <th className={th}>Amount (₹)</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((it, i) => (
              <tr key={i} className="border-b border-slate-100">
                <td className="px-2 text-xs text-slate-400">{i + 1}</td>
                <td className={`${td} min-w-[14rem]`}><input className={input} value={it.description} onChange={(e) => setItem(i, { description: e.target.value })} /></td>
                <td className={td}>
                  <select className={input} value={it.category ?? 'other'} onChange={(e) => setItem(i, { category: e.target.value })}>
                    {Object.entries(CATEGORY_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                </td>
                <td className={`${td} w-20`}><input className={input} value={text(it.quantity)} onChange={(e) => setItem(i, { quantity: nullable(e.target.value) })} /></td>
                <td className={`${td} w-28`}><input className={input} value={text(it.unit_price)} onChange={(e) => setItem(i, { unit_price: nullable(e.target.value) })} /></td>
                <td className={`${td} w-32`}><input className={input} value={it.amount} onChange={(e) => setItem(i, { amount: e.target.value })} /></td>
                <td className={td}>
                  <button type="button" aria-label={`Remove line ${i + 1}`} className="p-1 text-slate-400 hover:text-rose-600" onClick={() => set('line_items', items.filter((_, j) => j !== i))}>
                    <Trash2 className="size-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
        <button type="button" className={btn.ghost} onClick={() => set('line_items', [...items, { description: '', quantity: null, unit_price: null, amount: '0', category: 'other' }])}>
          <Plus className="size-3.5" /> Add line
        </button>
        <span className={draft.total_amount && Number(draft.total_amount).toFixed(2) !== sum ? 'font-medium text-amber-700' : 'text-slate-500'}>
          Lines add up to {rupees(sum)} · bill says {rupees(draft.total_amount)}
        </span>
      </div>
      <SaveBar saving={saving} onSave={save} raw={raw} />
    </div>
  )
}

export function SettlementEditor({ value, onSave, text: raw }: Editor<SettlementLetter>) {
  const { draft, set, saving, setSaving } = useDraft(value)
  const ded = draft.deductions
  const setDed = (i: number, patch: Partial<SettlementLetter['deductions'][number]>) =>
    set('deductions', ded.map((d, j) => (j === i ? { ...d, ...patch } : d)))
  const save = async () => {
    setSaving(true)
    await onSave(draft).finally(() => setSaving(false))
  }
  return (
    <div>
      <Grid>
        <TextField label="Insurer" obj={draft} k="insurer_name" set={set} />
        <TextField label="Claim number" obj={draft} k="claim_number" set={set} />
        <TextField label="Policy number" obj={draft} k="policy_number" set={set} />
        <TextField label="Patient" obj={draft} k="patient_name" set={set} />
        <TextField label="Hospital" obj={draft} k="hospital_name" set={set} />
        <TextField label="Amount claimed (₹)" obj={draft} k="claimed_amount" set={set} />
        <TextField label="Amount approved (₹)" obj={draft} k="approved_amount" set={set} />
        <TextField label="Stated total deductions (₹)" obj={draft} k="total_deductions" set={set} />
      </Grid>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className={th}>Deduction as stated by the insurer</th>
              <th className={th}>Clause cited</th>
              <th className={th}>Amount (₹)</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {ded.map((d, i) => (
              <tr key={i} className="border-b border-slate-100">
                <td className={td}><input className={input} value={d.description} onChange={(e) => setDed(i, { description: e.target.value })} /></td>
                <td className={`${td} w-24`}><input className={input} value={text(d.clause_ref)} onChange={(e) => setDed(i, { clause_ref: nullable(e.target.value) })} /></td>
                <td className={`${td} w-32`}><input className={input} value={d.amount} onChange={(e) => setDed(i, { amount: e.target.value })} /></td>
                <td className={td}>
                  <button type="button" aria-label={`Remove deduction ${i + 1}`} className="p-1 text-slate-400 hover:text-rose-600" onClick={() => set('deductions', ded.filter((_, j) => j !== i))}>
                    <Trash2 className="size-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
        <button type="button" className={btn.ghost} onClick={() => set('deductions', [...ded, { description: '', amount: '0', clause_ref: null }])}>
          <Plus className="size-3.5" /> Add deduction
        </button>
        <span className="text-slate-500">Itemised deductions add up to {rupees(displaySum(ded.map((d) => d.amount)))}</span>
      </div>
      <SaveBar saving={saving} onSave={save} raw={raw} />
    </div>
  )
}

const EXCLUDABLE = ['pharmacy', 'consumables', 'implants', 'diagnostics', 'icu']

export function PolicyEditor({ value, onSave, text: raw }: Editor<PolicyDocument>) {
  const { draft, set, saving, setSaving } = useDraft(value)
  const save = async () => {
    setSaving(true)
    await onSave(draft).finally(() => setSaving(false))
  }
  return (
    <div>
      <Grid>
        <TextField label="Policy name" obj={draft} k="policy_name" set={set} />
        <TextField label="Policy number" obj={draft} k="policy_number" set={set} />
        <TextField label="Sum insured (₹)" obj={draft} k="sum_insured" set={set} />
        <TextField label="Room-rent limit per day (₹)" obj={draft} k="room_rent_limit_per_day" set={set} />
        <TextField label="Room-rent clause" obj={draft} k="room_rent_clause" set={set} />
        <TextField label="ICU limit per day (₹)" obj={draft} k="icu_limit_per_day" set={set} />
        <TextField label="ICU clause" obj={draft} k="icu_clause" set={set} />
        <TextField label="Proportionate-deduction clause" obj={draft} k="proportionate_clause" set={set} />
        <TextField label="Co-payment %" obj={draft} k="copay_percent" set={set} />
        <TextField label="Co-payment applies…" obj={draft} k="copay_condition" set={set} />
        <TextField label="Co-payment clause" obj={draft} k="copay_clause" set={set} />
        <TextField label="Non-payable clause" obj={draft} k="non_payable_clause" set={set} />
      </Grid>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Field label="Proportionate deduction does not apply to">
          <div className="flex flex-wrap gap-3 pt-1">
            {EXCLUDABLE.map((c) => (
              <label key={c} className="flex items-center gap-1.5 text-sm font-normal text-slate-700">
                <input
                  type="checkbox"
                  className="accent-violet-600"
                  checked={draft.proportionate_exclusions.includes(c)}
                  onChange={(e) =>
                    set('proportionate_exclusions', e.target.checked
                      ? [...draft.proportionate_exclusions, c]
                      : draft.proportionate_exclusions.filter((x) => x !== c))
                  }
                />
                {CATEGORY_LABELS[c]}
              </label>
            ))}
          </div>
        </Field>
        <Field label="Non-payable items (one per line)">
          <textarea
            className={`${input} h-28`}
            value={draft.non_payable_items.join('\n')}
            onChange={(e) => set('non_payable_items', e.target.value.split('\n'))}
            onBlur={(e) => set('non_payable_items', e.target.value.split('\n').map((s) => s.trim()).filter(Boolean))}
          />
        </Field>
        <Field label="Sub-limits (name: amount)">
          <textarea
            className={`${input} h-28`}
            defaultValue={draft.sub_limits.map((s) => `${s.name}: ${s.limit}`).join('\n')}
            onBlur={(e) =>
              set('sub_limits', e.target.value.split('\n').map((line) => line.split(':')).filter((p) => p.length === 2 && p[0].trim()).map(([name, limit]) => ({
                name: name.trim(),
                limit: limit.trim(),
                clause_id: draft.sub_limits.find((s) => s.name === name.trim())?.clause_id ?? null,
              })))
            }
          />
        </Field>
      </div>
      <details className="mt-4 rounded-lg border border-slate-200">
        <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-navy-900">
          {draft.clauses.length} clauses recognised
        </summary>
        <ul className="divide-y divide-slate-100">
          {draft.clauses.map((c) => (
            <li key={c.id} className="px-3 py-2 text-xs">
              <span className="font-semibold text-violet-700">{c.id}</span> <span className="font-medium">{c.title}</span>
            </li>
          ))}
        </ul>
      </details>
      <SaveBar saving={saving} onSave={save} raw={raw} />
    </div>
  )
}
