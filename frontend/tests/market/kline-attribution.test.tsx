import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAPI } from '@panwatch/api'
import InteractiveKline from '@panwatch/biz-ui/components/InteractiveKline'
import KlineModal from '@panwatch/biz-ui/components/KlineModal'
import KlineAttribution, { KLINE_ATTRIBUTION_URL } from '@panwatch/biz-ui/components/kline-attribution'
import { changeLocale } from '@/i18n'

vi.mock('@panwatch/api', () => ({ fetchAPI: vi.fn() }))

// 任何屬性都回傳可呼叫的自己，讓圖表程式碼能跑完；只記錄 createChart 收到的設定
function fakeLightweightCharts() {
  const chartOptions: any[] = []
  const noop: any = new Proxy(function () {}, {
    get: (_t, key) => (key === Symbol.toPrimitive ? () => 0 : key === 'then' ? undefined : noop),
    apply: () => noop,
  })
  const LW = new Proxy({}, {
    get: (_t, key) => {
      if (key === 'createChart') {
        return (_el: unknown, options: any) => {
          chartOptions.push(options)
          return noop
        }
      }
      return noop
    },
  })
  return { LW, chartOptions }
}

const KLINES = Array.from({ length: 60 }, (_, i) => {
  const d = new Date(Date.UTC(2026, 0, 1 + i))
  const close = 100 + Math.sin(i / 5) * 10
  return {
    date: d.toISOString().slice(0, 10),
    open: close - 1, high: close + 2, low: close - 2, close, volume: 1000 + i,
  }
})

describe('lightweight-charts attribution', () => {
  beforeEach(() => {
    vi.mocked(fetchAPI).mockReset()
    vi.mocked(fetchAPI).mockImplementation(async (path: string) => path.startsWith('/chart-drawings?')
      ? [] as never
      : { symbol: '2330', market: 'TW', days: 120, klines: KLINES } as never)
  })
  afterEach(() => {
    delete (window as any).LightweightCharts
    vi.unstubAllGlobals()
  })

  it('turns off the in-chart TradingView logo on the main chart and every indicator pane', async () => {
    const { LW, chartOptions } = fakeLightweightCharts()
    ;(window as any).LightweightCharts = LW
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
    render(<InteractiveKline symbol="2330" market="TW" />)
    await waitFor(() => expect(chartOptions.length).toBeGreaterThanOrEqual(2))
    for (const options of chartOptions) {
      expect(options.layout.attributionLogo).toBe(false)
    }
  })

  it('links the attribution text to TradingView', async () => {
    await changeLocale('zh-TW')
    render(<KlineAttribution />)
    const link = screen.getByRole('link', { name: '圖表：TradingView Lightweight Charts™' })
    expect(link.getAttribute('href')).toBe(KLINE_ATTRIBUTION_URL)
    expect(link.getAttribute('target')).toBe('_blank')
  })

  it('shows the attribution at the bottom of the kline modal', async () => {
    await changeLocale('zh-TW')
    render(<KlineModal open onOpenChange={() => {}} symbol="2330" market="TW" />)
    const link = await screen.findByRole('link', { name: /TradingView Lightweight Charts/ })
    const dialog = screen.getByRole('dialog')
    const blocks = Array.from(dialog.children).filter(el => el.tagName !== 'BUTTON')
    expect(blocks[blocks.length - 1].contains(link)).toBe(true)
  })
})
