import { AlertTriangle, CheckCircle2, FileText, Plus, Save, Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import {
  CATEGORY_LABELS,
  type BillLineItem,
  type HospitalBill,
  type PolicyDocument,
  type SettlementLetter,
} from '../api'
import { Amount, Field, btn, cell, eyebrow, input } from './ui'

type Editor<T> = { value: T; onSave: (v: T) => Promise<void>; text: string }

// Sum shown for review only; the audit recomputes every total in Python with Decimal.
const displaySum = (xs: (string | null)[]) => xs.reduce((s, x) => s + (Number(x) || 0), 0).toFixed(2)

function useDraft<T>(value: T, onSave: (v: T) => Promise<void>) {
  const [draft, setDraft] = useState<T>(value)
  const [saving, setSaving] = useState(false)
  const set = <K extends keyof T>(k: K, v: T[K]) => setDraft((d) => ({ ...d, [k]: v }))
  const save = async () => {
    setSaving(true)
    await onSave(draft).finally(() => setSaving(false))
  }
  return { draft, set, saving, save, dirty: JSON.stringify(draft) !== JSON.stringify(value) }
}

function text(v: string | null | undefined) {
  return v ?? ''
}
function nullable(v: string) {
  return v.trim() === '' ? null : v
}

function SaveBar({ saving, dirty, onSave, raw }: { saving: boolean; dirty: boolean; onSave: () => void; raw: string }) {
  const [show, setShow] = useState(false)
  return (
    <div className="mt-6 space-y-3 border-t border-line pt-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button type="button" className={btn.ghost} onClick={() => setShow((s) => !s)} aria-expanded={show}>
          <FileText className="size-3.5" /> {show ? 'Hide' : 'Show'} extracted source text
        </button>
        <span className="flex items-center gap-3">
          {dirty && (
            <span className="flex items-center gap-1.5 text-xs font-medium text-amber-700">
              <span className="size-1.5 rounded-full bg-amber-500" /> Unsaved changes
            </span>
          )}
          <button type="button" className={dirty ? btn.primary : btn.secondary} onClick={onSave} disabled={saving}>
            <Save className="size-4" /> {saving ? 'Saving…' : 'Save corrections'}
          </button>
        </span>
      </div>
      {show && (
        <pre className="max-h-96 overflow-auto rounded-md border border-line bg-slate-50 p-4 font-mono text-xs leading-relaxed text-slate-700">{raw}</pre>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-6 first:mt-0">
      <h3 className={`${eyebrow} mb-3`}>{title}</h3>
      {children}
    </section>
  )
}

function Grid({ children }: { children: ReactNode }) {
  return <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
}

function TextField<T>({ label, obj, k, set, money }: { label: string; obj: T; k: keyof T; set: (k: keyof T, v: never) => void; money?: boolean }) {
  return (
    <Field label={label}>
      <input className={`${input} ${money ? 'text-right tabular-nums' : ''}`} inputMode={money ? 'decimal' : undefined}
        value={text(obj[k] as string | null)} onChange={(e) => set(k, nullable(e.target.value) as never)} />
    </Field>
  )
}

const th = 'px-2 py-2 text-left text-xs font-medium text-slate-500'
const td = 'px-1 py-1'
const num = `${cell} text-right tabular-nums`

function TableFrame({ children, minWidth }: { children: ReactNode; minWidth: string }) {
  return (
    <div className="overflow-x-auto rounded-md border border-line">
      <table className="w-full text-sm" style={{ minWidth }}>{children}</table>
    </div>
  )
}

function RemoveButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" aria-label={label} className="rounded p-1.5 text-slate-300 transition-colors hover:bg-rose-50 hover:text-rose-600" onClick={onClick}>
      <Trash2 className="size-4" />
    </button>
  )
}

function Reconcile({ sum, stated, what }: { sum: string; stated: string | null; what: string }) {
  if (!stated) return <span className="text-xs text-slate-500">No stated {what} to compare</span>
  const diff = Number(sum) - Number(stated)
  return Math.abs(diff) < 0.005 ? (
    <span className="flex items-center gap-1.5 text-xs text-emerald-700"><CheckCircle2 className="size-3.5" /> Matches the stated {what}</span>
  ) : (
    <span className="flex items-center gap-1.5 text-xs font-medium text-amber-700">
      <AlertTriangle className="size-3.5" /> Differs from the stated {what} (<Amount value={stated} />) by <Amount value={Math.abs(diff)} />
    </span>
  )
}

export function BillEditor({ value, onSave, text: raw }: Editor<HospitalBill>) {
  const { draft, set, saving, save, dirty } = useDraft(value, onSave)
  const items = draft.line_items
  const setItem = (i: number, patch: Partial<BillLineItem>) =>
    set('line_items', items.map((it, j) => (j === i ? { ...it, ...patch } : it)))
  const sum = displaySum(items.map((i) => i.amount))

  return (
    <div>
      <Section title="Bill details">
        <Grid>
          <TextField label="Hospital" obj={draft} k="hospital_name" set={set} />
          <TextField label="Patient" obj={draft} k="patient_name" set={set} />
          <TextField label="Bill number" obj={draft} k="bill_number" set={set} />
          <TextField label="Bill date" obj={draft} k="bill_date" set={set} />
          <TextField label="Stated bill total (₹)" obj={draft} k="total_amount" set={set} money />
        </Grid>
      </Section>
      <Section title={`Line items · ${items.length}`}>
        <TableFrame minWidth="680px">
          <thead className="bg-slate-50">
            <tr className="border-b border-line">
              <th className={`${th} w-10 pl-3`}>#</th>
              <th className={`${th} min-w-56`}>Description</th>
              <th className={`${th} w-44`}>Category</th>
              <th className={`${th} w-20 text-right`}>Qty</th>
              <th className={`${th} w-28 text-right`}>Rate (₹)</th>
              <th className={`${th} w-32 text-right`}>Amount (₹)</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {items.map((it, i) => (
              <tr key={i} className="hover:bg-slate-50/60">
                <td className="pl-3 font-mono text-xs text-slate-400">{i + 1}</td>
                <td className={td}><input className={cell} aria-label={`Line ${i + 1} description`} value={it.description} onChange={(e) => setItem(i, { description: e.target.value })} /></td>
                <td className={td}>
                  <select className={cell} aria-label={`Line ${i + 1} category`} value={it.category ?? 'other'} onChange={(e) => setItem(i, { category: e.target.value })}>
                    {Object.entries(CATEGORY_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                </td>
                <td className={td}><input className={num} inputMode="decimal" aria-label={`Line ${i + 1} quantity`} value={text(it.quantity)} onChange={(e) => setItem(i, { quantity: nullable(e.target.value) })} /></td>
                <td className={td}><input className={num} inputMode="decimal" aria-label={`Line ${i + 1} rate`} value={text(it.unit_price)} onChange={(e) => setItem(i, { unit_price: nullable(e.target.value) })} /></td>
                <td className={td}><input className={`${num} font-medium`} inputMode="decimal" aria-label={`Line ${i + 1} amount`} value={it.amount} onChange={(e) => setItem(i, { amount: e.target.value })} /></td>
                <td className={td}><RemoveButton label={`Remove line ${i + 1}`} onClick={() => set('line_items', items.filter((_, j) => j !== i))} /></td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t border-line bg-slate-50">
            <tr>
              <td colSpan={5} className="px-3 py-2 text-xs font-medium text-slate-600">Lines add up to</td>
              <td className="px-3 py-2 text-right text-sm font-semibold text-navy-900"><Amount value={sum} /></td>
              <td />
            </tr>
          </tfoot>
        </TableFrame>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <button type="button" className={btn.ghost} onClick={() => set('line_items', [...items, { description: '', quantity: null, unit_price: null, amount: '0', category: 'other' }])}>
            <Plus className="size-3.5" /> Add line
          </button>
          <Reconcile sum={sum} stated={draft.total_amount} what="bill total" />
        </div>
      </Section>
      <SaveBar saving={saving} dirty={dirty} onSave={save} raw={raw} />
    </div>
  )
}

export function SettlementEditor({ value, onSave, text: raw }: Editor<SettlementLetter>) {
  const { draft, set, saving, save, dirty } = useDraft(value, onSave)
  const ded = draft.deductions
  const setDed = (i: number, patch: Partial<SettlementLetter['deductions'][number]>) =>
    set('deductions', ded.map((d, j) => (j === i ? { ...d, ...patch } : d)))
  const sum = displaySum(ded.map((d) => d.amount))
  return (
    <div>
      <Section title="Claim">
        <Grid>
          <TextField label="Insurer" obj={draft} k="insurer_name" set={set} />
          <TextField label="Claim number" obj={draft} k="claim_number" set={set} />
          <TextField label="Policy number" obj={draft} k="policy_number" set={set} />
          <TextField label="Patient" obj={draft} k="patient_name" set={set} />
          <TextField label="Hospital" obj={draft} k="hospital_name" set={set} />
        </Grid>
      </Section>
      <Section title="Amounts">
        <Grid>
          <TextField label="Amount claimed (₹)" obj={draft} k="claimed_amount" set={set} money />
          <TextField label="Amount approved (₹)" obj={draft} k="approved_amount" set={set} money />
          <TextField label="Stated total deductions (₹)" obj={draft} k="total_deductions" set={set} money />
        </Grid>
      </Section>
      <Section title={`Deductions listed by the insurer · ${ded.length}`}>
        <TableFrame minWidth="560px">
          <thead className="bg-slate-50">
            <tr className="border-b border-line">
              <th className={`${th} w-10 pl-3`}>#</th>
              <th className={`${th} min-w-56`}>Deduction as stated</th>
              <th className={`${th} w-28`}>Clause cited</th>
              <th className={`${th} w-32 text-right`}>Amount (₹)</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {ded.map((d, i) => (
              <tr key={i} className="hover:bg-slate-50/60">
                <td className="pl-3 font-mono text-xs text-slate-400">{i + 1}</td>
                <td className={td}><input className={cell} aria-label={`Deduction ${i + 1} description`} value={d.description} onChange={(e) => setDed(i, { description: e.target.value })} /></td>
                <td className={td}><input className={`${cell} font-mono text-xs`} aria-label={`Deduction ${i + 1} clause`} value={text(d.clause_ref)} onChange={(e) => setDed(i, { clause_ref: nullable(e.target.value) })} /></td>
                <td className={td}><input className={`${num} font-medium`} inputMode="decimal" aria-label={`Deduction ${i + 1} amount`} value={d.amount} onChange={(e) => setDed(i, { amount: e.target.value })} /></td>
                <td className={td}><RemoveButton label={`Remove deduction ${i + 1}`} onClick={() => set('deductions', ded.filter((_, j) => j !== i))} /></td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t border-line bg-slate-50">
            <tr>
              <td colSpan={3} className="px-3 py-2 text-xs font-medium text-slate-600">Itemised deductions add up to</td>
              <td className="px-3 py-2 text-right text-sm font-semibold text-navy-900"><Amount value={sum} /></td>
              <td />
            </tr>
          </tfoot>
        </TableFrame>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <button type="button" className={btn.ghost} onClick={() => set('deductions', [...ded, { description: '', amount: '0', clause_ref: null }])}>
            <Plus className="size-3.5" /> Add deduction
          </button>
          <Reconcile sum={sum} stated={draft.total_deductions} what="total deductions" />
        </div>
      </Section>
      <SaveBar saving={saving} dirty={dirty} onSave={save} raw={raw} />
    </div>
  )
}

const EXCLUDABLE = ['pharmacy', 'consumables', 'implants', 'diagnostics', 'icu']

export function PolicyEditor({ value, onSave, text: raw }: Editor<PolicyDocument>) {
  const { draft, set, saving, save, dirty } = useDraft(value, onSave)
  return (
    <div>
      <Section title="Policy">
        <Grid>
          <TextField label="Policy name" obj={draft} k="policy_name" set={set} />
          <TextField label="Policy number" obj={draft} k="policy_number" set={set} />
          <TextField label="Sum insured (₹)" obj={draft} k="sum_insured" set={set} money />
        </Grid>
      </Section>
      <Section title="Room and ICU limits">
        <Grid>
          <TextField label="Room-rent limit per day (₹)" obj={draft} k="room_rent_limit_per_day" set={set} money />
          <TextField label="Room-rent clause" obj={draft} k="room_rent_clause" set={set} />
          <TextField label="Proportionate-deduction clause" obj={draft} k="proportionate_clause" set={set} />
          <TextField label="ICU limit per day (₹)" obj={draft} k="icu_limit_per_day" set={set} money />
          <TextField label="ICU clause" obj={draft} k="icu_clause" set={set} />
        </Grid>
      </Section>
      <Section title="Co-payment and non-payables">
        <Grid>
          <TextField label="Co-payment %" obj={draft} k="copay_percent" set={set} money />
          <TextField label="Co-payment applies…" obj={draft} k="copay_condition" set={set} />
          <TextField label="Co-payment clause" obj={draft} k="copay_clause" set={set} />
          <TextField label="Non-payable clause" obj={draft} k="non_payable_clause" set={set} />
        </Grid>
      </Section>
      <Section title="Rules">
        <div className="grid gap-4 lg:grid-cols-3">
          <Field label="Proportionate deduction does not apply to">
            <div className="flex flex-wrap gap-x-4 gap-y-2 pt-1.5">
              {EXCLUDABLE.map((c) => (
                <label key={c} className="flex items-center gap-1.5 text-sm font-normal text-slate-700">
                  <input
                    type="checkbox"
                    className="size-4 accent-navy-900"
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
              className={`${input} h-28 py-2`}
              value={draft.non_payable_items.join('\n')}
              onChange={(e) => set('non_payable_items', e.target.value.split('\n'))}
              onBlur={(e) => set('non_payable_items', e.target.value.split('\n').map((s) => s.trim()).filter(Boolean))}
            />
          </Field>
          <Field label="Sub-limits (name: amount)">
            <textarea
              className={`${input} h-28 py-2`}
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
      </Section>
      <details className="group mt-6 rounded-md border border-line">
        <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2.5 text-sm font-medium text-navy-900 hover:bg-slate-50">
          {draft.clauses.length} clauses recognised
          <span className="text-xs font-normal text-slate-500 group-open:hidden">Show</span>
          <span className="hidden text-xs font-normal text-slate-500 group-open:inline">Hide</span>
        </summary>
        <ul className="divide-y divide-line border-t border-line">
          {draft.clauses.map((c) => (
            <li key={c.id} className="grid grid-cols-[3.5rem_1fr] gap-2 px-3 py-2 text-sm">
              <span className="font-mono text-xs leading-5 text-slate-500">§ {c.id}</span>
              <span className="text-slate-700">{c.title}</span>
            </li>
          ))}
        </ul>
      </details>
      <SaveBar saving={saving} dirty={dirty} onSave={save} raw={raw} />
    </div>
  )
}
