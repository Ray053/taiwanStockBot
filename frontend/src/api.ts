import type { MacroSnapshot, ScreeningResult, StockHistory } from './types'

const BASE = '/api/v1'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  screening: {
    today: () => get<ScreeningResult>('/screening/today'),
    stock: (id: string, days = 30) =>
      get<StockHistory>(`/screening/stock/${id}?days=${days}`),
  },
  macro: {
    latest: () => get<MacroSnapshot>('/macro/latest'),
  },
  admin: {
    triggerScore: () =>
      fetch(`${BASE}/admin/trigger-score`, { method: 'POST' }).then(r => r.json()),
  },
}
