import { describe, expect, it } from 'vitest'
import {
  LEVEL_LABELS,
  buildTrendSeries,
  formatChange,
  groupDispersion,
  type DispersionLevel,
} from './dispersion'

const levels: DispersionLevel[] = Array.from({ length: 17 }, (_, i) => ({
  level: i + 1,
  holders: (i + 1) * 10,
  shares: (i + 1) * 1000,
  pct: i + 1 <= 15 ? 1 : i + 1 === 16 ? 0 : 100,
}))

describe('LEVEL_LABELS', () => {
  it('有 17 個，第 15 級是千張以上，最後是合計', () => {
    expect(LEVEL_LABELS).toHaveLength(17)
    expect(LEVEL_LABELS[14]).toContain('1,000')
    expect(LEVEL_LABELS[16]).toBe('合計')
  })
})

describe('groupDispersion', () => {
  it('散戶 1–3 級、中實戶 4–11 級、大戶 12–15 級', () => {
    const g = groupDispersion(levels)
    expect(g.retail).toEqual({ holders: 10 + 20 + 30, shares: 1000 + 2000 + 3000, pct: 3 })
    expect(g.mid.pct).toBe(8)
    expect(g.mid.holders).toBe([4, 5, 6, 7, 8, 9, 10, 11].reduce((a, n) => a + n * 10, 0))
    expect(g.big).toEqual({
      holders: (12 + 13 + 14 + 15) * 10,
      shares: (12 + 13 + 14 + 15) * 1000,
      pct: 4,
    })
  })

  it('不把差異數調整(16)與合計(17)算進任何一組', () => {
    const g = groupDispersion(levels)
    expect(g.retail.pct + g.mid.pct + g.big.pct).toBe(15)
  })

  it('百分比加總避開浮點誤差，取到小數 2 位', () => {
    const tiny = levels.map((r) => ({ ...r, pct: r.level <= 3 ? 0.1 : r.pct }))
    expect(groupDispersion(tiny).retail.pct).toBe(0.3)
  })

  it('空陣列回傳全 0', () => {
    expect(groupDispersion([])).toEqual({
      retail: { holders: 0, shares: 0, pct: 0 },
      mid: { holders: 0, shares: 0, pct: 0 },
      big: { holders: 0, shares: 0, pct: 0 },
    })
  })
})

describe('formatChange', () => {
  it('正負號與千分位', () => {
    expect(formatChange(0.12, 2)).toBe('+0.12')
    expect(formatChange(-0.5, 2)).toBe('-0.50')
    expect(formatChange(-1234, 0)).toBe('-1,234')
    expect(formatChange(1234, 0)).toBe('+1,234')
  })
  it('0 不帶正負號，null/undefined 顯示 —', () => {
    expect(formatChange(0, 2)).toBe('0.00')
    expect(formatChange(null, 2)).toBe('—')
    expect(formatChange(undefined, 0)).toBe('—')
  })
})

describe('buildTrendSeries', () => {
  const history = [
    { data_date: '2026-10-01', holder_num: 3_021_000, avg_shares: 1, big_holder_ratio: 87.4, thousand_lot_ratio: 84.65 },
    { data_date: '2026-10-08', holder_num: 3_020_649, avg_shares: 1, big_holder_ratio: 87.5, thousand_lot_ratio: 84.77 },
  ]
  it('輸出 lightweight-charts 用的 {time,value}，依日期遞增', () => {
    const s = buildTrendSeries([...history].reverse())
    expect(s.thousand).toEqual([
      { time: '2026-10-01', value: 84.65 },
      { time: '2026-10-08', value: 84.77 },
    ])
    expect(s.big.map((p) => p.value)).toEqual([87.4, 87.5])
    expect(s.holders.map((p) => p.value)).toEqual([3_021_000, 3_020_649])
  })
  it('略過欄位為 null 的點，不補 0', () => {
    const s = buildTrendSeries([
      { ...history[0], thousand_lot_ratio: null },
      history[1],
    ])
    expect(s.thousand).toEqual([{ time: '2026-10-08', value: 84.77 }])
    expect(s.holders).toHaveLength(2)
  })
})
