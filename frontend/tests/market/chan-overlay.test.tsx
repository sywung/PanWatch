import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAPI } from '@panwatch/api'
import { applySeriesMarkers, buildChanOverlay, chanPointLabel } from '@panwatch/biz-ui/chan-overlay'
import InteractiveKline from '@panwatch/biz-ui/components/InteractiveKline'
import { KlineSummaryDialog } from '@panwatch/biz-ui/components/kline-summary-dialog'
import { changeLocale } from '@/i18n'

vi.mock('@panwatch/api', () => ({ fetchAPI: vi.fn() }))

const BI = [
  { begin_time: '2026-01-02', begin_val: 10, end_time: '2026-01-10', end_val: 20, dir: 'up', sure: true },
  { begin_time: '2026-01-10', begin_val: 20, end_time: '2026-01-20', end_val: 15, dir: 'down', sure: true },
  { begin_time: '2026-01-20', begin_val: 15, end_time: '2026-01-28', end_val: 25, dir: 'up', sure: false },
]
const LEVEL = {
  level: 'day',
  bi: BI,
  seg: [{ begin_time: '2026-01-02', begin_val: 10, end_time: '2026-01-28', end_val: 25, dir: 'up', sure: false }],
  zs: [{ begin_time: '2026-01-10', end_time: '2026-01-20', zd: 15, zg: 20, sure: true }],
  bsp: [
    { time: '2026-01-20', is_buy: true, type: '2', sure: true, price: 15 },
    { time: '2026-01-10', is_buy: false, type: '1', sure: false, price: 20 },
  ],
  last_close: 24,
  position: 'above',
}
const day = (s: string) => {
  const [y, m, d] = s.split('-').map(Number)
  return { year: y, month: m, day: d }
}
const colors = { buy: '#e11d48', sell: '#059669', bi: '#6366f1', seg: '#f59e0b', zs: '#0ea5e9' }

describe('buildChanOverlay', () => {
  it('chains confirmed strokes and keeps the trailing unconfirmed stroke separate', () => {
    const o = buildChanOverlay(LEVEL, { colors, label: (t, b) => `${b ? 'B' : 'S'}${t}` })
    expect(o.biLine).toEqual([
      { time: day('2026-01-02'), value: 10 },
      { time: day('2026-01-10'), value: 20 },
      { time: day('2026-01-20'), value: 15 },
    ])
    expect(o.biPending).toEqual([
      { time: day('2026-01-20'), value: 15 },
      { time: day('2026-01-28'), value: 25 },
    ])
    expect(o.segLine).toEqual([])
    expect(o.segPending).toEqual([
      { time: day('2026-01-02'), value: 10 },
      { time: day('2026-01-28'), value: 25 },
    ])
  })

  it('turns each pivot into a top (ZG) and bottom (ZD) line over its time span', () => {
    const o = buildChanOverlay(LEVEL, { colors, label: (t, b) => `${b ? 'B' : 'S'}${t}` })
    expect(o.zsBoxes).toEqual([
      {
        top: [{ time: day('2026-01-10'), value: 20 }, { time: day('2026-01-20'), value: 20 }],
        bottom: [{ time: day('2026-01-10'), value: 15 }, { time: day('2026-01-20'), value: 15 }],
      },
    ])
  })

  it('builds time-sorted buy/sell markers and flags unconfirmed points', () => {
    const o = buildChanOverlay(LEVEL, { colors, label: (t, b) => `${b ? 'B' : 'S'}${t}` })
    expect(o.markers).toEqual([
      { time: day('2026-01-10'), position: 'aboveBar', shape: 'arrowDown', color: colors.sell, text: 'S1?' },
      { time: day('2026-01-20'), position: 'belowBar', shape: 'arrowUp', color: colors.buy, text: 'B2' },
    ])
  })

  it('handles empty or missing data', () => {
    const empty = buildChanOverlay(null, { colors, label: () => '' })
    expect(empty).toEqual({ biLine: [], biPending: [], segLine: [], segPending: [], zsBoxes: [], markers: [] })
  })
})

describe('applySeriesMarkers', () => {
  it('uses createSeriesMarkers on lightweight-charts v5', () => {
    const series = {}
    const create = vi.fn()
    applySeriesMarkers(series, { createSeriesMarkers: create }, [{ a: 1 }])
    expect(create).toHaveBeenCalledWith(series, [{ a: 1 }])
  })

  it('falls back to series.setMarkers on v4', () => {
    const series = { setMarkers: vi.fn() }
    applySeriesMarkers(series, {}, [{ a: 1 }])
    expect(series.setMarkers).toHaveBeenCalledWith([{ a: 1 }])
  })
})

describe('chanPointLabel', () => {
  it('localizes buy/sell point labels', async () => {
    await changeLocale('zh-TW')
    expect(chanPointLabel('2s', true)).toBe('買2s')
    expect(chanPointLabel('1', false)).toBe('賣1')
    await changeLocale('en-US')
    expect(chanPointLabel('1', true)).toBe('B1')
  })
})

describe('InteractiveKline Chan toggle', () => {
  beforeEach(() => {
    vi.mocked(fetchAPI).mockReset()
    vi.mocked(fetchAPI).mockImplementation(async (url: string) => {
      if (url.includes('/chan')) return LEVEL as never
      return { symbol: '2330', market: 'TW', days: 120, klines: [] } as never
    })
  })

  it('fetches the day-level Chan structure when toggled on', async () => {
    await changeLocale('zh-TW')
    const user = userEvent.setup()
    render(<InteractiveKline symbol="2330" market="TW" />)
    const toggle = await screen.findByRole('button', { name: '纏論' })
    expect(vi.mocked(fetchAPI).mock.calls.some(([u]) => String(u).includes('/chan'))).toBe(false)
    await user.click(toggle)
    await waitFor(() =>
      expect(vi.mocked(fetchAPI)).toHaveBeenCalledWith('/klines/2330/chan?market=TW&level=day'),
    )
  })
})

describe('KlineSummaryDialog Chan section', () => {
  it('shows pivot, latest points and interval nesting', async () => {
    await changeLocale('zh-TW')
    render(
      <KlineSummaryDialog
        open
        onOpenChange={() => {}}
        symbol="2330"
        market="TW"
        initialSummary={{
          last_close: 24,
          chan: {
            day: LEVEL,
            m30: { ...LEVEL, level: '30m', zs: [{ begin_time: '2026-01-27 09:00', end_time: '2026-01-28 13:00', zd: 22, zg: 23, sure: true }] },
            nesting: { confirmed: true, direction: 'buy' },
          },
        } as never}
      />,
    )
    expect(await screen.findByText('纏論')).toBeTruthy()
    const text = document.body.textContent || ''
    expect(text).toContain('中樞')
    expect(text).toContain('15')
    expect(text).toContain('20')
    expect(text).toContain('區間套')
    expect(text).toContain('30 分鐘')
  })

  it('omits the Chan section when there is no Chan data', async () => {
    await changeLocale('zh-TW')
    render(
      <KlineSummaryDialog open onOpenChange={() => {}} symbol="2330" market="TW" initialSummary={{ last_close: 24 } as never} />,
    )
    await screen.findAllByRole('dialog')
    expect(screen.queryByText('纏論')).toBeNull()
  })
})

describe('buildChanOverlay range clipping (2855 regression)', () => {
  // 后端用 250 根日 K 算缠论,图只画 120 天;超出范围的点会把主图时间轴往前拉,
  // 同步到 MACD/RSI 副图时 lightweight-charts 抛 "Value is null",整组图坏掉。
  const range = { from: '2026-01-10', to: '2026-01-25' }

  it('clips line points to the chart range and interpolates the boundary', () => {
    const o = buildChanOverlay(LEVEL, { colors, label: (t, b) => `${b ? 'B' : 'S'}${t}`, range })
    const all = [...o.biLine, ...o.biPending, ...o.segLine, ...o.segPending, ...o.zsBoxes.flatMap(b => [...b.top, ...b.bottom])]
    const key = (t: { year: number; month: number; day: number }) => `${t.year}-${String(t.month).padStart(2, '0')}-${String(t.day).padStart(2, '0')}`
    expect(all.every(p => key(p.time) >= range.from && key(p.time) <= range.to)).toBe(true)
    expect(o.biLine[0]).toEqual({ time: day('2026-01-10'), value: 20 })
    // 未确定笔 01-20(15) → 01-28(25),在 01-25 截断:15 + (25-15) * 5/8
    expect(o.biPending[o.biPending.length - 1].time).toEqual(day('2026-01-25'))
    expect(o.biPending[o.biPending.length - 1].value).toBeCloseTo(15 + 10 * 5 / 8, 6)
  })

  it('drops markers and pivots entirely outside the range', () => {
    const o = buildChanOverlay(
      { ...LEVEL, zs: [{ begin_time: '2025-12-01', end_time: '2025-12-20', zd: 1, zg: 2, sure: true }] },
      { colors, label: (t, b) => `${b ? 'B' : 'S'}${t}`, range: { from: '2026-01-15', to: '2026-01-31' } },
    )
    expect(o.zsBoxes).toEqual([])
    expect(o.markers.map(m => m.text)).toEqual(['B2'])
  })
})
