// Typed client for the Clavion API. Mirrors the Pydantic models in backend/app (money arrives as decimal strings).

export interface Health {
  status: 'ok' | 'degraded'
  version: string
  database: boolean
  llm_configured: boolean
  model: string
}

export interface LLMHealth {
  reachable: boolean
  model: string
  model_listed: boolean
  model_capabilities: { input?: string[]; toolCalling?: boolean; reasoning?: boolean } | null
  live_inference: boolean | null
  error: string | null
}

export type ProviderState =
  | 'available'
  | 'connected'
  | 'not_configured'
  | 'subscription_required'
  | 'connection_failed'
  | 'not_checked'

export interface Provider {
  id: 'local' | 'bharatcode' | 'demo'
  label: string
  ai: boolean
  demo: boolean
  status: { state: ProviderState; detail?: string; checked_at?: string; model?: string }
}

export type DocType = 'bill' | 'policy' | 'settlement'
export type Money = string

export interface BillLineItem {
  description: string
  quantity: Money | null
  unit_price: Money | null
  amount: Money
  category: string | null
}

export interface HospitalBill {
  hospital_name: string | null
  bill_number: string | null
  patient_name: string | null
  bill_date: string | null
  line_items: BillLineItem[]
  total_amount: Money | null
}

export interface SettlementDeduction {
  description: string
  amount: Money
  clause_ref: string | null
}

export interface SettlementLetter {
  insurer_name: string | null
  claim_number: string | null
  policy_number: string | null
  patient_name: string | null
  hospital_name: string | null
  claimed_amount: Money | null
  approved_amount: Money | null
  total_deductions: Money | null
  deductions: SettlementDeduction[]
}

export interface PolicyClause {
  id: string
  title: string
  text: string
}

export interface PolicyDocument {
  policy_name: string | null
  policy_number: string | null
  sum_insured: Money | null
  room_rent_limit_per_day: Money | null
  room_rent_clause: string | null
  icu_limit_per_day: Money | null
  icu_clause: string | null
  proportionate_clause: string | null
  proportionate_exclusions: string[]
  copay_percent: Money | null
  copay_condition: string | null
  copay_clause: string | null
  non_payable_items: string[]
  non_payable_clause: string | null
  sub_limits: { name: string; limit: Money; clause_id: string | null }[]
  clauses: PolicyClause[]
}

export interface Provenance {
  provider: Provider['id']
  label: string
  ai_generated: boolean
  demo: boolean
  manually_corrected: boolean
  text_method: string | null
  warnings: string[]
}

export interface StoredDocument<T> {
  data: T
  provenance: Provenance
  text: string
  filename: string
}

export interface Evidence {
  doc_type: DocType
  ref: string
  excerpt: string
  found: boolean
}

export type FindingStatus = 'supported' | 'contestable' | 'unverified'

export interface Finding {
  id: number
  description: string
  category: string
  insurer_amount: Money
  status: FindingStatus
  supported_amount: Money | null
  contestable_amount: Money
  explanation: string
  calculation: string[]
  evidence: Evidence[]
  related_clauses: string[]
}

export interface AuditReport {
  method: string
  demo: boolean
  generated_at: string
  bill_total: Money | null
  bill_stated_total: Money | null
  claimed_amount: Money | null
  approved_amount: Money | null
  total_deductions: Money
  supported_total: Money
  contestable_total: Money
  unverified_total: Money
  breakdown: { category: string; amount: Money; count: number }[]
  findings: Finding[]
  missing_information: string[]
}

export interface CaseDetail {
  id: string
  title: string
  status: 'draft' | 'audited'
  created_at: string
  demo: boolean
  documents: {
    bill?: StoredDocument<HospitalBill>
    policy?: StoredDocument<PolicyDocument>
    settlement?: StoredDocument<SettlementLetter>
  }
  audit: AuditReport | null
  appeal: { text: string; source: string; edited: boolean } | null
}

export interface CaseSummary {
  id: string
  title: string
  status: CaseDetail['status']
  created_at: string
  demo: boolean
  documents: DocType[]
  claimed_amount: Money | null
  approved_amount: Money | null
  contestable_total: Money | null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init).catch(() => {
    throw new Error('Cannot reach the Clavion server. Check your connection and that the backend is running.')
  })
  if (!r.ok) {
    let msg = r.status >= 500 ? `The Clavion server could not complete the request (${r.status}).` : `Request failed (${r.status}).`
    try {
      const body = await r.json()
      // Server messages are lowercase fragments; the UI shows them as sentences.
      msg = typeof body.detail === 'string' ? body.detail.charAt(0).toUpperCase() + body.detail.slice(1) : JSON.stringify(body.detail)
    } catch {
      /* non-JSON error body */
    }
    throw new Error(msg)
  }
  return r.json() as Promise<T>
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  health: () => request<Health>('/api/health'),
  llmHealth: (live = false) => request<LLMHealth>(`/api/health/llm${live ? '?live=true' : ''}`),
  providers: () => request<Provider[]>('/api/providers'),
  checkBharatCode: () => request<Provider>('/api/providers/bharatcode/check', { method: 'POST' }),
  cases: () => request<CaseSummary[]>('/api/cases'),
  case: (id: string) => request<CaseDetail>(`/api/cases/${id}`),
  createCase: (title: string) => request<CaseDetail>('/api/cases', json('POST', { title })),
  demoCase: () => request<CaseDetail>('/api/demo/case', { method: 'POST' }),
  upload: (id: string, docType: DocType, file: File, provider: Provider['id']) => {
    const form = new FormData()
    form.append('file', file)
    form.append('provider', provider)
    return request<CaseDetail>(`/api/cases/${id}/documents/${docType}`, { method: 'POST', body: form })
  },
  correct: (id: string, docType: DocType, data: unknown) =>
    request<CaseDetail>(`/api/cases/${id}/documents/${docType}`, json('PUT', data)),
  audit: (id: string) => request<CaseDetail>(`/api/cases/${id}/audit`, { method: 'POST' }),
  saveAppeal: (id: string, text: string) => request<CaseDetail>(`/api/cases/${id}/appeal`, json('PUT', { text })),
  exportUrl: (id: string, kind: 'report' | 'appeal') => `/api/cases/${id}/export.pdf?kind=${kind}`,
  demoDocumentUrl: (docType: DocType, format: 'pdf' | 'png' = 'pdf') =>
    `/api/demo/documents/${docType}?format=${format}`,
}

export const DOC_LABELS: Record<DocType, string> = {
  bill: 'Hospital bill',
  policy: 'Policy wording',
  settlement: 'Settlement letter',
}

export const CATEGORY_LABELS: Record<string, string> = {
  room_rent: 'Room rent',
  icu: 'ICU',
  professional: 'Professional fees',
  ot: 'Operation theatre',
  nursing: 'Nursing',
  pharmacy: 'Pharmacy',
  consumables: 'Consumables',
  implants: 'Implants & devices',
  diagnostics: 'Diagnostics',
  admin: 'Administrative',
  other: 'Other',
}

const inr = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export function rupees(v: Money | null | undefined): string {
  return v === null || v === undefined || v === '' ? '—' : `₹${inr.format(Number(v))}`
}
