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
type OverlayOptions = { colors: OverlayColors; label: (type: string, isBuy: boolean) => string }

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

export function buildChanOverlay(level: ChanLevel | null, options: OverlayOptions) {
  if (!level) return { biLine: [], biPending: [], segLine: [], segPending: [], zsBoxes: [], markers: [] as ChanMarker[] }
  const zsBoxes = (level.zs || []).flatMap((pivot) => {
    const begin = toDay(pivot.begin_time)
    const end = toDay(pivot.end_time)
    if (!begin || !end) return []
    return [{
      top: [{ time: begin, value: pivot.zg }, { time: end, value: pivot.zg }],
      bottom: [{ time: begin, value: pivot.zd }, { time: end, value: pivot.zd }],
    }]
  })
  const markers = (level.bsp || []).flatMap((point) => {
    const time = toDay(point.time)
    if (!time) return []
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
    biLine: pointsFor(level.bi, false),
    biPending: pointsFor(level.bi, true),
    segLine: pointsFor(level.seg, false),
    segPending: pointsFor(level.seg, true),
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
