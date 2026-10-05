import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchAPI } from '@panwatch/api'
import InteractiveKline from '@panwatch/biz-ui/components/InteractiveKline'

vi.mock('@panwatch/api', () => ({ fetchAPI: vi.fn() }))

const KLINES = Array.from({ length: 60 }, (_, index) => {
  const date = new Date(Date.UTC(2026, 0, 1 + index)).toISOString().slice(0, 10)
  return { date, open: 99, high: 103, low: 97, close: 100, volume: 1000 }
})

function drawingApi(initial: unknown[] = []) {
  const priceLines: any[] = []
  const clickHandlers: Array<(param: any) => void> = []
  const removePriceLine = vi.fn()
  const createPriceLine = vi.fn((options: any) => {
    const line = { options, applyOptions: vi.fn() }
    priceLines.push(line)
    return line
  })
  const candleSeries = {
    setData: vi.fn(),
    createPriceLine,
    removePriceLine,
    attachPrimitive: vi.fn(),
    detachPrimitive: vi.fn(),
    coordinateToPrice: (y: number) => 200 - y,
    priceToCoordinate: (price: number) => 200 - price,
  }
  const timeScale = {
    setVisibleLogicalRange: vi.fn(),
    subscribeVisibleTimeRangeChange: vi.fn(),
    unsubscribeVisibleTimeRangeChange: vi.fn(),
    subscribeVisibleLogicalRangeChange: vi.fn(),
    unsubscribeVisibleLogicalRangeChange: vi.fn(),
    logicalToCoordinate: (logical: number) => logical * 10,
    coordinateToLogical: (x: number) => x / 10,
  }
  const genericSeries = new Proxy(function () {}, {
    get: (_target, key) => key === 'then' ? undefined : genericSeries,
    apply: () => genericSeries,
  })
  const chart = {
    addCandlestickSeries: () => candleSeries,
    addHistogramSeries: () => genericSeries,
    addLineSeries: () => genericSeries,
    priceScale: () => genericSeries,
    timeScale: () => timeScale,
    subscribeClick: (handler: (param: any) => void) => clickHandlers.push(handler),
    unsubscribeClick: vi.fn(),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove: vi.fn(),
    applyOptions: vi.fn(),
    remove: vi.fn(),
  }
  const LW = new Proxy({}, {
    get: (_target, key) => key === 'createChart' ? () => chart : genericSeries,
  })
  return { LW, priceLines, clickHandlers, createPriceLine, removePriceLine, candleSeries, initial }
}

describe('InteractiveKline 畫線接線', () => {
  beforeEach(() => {
    vi.mocked(fetchAPI).mockReset()
    vi.mocked(fetchAPI).mockImplementation(async (path, options) => {
      if (path.startsWith('/chart-drawings?')) return [] as never
      if (path === '/chart-drawings' && options?.method === 'POST') {
        const body = JSON.parse(String(options.body))
        return { id: 2, ...body } as never
      }
      if (path.startsWith('/chart-drawings') && options?.method === 'DELETE') return { deleted: 1 } as never
      return { symbol: '2330', market: 'TW', days: 500, klines: KLINES } as never
    })
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  })

  afterEach(() => {
    delete (window as any).LightweightCharts
    vi.unstubAllGlobals()
  })

  it('places a horizontal line from a chart click and sends it to the API', async () => {
    const fake = drawingApi()
    ;(window as any).LightweightCharts = fake.LW
    render(<InteractiveKline symbol="2330" market="TW" />)

    const button = await screen.findByRole('button', { name: '水平线' })
    fireEvent.click(button)
    await waitFor(() => expect(fake.clickHandlers.length).toBeGreaterThan(0))
    act(() => fake.clickHandlers[0]({ point: { x: 20, y: 100 } }))

    await waitFor(() => expect(fetchAPI).toHaveBeenCalledWith('/chart-drawings', expect.objectContaining({ method: 'POST' })))
    await waitFor(() => expect(fake.createPriceLine).toHaveBeenCalledWith(expect.objectContaining({ price: 100, axisLabelVisible: true })))
    expect(fake.candleSeries.attachPrimitive).toHaveBeenCalledTimes(1)
  })

  it('requires a second click before clearing all saved lines', async () => {
    const initial = [{ id: 1, symbol: '2330', market: 'TW', kind: 'hline', data: { price: 100 } }]
    const fake = drawingApi(initial)
    ;(window as any).LightweightCharts = fake.LW
    vi.mocked(fetchAPI).mockImplementation(async (path, options) => {
      if (path.startsWith('/chart-drawings?')) return initial as never
      if (path.startsWith('/chart-drawings') && options?.method === 'DELETE') return { deleted: 1 } as never
      return { symbol: '2330', market: 'TW', days: 500, klines: KLINES } as never
    })
    render(<InteractiveKline symbol="2330" market="TW" />)

    const clearButton = await screen.findByRole('button', { name: '清除全部' })
    fireEvent.click(clearButton)
    expect(screen.getByRole('button', { name: '确定清除？' })).toBeTruthy()
    expect(fetchAPI).not.toHaveBeenCalledWith('/chart-drawings?symbol=2330&market=TW', expect.objectContaining({ method: 'DELETE' }))
    fireEvent.click(screen.getByRole('button', { name: '确定清除？' }))
    await waitFor(() => expect(fetchAPI).toHaveBeenCalledWith(
      '/chart-drawings?symbol=2330&market=TW',
      expect.objectContaining({ method: 'DELETE' }),
    ))
  })

  it('redraws saved horizontal lines after the chart is rebuilt for another interval', async () => {
    const initial = [{ id: 1, symbol: '2330', market: 'TW', kind: 'hline', data: { price: 100 } }]
    const fake = drawingApi(initial)
    ;(window as any).LightweightCharts = fake.LW
    vi.mocked(fetchAPI).mockImplementation(async (path) => {
      if (path.startsWith('/chart-drawings?')) return initial as never
      return { symbol: '2330', market: 'TW', days: 500, klines: KLINES } as never
    })
    render(<InteractiveKline symbol="2330" market="TW" />)
    await waitFor(() => expect(fake.createPriceLine).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('button', { name: '周K' }))
    await waitFor(() => expect(fetchAPI).toHaveBeenCalledWith(expect.stringContaining('interval=1w')))
    await waitFor(() => expect(fake.createPriceLine).toHaveBeenCalledTimes(2))
    expect(fake.createPriceLine).toHaveBeenLastCalledWith(expect.objectContaining({ price: 100 }))
  })
})
