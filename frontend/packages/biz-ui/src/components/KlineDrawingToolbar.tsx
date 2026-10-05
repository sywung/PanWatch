import { useEffect, useRef, useState } from 'react'
import { Button } from '@panwatch/base-ui/components/ui/button'
import { useTranslation } from 'react-i18next'
import type { DrawingToolState, KlineDrawing } from './kline-drawings'

type Props = {
  symbol: string
  market: string
  drawings: KlineDrawing[]
  error: string | null
  state: DrawingToolState
  capabilities: { hline: boolean; trend: boolean }
  onSelectTool: (tool: 'hline' | 'trend') => void
  onDeleteSelected: () => void
  onClear: () => void
}

export default function KlineDrawingToolbar({
  symbol,
  market,
  drawings,
  error,
  state,
  capabilities,
  onSelectTool,
  onDeleteSelected,
  onClear,
}: Props) {
  const { t } = useTranslation('bizUi')
  const [confirmClear, setConfirmClear] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const tr = (key: string) => (t as (key: string) => string)(`interactiveKline.drawings.${key}`)

  useEffect(() => {
    setConfirmClear(false)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = null
  }, [symbol, market])

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current)
  }, [])

  if (!capabilities.hline) return null

  const clear = () => {
    if (!confirmClear) {
      setConfirmClear(true)
      timerRef.current = setTimeout(() => {
        setConfirmClear(false)
        timerRef.current = null
      }, 3000)
      return
    }
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = null
    setConfirmClear(false)
    onClear()
  }

  return (
    <div className="inline-flex items-center gap-1 border-l border-border/60 pl-2">
      <Button
        variant={state.tool === 'placingHline' ? 'default' : 'secondary'}
        size="sm"
        className="h-8 px-2.5"
        onClick={() => onSelectTool('hline')}
      >
        {tr('hline')}
      </Button>
      {capabilities.trend ? (
        <Button
          variant={state.tool === 'placingTrend' ? 'default' : 'secondary'}
          size="sm"
          className="h-8 px-2.5"
          onClick={() => onSelectTool('trend')}
        >
          {tr('trend')}
        </Button>
      ) : null}
      {state.selectedId != null ? (
        <Button variant="secondary" size="sm" className="h-8 px-2.5" onClick={onDeleteSelected}>
          {tr('delete')}
        </Button>
      ) : null}
      {drawings.length ? (
        <Button
          variant={confirmClear ? 'destructive' : 'secondary'}
          size="sm"
          className="h-8 px-2.5"
          onClick={clear}
        >
          {confirmClear ? tr('confirmClear') : tr('clearAll')}
        </Button>
      ) : null}
      {state.tool === 'placingHline' ? (
        <span className="ml-1 text-[11px] text-amber-600 dark:text-amber-400">{tr('hlineHint')}</span>
      ) : state.tool === 'placingTrend' ? (
        <span className="ml-1 text-[11px] text-sky-600 dark:text-sky-400">{tr('trendHint')}</span>
      ) : null}
      {error ? <span className="max-w-40 text-[11px] text-rose-600" role="status">{error}</span> : null}
    </div>
  )
}
