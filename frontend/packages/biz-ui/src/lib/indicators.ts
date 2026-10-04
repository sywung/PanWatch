export interface IndicatorCandle {
  date: string
  high: number
  low: number
  close: number
  volume: number
}

export type IndicatorLine = Array<number | null>

export interface KdValues {
  k: IndicatorLine
  d: IndicatorLine
}

export interface BollingerValues {
  upper: IndicatorLine
  middle: IndicatorLine
  lower: IndicatorLine
}

export interface KlineIndicatorSettings {
  ma: boolean
  ma60: boolean
  ma120: boolean
  ma240: boolean
  boll: boolean
  vwap: boolean
  macd: boolean
  rsi: boolean
  kd: boolean
  obv: boolean
}

export const DEFAULT_KLINE_INDICATOR_SETTINGS: KlineIndicatorSettings = {
  ma: true,
  ma60: false,
  ma120: false,
  ma240: false,
  boll: false,
  vwap: false,
  macd: true,
  rsi: true,
  kd: false,
  obv: false,
}

export const KLINE_INDICATOR_STORAGE_KEY = 'panwatch.kline.indicators'

export function calculateSma(values: number[], period: number): IndicatorLine {
  const out: IndicatorLine = new Array(values.length).fill(null)
  if (!Number.isInteger(period) || period <= 0) return out
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= period) sum -= values[i - period]
    if (i >= period - 1) out[i] = sum / period
  }
  return out
}

export function calculateKd(klines: IndicatorCandle[]): KdValues {
  const k: IndicatorLine = new Array(klines.length).fill(null)
  const d: IndicatorLine = new Array(klines.length).fill(null)
  let previousK = 50
  let previousD = 50

  for (let i = 8; i < klines.length; i++) {
    let highest = -Infinity
    let lowest = Infinity
    for (let j = i - 8; j <= i; j++) {
      highest = Math.max(highest, klines[j].high)
      lowest = Math.min(lowest, klines[j].low)
    }
    const rsv = highest === lowest ? 50 : ((klines[i].close - lowest) / (highest - lowest)) * 100
    previousK = previousK * (2 / 3) + rsv * (1 / 3)
    previousD = previousD * (2 / 3) + previousK * (1 / 3)
    k[i] = previousK
    d[i] = previousD
  }

  return { k, d }
}

export function calculateBollinger(klines: IndicatorCandle[], period = 20, deviations = 2): BollingerValues {
  const upper: IndicatorLine = new Array(klines.length).fill(null)
  const middle: IndicatorLine = new Array(klines.length).fill(null)
  const lower: IndicatorLine = new Array(klines.length).fill(null)
  if (!Number.isInteger(period) || period <= 0) return { upper, middle, lower }

  for (let i = period - 1; i < klines.length; i++) {
    let sum = 0
    for (let j = i - period + 1; j <= i; j++) sum += klines[j].close
    const average = sum / period
    let squaredDifferenceSum = 0
    for (let j = i - period + 1; j <= i; j++) squaredDifferenceSum += (klines[j].close - average) ** 2
    const standardDeviation = Math.sqrt(squaredDifferenceSum / period)
    middle[i] = average
    upper[i] = average + deviations * standardDeviation
    lower[i] = average - deviations * standardDeviation
  }

  return { upper, middle, lower }
}

export function calculateObv(klines: IndicatorCandle[]): IndicatorLine {
  const out: IndicatorLine = new Array(klines.length).fill(null)
  if (klines.length === 0) return out
  out[0] = 0
  for (let i = 1; i < klines.length; i++) {
    const previous = out[i - 1] as number
    out[i] = klines[i].close > klines[i - 1].close
      ? previous + klines[i].volume
      : klines[i].close < klines[i - 1].close
        ? previous - klines[i].volume
        : previous
  }
  return out
}

export function calculateVwap(klines: IndicatorCandle[]): IndicatorLine {
  const out: IndicatorLine = new Array(klines.length).fill(null)
  let currentDate = ''
  let cumulativeVolume = 0
  let cumulativePriceVolume = 0

  for (let i = 0; i < klines.length; i++) {
    const date = klines[i].date.slice(0, 10)
    if (date !== currentDate) {
      currentDate = date
      cumulativeVolume = 0
      cumulativePriceVolume = 0
    }
    const { high, low, close, volume } = klines[i]
    const typicalPrice = (high + low + close) / 3
    cumulativeVolume += volume
    cumulativePriceVolume += typicalPrice * volume
    if (cumulativeVolume > 0) out[i] = cumulativePriceVolume / cumulativeVolume
  }
  return out
}

export function readKlineIndicatorSettings(
  storage?: Pick<Storage, 'getItem'>,
): KlineIndicatorSettings {
  try {
    const target = storage ?? (typeof window === 'undefined' ? undefined : window.localStorage)
    const raw = target?.getItem(KLINE_INDICATOR_STORAGE_KEY)
    if (!raw) return { ...DEFAULT_KLINE_INDICATOR_SETTINGS }
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { ...DEFAULT_KLINE_INDICATOR_SETTINGS }
    }
    const values = parsed as Record<string, unknown>
    return Object.fromEntries(
      Object.entries(DEFAULT_KLINE_INDICATOR_SETTINGS).map(([key, fallback]) => [
        key,
        typeof values[key] === 'boolean' ? values[key] : fallback,
      ]),
    ) as KlineIndicatorSettings
  } catch {
    return { ...DEFAULT_KLINE_INDICATOR_SETTINGS }
  }
}
