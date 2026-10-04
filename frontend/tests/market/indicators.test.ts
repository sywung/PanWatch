import { describe, expect, it } from 'vitest'

import {
  calculateBollinger,
  calculateKd,
  calculateObv,
  calculateSma,
  calculateVwap,
  DEFAULT_KLINE_INDICATOR_SETTINGS,
  KLINE_INDICATOR_STORAGE_KEY,
  readKlineIndicatorSettings,
  type IndicatorCandle,
} from '@panwatch/biz-ui/lib/indicators'

function candle(overrides: Partial<IndicatorCandle> = {}): IndicatorCandle {
  return {
    date: '2026-01-01',
    high: 10,
    low: 0,
    close: 5,
    volume: 1,
    ...overrides,
  }
}

describe('K-line indicators', () => {
  it('calculates Taiwan KD from the ninth bar, smoothing from 50, and uses RSV 50 for a flat range', () => {
    const bars = Array.from({ length: 8 }, () => candle())
    bars.push(candle({ close: 10 }), candle({ close: 0 }), candle({ close: 5 }))

    const kd = calculateKd(bars)
    expect(kd.k.slice(0, 8)).toEqual(Array(8).fill(null))
    expect(kd.d.slice(0, 8)).toEqual(Array(8).fill(null))
    expect(kd.k[8]).toBeCloseTo(66.6666666667, 8)
    expect(kd.d[8]).toBeCloseTo(55.5555555556, 8)
    expect(kd.k[9]).toBeCloseTo(44.4444444444, 8)
    expect(kd.d[9]).toBeCloseTo(51.8518518519, 8)
    expect(kd.k[10]).toBeCloseTo(46.2962962963, 8)
    expect(kd.d[10]).toBeCloseTo(49.9999999999, 8)

    const flat = calculateKd(Array.from({ length: 9 }, () => candle({ high: 7, low: 7, close: 7 })))
    expect(flat.k[8]).toBeCloseTo(50, 10)
    expect(flat.d[8]).toBeCloseTo(50, 10)
  })

  it('calculates 20-bar BOLL using population standard deviation', () => {
    const bars = Array.from({ length: 20 }, (_, i) => candle({ close: i + 1 }))
    const boll = calculateBollinger(bars)
    expect(boll.middle.slice(0, 19)).toEqual(Array(19).fill(null))
    expect(boll.upper.slice(0, 19)).toEqual(Array(19).fill(null))
    expect(boll.lower.slice(0, 19)).toEqual(Array(19).fill(null))
    expect(boll.middle[19]).toBe(10.5)
    expect(boll.upper[19]).toBeCloseTo(22.0325625947, 8)
    expect(boll.lower[19]).toBeCloseTo(-1.0325625947, 8)
  })

  it('returns null until MA60, MA120, and MA240 each have enough closes', () => {
    const closes = Array.from({ length: 240 }, (_, i) => i + 1)
    for (const period of [60, 120, 240]) {
      expect(calculateSma(closes.slice(0, period - 1), period)).toEqual(Array(period - 1).fill(null))
    }
    expect(calculateSma(closes, 60)[59]).toBe(30.5)
    expect(calculateSma(closes, 60)[239]).toBe(210.5)
    expect(calculateSma(closes, 120)[119]).toBe(60.5)
    expect(calculateSma(closes, 120)[239]).toBe(180.5)
    expect(calculateSma(closes, 240)[239]).toBe(120.5)
  })

  it('accumulates OBV on up and down closes and holds on flat closes', () => {
    const bars = [
      candle({ close: 10, volume: 5 }),
      candle({ close: 11, volume: 3 }),
      candle({ close: 10, volume: 7 }),
      candle({ close: 10, volume: 11 }),
    ]
    expect(calculateObv(bars)).toEqual([0, 3, -4, -4])
  })

  it('resets VWAP by trading date and leaves zero cumulative-volume bars null', () => {
    const bars = [
      candle({ date: '2026-01-01 09:00', high: 12, low: 9, close: 9, volume: 0 }),
      candle({ date: '2026-01-01 09:05', high: 12, low: 9, close: 9, volume: 2 }),
      candle({ date: '2026-01-01 09:10', high: 15, low: 12, close: 15, volume: 2 }),
      candle({ date: '2026-01-02 09:00', high: 22, low: 19, close: 19, volume: 0 }),
      candle({ date: '2026-01-02 09:05', high: 22, low: 19, close: 19, volume: 4 }),
    ]
    const vwap = calculateVwap(bars)
    expect(vwap[0]).toBeNull()
    expect(vwap[1]).toBe(10)
    expect(vwap[2]).toBe(12)
    expect(vwap[3]).toBeNull()
    expect(vwap[4]).toBe(20)
  })

  it('uses default indicator toggles when localStorage getItem throws', () => {
    const storage = {
      getItem: (_key: string) => { throw new Error('storage unavailable') },
    }
    expect(readKlineIndicatorSettings(storage)).toEqual(DEFAULT_KLINE_INDICATOR_SETTINGS)
    expect(KLINE_INDICATOR_STORAGE_KEY).toBe('panwatch.kline.indicators')
  })
})
