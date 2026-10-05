import { anchorToLogical, type DrawingAnchor, type KlineDrawing, type TrendDrawing } from './kline-drawings'

type PrimitivePoint = { x: number; y: number }
type RenderedLine = {
  x1: number
  y1: number
  x2: number
  y2: number
  selected: boolean
  preview: boolean
}
export type TrendPreview = { p1: DrawingAnchor; p2: { logical: number; price: number } } | null

function finitePoint(x: number | null, y: number | null): PrimitivePoint | null {
  return x == null || y == null || !Number.isFinite(x) || !Number.isFinite(y) ? null : { x, y }
}

export function createKlineTrendlinePrimitive(
  candleSeries: any,
  chart: any,
  getDates: () => string[],
  colors: { line: string; selected: string },
) {
  let drawings: KlineDrawing[] = []
  let preview: TrendPreview = null
  let selectedId: number | null = null
  let requestUpdate: (() => void) | null = null
  let renderedLines: RenderedLine[] = []

  const draw = (target: any) => {
    target.useBitmapCoordinateSpace(({ context, horizontalPixelRatio, verticalPixelRatio }: any) => {
      for (const line of renderedLines) {
        const x1 = line.x1 * horizontalPixelRatio
        const x2 = line.x2 * horizontalPixelRatio
        const y1 = line.y1 * verticalPixelRatio
        const y2 = line.y2 * verticalPixelRatio
        const scale = (horizontalPixelRatio + verticalPixelRatio) / 2
        context.save()
        context.beginPath()
        context.strokeStyle = line.selected ? colors.selected : colors.line
        context.lineWidth = (line.selected ? 3 : 2) * scale
        context.setLineDash(line.preview ? [6 * scale, 4 * scale] : [])
        context.moveTo(x1, y1)
        context.lineTo(x2, y2)
        context.stroke()
        if (line.selected && !line.preview) {
          for (const [x, y] of [[x1, y1], [x2, y2]]) {
            context.beginPath()
            context.fillStyle = colors.selected
            context.arc(x, y, 4 * scale, 0, Math.PI * 2)
            context.fill()
            context.lineWidth = scale
            context.strokeStyle = 'rgba(255,255,255,0.95)'
            context.stroke()
          }
        }
        context.restore()
      }
    })
  }

  const renderer = { draw }
  const paneView = {
    renderer: () => renderer,
    zOrder: () => 'top',
  }

  const primitive = {
    attached({ requestUpdate: update }: { requestUpdate: () => void }) {
      requestUpdate = update
      this.updateAllViews()
    },
    detached() {
      requestUpdate = null
      renderedLines = []
    },
    updateAllViews() {
      const dates = getDates()
      const projectAnchor = (anchor: DrawingAnchor): PrimitivePoint | null => {
        const logical = anchorToLogical(anchor.time, dates)
        if (logical == null) return null
        return finitePoint(
          chart.timeScale().logicalToCoordinate(logical),
          candleSeries.priceToCoordinate(anchor.price),
        )
      }
      const lines: RenderedLine[] = []
      for (const drawing of drawings) {
        if (drawing.kind !== 'trend') continue
        const p1 = projectAnchor(drawing.data.p1)
        const p2 = projectAnchor(drawing.data.p2)
        if (!p1 || !p2) continue
        lines.push({
          x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y,
          selected: drawing.id === selectedId,
          preview: false,
        })
      }
      if (preview) {
        const p1 = projectAnchor(preview.p1)
        const p2 = finitePoint(
          chart.timeScale().logicalToCoordinate(preview.p2.logical),
          candleSeries.priceToCoordinate(preview.p2.price),
        )
        if (p1 && p2) lines.push({ x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y, selected: false, preview: true })
      }
      renderedLines = lines
      requestUpdate?.()
    },
    paneViews: () => [paneView],
    updateData(nextDrawings: KlineDrawing[], nextPreview: TrendPreview, nextSelectedId: number | null) {
      drawings = nextDrawings
      preview = nextPreview
      selectedId = nextSelectedId
      this.updateAllViews()
    },
  }
  return primitive
}

export function isTrendDrawing(drawing: KlineDrawing): drawing is TrendDrawing {
  return drawing.kind === 'trend'
}
