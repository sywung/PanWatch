import { describe, expect, it } from 'vitest'

import {
  crosshairDateKey,
  decideKlineExpansion,
  doubledKlineRequestDays,
  isIntradayInterval,
  klineRequestUrl,
  parseKlineTime,
  shiftLogicalRange,
} from '@panwatch/biz-ui/components/interactive-kline-utils'

describe('interactive kline time conversion', () => {
  it('treats exchange-local minute digits as UTC timestamps', () => {
    expect(parseKlineTime('2026-10-01 09:00', '30m')).toBe(Date.UTC(2026, 9, 1, 9, 0) / 1000)
    expect(crosshairDateKey(Date.UTC(2026, 9, 1, 9, 0) / 1000, true)).toBe('2026-10-01 09:00')
  })

  it('keeps daily, weekly, and monthly bars as BusinessDay values', () => {
    expect(parseKlineTime('2026-10-01', '1d')).toEqual({ year: 2026, month: 10, day: 1 })
    expect(parseKlineTime('2026-10-01', '1w')).toEqual({ year: 2026, month: 10, day: 1 })
    expect(parseKlineTime('2026-10-01', '1m')).toEqual({ year: 2026, month: 10, day: 1 })
    expect(isIntradayInterval('1m')).toBe(false)
  })
})

describe('interactive kline requests and history expansion', () => {
  it('keeps 1m as the monthly interval in the request', () => {
    expect(klineRequestUrl('2330', 'TW', 1300, '1m')).toBe(
      '/klines/2330?market=TW&days=1300&interval=1m',
    )
  })

  it('sends the selected minute interval', () => {
    expect(klineRequestUrl('2330', 'TW', 500, '30m')).toBe(
      '/klines/2330?market=TW&days=500&interval=30m',
    )
  })

  it('doubles requested history up to 5200 days', () => {
    expect(doubledKlineRequestDays(500)).toBe(1000)
    expect(doubledKlineRequestDays(2600)).toBe(5200)
    expect(doubledKlineRequestDays(5200)).toBe(5200)
  })

  it('stops when the expanded response has no more bars', () => {
    expect(decideKlineExpansion(1000, 700, 700)).toEqual({
      added: 0,
      nextDays: 1000,
      reachedEarliest: true,
    })
  })

  it('stops at the request cap and shifts the old logical range by added bars', () => {
    expect(decideKlineExpansion(2600, 1800, 2300)).toEqual({
      added: 500,
      nextDays: 5200,
      reachedEarliest: false,
    })
    expect(decideKlineExpansion(5200, 2300, 2400).reachedEarliest).toBe(true)
    expect(shiftLogicalRange({ from: 4, to: 104 }, 500)).toEqual({ from: 504, to: 604 })
  })
})
