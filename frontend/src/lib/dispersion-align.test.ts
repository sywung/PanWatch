import { describe, expect, it } from 'vitest'
import { alignDispersionToBars, type DispersionHistoryPoint } from './dispersion'

const point = (
  data_date: string,
  thousand: number | null,
  holders: number | null = 1000,
  big: number | null = null,
): DispersionHistoryPoint => ({
  data_date,
  holder_num: holders,
  avg_shares: null,
  big_holder_ratio: big,
  thousand_lot_ratio: thousand,
})

// 週快照：10-02、10-09（週五）
const history = [point('2026-09-25', 80), point('2026-10-02', 81), point('2026-10-09', 82)]
const bars = (...dates: string[]) => dates.map((date) => ({ date }))

describe('alignDispersionToBars：日 K', () => {
  it('每根 K 線取「日期 ≤ 該日」最新的一筆快照（階梯延續）', () => {
    const out = alignDispersionToBars(
      bars('2026-09-28', '2026-09-30', '2026-10-01', '2026-10-05', '2026-10-08'),
      history,
      'thousand_lot_ratio',
    )
    expect(out).toEqual([80, 80, 80, 81, 81])
  })

  it('快照日當天就採用該週（含等於）', () => {
    const out = alignDispersionToBars(bars('2026-10-01', '2026-10-02', '2026-10-09'), history, 'thousand_lot_ratio')
    expect(out).toEqual([80, 81, 82])
  })

  it('最新快照之後的 K 線沿用最後一筆', () => {
    const out = alignDispersionToBars(bars('2026-10-12', '2026-10-15'), history, 'thousand_lot_ratio')
    expect(out).toEqual([82, 82])
  })

  it('第一筆快照之前的 K 線沒有值（null），不外推', () => {
    const out = alignDispersionToBars(bars('2026-09-01', '2026-09-24', '2026-09-25'), history, 'thousand_lot_ratio')
    expect(out).toEqual([null, null, 80])
  })
})

describe('alignDispersionToBars：週 K／月 K（K 線日期＝該期最後一個交易日）', () => {
  it('週 K 取該週五（含）以前最新快照', () => {
    const out = alignDispersionToBars(bars('2026-09-25', '2026-10-02', '2026-10-09'), history, 'thousand_lot_ratio')
    expect(out).toEqual([80, 81, 82])
  })

  it('週五休市時週 K 落在週四，仍取前一週快照而不是還沒到的那一筆', () => {
    // 快照 10-09（週五）；若該週最後交易日是 10-08（週四），當時還沒有 10-09 的資料
    const out = alignDispersionToBars(bars('2026-10-08'), history, 'thousand_lot_ratio')
    expect(out).toEqual([81])
  })

  it('月 K（月底日期）取該月底以前最新快照', () => {
    const out = alignDispersionToBars(bars('2026-08-31', '2026-09-30', '2026-10-30'), history, 'thousand_lot_ratio')
    expect(out).toEqual([null, 80, 82])
  })
})

describe('alignDispersionToBars：分 K（日期含時間）', () => {
  it('以日期部分對齊，同一天內每根分 K 值相同', () => {
    const out = alignDispersionToBars(
      bars('2026-10-01 09:05', '2026-10-01 13:25', '2026-10-02 09:05', '2026-10-09 13:30'),
      history,
      'thousand_lot_ratio',
    )
    expect(out).toEqual([80, 80, 81, 82])
  })

  it('分 K 與日 K 對同一天給同一個值', () => {
    const intraday = alignDispersionToBars(bars('2026-10-05 10:00'), history, 'thousand_lot_ratio')
    const daily = alignDispersionToBars(bars('2026-10-05'), history, 'thousand_lot_ratio')
    expect(intraday).toEqual(daily)
  })
})

describe('alignDispersionToBars：欄位與資料品質', () => {
  it('可選擇欄位：股東人數、大戶比例', () => {
    const rows = [point('2026-10-02', 81, 3000, 90.1), point('2026-10-09', 82, 2900, 90.5)]
    expect(alignDispersionToBars(bars('2026-10-05', '2026-10-12'), rows, 'holder_num')).toEqual([3000, 2900])
    expect(alignDispersionToBars(bars('2026-10-05', '2026-10-12'), rows, 'big_holder_ratio')).toEqual([90.1, 90.5])
  })

  it('該欄位為 null 的快照視為沒有，沿用前一筆有效值', () => {
    const rows = [point('2026-10-02', 81), point('2026-10-09', null)]
    expect(alignDispersionToBars(bars('2026-10-12'), rows, 'thousand_lot_ratio')).toEqual([81])
  })

  it('欄位為 0 是有效值，不會被當成缺值', () => {
    const rows = [point('2026-10-02', 81), point('2026-10-09', 0)]
    expect(alignDispersionToBars(bars('2026-10-12'), rows, 'thousand_lot_ratio')).toEqual([0])
  })

  it('history 沒排序也能正確對齊，且不改動輸入', () => {
    const shuffled = [history[2], history[0], history[1]]
    const snapshot = JSON.parse(JSON.stringify(shuffled))
    const barList = bars('2026-10-05')
    const out = alignDispersionToBars(barList, shuffled, 'thousand_lot_ratio')
    expect(out).toEqual([81])
    expect(shuffled).toEqual(snapshot)
    expect(barList).toEqual([{ date: '2026-10-05' }])
  })

  it('回傳長度永遠等於 K 線根數；空 history 全為 null；空 K 線回空陣列', () => {
    expect(alignDispersionToBars(bars('2026-10-05', '2026-10-06'), [], 'thousand_lot_ratio')).toEqual([null, null])
    expect(alignDispersionToBars([], history, 'thousand_lot_ratio')).toEqual([])
  })

  it('無法解析的 K 線日期回 null，不影響其他根', () => {
    const out = alignDispersionToBars(bars('2026-10-05', '', 'bad', '2026-10-09'), history, 'thousand_lot_ratio')
    expect(out).toEqual([81, null, null, 82])
  })
})
