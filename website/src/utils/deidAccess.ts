const STORAGE_KEY = 'deid_access_session'

export function getDeidAccessToken(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export function setDeidAccessToken(session: string): void {
  sessionStorage.setItem(STORAGE_KEY, session.trim())
}

export function clearDeidAccessToken(): void {
  sessionStorage.removeItem(STORAGE_KEY)
}

export function deidFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const session = getDeidAccessToken()
  const headers = new Headers(init?.headers)
  if (session) headers.set('X-Deid-Access-Token', session)
  return fetch(input, { ...init, headers })
}

export function deidEventSourceUrl(path: string): string {
  const session = getDeidAccessToken()
  if (!session) return path
  const sep = path.includes('?') ? '&' : '?'
  return `${path}${sep}access_token=${encodeURIComponent(session)}`
}

/** Submit day code; server validates and returns opaque session. */
export async function verifyDeidDayCode(code: string): Promise<string | null> {
  const r = await fetch('/api/deid/access/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: code.trim() }),
  })
  if (!r.ok) return null
  const data = (await r.json()) as { session?: string }
  return data.session ?? null
}

/** Re-validate stored session with server (no client-side calculation). */
export async function checkDeidSession(): Promise<boolean> {
  const session = getDeidAccessToken()
  if (!session) return false
  const r = await deidFetch('/api/deid/access/check')
  return r.ok
}
