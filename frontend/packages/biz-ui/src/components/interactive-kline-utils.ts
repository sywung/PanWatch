export type KlineInterval = '1d' | '1w' | '1m' | '5m' | '15m' | '30m' | '60m'
export type BusinessDay = { year: number; month: number; day: number }
export type UTCTimestamp = number & { readonly __utcTimestamp: unique symbol }
export type KlineTime = BusinessDay | UTCTimestamp
export type LogicalRange = { from: number; to: number }

export const MAX_KLINE_DAYS = 5200

export function doubledKlineRequestDays(requestedDays: number, maxDays = MAX_KLINE_DAYS): number {
  return Math.min(maxDays, requestedDays * 2)
}

export function isIntradayInterval(interval: KlineInterval): boolean {
  return interval === '5m' || interval === '15m' || interval === '30m' || interval === '60m'
}

export function parseKlineTime(date: string, interval: KlineInterval): KlineTime | null {
  const value = String(date || '').trim()
  const intraday = value.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/)
  if (isIntradayInterval(interval)) {
    if (!intraday) return null
    const [, year, month, day, hour, minute] = intraday
    return (Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute)) / 1000) as UTCTimestamp
  }

  const daily = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!daily) return null
  return { year: Number(daily[1]), month: Number(daily[2]), day: Number(daily[3]) }
}

export function crosshairDateKey(time: unknown, intraday: boolean): string | null {
  if (intraday) {
    if (typeof time !== 'number' || !Number.isFinite(time)) return null
    const date = new Date(time * 1000)
    if (Number.isNaN(date.getTime())) return null
    return date.toISOString().slice(0, 16).replace('T', ' ')
  }
  if (!time || typeof time !== 'object') return null
  const value = time as Partial<BusinessDay>
  const year = Number(value.year)
  const month = Number(value.month)
  const day = Number(value.day)
  if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) return null
  return `${year.toString().padStart(4, '0')}-${month.toString().padStart(2, '0')}-${day.toString().padStart(2, '0')}`
}

export function klineRequestUrl(symbol: string, market: string, days: number, interval: KlineInterval): string {
  return `/klines/${encodeURIComponent(symbol)}?market=${encodeURIComponent(market)}&days=${encodeURIComponent(String(days))}&interval=${encodeURIComponent(interval)}`
}

export type ExpansionDecision = {
  added: number
  nextDays: number
  reachedEarliest: boolean
}

export function decideKlineExpansion(
  requestedDays: number,
  oldCount: number,
  newCount: number,
  maxDays = MAX_KLINE_DAYS,
): ExpansionDecision {
  const added = Math.max(0, newCount - oldCount)
  const reachedEarliest = added === 0 || requestedDays >= maxDays
  return {
    added,
    nextDays: reachedEarliest ? Math.min(maxDays, requestedDays) : doubledKlineRequestDays(requestedDays, maxDays),
    reachedEarliest,
  }
}

export function shiftLogicalRange(range: LogicalRange, added: number): LogicalRange {
  return { from: range.from + added, to: range.to + added }
}
