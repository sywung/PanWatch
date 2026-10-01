import i18n, { getCurrentLocale } from '@/i18n'

export type ChanTime = { year: number; month: number; day: number }
export type ChanLinePoint = { time: ChanTime; value: number }
export type ChanMarker = {
  time: ChanTime
  position: 'aboveBar' | 'belowBar'
  shape: 'arrowDown' | 'arrowUp'
  color: string
  text: string
}

type ChanStroke = {
  begin_time: string
  begin_val: number
  end_time: string
  end_val: number
  sure?: boolean
}
type ChanPivot = { begin_time: string; end_time: string; zd: number; zg: number }
type ChanPoint = { time: string; is_buy: boolean; type: string; sure?: boolean }
export type ChanLevel = { bi?: ChanStroke[]; seg?: ChanStroke[]; zs?: ChanPivot[]; bsp?: ChanPoint[] }

type OverlayColors = { buy: string; sell: string; bi: string; seg: string; zs: string }
// range:图上 K 线的首尾日期(YYYY-MM-DD)。超出范围的点会把主图时间轴往外拉,
// 同步到 MACD/RSI 副图时 lightweight-charts 会抛 "Value is null",所以一律裁切到范围内。
type OverlayRange = { from: string; to: string }
type OverlayOptions = {
  colors: OverlayColors
  label: (type: string, isBuy: boolean) => string
  range?: OverlayRange
}

const toDay = (value: string): ChanTime | null => {
  const match = String(value || '').trim().match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return match ? { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) } : null
}

function pointsFor(strokes: ChanStroke[] | undefined, pending: boolean): ChanLinePoint[] {
  const items = (strokes || []).filter(stroke => Boolean(stroke.sure) !== pending)
  if (!items.length) return []
  const points: ChanLinePoint[] = []
  const append = (time: string, value: number) => {
    const day = toDay(time)
    if (!day) return
    const previous = points[points.length - 1]
    if (previous && previous.time.year === day.year && previous.time.month === day.month && previous.time.day === day.day && previous.value === value) return
    points.push({ time: day, value })
  }
  if (pending) {
    const confirmed = (strokes || []).filter(stroke => stroke.sure)
    const lastConfirmed = confirmed[confirmed.length - 1]
    if (lastConfirmed) append(lastConfirmed.end_time, lastConfirmed.end_val)
  }
  for (const stroke of items) {
    append(stroke.begin_time, stroke.begin_val)
    append(stroke.end_time, stroke.end_val)
  }
  return points
}

const dayKey = (time: ChanTime) =>
  `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`

const dayNumber = (time: ChanTime) => Date.UTC(time.year, time.month - 1, time.day) / 86400000

function clipLine(points: ChanLinePoint[], range?: OverlayRange): ChanLinePoint[] {
  if (!range || points.length === 0) return points
  const from = toDay(range.from)
  const to = toDay(range.to)
  if (!from || !to) return points
  const lo = dayNumber(from)
  const hi = dayNumber(to)
  const out: ChanLinePoint[] = []
  const push = (point: ChanLinePoint) => {
    const last = out[out.length - 1]
    if (last && dayKey(last.time) === dayKey(point.time)) return
    out.push(point)
  }
  const at = (a: ChanLinePoint, b: ChanLinePoint, day: number, time: ChanTime): ChanLinePoint => {
    const span = dayNumber(b.time) - dayNumber(a.time)
    const value = span === 0 ? a.value : a.value + (b.value - a.value) * (day - dayNumber(a.time)) / span
    return { time, value }
  }
  for (let i = 0; i < points.length; i += 1) {
    const point = points[i]
    const day = dayNumber(point.time)
    const next = points[i + 1]
    if (day >= lo && day <= hi) push(point)
    if (!next) continue
    const nextDay = dayNumber(next.time)
    if (day < lo && nextDay >= lo) push(at(point, next, lo, from))
    if (day <= hi && nextDay > hi) push(at(point, next, hi, to))
  }
  return out
}

export function buildChanOverlay(level: ChanLevel | null, options: OverlayOptions) {
  if (!level) return { biLine: [], biPending: [], segLine: [], segPending: [], zsBoxes: [], markers: [] as ChanMarker[] }
  const inRange = (time: ChanTime) =>
    !options.range || (dayKey(time) >= options.range.from && dayKey(time) <= options.range.to)
  const zsBoxes = (level.zs || []).flatMap((pivot) => {
    let begin = toDay(pivot.begin_time)
    let end = toDay(pivot.end_time)
    if (!begin || !end) return []
    if (options.range) {
      const from = toDay(options.range.from)
      const to = toDay(options.range.to)
      if (from && dayKey(begin) < options.range.from) begin = from
      if (to && dayKey(end) > options.range.to) end = to
      if (dayKey(begin) > dayKey(end)) return []
    }
    return [{
      top: [{ time: begin, value: pivot.zg }, { time: end, value: pivot.zg }],
      bottom: [{ time: begin, value: pivot.zd }, { time: end, value: pivot.zd }],
    }]
  })
  const markers = (level.bsp || []).flatMap((point) => {
    const time = toDay(point.time)
    if (!time || !inRange(time)) return []
    const isBuy = Boolean(point.is_buy)
    return [{
      time,
      position: isBuy ? 'belowBar' as const : 'aboveBar' as const,
      shape: isBuy ? 'arrowUp' as const : 'arrowDown' as const,
      color: isBuy ? options.colors.buy : options.colors.sell,
      text: `${options.label(point.type, isBuy)}${point.sure ? '' : '?'}`,
    }]
  }).sort((a, b) => a.time.year - b.time.year || a.time.month - b.time.month || a.time.day - b.time.day)
  return {
    biLine: clipLine(pointsFor(level.bi, false), options.range),
    biPending: clipLine(pointsFor(level.bi, true), options.range),
    segLine: clipLine(pointsFor(level.seg, false), options.range),
    segPending: clipLine(pointsFor(level.seg, true), options.range),
    zsBoxes,
    markers,
  }
}

export function applySeriesMarkers(series: any, LW: any, markers: ChanMarker[]) {
  if (typeof LW?.createSeriesMarkers === 'function') return LW.createSeriesMarkers(series, markers)
  if (typeof series?.setMarkers === 'function') return series.setMarkers(markers)
  return undefined
}

export function chanPointLabel(type: string, isBuy: boolean): string {
  const key = isBuy ? 'chan.labels.buy' : 'chan.labels.sell'
  const locale = getCurrentLocale()
  return i18n.t(key, { ns: 'bizUi', type, locale })
}
