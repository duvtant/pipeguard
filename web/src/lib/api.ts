// Typed API client. Types are generated from the API's OpenAPI schema:
//   pnpm gen:api   (needs the API running on :8000, writes src/lib/api-types.ts)
// All paths are relative (/api) so the same bundle works behind nginx and the tunnel.
export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}
