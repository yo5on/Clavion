// Typed client for the Clavion API. Mirrors the Pydantic models in backend/app (money arrives as decimal strings).

export interface Health {
  status: 'ok' | 'degraded'
  version: string
  database: boolean
  ocr_available: boolean
  analysis: string
}

export interface OwnerSession {
  enabled: boolean
  authenticated: boolean
}

export type ProviderState = 'available'

// Both providers run on the Clavion server; neither calls an external or AI service.
export interface Provider {
  id: 'local' | 'demo'
  label: string
  ai: boolean
  demo: boolean
  status: { state: ProviderState; detail?: string }
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
  admission_date: string | null
  discharge_date: string | null
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
  paid_amount: Money | null
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
  room_rent_category: string | null
  icu_limit_per_day: Money | null
  icu_clause: string | null
  proportionate_clause: string | null
  proportionate_exclusions: string[]
  copay_percent: Money | null
  copay_condition: string | null
  copay_clause: string | null
  non_payable_items: string[]
  non_payable_clause: string | null
  exclusions: string[]
  exclusions_clause: string | null
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
  pages: number
  sha256: string | null
  warnings: string[]
}

/** Where a value was read: page and line (1-based, blank lines counted) of the stored text. */
export interface SourceRef {
  page: number
  line: number
  text: string
}

export type FieldStatus = 'extracted' | 'inferred' | 'missing' | 'corrected'

export interface FieldMeta {
  status: FieldStatus
  source: SourceRef | null
  note: string | null
}

export interface StoredDocument<T> {
  data: T
  provenance: Provenance
  /** Extracted text; pages are separated by a form feed. */
  text: string
  filename: string
  /** Status and source of each field, keyed by path: "total_amount", "line_items.2", "line_items.2.quantity". */
  fields?: Record<string, FieldMeta>
}

export interface Evidence {
  doc_type: DocType
  ref: string
  excerpt: string
  found: boolean
  document: string | null
  source: SourceRef | null
}

export interface Condition {
  text: string
  /** null: could not be checked with the documents provided */
  met: boolean | null
}

export interface Check {
  id: string
  title: string
  status: 'passed' | 'failed' | 'not_checked'
  detail: string
  requires: string[]
  evidence: Evidence[]
}

export interface Readiness {
  state: 'ready' | 'needs_information' | 'nothing_to_appeal'
  summary: string
  items: { label: string; ok: boolean; detail: string }[]
}

export type StatementKind = 'source_fact' | 'calculation' | 'suggestion' | 'standard'

export interface AppealStatement {
  id: string
  section: string
  kind: StatementKind
  text: string
  refs: string[]
  include: boolean
  edited: boolean
  finding_id: number | null
}

export interface TrailEvent {
  at: string
  event: string
  detail: string
}

export type FindingStatus = 'supported' | 'contestable' | 'unverified'

export interface Finding {
  id: number
  rule_id: string
  rule_title: string
  description: string
  category: string
  insurer_amount: Money
  status: FindingStatus
  basis: 'recalculated' | 'policy_list' | 'clause_absent' | 'insufficient' | 'no_reason' | 'reconciliation'
  basis_label: string
  supported_amount: Money | null
  contestable_amount: Money
  what_happened: string
  insurer_statement: string
  policy_clause: string | null
  explanation: string
  contestable_reason: string | null
  missing: string[]
  next_step: string
  classification: string
  conditions: Condition[]
  calculation: string[]
  evidence: Evidence[]
  related_clauses: string[]
}

export interface AuditReport {
  method: string
  rules_version: string
  demo: boolean
  generated_at: string
  bill_total: Money | null
  bill_stated_total: Money | null
  claimed_amount: Money | null
  approved_amount: Money | null
  paid_amount: Money | null
  total_deductions: Money
  supported_total: Money
  contestable_total: Money
  unverified_total: Money
  breakdown: { category: string; amount: Money; count: number }[]
  findings: Finding[]
  checks: Check[]
  readiness: Readiness | null
  documents_to_request: string[]
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
  appeal: { text: string; statements?: AppealStatement[]; source: string; edited: boolean } | null
  trail?: TrailEvent[]
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

// Empty by default: local Vite proxy or a same-origin reverse proxy handles /api.
export function apiUrl(path: string, origin = import.meta.env?.VITE_API_ORIGIN ?? ''): string {
  return origin.trim().replace(/\/+$/, '') + path
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(apiUrl(path), { ...init, credentials: 'include' }).catch(() => {
    throw new Error('Cannot reach the Clavion server. Check your connection and that the backend is running.')
  })
  if (r.status === 204) return undefined as T
  if (!r.ok) {
    if (r.status === 401 && typeof window !== 'undefined') window.dispatchEvent(new Event('clavion-auth-required'))
    let msg = r.status >= 500 ? `The Clavion server could not complete the request (${r.status}).` : `Request failed (${r.status}).`
    try {
      const body = await r.json()
      // Server messages are lowercase fragments; the UI shows them as sentences.
      msg = typeof body.detail === 'string' ? body.detail.charAt(0).toUpperCase() + body.detail.slice(1)
        : Array.isArray(body.detail) // validation errors: "line items › 2 › amount: Input should be ..."
          ? 'Not saved. ' + body.detail.map((e: { loc: (string | number)[]; msg: string }) =>
              `${e.loc.map((p) => (typeof p === 'number' ? p + 1 : p.replace(/_/g, ' '))).join(' › ')}: ${e.msg}`).join('; ')
          : JSON.stringify(body.detail)
      // FastAPI's generic 404 means the route itself is missing: an older backend is answering on this port.
      if (r.status === 404 && body.detail === 'Not Found')
        msg = 'This Clavion server does not support this request. An outdated backend may be running on port 8000: stop it and restart with the documented command.'

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
  authStatus: () => request<OwnerSession>('/api/auth/session'),
  login: (password: string) => request<{ authenticated: boolean }>('/api/auth/login', json('POST', { password })),
  logout: () => request<{ authenticated: boolean }>('/api/auth/logout', { method: 'POST' }),
  health: () => request<Health>('/api/health'),
  providers: () => request<Provider[]>('/api/providers'),
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
  deleteCase: (id: string) => request<void>(`/api/cases/${id}`, { method: 'DELETE' }),
  saveAppeal: (id: string, body: { text: string } | { statements: AppealStatement[] }) =>
    request<CaseDetail>(`/api/cases/${id}/appeal`, json('PUT', body)),
  exportUrl: (id: string, kind: 'report' | 'appeal') => apiUrl(`/api/cases/${id}/export.pdf?kind=${kind}`),
  demoDocumentUrl: (docType: DocType, format: 'pdf' | 'png' = 'pdf') =>
    apiUrl(`/api/demo/documents/${docType}?format=${format}`),
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

export { rupees } from './money.ts'

/** Letter text from the included statements; mirrors services/report.compose on the server. */
export function composeAppeal(statements: AppealStatement[]): string {
  const out: string[] = []
  let section: string | null = null
  for (const st of statements) {
    if (!st.include || !st.text.trim()) continue
    if (section !== null && (st.section !== section || st.kind === 'standard')) out.push('')
    out.push(st.text.trim())
    section = st.section
  }
  return out.join('\n')
}

/** "p. 2, line 14" for a source reference. */
export const where = (s: SourceRef | null | undefined) => (s ? `p. ${s.page}, line ${s.line}` : '')
