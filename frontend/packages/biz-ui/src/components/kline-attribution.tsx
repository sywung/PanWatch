import { useTranslation } from 'react-i18next'

// lightweight-charts 授權要求頁面上保留出處與連結；圖表內的 TV 圖標已關閉，改由這行滿足
export const KLINE_ATTRIBUTION_URL = 'https://www.tradingview.com/'

export default function KlineAttribution() {
  const { t } = useTranslation('bizUi')
  return (
    <div className="pt-3 text-right text-[11px] text-muted-foreground/70">
      <a
        href={KLINE_ATTRIBUTION_URL}
        target="_blank"
        rel="noreferrer"
        className="hover:text-muted-foreground hover:underline"
      >
        {t('klineModal.attribution')}
      </a>
    </div>
  )
}
