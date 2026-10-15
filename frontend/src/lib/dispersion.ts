export interface DispersionLevel {
  level: number
  holders: number
  shares: number
  pct: number
}

export interface DispersionHistoryPoint {
  data_date: string
  holder_num: number | null
  avg_shares: number | null
  big_holder_ratio: number | null
  thousand_lot_ratio: number | null
}

export const LEVEL_LABELS = [
  '1–999 股',
  '1–5 張',
  '5–10 張',
  '10–15 張',
  '15–20 張',
  '20–30 張',
  '30–40 張',
  '40–50 張',
  '50–100 張',
  '100–200 張',
  '200–400 張',
  '400–600 張',
  '600–800 張',
  '800–1,000 張',
  '1,000 張以上',
  '差異數調整',
  '合計',
] as const

type DispersionGroup = { holders: number; shares: number; pct: number }

export function groupDispersion(levels: DispersionLevel[]): {
  retail: DispersionGroup
  mid: DispersionGroup
  big: DispersionGroup
} {
  const sumGroup = (from: number, to: number): DispersionGroup => {
    const selected = levels.filter(({ level }) => level >= from && level <= to)
    const pctTotal = selected.reduce((sum, row) => sum + row.pct, 0)
    return {
      holders: selected.reduce((sum, row) => sum + row.holders, 0),
      shares: selected.reduce((sum, row) => sum + row.shares, 0),
      pct: Math.round((pctTotal + Number.EPSILON) * 100) / 100,
    }
  }

  return {
    retail: sumGroup(1, 3),
    mid: sumGroup(4, 11),
    big: sumGroup(12, 15),
  }
}

export function formatChange(value: number | null | undefined, digits: number): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const normalized = value === 0 ? 0 : value
  const formatted = normalized.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
  return normalized > 0 ? `+${formatted}` : formatted
}

export function buildTrendSeries(history: DispersionHistoryPoint[]): {
  thousand: Array<{ time: string; value: number }>
  big: Array<{ time: string; value: number }>
  holders: Array<{ time: string; value: number }>
} {
  const ordered = [...history].sort((a, b) => a.data_date.localeCompare(b.data_date))
  const makeSeries = (key: 'thousand_lot_ratio' | 'big_holder_ratio' | 'holder_num') =>
    ordered.flatMap((point) => {
      const value = point[key]
      return value == null ? [] : [{ time: point.data_date, value }]
    })

  return {
    thousand: makeSeries('thousand_lot_ratio'),
    big: makeSeries('big_holder_ratio'),
    holders: makeSeries('holder_num'),
  }
}
