import { isFuturesMarket, marketCurrency } from './market'

const FUTURES_BASIS_LABELS_ZH = {
  zhTW: { positive: '正價差', negative: '逆價差', parity: '平價' },
  zhCN: { positive: '正价差', negative: '逆价差', parity: '平价' },
}
const FUTURES_BASIS_LABELS_EN = { positive: 'Contango', negative: 'Backwardation', parity: 'At parity' }

export interface FuturesNewsInfo {
  kind?: string | null
  underlying_code?: string | null
  name?: string | null
}

export function settlementUrgency(days?: number | null): 'expired' | 'today' | 'soon' | 'none' {
  if (days == null || !Number.isFinite(days)) return 'none'
  if (days < 0) return 'expired'
  if (days === 0) return 'today'
  if (days <= 5) return 'soon'
  return 'none'
}

export function futuresUnderlyingName(name: string): string {
  return String(name || '').replace(/^小型/, '').replace(/期貨$/, '')
}

export function futuresNewsTarget(info?: FuturesNewsInfo | null): { symbol: string; name: string; market: 'TW' } | null {
  if (info?.kind !== 'stock' || !info.underlying_code) return null
  return {
    symbol: info.underlying_code,
    name: futuresUnderlyingName(info.name || ''),
    market: 'TW',
  }
}

// 后端 spot_time 为期交所 MIS 的 "HH:MM:SS"(当日行情时间),不是 ISO 时间戳
export function formatSpotTime(value?: string | null): string {
  const match = /^(\d{2}):(\d{2}):\d{2}$/.exec(String(value || '').trim())
  return match ? `${match[1]}:${match[2]}` : ''
}

export function canEvaluateAddPosition(market?: string): boolean {
  return !isFuturesMarket(market)
}

export function futuresBasisLabel(basis: number | null | undefined, locale: string): string {
  if (basis == null || Number.isNaN(Number(basis))) return ''
  const language = String(locale || '').toLowerCase()
  if (language.startsWith('zh-tw')) {
    return basis > 0 ? FUTURES_BASIS_LABELS_ZH.zhTW.positive
      : basis < 0 ? FUTURES_BASIS_LABELS_ZH.zhTW.negative
        : FUTURES_BASIS_LABELS_ZH.zhTW.parity
  }
  if (language.startsWith('zh')) {
    return basis > 0 ? FUTURES_BASIS_LABELS_ZH.zhCN.positive
      : basis < 0 ? FUTURES_BASIS_LABELS_ZH.zhCN.negative
        : FUTURES_BASIS_LABELS_ZH.zhCN.parity
  }
  return basis > 0 ? FUTURES_BASIS_LABELS_EN.positive
    : basis < 0 ? FUTURES_BASIS_LABELS_EN.negative
      : FUTURES_BASIS_LABELS_EN.parity
}

export function formatCompactAmount(value: number | null | undefined, locale: string): string {
  if (value == null || !Number.isFinite(Number(value))) return '--'
  const n = Number(value)
  const abs = Math.abs(n)
  if (abs < 1e4) return Number.isInteger(n) ? String(n) : n.toFixed(2)

  const language = String(locale || '').toLowerCase()
  if (language.startsWith('zh-tw')) {
    if (abs >= 1e8) return `${(n / 1e8).toFixed(2)}億`
    return `${(n / 1e4).toFixed(2)}萬`
  }
  if (language.startsWith('zh')) {
    if (abs >= 1e8) return `${(n / 1e8).toFixed(2)}亿`
    return `${(n / 1e4).toFixed(2)}万`
  }
  if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${(n / 1e6).toFixed(2)}M`
  return `${(n / 1e3).toFixed(2)}K`
}

export function formatMarketCapLabel(
  value: number | null | undefined,
  market: string | undefined,
  locale: string
): string {
  if (value == null || !Number.isFinite(Number(value))) return '--'
  const n = Number(value)
  const code = String(market || '').trim().toUpperCase()
  const language = String(locale || '').toLowerCase()

  if (language.startsWith('en')) {
    const abs = Math.abs(n)
    const currency = marketCurrency(code)
    if (abs >= 10000) return `${(n / 10000).toFixed(2)}T ${currency}`
    if (abs >= 10) return `${(n / 10).toFixed(2)}B ${currency}`
    return `${(n * 100).toFixed(2)}M ${currency}`
  }

  if (language.startsWith('zh-tw')) {
    if (code === 'US') return `${n.toFixed(2)}億美元`
    if (code === 'HK') return `${n.toFixed(2)}億港元`
    if (code === 'TW' || code === 'TWF') return `${n.toFixed(2)}億新台幣`
    return `${n.toFixed(2)}億元（人民幣）`
  }

  if (code === 'US') return `${n.toFixed(2)}亿美元`
  if (code === 'HK') return `${n.toFixed(2)}亿港元`
  if (code === 'TW' || code === 'TWF') return `${n.toFixed(2)}亿新台币`
  return `${n.toFixed(2)}亿元（人民币）`
}
