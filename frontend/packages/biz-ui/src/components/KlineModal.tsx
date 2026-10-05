import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@panwatch/base-ui/components/ui/dialog'
import InteractiveKline from '@panwatch/biz-ui/components/InteractiveKline'
import type { KlineInterval } from './interactive-kline-utils'
import { useTranslation } from 'react-i18next'
import { DEFAULT_MARKET } from '../market'
import KlineAttribution from './kline-attribution'

export default function KlineModal(props: {
  open: boolean
  onOpenChange: (open: boolean) => void
  symbol: string
  market: string
  title?: string
  description?: string
  initialInterval?: KlineInterval
  initialDays?: number | string
}) {
  const { t } = useTranslation('bizUi')
  const symbol = String(props.symbol || '').trim()
  const market = String(props.market || '').trim() || DEFAULT_MARKET

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>{props.title || (symbol ? t('klineModal.title', { symbol }) : t('klineModal.fallbackTitle'))}</DialogTitle>
          <DialogDescription>
            {props.description || t('klineModal.description')}
          </DialogDescription>
        </DialogHeader>
        {symbol ? (
          <InteractiveKline
            symbol={symbol}
            market={market}
            initialInterval={props.initialInterval}
            initialDays={props.initialDays}
          />
        ) : (
          <div className="text-[12px] text-muted-foreground py-8 text-center">{t('klineModal.noStock')}</div>
        )}
        <KlineAttribution />
      </DialogContent>
    </Dialog>
  )
}
