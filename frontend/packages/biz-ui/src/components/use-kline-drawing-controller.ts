import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'
import {
  anchorToLogical,
  drawingReducer,
  hitTestDrawings,
  initialDrawingToolState,
  logicalToAnchorTime,
  type DrawingEvent,
  type DrawingToolState,
} from './kline-drawings'
import { createKlineTrendlinePrimitive, type TrendPreview } from './kline-trendline-primitive'
import { useKlineDrawings } from './use-kline-drawings'

export function useKlineDrawingController(symbol: string, market: string) {
  const drawingApi = useKlineDrawings(symbol, market)
  const [toolState, setToolState] = useState<DrawingToolState>(initialDrawingToolState)
  const [capabilities, setCapabilities] = useState({ hline: false, trend: false })
  const [chartVersion, setChartVersion] = useState(0)
  const chartFocusRef = useRef<HTMLDivElement | null>(null)
  const chartPointerRef = useRef(false)
  const toolStateRef = useRef<DrawingToolState>(initialDrawingToolState)
  const drawingsRef = useRef(drawingApi.drawings)
  const previewRef = useRef<TrendPreview>(null)
  const primitiveRef = useRef<any>(null)
  const candleSeriesRef = useRef<any>(null)
  const priceLinesRef = useRef<Map<number, any>>(new Map())
  drawingsRef.current = drawingApi.drawings
  toolStateRef.current = toolState

  const updatePreview = useCallback((preview: TrendPreview) => {
    previewRef.current = preview
    primitiveRef.current?.updateData(
      drawingsRef.current,
      preview,
      toolStateRef.current.selectedId,
    )
  }, [])

  const dispatch = useCallback((event: DrawingEvent) => {
    const transition = drawingReducer(toolStateRef.current, event)
    toolStateRef.current = transition.state
    setToolState(transition.state)
    if (event.type === 'escape' || (event.type === 'chartClick' && transition.state.tool !== 'placingTrend')) {
      updatePreview(null)
    }
    if (transition.action?.type === 'add') void drawingApi.addDrawing(transition.action.drawing)
    if (transition.action?.type === 'delete') void drawingApi.deleteDrawing(transition.action.id)
  }, [drawingApi.addDrawing, drawingApi.deleteDrawing, updatePreview])

  const bindChart = useCallback((chart: any, candleSeries: any, getDates: () => string[]) => {
    candleSeriesRef.current = candleSeries
    const hline = typeof candleSeries.createPriceLine === 'function'
    const trend = typeof candleSeries.attachPrimitive === 'function'
    setCapabilities(previous => previous.hline === hline && previous.trend === trend
      ? previous
      : { hline, trend })
    if (trend) {
      const primitive = createKlineTrendlinePrimitive(
        candleSeries,
        chart,
        getDates,
        { line: '#38bdf8', selected: '#7dd3fc' },
      )
      candleSeries.attachPrimitive(primitive)
      primitiveRef.current = primitive
    }
    setChartVersion(version => version + 1)

    const onCrosshairMove = (param: any) => {
      const state = toolStateRef.current
      const point = param?.point
      if (state.tool === 'placingTrend' && state.firstPoint && point) {
        const logical = chart.timeScale().coordinateToLogical?.(point.x)
        const price = candleSeries.coordinateToPrice?.(point.y)
        if (Number.isFinite(logical) && Number.isFinite(price) && Number(price) > 0) {
          updatePreview({ p1: state.firstPoint, p2: { logical: Number(logical), price: Number(price) } })
        } else {
          updatePreview(null)
        }
      } else {
        updatePreview(null)
      }
    }

    const onClick = (param: any) => {
      const point = param?.point
      if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) return
      const dates = getDates()
      const state = toolStateRef.current
      if (state.tool !== 'idle') {
        const logical = chart.timeScale().coordinateToLogical?.(point.x)
        const price = candleSeries.coordinateToPrice?.(point.y)
        if (!Number.isFinite(logical) || !Number.isFinite(price) || Number(price) <= 0) return
        const time = logicalToAnchorTime(Number(logical), dates)
        if (time) dispatch({ type: 'chartClick', point: { time, price: Number(price) } })
        return
      }

      const selectedId = hitTestDrawings(point, drawingsRef.current, drawing => {
        if (drawing.kind === 'hline') {
          const y = candleSeries.priceToCoordinate?.(drawing.data.price)
          return Number.isFinite(y) ? { kind: 'hline', y: Number(y) } : null
        }
        const logical1 = anchorToLogical(drawing.data.p1.time, dates)
        const logical2 = anchorToLogical(drawing.data.p2.time, dates)
        if (logical1 == null || logical2 == null) return null
        const x1 = chart.timeScale().logicalToCoordinate?.(logical1)
        const x2 = chart.timeScale().logicalToCoordinate?.(logical2)
        const y1 = candleSeries.priceToCoordinate?.(drawing.data.p1.price)
        const y2 = candleSeries.priceToCoordinate?.(drawing.data.p2.price)
        if (![x1, x2, y1, y2].every(Number.isFinite)) return null
        return { kind: 'trend', x1: Number(x1), y1: Number(y1), x2: Number(x2), y2: Number(y2) }
      })
      dispatch({ type: 'select', id: selectedId })
    }

    const cleanup = () => {
      for (const [id, line] of priceLinesRef.current) {
        try { candleSeries.removePriceLine?.(line) } catch { /* chart may already be detached */ }
        priceLinesRef.current.delete(id)
      }
      if (primitiveRef.current) {
        try { candleSeries.detachPrimitive?.(primitiveRef.current) } catch { /* chart may already be detached */ }
        primitiveRef.current = null
      }
      if (candleSeriesRef.current === candleSeries) candleSeriesRef.current = null
    }
    return { onCrosshairMove, onClick, cleanup }
  }, [dispatch, updatePreview])

  useEffect(() => {
    primitiveRef.current?.updateData(
      drawingApi.drawings,
      previewRef.current,
      toolState.selectedId,
    )
  }, [drawingApi.drawings, toolState.selectedId, chartVersion])

  useEffect(() => {
    const candleSeries = candleSeriesRef.current
    if (!capabilities.hline || !candleSeries) return
    const lines = priceLinesRef.current
    const activeIds = new Set<number>()
    for (const drawing of drawingApi.drawings) {
      if (drawing.kind !== 'hline') continue
      activeIds.add(drawing.id)
      let line = lines.get(drawing.id)
      if (!line) {
        line = candleSeries.createPriceLine({
          price: drawing.data.price,
          color: '#fbbf24',
          lineWidth: drawing.id === toolState.selectedId ? 3 : 1,
          lineStyle: (window as any).LightweightCharts?.LineStyle?.Solid ?? 0,
          axisLabelVisible: true,
          title: '',
        })
        lines.set(drawing.id, line)
      } else {
        line.applyOptions?.({ lineWidth: drawing.id === toolState.selectedId ? 3 : 1 })
      }
    }
    for (const [id, line] of lines) {
      if (activeIds.has(id)) continue
      try { candleSeries.removePriceLine?.(line) } catch { /* chart may already be detached */ }
      lines.delete(id)
    }
  }, [capabilities.hline, drawingApi.drawings, toolState.selectedId, chartVersion])

  useEffect(() => {
    const transition = drawingReducer(toolStateRef.current, { type: 'escape' })
    toolStateRef.current = transition.state
    setToolState(transition.state)
    updatePreview(null)
  }, [symbol, market, updatePreview])

  const onKeyDown = useCallback((event: KeyboardEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement
    const hasChartContext = chartPointerRef.current || document.activeElement === chartFocusRef.current
    if (event.key === 'Escape' && toolStateRef.current.tool !== 'idle') {
      event.preventDefault()
      dispatch({ type: 'escape' })
    } else if (
      (event.key === 'Delete' || event.key === 'Backspace') && hasChartContext &&
      !target.closest('input, textarea, select, [contenteditable="true"]') &&
      toolStateRef.current.selectedId != null
    ) {
      event.preventDefault()
      dispatch({ type: 'deleteSelected' })
    }
  }, [dispatch])

  const onChartMouseDown = useCallback((event: MouseEvent<HTMLDivElement>, container: HTMLDivElement | null) => {
    if (container?.contains(event.target as Node)) chartFocusRef.current?.focus({ preventScroll: true })
  }, [])

  return {
    ...drawingApi,
    toolState,
    capabilities,
    chartFocusRef,
    bindChart,
    dispatch,
    onKeyDown,
    onChartMouseDown,
    onChartMouseEnter: () => { chartPointerRef.current = true },
    onChartMouseLeave: () => { chartPointerRef.current = false },
  }
}
