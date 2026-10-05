import { useEffect, useMemo, useRef, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { fetchAPI } from '@panwatch/api'
import { Button } from '@panwatch/base-ui/components/ui/button'
import { useTranslation } from 'react-i18next'
import { useMarketColors } from '@/hooks/use-market-colors'
import { getMarketColorPalette, marketColorWithAlpha, marketSignTextClass } from '@/lib/market-colors'
import {
  calculateBollinger,
  calculateKd,
  calculateObv,
  calculateSma,
  calculateVwap,
  KLINE_INDICATOR_STORAGE_KEY,
  readKlineIndicatorSettings,
  type KlineIndicatorSettings,
} from '../lib/indicators'
import { applySeriesMarkers, buildChanOverlay, chanPointLabel, densifyLine, type ChanLevel } from '@panwatch/biz-ui/chan-overlay'
import {
  crosshairDateKey,
  decideKlineExpansion,
  doubledKlineRequestDays,
  isIntradayInterval,
  klineRequestUrl,
  MAX_KLINE_DAYS,
  parseKlineTime,
  shiftLogicalRange,
  type KlineInterval,
  type LogicalRange,
} from './interactive-kline-utils'
import KlineDrawingToolbar from './KlineDrawingToolbar'
import { useKlineDrawingController } from './use-kline-drawing-controller'
import { panePointFromClick } from './kline-drawings'

type KlineItem = {
  date: string
  open: number
  close: number
  high: number
  low: number
  volume: number
}

type KlinesResponse = {
  symbol: string
  market: string
  days: number
  interval?: string
  klines: KlineItem[]
}

type ChanResponse = ChanLevel & { level?: string }

type HoverTipRow = {
  date: string
  open: number
  high: number
  low: number
  close: number
  ma5: number | null
  ma10: number | null
  ma20: number | null
  ma60: number | null
  ma120: number | null
  ma240: number | null
  bollUpper: number | null
  bollMiddle: number | null
  bollLower: number | null
  vwap: number | null
  kdK: number | null
  kdD: number | null
  obv: number | null
  macd: number | null
  signal: number | null
  rsi6: number | null
}

type HoverTip = {
  visible: boolean
  x: number
  y: number
  row: HoverTipRow | null
}

function sma(values: number[], period: number): Array<number | null> {
  if (period <= 1) return values.map(v => v)
  const out: Array<number | null> = new Array(values.length).fill(null)
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= period) sum -= values[i - period]
    if (i >= period - 1) out[i] = sum / period
  }
  return out
}

function ema(values: number[], period: number): Array<number | null> {
  const out: Array<number | null> = new Array(values.length).fill(null)
  if (values.length === 0) return out
  const k = 2 / (period + 1)
  let prev: number | null = null
  for (let i = 0; i < values.length; i++) {
    const v = values[i]
    if (prev == null) {
      prev = v
      out[i] = v
      continue
    }
    prev = v * k + prev * (1 - k)
    out[i] = prev
  }
  return out
}

function computeMacd(closes: number[]) {
  const e12 = ema(closes, 12)
  const e26 = ema(closes, 26)
  const macd: Array<number | null> = closes.map((_, i) => {
    const a = e12[i]
    const b = e26[i]
    if (a == null || b == null) return null
    return a - b
  })
  const macdVals = macd.map(v => (v == null ? 0 : v))
  const signal = ema(macdVals, 9)
  const hist: Array<number | null> = macd.map((v, i) => {
    if (v == null || signal[i] == null) return null
    return v - (signal[i] as number)
  })
  return { macd, signal, hist }
}

function computeRsi(closes: number[], period = 6): Array<number | null> {
  const out: Array<number | null> = new Array(closes.length).fill(null)
  if (closes.length <= period) return out
  let gain = 0
  let loss = 0
  for (let i = 1; i <= period; i++) {
    const diff = closes[i] - closes[i - 1]
    if (diff >= 0) gain += diff
    else loss += -diff
  }
  let avgGain = gain / period
  let avgLoss = loss / period
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)
  for (let i = period + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1]
    const g = diff > 0 ? diff : 0
    const l = diff < 0 ? -diff : 0
    avgGain = (avgGain * (period - 1) + g) / period
    avgLoss = (avgLoss * (period - 1) + l) / period
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)
  }
  return out
}

function getLW() {
  return (window as any)?.LightweightCharts || null
}

function addCandles(chart: any, LW: any, options: any) {
  if (typeof chart?.addCandlestickSeries === 'function') return chart.addCandlestickSeries(options)
  if (typeof chart?.addSeries === 'function' && LW?.CandlestickSeries) return chart.addSeries(LW.CandlestickSeries, options)
  throw new Error('Candlestick series API not available')
}

function addLine(chart: any, LW: any, options: any) {
  if (typeof chart?.addLineSeries === 'function') return chart.addLineSeries(options)
  if (typeof chart?.addSeries === 'function' && LW?.LineSeries) return chart.addSeries(LW.LineSeries, options)
  throw new Error('Line series API not available')
}

function addHistogram(chart: any, LW: any, options: any) {
  if (typeof chart?.addHistogramSeries === 'function') return chart.addHistogramSeries(options)
  if (typeof chart?.addSeries === 'function' && LW?.HistogramSeries) return chart.addSeries(LW.HistogramSeries, options)
  throw new Error('Histogram series API not available')
}

export default function InteractiveKline(props: {
  symbol: string
  market: string
  initialInterval?: KlineInterval
  initialDays?: number | string
}) {
  const { t, i18n } = useTranslation('bizUi')
  const marketColors = useMarketColors()
  const palette = useMemo(() => getMarketColorPalette(marketColors.effectiveScheme), [marketColors.effectiveScheme])
  const tr = (key: string, options?: Record<string, unknown>) =>
    (t as unknown as (key: string, options?: Record<string, unknown>) => string)(`interactiveKline.${key}`, options)
  const english = (i18n.resolvedLanguage || i18n.language).toLowerCase().startsWith('en')
  const [lwReady, setLwReady] = useState(!!getLW())
  const [libError, setLibError] = useState(false)
  const [interval, setIntervalValue] = useState<KlineInterval>(props.initialInterval || '1d')
  const [loading, setLoading] = useState(false)
  const [loadingEarlier, setLoadingEarlier] = useState(false)
  const [error, setError] = useState<string>('')
  const [data, setData] = useState<KlineItem[]>([])
  const [indicators, setIndicators] = useState<KlineIndicatorSettings>(readKlineIndicatorSettings)
  const [showChan, setShowChan] = useState(false)
  const [chanByKey, setChanByKey] = useState<Record<string, ChanResponse>>({})
  const [hoverTip, setHoverTip] = useState<HoverTip>({ visible: false, x: 0, y: 0, row: null })
  const drawingController = useKlineDrawingController(props.symbol, props.market)
  const { drawings, error: drawingError, toolState: drawingToolState, capabilities: drawingCapabilities } = drawingController

  const fixedDays = useMemo(() => {
    const customDays = Number(props.initialDays)
    if (Number.isFinite(customDays) && customDays > 0) {
      return Math.min(MAX_KLINE_DAYS, Math.floor(customDays))
    }
    if (interval === '5m' || interval === '15m' || interval === '30m' || interval === '60m') return 500
    if (interval === '1m') return 1300
    if (interval === '1w') return 780
    return 500
  }, [props.initialDays, interval])

  const containerRef = useRef<HTMLDivElement | null>(null)
  const panesRef = useRef<HTMLDivElement | null>(null)
  const chanCacheRef = useRef<Record<string, ChanResponse>>({})
  const loadGenerationRef = useRef(0)
  const loadingRef = useRef(false)
  const expansionRef = useRef({ requestedDays: fixedDays, loading: false, canLoad: false, reachedEarliest: false })
  const pendingRangeRef = useRef<LogicalRange | null>(null)
  const pendingRangeShiftRef = useRef(0)

  useEffect(() => {
    try {
      window.localStorage.setItem(KLINE_INDICATOR_STORAGE_KEY, JSON.stringify(indicators))
    } catch {
      // Indicator preferences remain usable for this session when storage is unavailable.
    }
  }, [indicators])

  const setIndicator = (key: keyof KlineIndicatorSettings, value: boolean) => {
    setIndicators(previous => ({ ...previous, [key]: value }))
  }

  const chanKey = `${props.market}:${props.symbol}`
  const chanLevel = showChan && interval === '1d' ? chanByKey[chanKey] || null : null

  useEffect(() => {
    if (!showChan || interval !== '1d' || !props.symbol) return
    if (chanCacheRef.current[chanKey]) return
    let cancelled = false
    fetchAPI<ChanResponse>(`/klines/${encodeURIComponent(props.symbol)}/chan?market=${encodeURIComponent(props.market)}&level=day`)
      .then((value) => {
        if (cancelled) return
        chanCacheRef.current[chanKey] = value
        setChanByKey(previous => ({ ...previous, [chanKey]: value }))
      })
      .catch(() => undefined)
    return () => { cancelled = true }
  }, [showChan, interval, props.symbol, props.market, chanKey])

  const load = async () => {
    if (!props.symbol) return
    const requestGeneration = ++loadGenerationRef.current
    expansionRef.current = { requestedDays: fixedDays, loading: false, canLoad: false, reachedEarliest: false }
    pendingRangeRef.current = null
    pendingRangeShiftRef.current = 0
    setLoadingEarlier(false)
    loadingRef.current = true
    setLoading(true)
    setError('')
    setHoverTip(prev => (prev.visible ? { visible: false, x: 0, y: 0, row: null } : prev))
    try {
      const query = (days: number) => klineRequestUrl(props.symbol, props.market, days, interval)
      const attempts = Array.from(new Set([fixedDays, Math.max(90, Math.floor(fixedDays * 0.75))]))
      let best: KlineItem[] = []
      let lastError: unknown = null
      for (const d of attempts) {
        try {
          const res = await fetchAPI<KlinesResponse>(query(d))
          const kl = res.klines || []
          if (kl.length > best.length) best = kl
          if (d === fixedDays && kl.length > 0) break
        } catch (e) {
          lastError = e
        }
      }
      if (!best.length && lastError) throw lastError
      if (requestGeneration !== loadGenerationRef.current) return
      expansionRef.current = {
        requestedDays: fixedDays,
        loading: false,
        canLoad: !isIntradayInterval(interval) && best.length > 0 && fixedDays < MAX_KLINE_DAYS,
        reachedEarliest: false,
      }
      setData(best)
    } catch (e) {
      if (requestGeneration !== loadGenerationRef.current) return
      setError(e instanceof Error ? e.message : tr('loadFailed'))
      setData([])
    } finally {
      if (requestGeneration === loadGenerationRef.current) {
        loadingRef.current = false
        setLoading(false)
      }
    }
  }

  useEffect(() => {
    void load()
    return () => { loadGenerationRef.current += 1 }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.symbol, props.market, interval, fixedDays])

  useEffect(() => {
    if (props.initialInterval) setIntervalValue(props.initialInterval)
  }, [props.initialInterval, props.symbol, props.market])

  useEffect(() => {
    if (lwReady) return
    let cancelled = false
    const start = Date.now()
    const t = window.setInterval(() => {
      if (cancelled) return
      if (getLW()) {
        setLwReady(true)
        clearInterval(t)
        return
      }
      if (Date.now() - start > 3500) {
        setLibError(true)
        clearInterval(t)
      }
    }, 200)
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [lwReady])

  const series = useMemo(() => {
    const klines = (data || []).slice().filter(k => parseKlineTime(k.date, interval) != null)
    const candles = klines.map(k => ({
      time: parseKlineTime(k.date, interval) as any,
      open: k.open,
      high: k.high,
      low: k.low,
      close: k.close,
    }))
    const volumes = klines.map(k => ({
      time: parseKlineTime(k.date, interval) as any,
      value: k.volume,
      color: marketColorWithAlpha(k.close > k.open ? palette.up.bright : k.close < k.open ? palette.down.bright : palette.flat, 0.35),
    }))
    const closes = klines.map(k => k.close)
    const ma5 = sma(closes, 5)
    const ma10 = sma(closes, 10)
    const ma20 = sma(closes, 20)
    const volRaw = klines.map(k => k.volume)
    const volMa5 = sma(volRaw, 5)
    const volMa10 = sma(volRaw, 10)
    const macd = computeMacd(closes)
    const rsi6 = computeRsi(closes, 6)
    const ma60 = calculateSma(closes, 60)
    const ma120 = calculateSma(closes, 120)
    const ma240 = calculateSma(closes, 240)
    const boll = calculateBollinger(klines)
    const kd = calculateKd(klines)
    const obv = calculateObv(klines)
    const vwap = calculateVwap(klines)
    return { klines, candles, volumes, ma5, ma10, ma20, ma60, ma120, ma240, boll, kd, obv, vwap, volMa5, volMa10, macd, rsi6 }
  }, [data, interval, palette])

  const latestMetrics = useMemo(() => {
    if (!series.klines.length) return null
    const last = series.klines[series.klines.length - 1]
    const prev = series.klines.length > 1 ? series.klines[series.klines.length - 2] : null
    const maxHigh = Math.max(...series.klines.map(k => k.high))
    const minLow = Math.min(...series.klines.map(k => k.low))
    const avgVol = series.klines.reduce((acc, k) => acc + (k.volume || 0), 0) / series.klines.length
    const changePct = prev && prev.close ? ((last.close - prev.close) / prev.close) * 100 : 0
    const ampPct = last.close ? ((last.high - last.low) / last.close) * 100 : 0
    return { last, changePct, ampPct, maxHigh, minLow, avgVol }
  }, [series.klines])

  const indexByDate = useMemo(() => {
    const m = new Map<string, number>()
    for (let i = 0; i < series.klines.length; i++) {
      m.set(series.klines[i].date, i)
    }
    return m
  }, [series.klines])
  const showSkeleton = loading && !series.klines.length

  useEffect(() => {
    const LW = getLW()
    if (!LW || !lwReady) return
    if (!containerRef.current) return
    if (!series.candles.length) return

    const container = containerRef.current
    const panesEl = panesRef.current

    container.innerHTML = ''
    if (panesEl) panesEl.innerHTML = ''

    const rootStyle = getComputedStyle(document.documentElement)
    const bg = rootStyle.getPropertyValue('--card').trim()
    const fg = rootStyle.getPropertyValue('--foreground').trim()

    const intraday = isIntradayInterval(interval)
    const defaultBars = intraday ? 120 : interval === '1d' ? 100 : interval === '1w' ? 78 : 72
    const defaultSpacing = interval === '1d' ? 8.5 : 10
    const chart = LW.createChart(container, {
      width: container.clientWidth,
      height: 380,
      layout: {
        background: { color: `hsl(${bg})` },
        textColor: `hsl(${fg} / 0.85)`,
        attributionLogo: false,
      },
      rightPriceScale: { borderVisible: false },
      timeScale: {
        borderVisible: false,
        fixRightEdge: true,
        rightOffset: 1,
        barSpacing: defaultSpacing,
        minBarSpacing: 1,
        lockVisibleTimeRangeOnResize: true,
        ...(intraday ? { timeVisible: true, secondsVisible: false } : {}),
      },
      handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
      handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      grid: {
        vertLines: { color: 'rgba(148, 163, 184, 0.08)' },
        horzLines: { color: 'rgba(148, 163, 184, 0.08)' },
      },
      crosshair: { mode: 1 },
    })

    const candleSeries = addCandles(chart, LW, {
      upColor: palette.up.bright,
      downColor: palette.down.bright,
      borderUpColor: palette.up.bright,
      borderDownColor: palette.down.bright,
      wickUpColor: palette.up.bright,
      wickDownColor: palette.down.bright,
    })
    candleSeries.setData(series.candles)
    const drawingDates = series.klines.map(kline => kline.date)
    const drawingChart = drawingController.bindChart(chart, candleSeries, () => drawingDates)

    const volSeries = addHistogram(chart, LW, {
      priceScaleId: 'vol',
      priceFormat: { type: 'volume' },
    })
    volSeries.setData(series.volumes)
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    const volMa5Series = addLine(chart, LW, { priceScaleId: 'vol', color: 'rgba(245, 158, 11, 0.9)', lineWidth: 1 })
    const volMa10Series = addLine(chart, LW, { priceScaleId: 'vol', color: 'rgba(14, 165, 233, 0.9)', lineWidth: 1 })

    const mapLine = (arr: Array<number | null>) =>
      series.klines
        .map((k, i) => {
          const v = arr[i]
          return v == null ? null : { time: parseKlineTime(k.date, interval) as any, value: v }
        })
        .filter(Boolean)

    if (indicators.ma) {
      addLine(chart, LW, { color: 'rgba(99, 102, 241, 0.9)', lineWidth: 2 }).setData(mapLine(series.ma5) as any)
      addLine(chart, LW, { color: marketColorWithAlpha(palette.up.bright, 0.95), lineWidth: 2 }).setData(mapLine(series.ma10) as any)
      addLine(chart, LW, { color: 'rgba(14, 165, 233, 0.95)', lineWidth: 2 }).setData(mapLine(series.ma20) as any)
    }
    if (indicators.ma60) addLine(chart, LW, { color: marketColorWithAlpha(palette.down.bright, 0.98), lineWidth: 2 }).setData(mapLine(series.ma60) as any)
    if (indicators.ma120) addLine(chart, LW, { color: 'rgba(168, 85, 247, 0.98)', lineWidth: 2 }).setData(mapLine(series.ma120) as any)
    if (indicators.ma240) addLine(chart, LW, { color: 'rgba(245, 158, 11, 0.98)', lineWidth: 2 }).setData(mapLine(series.ma240) as any)
    if (indicators.boll) {
      addLine(chart, LW, { color: marketColorWithAlpha(palette.down.bright, 0.9), lineWidth: 1 }).setData(mapLine(series.boll.upper) as any)
      addLine(chart, LW, { color: 'rgba(148, 163, 184, 0.95)', lineWidth: 1 }).setData(mapLine(series.boll.middle) as any)
      addLine(chart, LW, { color: marketColorWithAlpha(palette.up.bright, 0.9), lineWidth: 1 }).setData(mapLine(series.boll.lower) as any)
    }
    if (indicators.vwap && isIntradayInterval(interval)) {
      addLine(chart, LW, { color: 'rgba(217, 70, 239, 0.98)', lineWidth: 2 }).setData(mapLine(series.vwap) as any)
    }
    volMa5Series.setData(mapLine(series.volMa5) as any)
    volMa10Series.setData(mapLine(series.volMa10) as any)

    if (chanLevel) {
      const overlay = buildChanOverlay(chanLevel, {
        colors: { buy: palette.up.bright, sell: palette.down.bright, bi: palette.flat, seg: palette.flat, zs: marketColorWithAlpha(palette.flat, 0.55) },
        label: chanPointLabel,
        range: series.klines.length
          ? { from: series.klines[0].date, to: series.klines[series.klines.length - 1].date }
          : undefined,
      })
      const chartDates = series.klines.map(k => k.date)
      const chanLine = (points: unknown[], color: string, lineWidth: number, lineStyle?: number) => {
        // 缠论线只在少数日期有点:关掉十字游标标记/最后值标签/价格线,
        // 否则游标落在没有资料的日期时 lightweight-charts v5 会抛 "Value is null",整张图停止绘制
        const line = addLine(chart, LW, {
          color,
          lineWidth,
          crosshairMarkerVisible: false,
          lastValueVisible: false,
          priceLineVisible: false,
          ...(lineStyle == null ? {} : { lineStyle }),
        })
        line.setData(densifyLine(points as any, chartDates) as any)
        return line
      }
      chanLine(overlay.biLine, palette.flat, 1)
      chanLine(overlay.biPending, palette.flat, 1, 2)
      chanLine(overlay.segLine, palette.flat, 3)
      chanLine(overlay.segPending, palette.flat, 3, 2)
      for (const box of overlay.zsBoxes) {
        chanLine(box.top, marketColorWithAlpha(palette.flat, 0.55), 1)
        chanLine(box.bottom, marketColorWithAlpha(palette.flat, 0.55), 1)
      }
      applySeriesMarkers(candleSeries, LW, overlay.markers)
    }

    const subCharts: any[] = []
    const createPane = (title: string, height: number, margins?: { top: number; bottom: number }) => {
      if (!panesEl) return null
      const pane = document.createElement('section')
      pane.className = 'overflow-hidden rounded-xl border border-border/50'
      const heading = document.createElement('div')
      heading.className = 'border-b border-border/40 bg-accent/15 px-2.5 py-1 text-[11px] text-muted-foreground'
      heading.textContent = title
      const plot = document.createElement('div')
      plot.className = 'w-full'
      plot.style.height = `${height}px`
      pane.append(heading, plot)
      panesEl.appendChild(pane)
      const subChart = LW.createChart(plot, {
        width: plot.clientWidth,
        height,
        layout: {
          background: { color: `hsl(${bg})` },
          textColor: `hsl(${fg} / 0.75)`,
          attributionLogo: false,
        },
        rightPriceScale: { borderVisible: false, ...(margins ? { scaleMargins: margins } : {}) },
        timeScale: { borderVisible: false, visible: false },
        grid: {
          vertLines: { color: 'rgba(148, 163, 184, 0.08)' },
          horzLines: { color: 'rgba(148, 163, 184, 0.08)' },
        },
        crosshair: { mode: 0 },
      })
      subCharts.push({ chart: subChart, plot })
      return subChart
    }
    const lineData = (values: Array<number | null>) => series.klines
      .map((k, i) => values[i] == null ? null : { time: parseKlineTime(k.date, interval) as any, value: values[i] as number })
      .filter(Boolean)

    if (indicators.macd) {
      const macdChart = createPane(tr('macd'), 150)
      if (macdChart) {
      const macdLine = addLine(macdChart, LW, { color: 'rgba(99, 102, 241, 0.85)', lineWidth: 2 })
      const sigLine = addLine(macdChart, LW, { color: 'rgba(14, 165, 233, 0.85)', lineWidth: 2 })
      const hist = addHistogram(macdChart, LW, {
        priceFormat: { type: 'price', precision: 3, minMove: 0.001 },
      })
      const histData = series.klines
        .map((k, i) => {
          const v = series.macd.hist[i]
          if (v == null) return null
          return {
            time: parseKlineTime(k.date, interval) as any,
            value: v,
            color: marketColorWithAlpha(v > 0 ? palette.up.bright : v < 0 ? palette.down.bright : palette.flat, 0.35),
          }
        })
        .filter(Boolean)

      macdLine.setData(lineData(series.macd.macd) as any)
      sigLine.setData(lineData(series.macd.signal) as any)
      hist.setData(histData as any)
      }
    }

    if (indicators.rsi) {
      const rsiChart = createPane(tr('rsi'), 110, { top: 0.15, bottom: 0.1 })
      if (rsiChart) {
      const rsiLine = addLine(rsiChart, LW, { color: 'rgba(234, 88, 12, 0.9)', lineWidth: 2 })
      rsiLine.setData(lineData(series.rsi6) as any)
      rsiLine.createPriceLine?.({ price: 70, color: 'rgba(239,68,68,0.45)', lineWidth: 1, lineStyle: 2, title: '70' })
      rsiLine.createPriceLine?.({ price: 30, color: 'rgba(16,185,129,0.45)', lineWidth: 1, lineStyle: 2, title: '30' })
      }
    }

    if (indicators.kd) {
      const kdChart = createPane(tr('kd'), 110, { top: 0.15, bottom: 0.1 })
      if (kdChart) {
        const kLine = addLine(kdChart, LW, { color: 'rgba(99, 102, 241, 0.95)', lineWidth: 2 })
        const dLine = addLine(kdChart, LW, { color: 'rgba(245, 158, 11, 0.95)', lineWidth: 2 })
        kLine.setData(lineData(series.kd.k) as any)
        dLine.setData(lineData(series.kd.d) as any)
        kLine.createPriceLine?.({ price: 80, color: 'rgba(239,68,68,0.5)', lineWidth: 1, lineStyle: 2, title: '80' })
        kLine.createPriceLine?.({ price: 20, color: 'rgba(16,185,129,0.5)', lineWidth: 1, lineStyle: 2, title: '20' })
      }
    }

    if (indicators.obv) {
      const obvChart = createPane(tr('obv'), 110)
      if (obvChart) addLine(obvChart, LW, { color: 'rgba(14, 165, 233, 0.95)', lineWidth: 2 }).setData(lineData(series.obv) as any)
    }

    const sync = (range: any) => {
      for (const item of subCharts) {
        try {
          item.chart.timeScale().setVisibleRange(range)
        } catch {
          // An empty indicator pane may not have a valid range yet.
        }
      }
    }
    chart.timeScale().subscribeVisibleTimeRangeChange(sync)
    const requestEarlier = async (range: any) => {
      const pagination = expansionRef.current
      if (
        intraday ||
        range?.from == null ||
        range?.to == null ||
        !Number.isFinite(range.from) ||
        !Number.isFinite(range.to) ||
        range.from >= 10 ||
        loadingRef.current ||
        pagination.loading ||
        !pagination.canLoad ||
        pagination.reachedEarliest
      ) return

      const nextDays = doubledKlineRequestDays(pagination.requestedDays)
      if (nextDays <= pagination.requestedDays) {
        pagination.reachedEarliest = true
        pagination.canLoad = false
        return
      }
      const requestGeneration = loadGenerationRef.current
      const previousCount = series.klines.length
      pagination.loading = true
      pendingRangeRef.current = { from: range.from, to: range.to }
      setLoadingEarlier(true)
      try {
        const response = await fetchAPI<KlinesResponse>(klineRequestUrl(props.symbol, props.market, nextDays, interval))
        if (requestGeneration !== loadGenerationRef.current) return
        const nextData = (response.klines || []).filter(k => parseKlineTime(k.date, interval) != null)
        const decision = decideKlineExpansion(pagination.requestedDays, previousCount, nextData.length)
        if (!decision.added) {
          pagination.reachedEarliest = true
          pagination.canLoad = false
          pendingRangeRef.current = null
          pendingRangeShiftRef.current = 0
          return
        }
        pagination.requestedDays = nextDays
        pagination.reachedEarliest = decision.reachedEarliest
        pagination.canLoad = !decision.reachedEarliest
        pendingRangeShiftRef.current = decision.added
        setData(nextData)
      } catch {
        // Keep the current chart; reaching the old edge again can retry.
        pendingRangeRef.current = null
        pendingRangeShiftRef.current = 0
      } finally {
        if (requestGeneration === loadGenerationRef.current) {
          pagination.loading = false
          setLoadingEarlier(false)
        }
      }
    }
    const onLogicalRangeChange = (range: any) => { void requestEarlier(range) }
    chart.timeScale().subscribeVisibleLogicalRangeChange?.(onLogicalRangeChange)
    const onCrosshairMove = (param: any) => {
      const point = param?.point
      drawingChart.onCrosshairMove(param)
      const dateKey = crosshairDateKey(param?.time, intraday)
      if (!point || !dateKey || !series.klines.length) {
        setHoverTip(prev => (prev.visible ? { visible: false, x: 0, y: 0, row: null } : prev))
        return
      }
      const inBounds =
        point.x >= 0 &&
        point.y >= 0 &&
        point.x <= container.clientWidth &&
        point.y <= container.clientHeight
      if (!inBounds) {
        setHoverTip(prev => (prev.visible ? { visible: false, x: 0, y: 0, row: null } : prev))
        return
      }
      const idx = indexByDate.get(dateKey)
      if (idx == null || idx < 0 || idx >= series.klines.length) {
        setHoverTip(prev => (prev.visible ? { visible: false, x: 0, y: 0, row: null } : prev))
        return
      }

      const k = series.klines[idx]
      const tooltipWidth = 340
      const tooltipHeight = 230
      let x = point.x + 12
      let y = point.y + 12
      if (x + tooltipWidth > container.clientWidth - 6) x = point.x - tooltipWidth - 12
      if (y + tooltipHeight > container.clientHeight - 6) y = point.y - tooltipHeight - 12
      x = Math.max(6, Math.min(x, Math.max(6, container.clientWidth - tooltipWidth - 6)))
      y = Math.max(6, Math.min(y, Math.max(6, container.clientHeight - tooltipHeight - 6)))

      setHoverTip({
        visible: true,
        x,
        y,
        row: {
          date: k.date,
          open: k.open,
          high: k.high,
          low: k.low,
          close: k.close,
          ma5: series.ma5[idx],
          ma10: series.ma10[idx],
          ma20: series.ma20[idx],
          ma60: series.ma60[idx],
          ma120: series.ma120[idx],
          ma240: series.ma240[idx],
          bollUpper: series.boll.upper[idx],
          bollMiddle: series.boll.middle[idx],
          bollLower: series.boll.lower[idx],
          vwap: isIntradayInterval(interval) ? series.vwap[idx] : null,
          kdK: series.kd.k[idx],
          kdD: series.kd.d[idx],
          obv: series.obv[idx],
          macd: series.macd.macd[idx],
          signal: series.macd.signal[idx],
          rsi6: series.rsi6[idx],
        },
      })
    }
    chart.subscribeCrosshairMove?.(onCrosshairMove)
    const onChartClick = (event: MouseEvent) => {
      const timeScale = chart.timeScale()
      const paneHeight = container.clientHeight - Number(timeScale.height?.() ?? 0)
      const point = panePointFromClick(
        event.clientX, event.clientY, container.getBoundingClientRect(), Number(timeScale.width?.() ?? 0), paneHeight,
      )
      if (point) drawingChart.onClick({ point })
    }
    container.addEventListener('click', onChartClick)

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: container.clientWidth })
      for (const item of subCharts) item.chart.applyOptions({ width: item.plot.clientWidth })
    })
    ro.observe(container)
    if (panesEl) ro.observe(panesEl)

    const total = series.candles.length
    const pendingRange = pendingRangeRef.current
    if (pendingRange) {
      chart.timeScale().setVisibleLogicalRange(shiftLogicalRange(pendingRange, pendingRangeShiftRef.current))
      pendingRangeRef.current = null
      pendingRangeShiftRef.current = 0
    } else {
      const from = Math.max(0, total - defaultBars)
      const to = Math.max(total - 1, 0)
      chart.timeScale().setVisibleLogicalRange({ from, to })
    }
    return () => {
      ro.disconnect()
      chart.timeScale().unsubscribeVisibleLogicalRangeChange?.(onLogicalRangeChange)
      chart.unsubscribeCrosshairMove?.(onCrosshairMove)
      container.removeEventListener('click', onChartClick)
      drawingChart.cleanup()
      try {
        chart.remove()
      } catch {
        // ignore
      }
      for (const item of subCharts) {
        try { item.chart.remove() } catch { /* ignore */ }
      }
    }
  }, [series, lwReady, indicators, indexByDate, interval, palette, chanLevel, props.symbol, props.market, i18n.language, i18n.resolvedLanguage, drawingController.bindChart])

  return (
    <div className="card p-4 md:p-5" onKeyDown={drawingController.onKeyDown}>
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 mb-3">
        <div className="text-[13px] font-semibold text-foreground">{tr('title')}</div>
        <div className="flex items-center gap-2 flex-wrap">
          {([
            { key: 'ma', label: 'ma', disabled: false },
            { key: 'ma60', label: 'ma60', disabled: false },
            { key: 'ma120', label: 'ma120', disabled: false },
            { key: 'ma240', label: 'ma240', disabled: false },
            { key: 'boll', label: 'boll', disabled: false },
            { key: 'vwap', label: 'vwap', disabled: !isIntradayInterval(interval) },
            { key: 'macd', label: 'macd', disabled: false },
            { key: 'rsi', label: 'rsi', disabled: false },
            { key: 'kd', label: 'kd', disabled: false },
            { key: 'obv', label: 'obv', disabled: false },
          ] as const).map(item => (
            <Button
              key={item.key}
              variant={indicators[item.key] ? 'default' : 'secondary'}
              size="sm"
              className="h-8 px-2.5"
              onClick={() => setIndicator(item.key, !indicators[item.key])}
              disabled={item.disabled}
            >
              {tr(item.label)}
            </Button>
          ))}
          <Button
            variant={showChan ? 'default' : 'secondary'}
            size="sm"
            className="h-8 px-2.5"
            onClick={() => setShowChan(v => !v)}
            disabled={interval !== '1d'}
            title={interval !== '1d' ? tr('chanDisabled') : undefined}
          >
            {tr('chan')}
          </Button>
          <KlineDrawingToolbar
            symbol={props.symbol}
            market={props.market}
            drawings={drawings}
            error={drawingError}
            state={drawingToolState}
            capabilities={drawingCapabilities}
            onSelectTool={tool => drawingController.dispatch({ type: 'selectTool', tool })}
            onDeleteSelected={() => drawingController.dispatch({ type: 'deleteSelected' })}
            onClear={() => {
              drawingController.dispatch({ type: 'select', id: null })
              void drawingController.clearDrawings()
            }}
          />
          <div className="inline-flex rounded-lg border border-border/60 bg-accent/20 p-0.5">
            {([
              { value: '1d', label: tr('intervals.day') },
              { value: '1w', label: tr('intervals.week') },
              { value: '1m', label: tr('intervals.month') },
              { value: '5m', label: tr('intervals.fiveMinutes') },
              { value: '15m', label: tr('intervals.fifteenMinutes') },
              { value: '30m', label: tr('intervals.thirtyMinutes') },
              { value: '60m', label: tr('intervals.sixtyMinutes') },
            ] as const).map(item => (
              <button
                key={item.value}
                type="button"
                className={`h-7 min-w-[44px] rounded-md px-2.5 text-[12px] transition-colors ${
                  interval === item.value
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent/60'
                } ${props.market.toUpperCase() === 'CN' && isIntradayInterval(item.value) ? 'opacity-40 cursor-not-allowed' : ''}`}
                disabled={props.market.toUpperCase() === 'CN' && isIntradayInterval(item.value)}
                onClick={() => setIntervalValue(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <Button variant="secondary" size="sm" className="h-8" onClick={() => void load()} disabled={loading || loadingEarlier}>
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">{tr('refresh')}</span>
          </Button>
        </div>
      </div>

      {error ? (
        <div className="text-[12px] text-rose-600 bg-rose-500/10 border border-rose-500/20 rounded-lg px-3 py-2 mb-3">
          {error}
        </div>
      ) : null}

      {!lwReady && libError ? (
        <div className="text-[12px] text-amber-700 dark:text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 mb-3">
          {tr('libraryFailed')}
        </div>
      ) : null}

      {showSkeleton ? (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-3 animate-pulse">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="rounded-lg bg-accent/20 px-2.5 py-2">
              <div className="h-3 w-14 bg-accent/60 rounded" />
              <div className="h-3 w-16 bg-accent/60 rounded mt-2" />
            </div>
          ))}
        </div>
      ) : latestMetrics ? (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-3">
          <div className="rounded-lg bg-accent/20 px-2.5 py-2 text-[11px]"><span className="text-muted-foreground">{tr('metrics.latest')}</span> <span className="font-mono ml-1">{latestMetrics.last.close.toFixed(2)}</span></div>
          <div className="rounded-lg bg-accent/20 px-2.5 py-2 text-[11px]"><span className="text-muted-foreground">{tr('metrics.change')}</span> <span className={`font-mono ml-1 ${marketSignTextClass(latestMetrics.changePct)}`}>{latestMetrics.changePct >= 0 ? '+' : ''}{latestMetrics.changePct.toFixed(2)}%</span></div>
          <div className="rounded-lg bg-accent/20 px-2.5 py-2 text-[11px]"><span className="text-muted-foreground">{tr('metrics.amplitude')}</span> <span className="font-mono ml-1">{latestMetrics.ampPct.toFixed(2)}%</span></div>
          <div className="rounded-lg bg-accent/20 px-2.5 py-2 text-[11px]"><span className="text-muted-foreground">{tr('metrics.range')}</span> <span className="font-mono ml-1">{latestMetrics.maxHigh.toFixed(2)}/{latestMetrics.minLow.toFixed(2)}</span></div>
          <div className="rounded-lg bg-accent/20 px-2.5 py-2 text-[11px]"><span className="text-muted-foreground">{tr('metrics.averageVolume')}</span> <span className="font-mono ml-1">{english ? `${(latestMetrics.avgVol / 1000).toFixed(1)}K` : tr('tenThousand', { value: (latestMetrics.avgVol / 10000).toFixed(1) })}</span></div>
        </div>
      ) : null}
      <div
        ref={drawingController.chartFocusRef}
        className="relative"
        tabIndex={-1}
        onMouseEnter={drawingController.onChartMouseEnter}
        onMouseLeave={drawingController.onChartMouseLeave}
        onMouseDown={event => drawingController.onChartMouseDown(event, containerRef.current)}
      >
        {showSkeleton ? (
          <div className="w-full h-[380px] rounded-xl overflow-hidden border border-border/50 p-3 animate-pulse">
            <div className="h-full w-full rounded-lg bg-accent/20" />
          </div>
        ) : (
          <div
            ref={containerRef}
            className="w-full h-[380px] rounded-xl overflow-hidden border border-border/50"
            style={{ cursor: drawingToolState.tool === 'idle' ? undefined : 'crosshair' }}
          />
        )}
        {loadingEarlier ? (
          <div className="pointer-events-none absolute left-3 top-3 z-20 rounded-md border border-border/60 bg-card/90 px-2.5 py-1 text-[11px] text-muted-foreground shadow-sm">
            {tr('loadingEarlier')}
          </div>
        ) : null}
        {hoverTip.visible && hoverTip.row ? (
          <div
            className="pointer-events-none absolute z-10 w-[340px] rounded-lg border border-border/60 bg-card/95 px-3 py-2 shadow-lg backdrop-blur-[2px]"
            style={{ left: `${hoverTip.x}px`, top: `${hoverTip.y}px` }}
          >
            <div className="text-[11px] text-foreground font-medium mb-1.5">{hoverTip.row.date}</div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
              <span>{tr('hover.open')} <span className="font-mono text-foreground">{hoverTip.row.open.toFixed(2)}</span></span>
              <span>{tr('hover.close')} <span className="font-mono text-foreground">{hoverTip.row.close.toFixed(2)}</span></span>
              <span>{tr('hover.high')} <span className="font-mono text-foreground">{hoverTip.row.high.toFixed(2)}</span></span>
              <span>{tr('hover.low')} <span className="font-mono text-foreground">{hoverTip.row.low.toFixed(2)}</span></span>
              {indicators.ma ? <>
                <span>{tr('hover.ma5')} <span className="font-mono text-foreground">{hoverTip.row.ma5?.toFixed(2) ?? '--'}</span></span>
                <span>{tr('hover.ma10')} <span className="font-mono text-foreground">{hoverTip.row.ma10?.toFixed(2) ?? '--'}</span></span>
                <span>{tr('hover.ma20')} <span className="font-mono text-foreground">{hoverTip.row.ma20?.toFixed(2) ?? '--'}</span></span>
              </> : null}
              {indicators.ma60 ? <span>{tr('hover.ma60')} <span className="font-mono text-foreground">{hoverTip.row.ma60?.toFixed(2) ?? '--'}</span></span> : null}
              {indicators.ma120 ? <span>{tr('hover.ma120')} <span className="font-mono text-foreground">{hoverTip.row.ma120?.toFixed(2) ?? '--'}</span></span> : null}
              {indicators.ma240 ? <span>{tr('hover.ma240')} <span className="font-mono text-foreground">{hoverTip.row.ma240?.toFixed(2) ?? '--'}</span></span> : null}
              {indicators.boll ? <>
                <span>{tr('hover.bollUpper')} <span className="font-mono text-foreground">{hoverTip.row.bollUpper?.toFixed(2) ?? '--'}</span></span>
                <span>{tr('hover.bollMiddle')} <span className="font-mono text-foreground">{hoverTip.row.bollMiddle?.toFixed(2) ?? '--'}</span></span>
                <span>{tr('hover.bollLower')} <span className="font-mono text-foreground">{hoverTip.row.bollLower?.toFixed(2) ?? '--'}</span></span>
              </> : null}
              {indicators.vwap && isIntradayInterval(interval) ? <span>{tr('hover.vwap')} <span className="font-mono text-foreground">{hoverTip.row.vwap?.toFixed(2) ?? '--'}</span></span> : null}
              {indicators.macd ? <>
                <span>{tr('hover.macd')} <span className="font-mono text-foreground">{hoverTip.row.macd?.toFixed(3) ?? '--'}</span></span>
                <span>{tr('hover.signal')} <span className="font-mono text-foreground">{hoverTip.row.signal?.toFixed(3) ?? '--'}</span></span>
              </> : null}
              {indicators.rsi ? <span>{tr('hover.rsi')} <span className="font-mono text-foreground">{hoverTip.row.rsi6?.toFixed(1) ?? '--'}</span></span> : null}
              {indicators.kd ? <span>{tr('hover.kd')} <span className="font-mono text-foreground">{hoverTip.row.kdK?.toFixed(1) ?? '--'} / {hoverTip.row.kdD?.toFixed(1) ?? '--'}</span></span> : null}
              {indicators.obv ? <span>{tr('hover.obv')} <span className="font-mono text-foreground">{hoverTip.row.obv?.toFixed(0) ?? '--'}</span></span> : null}
            </div>
          </div>
        ) : null}
      </div>
      {(indicators.macd || indicators.rsi || indicators.kd || indicators.obv) ? (
        <div className="mt-3 grid grid-cols-1 gap-3">
          <div>
            <div className="text-[11px] text-muted-foreground mb-1">
              {tr('momentum', { rsi: [indicators.macd && tr('macd'), indicators.rsi && tr('rsi'), indicators.kd && tr('kd'), indicators.obv && tr('obv')].filter(Boolean).join(' · ') })}
            </div>
            <div className="text-[11px] text-muted-foreground mb-2 rounded-lg bg-accent/15 border border-border/40 px-2.5 py-1.5">
              {tr('help')}
            </div>
            {showSkeleton ? (
              <div className="w-full h-[150px] rounded-xl overflow-hidden border border-border/50 animate-pulse">
                <div className="h-full w-full bg-accent/20" />
              </div>
            ) : (
              <div ref={panesRef} className="w-full grid grid-cols-1 gap-2" />
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
