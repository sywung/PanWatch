export interface MarketBadgeInfo {
  style: string
  label: string
}

export const DEFAULT_MARKET = 'TW' as const
export const BASE_CURRENCY = 'TWD' as const
export const MARKET_CODES = ['TW', 'CN', 'HK', 'US'] as const
export type MarketCode = typeof MARKET_CODES[number]

type Translate = (key: string) => string

export function marketCurrency(market?: string): string {
  switch (String(market || '').trim().toUpperCase()) {
    case 'TW': return 'TWD'
    case 'CN': return 'CNY'
    case 'HK': return 'HKD'
    case 'US': return 'USD'
    default: return BASE_CURRENCY
  }
}

export function marketLotSize(market?: string): number | null {
  const code = String(market || '').trim().toUpperCase()
  if (code === 'TW') return 1000
  if (code === 'CN') return 100
  return null
}

export function getMarketBadge(market: string | undefined, t: Translate): MarketBadgeInfo | null {
  const code = String(market || '').trim().toUpperCase()
  if (code === DEFAULT_MARKET) return null
  if (code === 'CN') return { style: 'bg-blue-500/10 text-blue-600', label: t('CN') }
  if (code === 'HK') return { style: 'bg-orange-500/10 text-orange-600', label: t('HK') }
  if (code === 'US') return { style: 'bg-green-500/10 text-green-600', label: t('US') }
  return { style: 'bg-slate-500/10 text-slate-600', label: code || '—' }
}
