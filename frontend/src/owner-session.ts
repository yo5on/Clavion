import { api, type OwnerSession } from './api.ts'

// A status response started before sign-out/expiry must never reopen the case views.
export function createSessionRefresh(onSession: (session: OwnerSession) => void, onError: (error: Error) => void) {
  let generation = 0
  return {
    invalidate() { generation++ },
    async refresh() {
      const request = ++generation
      try {
        const session = await api.authStatus()
        if (request === generation) onSession(session)
      } catch (error) {
        if (request === generation) onError(error as Error)
      }
    },
  }
}
