import assert from 'node:assert/strict'
import { test } from 'node:test'
import { api, apiUrl } from '../src/api.ts'

test('API URLs preserve local routing and support a separately hosted backend', () => {
  for (const path of ['/api/health', '/api/cases/id/export.pdf?kind=appeal', '/api/demo/documents/bill?format=pdf']) {
    assert.equal(apiUrl(path, ''), path)
    assert.equal(apiUrl(path, '  https://backend.example/  '), `https://backend.example${path}`)
    assert.equal(apiUrl(path, 'https://example.test/clavion/'), `https://example.test/clavion${path}`)
  }
})

test('requests, uploads and download links retain the API routes', async (t) => {
  const calls: { url: string; init?: RequestInit }[] = []
  t.mock.method(globalThis, 'fetch', async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    return new Response('{}', { headers: { 'Content-Type': 'application/json' } })
  })
  await api.health()
  await api.createCase('Synthetic test')
  await api.upload('id', 'bill', new File(['synthetic'], 'bill.txt'), 'local')
  assert.deepEqual(calls.map(c => c.url), ['/api/health', '/api/cases', '/api/cases/id/documents/bill'])
  assert.equal(calls[1].init?.method, 'POST')
  assert.ok(calls.every(c => c.init?.credentials === 'include'))
  assert.equal(calls[1].init?.body, JSON.stringify({ title: 'Synthetic test' }))
  assert.ok(calls[2].init?.body instanceof FormData)
  assert.equal(api.exportUrl('id', 'appeal'), '/api/cases/id/export.pdf?kind=appeal')
  assert.equal(api.demoDocumentUrl('bill', 'png'), '/api/demo/documents/bill?format=png')
})

test('owner authentication uses cookie requests without storing credentials', async (t) => {
  const calls: { url: string; init?: RequestInit }[] = []
  t.mock.method(globalThis, 'fetch', async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    return new Response('{}')
  })
  await api.authStatus()
  await api.login('synthetic test password')
  await api.logout()
  assert.deepEqual(calls.map(c => c.url), ['/api/auth/session', '/api/auth/login', '/api/auth/logout'])
  assert.ok(calls.every(c => c.init?.credentials === 'include'))
  assert.equal(calls[1].init?.body, JSON.stringify({ password: 'synthetic test password' }))
  assert.equal(calls[2].init?.method, 'POST')
})

test('an expired session notifies the UI and rejects the protected request', async (t) => {
  const browser = new EventTarget()
  Object.defineProperty(globalThis, 'window', { value: browser, configurable: true })
  t.after(() => Reflect.deleteProperty(globalThis, 'window'))
  let expired = 0
  browser.addEventListener('clavion-auth-required', () => expired++)
  t.mock.method(globalThis, 'fetch', async () => new Response(
    JSON.stringify({ detail: 'authentication required' }), { status: 401 },
  ))
  await assert.rejects(api.cases(), /Authentication required/)
  assert.equal(expired, 1)
})
