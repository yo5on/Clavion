import { AlertTriangle, CheckCircle2, ChevronDown, Plus, Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import {
  CATEGORY_LABELS,
  type BillLineItem,
  type HospitalBill,
  type PolicyDocument,
  type SettlementLetter,
} from '../api'
import { Amount, Field, btn, cell, input } from './ui'

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
    <div className="mt-10 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <button type="button" className={btn.linkSm} onClick={() => setShow((s) => !s)} aria-expanded={show}>
          {show ? 'Hide' : 'Show'} the extracted text
          <ChevronDown aria-hidden className={`size-4 transition-transform duration-300 ${show ? 'rotate-180' : ''}`} />
        </button>
        <span className="flex items-center gap-4">
          {dirty && (
            <span className="flex animate-fade-in items-center gap-2 text-[13px] font-medium text-caution">
              <span aria-hidden className="size-1.5 rounded-full bg-caution-fill" /> Unsaved changes
            </span>
          )}
          <button type="button" className={dirty ? btn.primarySm : btn.secondarySm} onClick={onSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save corrections'}
          </button>
        </span>
      </div>
      {show && (
        // A paper sheet, so the raw text reads as the document it came from.
        <div className="animate-fade-in rounded-2xl bg-tile p-2 sm:p-3">
          <pre className="max-h-[28rem] overflow-auto rounded-xl bg-paper px-6 py-7 font-mono text-[12.5px] leading-6 text-ink-2 shadow-[0_1px_3px_rgb(0_0_0/0.06)] sm:px-10 sm:py-9">{raw}</pre>
        </div>
      )}
    </div>
  )
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-10 first:mt-0">
      <h3 className="mb-4 text-[15px] font-semibold text-ink">{title}</h3>
      {children}
    </section>
  )
}

function Grid({ children }: { children: ReactNode }) {
  return <div className="grid gap-x-5 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
}

function TextField<T>({ label, obj, k, set, money }: { label: string; obj: T; k: keyof T; set: (k: keyof T, v: never) => void; money?: boolean }) {
  return (
    <Field label={label}>
      <input className={`${input} ${money ? 'text-right tabular-nums' : ''}`} inputMode={money ? 'decimal' : undefined}
        value={text(obj[k] as string | null)} onChange={(e) => set(k, nullable(e.target.value) as never)} />
    </Field>
  )
}

const th = 'px-2 pb-2.5 text-left text-[13px] font-medium text-mute'
const td = 'px-1 py-1'
const num = `${cell} text-right tabular-nums`

function TableFrame({ children, minWidth }: { children: ReactNode; minWidth: string }) {
  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="w-full text-[15px]" style={{ minWidth }}>{children}</table>
    </div>
  )
}

function RemoveButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" aria-label={label} className="rounded-full p-2 text-faint transition-colors duration-200 hover:bg-alert-soft hover:text-alert" onClick={onClick}>
      <Trash2 className="size-4" strokeWidth={1.75} />
    </button>
  )
}

function Reconcile({ sum, stated, what }: { sum: string; stated: string | null; what: string }) {
  if (!stated) return <span className="text-[13px] text-mute">No stated {what} to compare</span>
  const diff = Number(sum) - Number(stated)
  return Math.abs(diff) < 0.005 ? (
    <span className="flex items-center gap-1.5 text-[13px] text-ok"><CheckCircle2 className="size-3.5" /> Matches the stated {what}</span>
  ) : (
    <span className="flex items-center gap-1.5 text-[13px] font-medium text-caution">
      <AlertTriangle className="size-3.5" /> Differs from the stated {what} (<Amount value={stated} />) by <Amount value={Math.abs(diff)} />
    </span>
  )
}

function TotalRow({ span, label, sum }: { span: number; label: string; sum: string }) {
  return (
    <tfoot className="border-t border-hairline-strong">
      <tr>
        <td colSpan={span} className="px-3 py-3 text-sm text-mute">{label}</td>
        <td className="px-3 py-3 text-right"><Amount value={sum} className="type-figure text-[17px]" /></td>
        <td />
      </tr>
    </tfoot>
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
      <Group title="Bill details">
        <Grid>
          <TextField label="Hospital" obj={draft} k="hospital_name" set={set} />
          <TextField label="Patient" obj={draft} k="patient_name" set={set} />
          <TextField label="Bill number" obj={draft} k="bill_number" set={set} />
          <TextField label="Bill date" obj={draft} k="bill_date" set={set} />
          <TextField label="Stated bill total (₹)" obj={draft} k="total_amount" set={set} money />
        </Grid>
      </Group>
      <Group title={`Line items · ${items.length}`}>
        <TableFrame minWidth="680px">
          <thead className="border-b border-hairline">
            <tr>
              <th className={`${th} w-10 pl-3`}>#</th>
              <th className={`${th} min-w-56`}>Description</th>
              <th className={`${th} w-44`}>Category</th>
              <th className={`${th} w-20 text-right`}>Qty</th>
              <th className={`${th} w-28 text-right`}>Rate (₹)</th>
              <th className={`${th} w-32 text-right`}>Amount (₹)</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {items.map((it, i) => (
              <tr key={i} className="transition-colors duration-150 hover:bg-tile/50">
                <td className="pl-3 text-sm tabular-nums text-mute">{i + 1}</td>
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
          <TotalRow span={5} label="Lines add up to" sum={sum} />
        </TableFrame>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <button type="button" className={btn.linkSm} onClick={() => set('line_items', [...items, { description: '', quantity: null, unit_price: null, amount: '0', category: 'other' }])}>
            <Plus className="size-4" /> Add line
          </button>
          <Reconcile sum={sum} stated={draft.total_amount} what="bill total" />
        </div>
      </Group>
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
      <Group title="Claim">
        <Grid>
          <TextField label="Insurer" obj={draft} k="insurer_name" set={set} />
          <TextField label="Claim number" obj={draft} k="claim_number" set={set} />
          <TextField label="Policy number" obj={draft} k="policy_number" set={set} />
          <TextField label="Patient" obj={draft} k="patient_name" set={set} />
          <TextField label="Hospital" obj={draft} k="hospital_name" set={set} />
        </Grid>
      </Group>
      <Group title="Amounts">
        <Grid>
          <TextField label="Amount claimed (₹)" obj={draft} k="claimed_amount" set={set} money />
          <TextField label="Amount approved (₹)" obj={draft} k="approved_amount" set={set} money />
          <TextField label="Stated total deductions (₹)" obj={draft} k="total_deductions" set={set} money />
        </Grid>
      </Group>
      <Group title={`Deductions listed by the insurer · ${ded.length}`}>
        <TableFrame minWidth="560px">
          <thead className="border-b border-hairline">
            <tr>
              <th className={`${th} w-10 pl-3`}>#</th>
              <th className={`${th} min-w-56`}>Deduction as stated</th>
              <th className={`${th} w-28`}>Clause cited</th>
              <th className={`${th} w-32 text-right`}>Amount (₹)</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {ded.map((d, i) => (
              <tr key={i} className="transition-colors duration-150 hover:bg-tile/50">
                <td className="pl-3 text-sm tabular-nums text-mute">{i + 1}</td>
                <td className={td}><input className={cell} aria-label={`Deduction ${i + 1} description`} value={d.description} onChange={(e) => setDed(i, { description: e.target.value })} /></td>
                <td className={td}><input className={`${cell} tabular-nums`} aria-label={`Deduction ${i + 1} clause`} value={text(d.clause_ref)} onChange={(e) => setDed(i, { clause_ref: nullable(e.target.value) })} /></td>
                <td className={td}><input className={`${num} font-medium`} inputMode="decimal" aria-label={`Deduction ${i + 1} amount`} value={d.amount} onChange={(e) => setDed(i, { amount: e.target.value })} /></td>
                <td className={td}><RemoveButton label={`Remove deduction ${i + 1}`} onClick={() => set('deductions', ded.filter((_, j) => j !== i))} /></td>
              </tr>
            ))}
          </tbody>
          <TotalRow span={3} label="Itemised deductions add up to" sum={sum} />
        </TableFrame>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <button type="button" className={btn.linkSm} onClick={() => set('deductions', [...ded, { description: '', amount: '0', clause_ref: null }])}>
            <Plus className="size-4" /> Add deduction
          </button>
          <Reconcile sum={sum} stated={draft.total_deductions} what="total deductions" />
        </div>
      </Group>
      <SaveBar saving={saving} dirty={dirty} onSave={save} raw={raw} />
    </div>
  )
}

const EXCLUDABLE = ['pharmacy', 'consumables', 'implants', 'diagnostics', 'icu']

export function PolicyEditor({ value, onSave, text: raw }: Editor<PolicyDocument>) {
  const { draft, set, saving, save, dirty } = useDraft(value, onSave)
  return (
    <div>
      <Group title="Policy">
        <Grid>
          <TextField label="Policy name" obj={draft} k="policy_name" set={set} />
          <TextField label="Policy number" obj={draft} k="policy_number" set={set} />
          <TextField label="Sum insured (₹)" obj={draft} k="sum_insured" set={set} money />
        </Grid>
      </Group>
      <Group title="Room and ICU limits">
        <Grid>
          <TextField label="Room-rent limit per day (₹)" obj={draft} k="room_rent_limit_per_day" set={set} money />
          <TextField label="Room-rent clause" obj={draft} k="room_rent_clause" set={set} />
          <TextField label="Proportionate-deduction clause" obj={draft} k="proportionate_clause" set={set} />
          <TextField label="ICU limit per day (₹)" obj={draft} k="icu_limit_per_day" set={set} money />
          <TextField label="ICU clause" obj={draft} k="icu_clause" set={set} />
        </Grid>
      </Group>
      <Group title="Co-payment and non-payables">
        <Grid>
          <TextField label="Co-payment %" obj={draft} k="copay_percent" set={set} money />
          <TextField label="Co-payment applies…" obj={draft} k="copay_condition" set={set} />
          <TextField label="Co-payment clause" obj={draft} k="copay_clause" set={set} />
          <TextField label="Non-payable clause" obj={draft} k="non_payable_clause" set={set} />
        </Grid>
      </Group>
      <Group title="Rules">
        <div className="grid gap-6 lg:grid-cols-3">
          <Field label="Proportionate deduction does not apply to">
            <div className="flex flex-wrap gap-x-5 gap-y-3 pt-2">
              {EXCLUDABLE.map((c) => (
                <label key={c} className="flex items-center gap-2 text-[15px] font-normal text-ink-2">
                  <input
                    type="checkbox"
                    className="size-[18px] accent-ink"
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
              className={`${input} h-32 py-2.5 leading-relaxed`}
              value={draft.non_payable_items.join('\n')}
              onChange={(e) => set('non_payable_items', e.target.value.split('\n'))}
              onBlur={(e) => set('non_payable_items', e.target.value.split('\n').map((s) => s.trim()).filter(Boolean))}
            />
          </Field>
          <Field label="Sub-limits (name: amount)">
            <textarea
              className={`${input} h-32 py-2.5 leading-relaxed`}
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
      </Group>
      <details className="group mt-10 border-y border-hairline">
        <summary className="flex cursor-pointer list-none items-center justify-between py-4 text-[15px] font-medium text-ink">
          {draft.clauses.length} clauses recognised
          <ChevronDown aria-hidden className="size-4 text-mute transition-transform duration-300 group-open:rotate-180" />
        </summary>
        <ul className="divide-y divide-hairline border-t border-hairline">
          {draft.clauses.map((c) => (
            <li key={c.id} className="grid grid-cols-[4.5rem_1fr] gap-3 py-3 text-[15px]">
              <span className="tabular-nums text-mute">{c.id}</span>
              <span className="text-ink-2">{c.title}</span>
            </li>
          ))}
        </ul>
      </details>
      <SaveBar saving={saving} dirty={dirty} onSave={save} raw={raw} />
    </div>
  )
}
