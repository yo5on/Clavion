import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createSessionRefresh } from '../src/owner-session.ts'
import type { OwnerSession } from '../src/api.ts'

function pendingResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((done) => { resolve = done })
  return { promise, resolve }
}

test('an old authenticated response cannot undo logout, expiration or effect cleanup', async (t) => {
  const response = pendingResponse()
  t.mock.method(globalThis, 'fetch', () => response.promise)
  const sessions: OwnerSession[] = []
  const errors: Error[] = []
  const refresh = createSessionRefresh(s => sessions.push(s), e => errors.push(e))
  const request = refresh.refresh()
  refresh.invalidate()
  response.resolve(Response.json({ enabled: true, authenticated: true }))
  await request
  assert.deepEqual(sessions, [])
  assert.deepEqual(errors, [])
})

test('out-of-order status responses keep the latest session state', async (t) => {
  const first = pendingResponse()
  const second = pendingResponse()
  const responses = [first, second]
  t.mock.method(globalThis, 'fetch', () => responses.shift()!.promise)
  const sessions: OwnerSession[] = []
  const refresh = createSessionRefresh(s => sessions.push(s), e => { throw e })
  const oldRequest = refresh.refresh()
  const newRequest = refresh.refresh()
  second.resolve(Response.json({ enabled: true, authenticated: false }))
  await newRequest
  first.resolve(Response.json({ enabled: true, authenticated: true }))
  await oldRequest
  assert.deepEqual(sessions, [{ enabled: true, authenticated: false }])
})

test('a stale connection failure cannot replace a newer successful status', async (t) => {
  const first = pendingResponse()
  const responses = [first.promise, Promise.resolve(Response.json({ enabled: false, authenticated: true }))]
  t.mock.method(globalThis, 'fetch', () => responses.shift()!)
  const errors: Error[] = []
  const sessions: OwnerSession[] = []
  const refresh = createSessionRefresh(s => sessions.push(s), e => errors.push(e))
  const oldRequest = refresh.refresh()
  await refresh.refresh()
  first.resolve(new Response('unavailable', { status: 503 }))
  await oldRequest
  assert.deepEqual(sessions, [{ enabled: false, authenticated: true }])
  assert.deepEqual(errors, [])
})

test('current status failures reach the connection error view', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('network unavailable') })
  const errors: Error[] = []
  const refresh = createSessionRefresh(() => assert.fail('failed request cannot open the application'), e => errors.push(e))
  await refresh.refresh()
  assert.equal(errors.length, 1)
  assert.match(errors[0].message, /Cannot reach the Clavion server/)
})
