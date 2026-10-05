import { describe, expect, it } from 'vitest'
import { createKlineTrendlinePrimitive } from '@panwatch/biz-ui/components/kline-trendline-primitive'
import type { KlineDrawing } from '@panwatch/biz-ui/components/kline-drawings'

const DATES = ['2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06', '2026-10-07']

function render(drawings: KlineDrawing[], pixelRatio = 1) {
  const calls: Array<[string, number, number]> = []
  const context = {
    save() {}, restore() {}, beginPath() {}, stroke() {}, fill() {}, arc() {}, setLineDash() {},
    moveTo: (x: number, y: number) => calls.push(['moveTo', x, y]),
    lineTo: (x: number, y: number) => calls.push(['lineTo', x, y]),
  } as any
  const chart = { timeScale: () => ({ logicalToCoordinate: (logical: number) => 100 + logical * 50 }) }
  const series = { priceToCoordinate: (price: number) => 400 - price }
  const primitive = createKlineTrendlinePrimitive(series, chart, () => DATES, { line: '#000', selected: '#111' })
  primitive.updateData(drawings, null, null)
  const target = {
    useBitmapCoordinateSpace: (fn: (scope: any) => void) => fn({
      context, bitmapSize: { width: 1000 * pixelRatio, height: 400 * pixelRatio },
      horizontalPixelRatio: pixelRatio, verticalPixelRatio: pixelRatio,
    }),
  }
  primitive.paneViews()[0].renderer().draw(target)
  return calls
}

const trend = (p1: string, price1: number, p2: string, price2: number): KlineDrawing => ({
  id: 1, symbol: '2330', market: 'TW', kind: 'trend',
  data: { p1: { time: p1, price: price1 }, p2: { time: p2, price: price2 } },
})

describe('趨勢線 primitive 繪製', () => {
  it('draws the trend line across the whole pane instead of between its two points', () => {
    // p1 at logical 1 -> x 150, y 300; p2 at logical 3 -> x 250, y 250; slope -0.5
    const calls = render([trend('2026-10-02', 100, '2026-10-06', 150)])
    expect(calls).toEqual([['moveTo', 0, 375], ['lineTo', 1000, -125]])
  })

  it('scales the extension to the bitmap size on high-DPI screens', () => {
    const calls = render([trend('2026-10-02', 100, '2026-10-06', 150)], 2)
    expect(calls).toEqual([['moveTo', 0, 750], ['lineTo', 2000, -250]])
  })
})
