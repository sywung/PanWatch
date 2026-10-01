import { fetchAPI } from './client'

export interface FuturesInfo {
  code: string
  name: string
  kind: 'index' | 'stock'
  underlying_code: string | null
  contract: string
  contract_month: string
  settlement_date: string
  days_to_settlement: number
  session: string
  futures_price: number | null
  spot: number | null
  spot_time: string | null
  basis: number | null
  basis_pct: number | null
}

export const futuresApi = {
  info: (code: string) => fetchAPI<FuturesInfo>(`/futures/${encodeURIComponent(code)}`),
}
