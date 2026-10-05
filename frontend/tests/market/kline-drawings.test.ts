import { describe, expect, it } from 'vitest'
import {
  anchorToLogical,
  distanceToSegment,
  drawingReducer,
  distanceToLine,
  extendLineAcross,
  hitTestDrawings,
  initialDrawingToolState,
  logicalToAnchorTime,
  panePointFromClick,
  type KlineDrawing,
} from '@panwatch/biz-ui/components/kline-drawings'

const DAYS = ['2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06']

describe('K 線畫線座標對位', () => {
  it('same-period anchors select the last candle at or before the saved time', () => {
    expect(anchorToLogical('2026-10-05', DAYS)).toBe(2)
    expect(anchorToLogical('2026-10-04', DAYS)).toBe(1)
  })

  it('maps daily anchors into the weekly candle covering that ISO week', () => {
    expect(anchorToLogical('2026-10-07', ['2026-10-02', '2026-10-09', '2026-10-16'])).toBe(1)
  })

  it('maps daily anchors into the monthly candle covering that month', () => {
    expect(anchorToLogical('2026-10-12', ['2026-09-30', '2026-10-30', '2026-11-30'])).toBe(1)
  })

  it('maps a date-only anchor to that day’s first intraday candle', () => {
    expect(anchorToLogical('2026-10-05', [
      '2026-10-02 13:25', '2026-10-05 09:00', '2026-10-05 09:05', '2026-10-05 09:10',
    ])).toBe(1)
  })

  it('linearly extrapolates before and after available dates', () => {
    expect(anchorToLogical('2026-09-30', ['2026-10-01', '2026-10-03', '2026-10-05'])).toBe(-0.5)
    expect(anchorToLogical('2026-10-07', ['2026-10-01', '2026-10-03', '2026-10-05'])).toBe(3)
  })

  it('returns null with fewer than two dates or invalid inputs', () => {
    expect(anchorToLogical('2026-10-01', [])).toBeNull()
    expect(anchorToLogical('2026-10-01', ['2026-10-01'])).toBeNull()
    expect(anchorToLogical('2026-02-30', DAYS)).toBeNull()
  })

  it('snaps to rounded real candles and clamps both ends', () => {
    expect(logicalToAnchorTime(1.6, DAYS)).toBe(DAYS[2])
    expect(logicalToAnchorTime(-8, DAYS)).toBe(DAYS[0])
    expect(logicalToAnchorTime(90, DAYS)).toBe(DAYS[DAYS.length - 1])
  })
})

describe('K 線畫線命中測試', () => {
  const drawings: KlineDrawing[] = [
    { id: 1, symbol: '2330', market: 'TW', kind: 'hline', data: { price: 100 } },
    {
      id: 2, symbol: '2330', market: 'TW', kind: 'trend',
      data: { p1: { time: '2026-10-01', price: 80 }, p2: { time: '2026-10-05', price: 120 } },
    },
  ]

  it('hits horizontal lines and returns the closest matching id', () => {
    expect(hitTestDrawings({ x: 20, y: 103 }, drawings, drawing =>
      drawing.kind === 'hline' ? { kind: 'hline', y: 100 } : { kind: 'trend', x1: 0, y1: 0, x2: 10, y2: 10 },
    )).toBe(1)
  })

  it('hits a trend line anywhere along its extension in both directions', () => {
    const onlyTrend = drawings.slice(1)
    const project = () => ({ kind: 'trend' as const, x1: 10, y1: 20, x2: 30, y2: 40 })
    expect(hitTestDrawings({ x: 20, y: 30 }, onlyTrend, project)).toBe(2)
    expect(hitTestDrawings({ x: 300, y: 310 }, onlyTrend, project)).toBe(2)
    expect(hitTestDrawings({ x: -200, y: -190 }, onlyTrend, project)).toBe(2)
    expect(hitTestDrawings({ x: 300, y: 320 }, onlyTrend, project)).toBeNull()
  })

  it('ignores clicks more than six pixels away from a horizontal line', () => {
    const onlyHline = drawings.slice(0, 1)
    const project = () => ({ kind: 'hline' as const, y: 100 })
    expect(hitTestDrawings({ x: 20, y: 106 }, onlyHline, project)).toBe(1)
    expect(hitTestDrawings({ x: 20, y: 107 }, onlyHline, project)).toBeNull()
  })

  it('hits a near-vertical trend line clicked slightly to its side', () => {
    const onlyTrend = drawings.slice(1)
    const project = () => ({ kind: 'trend' as const, x1: 50, y1: 10, x2: 51, y2: 200 })
    expect(hitTestDrawings({ x: 53, y: 100 }, onlyTrend, project)).toBe(2)
    expect(hitTestDrawings({ x: 60, y: 100 }, onlyTrend, project)).toBeNull()
  })

  it('calculates point-to-segment distance, including a degenerate segment', () => {
    expect(distanceToSegment(5, 2, 0, 0, 10, 0)).toBe(2)
    expect(distanceToSegment(4, 3, 1, 1, 1, 1)).toBeCloseTo(3.605551275463989, 12)
  })
})

describe('畫線工具狀態轉換', () => {
  const first = { time: '2026-10-01', price: 100 }
  const second = { time: '2026-10-05', price: 110 }

  it('selects a tool and pressing it again cancels placement', () => {
    const active = drawingReducer(initialDrawingToolState, { type: 'selectTool', tool: 'hline' }).state
    expect(active.tool).toBe('placingHline')
    expect(drawingReducer(active, { type: 'selectTool', tool: 'hline' }).state).toEqual(initialDrawingToolState)
  })

  it('creates a horizontal line on one click', () => {
    const placing = { tool: 'placingHline' as const, selectedId: null }
    expect(drawingReducer(placing, { type: 'chartClick', point: first })).toEqual({
      state: initialDrawingToolState,
      action: { type: 'add', drawing: { kind: 'hline', data: { price: 100 } } },
    })
  })

  it('creates a trend only after two clicks and escape clears its first point', () => {
    const placing = { tool: 'placingTrend' as const, selectedId: null }
    const afterFirst = drawingReducer(placing, { type: 'chartClick', point: first }).state
    expect(afterFirst.firstPoint).toEqual(first)
    expect(drawingReducer(afterFirst, { type: 'chartClick', point: second })).toEqual({
      state: initialDrawingToolState,
      action: { type: 'add', drawing: { kind: 'trend', data: { p1: first, p2: second } } },
    })
    expect(drawingReducer(afterFirst, { type: 'escape' }).state).toEqual(initialDrawingToolState)
  })

  it('ignores a second trend click on the same candle instead of creating a vertical line', () => {
    const placing = { tool: 'placingTrend' as const, selectedId: null }
    const afterFirst = drawingReducer(placing, { type: 'chartClick', point: first }).state
    const sameCandle = drawingReducer(afterFirst, { type: 'chartClick', point: { ...first, price: first.price + 50 } })
    expect(sameCandle.action).toBeUndefined()
    expect(sameCandle.state).toEqual(afterFirst)
  })

  it('selects, deletes the selected drawing, and clears selection on a blank chart click', () => {
    const selected = drawingReducer(initialDrawingToolState, { type: 'select', id: 7 }).state
    expect(selected.selectedId).toBe(7)
    expect(drawingReducer(selected, { type: 'deleteSelected' })).toEqual({
      state: { tool: 'idle', selectedId: null },
      action: { type: 'delete', id: 7 },
    })
    expect(drawingReducer(selected, { type: 'chartClick', point: first }).state.selectedId).toBeNull()
  })
})

describe('panePointFromClick', () => {
  const rect = { left: 100, top: 50 }
  it('converts client coordinates into pane coordinates', () => {
    expect(panePointFromClick(130, 90, rect, 900, 350)).toEqual({ x: 30, y: 40 })
  })
  it('rejects clicks on the price axis, the time axis and outside the chart', () => {
    expect(panePointFromClick(1000, 90, rect, 900, 350)).toBeNull()
    expect(panePointFromClick(130, 400, rect, 900, 350)).toBeNull()
    expect(panePointFromClick(90, 90, rect, 900, 350)).toBeNull()
    expect(panePointFromClick(130, 90, rect, 0, 350)).toBeNull()
  })
})

describe('趨勢線延伸', () => {
  it('extends the line through both points to the left and right pane edges', () => {
    expect(extendLineAcross(100, 50, 200, 100, 1000)).toEqual({ x1: 0, y1: 0, x2: 1000, y2: 500 })
    expect(extendLineAcross(300, 80, 100, 80, 600)).toEqual({ x1: 0, y1: 80, x2: 600, y2: 80 })
  })
  it('returns null for a vertical line', () => {
    expect(extendLineAcross(50, 10, 50, 90, 600)).toBeNull()
  })
  it('measures perpendicular distance to the infinite line', () => {
    expect(distanceToLine(500, 0, 0, 0, 10, 0)).toBe(0)
    expect(distanceToLine(-500, 3, 0, 0, 10, 0)).toBe(3)
    expect(distanceToLine(3, 4, 0, 0, 0, 0)).toBe(5)
  })
})
