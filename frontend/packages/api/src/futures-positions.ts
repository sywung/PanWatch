import { fetchAPI } from './client'

export interface FuturesPosition {
  id: number
  account_id: number
  account_name: string | null
  product_code: string
  product_name: string
  contract_month: string
  contract_symbol: string
  direction: 'long' | 'short'
  lots: number
  entry_price: number
  multiplier: number | null
  note: string | null
  current_price: number | null
  unrealized_pnl: number | null
  margin_used: number | null
  maintenance_required: number | null
  equity: number | null
  margin_call: boolean | null
  settlement_date: string | null
  days_to_settlement: number | null
}

export interface FuturesPositionCreatePayload {
  account_id: number
  product_code: string
  contract_month: string
  direction: 'long' | 'short'
  lots: number
  entry_price: number
  multiplier?: number | null
  note?: string | null
}

export interface FuturesPositionUpdatePayload {
  contract_month?: string | null
  direction?: 'long' | 'short'
  lots?: number
  entry_price?: number
  multiplier?: number | null
  note?: string | null
}

export interface FuturesPositionOptions {
  product_code: string
  product_name: string
  multiplier: number
  months: Array<{
    contract_month: string
    contract_symbol: string
    settlement_date: string
  }>
}

export const futuresPositionsApi = {
  list: (accountId?: number) => fetchAPI<FuturesPosition[]>(
    `/futures-positions${accountId == null ? '' : `?account_id=${encodeURIComponent(accountId)}`}`,
  ),
  create: (payload: FuturesPositionCreatePayload) => fetchAPI<FuturesPosition>('/futures-positions', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  update: (id: number, payload: FuturesPositionUpdatePayload) => fetchAPI<FuturesPosition>(
    `/futures-positions/${encodeURIComponent(id)}`,
    { method: 'PUT', body: JSON.stringify(payload) },
  ),
  remove: (id: number) => fetchAPI<{ success: boolean }>(`/futures-positions/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  }),
  options: (productCode: string) => fetchAPI<FuturesPositionOptions>(
    `/futures-positions/options?product_code=${encodeURIComponent(productCode)}`,
  ),
}
