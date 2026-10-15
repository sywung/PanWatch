import { describe, expect, it } from 'vitest'
import { visibleHighLow } from '@panwatch/biz-ui/components/interactive-kline-utils'

// 每根：high / low 刻意與 close 無關，確保取的是最高價與最低價
const bars = [
  { high: 10, low: 5 },   // 0
  { high: 12, low: 6 },   // 1
  { high: 30, low: 8 },   // 2
  { high: 11, low: 2 },   // 3
  { high: 15, low: 7 },   // 4
  { high: 9, low: 4 },    // 5
]

describe('visibleHighLow：區間高低只算畫面上看得到的 K 線', () => {
  it('沒有可見範圍時算全部', () => {
    expect(visibleHighLow(bars, null)).toEqual({ high: 30, low: 2 })
  })

  it('整數邏輯範圍取其中（含頭尾）的 K 線', () => {
    expect(visibleHighLow(bars, { from: 0, to: 1 })).toEqual({ high: 12, low: 5 })
    expect(visibleHighLow(bars, { from: 4, to: 5 })).toEqual({ high: 15, low: 4 })
    expect(visibleHighLow(bars, { from: 2, to: 2 })).toEqual({ high: 30, low: 8 })
  })

  it('邊緣露出一半以上的 K 線算可見：index 落在 [from-0.5, to+0.5]', () => {
    // from 1.6 → 第 1 根只露不到一半（中心在 1 < 1.1）不算；to 3.4 → 第 4 根中心 4 > 3.9 不算
    expect(visibleHighLow(bars, { from: 1.6, to: 3.4 })).toEqual({ high: 30, low: 2 })
    expect(visibleHighLow(bars, { from: 2.6, to: 3.4 })).toEqual({ high: 11, low: 2 })    // 只剩第 3 根
    // from 1.4 → 第 1 根（1 ≥ 0.9）算；to 3.6 → 第 4 根（4 ≤ 4.1）算
    expect(visibleHighLow(bars, { from: 1.4, to: 3.6 })).toEqual({ high: 30, low: 2 })
    expect(visibleHighLow(bars, { from: 3.6, to: 4.4 })).toEqual({ high: 15, low: 7 })    // 只剩第 4 根
  })

  it('範圍超出資料時夾在資料內（圖左右留白）', () => {
    expect(visibleHighLow(bars, { from: -10, to: 1 })).toEqual({ high: 12, low: 5 })
    expect(visibleHighLow(bars, { from: 4, to: 99 })).toEqual({ high: 15, low: 4 })
    expect(visibleHighLow(bars, { from: -10, to: 99 })).toEqual({ high: 30, low: 2 })
  })

  it('完全落在資料外、範圍不合法、K 線為空時回 null（呼叫端退回全部）', () => {
    expect(visibleHighLow(bars, { from: 50, to: 60 })).toBeNull()
    expect(visibleHighLow(bars, { from: -20, to: -10 })).toBeNull()
    expect(visibleHighLow(bars, { from: Number.NaN, to: 3 })).toBeNull()
    expect(visibleHighLow(bars, { from: 1, to: Number.POSITIVE_INFINITY })).toBeNull()
    expect(visibleHighLow(bars, { from: 4, to: 1 })).toBeNull()
    expect(visibleHighLow([], { from: 0, to: 1 })).toBeNull()
    expect(visibleHighLow([], null)).toBeNull()
  })

  it('不改動輸入', () => {
    const copy = JSON.parse(JSON.stringify(bars))
    visibleHighLow(bars, { from: 1, to: 3 })
    expect(bars).toEqual(copy)
  })
})
