export type DrawingAnchor = { time: string; price: number }

export type HlineDrawing = {
  id: number
  symbol: string
  market: string
  kind: 'hline'
  data: { price: number }
}

export type TrendDrawing = {
  id: number
  symbol: string
  market: string
  kind: 'trend'
  data: { p1: DrawingAnchor; p2: DrawingAnchor }
}

export type KlineDrawing = HlineDrawing | TrendDrawing
export type NewDrawing = Omit<HlineDrawing, 'id' | 'symbol' | 'market'> | Omit<TrendDrawing, 'id' | 'symbol' | 'market'>
export type ProjectedDrawing =
  | { kind: 'hline'; y: number }
  | { kind: 'trend'; x1: number; y1: number; x2: number; y2: number }

type TimeParts = { date: string; hasTime: boolean; timestamp: number }

function parseTime(value: string): TimeParts | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?: (\d{2}):(\d{2}))?$/.exec(value)
  if (!match) return null
  const [, yearText, monthText, dayText, hourText, minuteText] = match
  const year = Number(yearText)
  const month = Number(monthText)
  const day = Number(dayText)
  const hour = hourText == null ? 0 : Number(hourText)
  const minute = minuteText == null ? 0 : Number(minuteText)
  const timestamp = Date.UTC(year, month - 1, day, hour, minute)
  const parsed = new Date(timestamp)
  if (
    parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day || parsed.getUTCHours() !== hour || parsed.getUTCMinutes() !== minute
  ) return null
  return { date: `${yearText}-${monthText}-${dayText}`, hasTime: hourText != null, timestamp }
}

function meanStep(dates: string[]): number {
  const timestamps = dates.map(parseTime).map(value => value?.timestamp)
  const gaps: number[] = []
  for (let i = 1; i < timestamps.length; i++) {
    const gap = (timestamps[i] ?? 0) - (timestamps[i - 1] ?? 0)
    if (gap > 0) gaps.push(gap)
  }
  return gaps.length ? gaps.reduce((sum, gap) => sum + gap, 0) / gaps.length : 0
}

function isoWeekKey(date: string): string {
  const [year, month, day] = date.split('-').map(Number)
  const current = new Date(Date.UTC(year, month - 1, day))
  const weekday = current.getUTCDay() || 7
  current.setUTCDate(current.getUTCDate() + 4 - weekday)
  const weekYear = current.getUTCFullYear()
  const firstThursday = new Date(Date.UTC(weekYear, 0, 4))
  const firstWeekday = firstThursday.getUTCDay() || 7
  firstThursday.setUTCDate(firstThursday.getUTCDate() + 4 - firstWeekday)
  const week = 1 + Math.round((current.getTime() - firstThursday.getTime()) / (7 * 86400000))
  return `${weekYear}-W${String(week).padStart(2, '0')}`
}

function median(values: number[]): number {
  if (!values.length) return 0
  const ordered = [...values].sort((a, b) => a - b)
  const middle = Math.floor(ordered.length / 2)
  return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2
}

/** Map a saved anchor to a fractional chart logical index, including calendar periods. */
type DateIndex = {
  timestamps: number[]
  intraday: boolean
  typicalDays: number
  step: number
  weekKeys: string[] | null
}

// 圖表每次重畫都會對每個錨點呼叫 anchorToLogical；同一份 dates 只解析一次
const dateIndexCache = new WeakMap<string[], DateIndex | null>()

function dateIndexFor(dates: string[]): DateIndex | null {
  if (dateIndexCache.has(dates)) return dateIndexCache.get(dates) ?? null
  const parsedDates = dates.map(parseTime)
  let index: DateIndex | null = null
  if (!parsedDates.some(value => value == null)) {
    const timestamps = parsedDates.map(value => value!.timestamp)
    if (!timestamps.some((value, i) => i > 0 && value < timestamps[i - 1])) {
      const gapsInDays = timestamps.slice(1).map((value, i) => (value - timestamps[i]) / 86400000)
      index = {
        timestamps,
        intraday: dates.some(date => date.includes(' ')),
        typicalDays: median(gapsInDays),
        step: meanStep(dates),
        weekKeys: null,
      }
    }
  }
  dateIndexCache.set(dates, index)
  return index
}

export function anchorToLogical(time: string, dates: string[]): number | null {
  if (dates.length < 2) return null
  const anchor = parseTime(time)
  const index = anchor ? dateIndexFor(dates) : null
  if (!anchor || !index) return null
  const { timestamps, intraday, typicalDays } = index
  if (!anchor.hasTime && intraday) {
    const sameDay = dates.findIndex(date => date.slice(0, 10) === anchor.date)
    if (sameDay >= 0) return sameDay
  }

  if (!anchor.hasTime && !intraday && typicalDays >= 20) {
    const month = anchor.date.slice(0, 7)
    const containingMonth = dates.findIndex(date => date.slice(0, 7) === month)
    if (containingMonth >= 0) return containingMonth
  } else if (!anchor.hasTime && !intraday && typicalDays >= 5) {
    const week = isoWeekKey(anchor.date)
    index.weekKeys ??= dates.map(isoWeekKey)
    const containingWeek = index.weekKeys.indexOf(week)
    if (containingWeek >= 0) return containingWeek
  }

  const { step } = index
  if (!(step > 0)) return null
  if (anchor.timestamp < timestamps[0]) return (anchor.timestamp - timestamps[0]) / step
  const last = timestamps.length - 1
  if (anchor.timestamp > timestamps[last]) return last + (anchor.timestamp - timestamps[last]) / step

  let low = 0
  let high = dates.length
  while (low < high) {
    const mid = (low + high) >>> 1
    if (timestamps[mid] <= anchor.timestamp) low = mid + 1
    else high = mid
  }
  return Math.max(0, low - 1)
}

export function logicalToAnchorTime(logical: number, dates: string[]): string {
  if (!dates.length) return ''
  if (!Number.isFinite(logical)) return dates[0]
  const index = Math.max(0, Math.min(dates.length - 1, Math.round(logical)))
  return dates[index]
}

export function distanceToSegment(
  px: number, py: number, x1: number, y1: number, x2: number, y2: number,
): number {
  const dx = x2 - x1
  const dy = y2 - y1
  const lengthSquared = dx * dx + dy * dy
  if (lengthSquared === 0) return Math.hypot(px - x1, py - y1)
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lengthSquared))
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
}

/** Return the nearest projected line ID within six screen pixels. */
export function hitTestDrawings(
  point: { x: number; y: number },
  drawings: KlineDrawing[],
  project: (drawing: KlineDrawing) => ProjectedDrawing | null,
): number | null {
  let nearestId: number | null = null
  let nearestDistance = 6
  for (const drawing of drawings) {
    const projected = project(drawing)
    if (!projected) continue
    let distance: number
    if (projected.kind === 'hline') {
      distance = Math.abs(point.y - projected.y)
    } else {
      // distanceToSegment 已把投影夾在兩端點之間；不能再用 x 範圍過濾，否則陡峭的線幾乎點不到
      distance = distanceToSegment(point.x, point.y, projected.x1, projected.y1, projected.x2, projected.y2)
    }
    if (distance <= nearestDistance) {
      nearestDistance = distance
      nearestId = drawing.id
    }
  }
  return nearestId
}

export type DrawingTool = 'idle' | 'placingHline' | 'placingTrend'
export type DrawingToolState = {
  tool: DrawingTool
  firstPoint?: DrawingAnchor
  selectedId: number | null
}
export type DrawingAction =
  | { type: 'add'; drawing: NewDrawing }
  | { type: 'delete'; id: number }
export type DrawingTransition = { state: DrawingToolState; action?: DrawingAction }
export type DrawingEvent =
  | { type: 'selectTool'; tool: 'hline' | 'trend' }
  | { type: 'chartClick'; point: DrawingAnchor }
  | { type: 'escape' }
  | { type: 'deleteSelected' }
  | { type: 'select'; id: number | null }

export const initialDrawingToolState: DrawingToolState = { tool: 'idle', selectedId: null }

export function drawingReducer(state: DrawingToolState, event: DrawingEvent): DrawingTransition {
  switch (event.type) {
    case 'selectTool': {
      const tool: DrawingTool = event.tool === 'hline' ? 'placingHline' : 'placingTrend'
      return {
        state: {
          tool: state.tool === tool ? 'idle' : tool,
          selectedId: null,
        },
      }
    }
    case 'chartClick':
      if (state.tool === 'placingHline') {
        return {
          state: { tool: 'idle', selectedId: null },
          action: { type: 'add', drawing: { kind: 'hline', data: { price: event.point.price } } },
        }
      }
      if (state.tool === 'placingTrend') {
        if (!state.firstPoint) return { state: { ...state, firstPoint: event.point } }
        return {
          state: { tool: 'idle', selectedId: null },
          action: {
            type: 'add',
            drawing: { kind: 'trend', data: { p1: state.firstPoint, p2: event.point } },
          },
        }
      }
      return { state: { ...state, selectedId: null } }
    case 'escape':
      return { state: { tool: 'idle', selectedId: null } }
    case 'deleteSelected':
      return state.selectedId == null
        ? { state }
        : { state: { ...state, selectedId: null }, action: { type: 'delete', id: state.selectedId } }
    case 'select':
      return { state: { tool: 'idle', selectedId: event.id } }
  }
}
