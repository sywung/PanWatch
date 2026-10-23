import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, RefreshCw } from 'lucide-react'
import { fetchAPI } from '@panwatch/api'
import { useTranslation } from 'react-i18next'
import { useMarketColors } from '@/hooks/use-market-colors'
import { marketSignTextClass } from '@/lib/market-colors'
import { buildTrendSeries, formatChange, groupDispersion, LEVEL_LABELS, type DispersionHistoryPoint, type DispersionLevel } from '@/lib/dispersion'
import { getCurrentLocale } from '@/i18n'

interface DispersionLatest {
  data_date: string
  holder_num: number | null
  avg_shares: number | null
  big_holder_ratio: number | null
  thousand_lot_ratio: number | null
  levels: DispersionLevel[]
  holder_num_change: number | null
  big_holder_ratio_change: number | null
  thousand_lot_ratio_change: number | null
}

interface DispersionResponse {
  symbol: string
  market: string
  latest: DispersionLatest | null
  history: DispersionHistoryPoint[]
}

interface DispersionPanelProps {
  symbol: string
  market: string
  enabled: boolean
}

type Translate = (key: string, options?: Record<string, unknown>) => string

function chartLibrary(): any {
  return (window as any)?.LightweightCharts || null
}

function addLineSeries(chart: any, library: any, options: Record<string, unknown>) {
  if (typeof chart.addLineSeries === 'function') return chart.addLineSeries(options)
  if (typeof chart.addSeries === 'function' && library.LineSeries) return chart.addSeries(library.LineSeries, options)
  throw new Error('Line series API is unavailable')
}

function numberText(value: number | null | undefined, locale: string, digits = 0): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toLocaleString(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function DispersionPanel({ symbol, market, enabled }: DispersionPanelProps) {
  const { t } = useTranslation('bizUi')
  const tr = useCallback<Translate>(
    (key, options) => (t as unknown as Translate)(`dispersion.${key}`, options),
    [t],
  )
  const locale = getCurrentLocale()
  const { palette } = useMarketColors()
  const [data, setData] = useState<DispersionResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [retryCount, setRetryCount] = useState(0)
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const groups = useMemo(() => data?.latest ? groupDispersion(data.latest.levels) : null, [data?.latest])
  const trend = useMemo(() => buildTrendSeries(data?.history ?? []), [data?.history])

  useEffect(() => {
    if (!enabled || market !== 'TW' || !symbol) return
    const controller = new AbortController()
    const params = new URLSearchParams({ symbol, market: 'TW', weeks: '52' })
    setLoading(true)
    setError(false)
    fetchAPI<DispersionResponse>(`/shareholders/dispersion?${params}`, { signal: controller.signal })
      .then((response) => setData(response))
      .catch(() => {
        if (!controller.signal.aborted) setError(true)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [enabled, market, symbol, retryCount])

  useEffect(() => {
    const container = chartContainerRef.current
    if (!container || !data || data.history.length < 2) return
    const library = chartLibrary()
    if (!library?.createChart) return

    let chart: any
    try {
      chart = library.createChart(container, {
        width: container.clientWidth,
        height: 240,
        layout: { background: { color: 'transparent' }, textColor: '#94a3b8', fontFamily: 'inherit', fontSize: 11, attributionLogo: false },
        grid: { vertLines: { color: 'rgba(148, 163, 184, 0.08)' }, horzLines: { color: 'rgba(148, 163, 184, 0.12)' } },
        rightPriceScale: { visible: true, borderVisible: false },
        leftPriceScale: { visible: true, borderVisible: false },
        timeScale: { borderVisible: false, timeVisible: false },
        crosshair: { vertLine: { labelVisible: true }, horzLine: { labelVisible: true } },
      })
      const thousandSeries = addLineSeries(chart, library, {
        color: palette.up.text,
        lineWidth: 2,
        priceScaleId: 'left',
        title: tr('thousandTrend'),
        priceFormat: { type: 'custom', formatter: (value: number) => `${value.toFixed(2)}%` },
      })
      const holderSeries = addLineSeries(chart, library, {
        color: '#94a3b8',
        lineWidth: 2,
        priceScaleId: 'right',
        title: tr('holdersTrend'),
        priceFormat: { type: 'custom', minMove: 1, formatter: (value: number) => Math.round(value).toLocaleString('en-US') },
      })
      thousandSeries.setData(trend.thousand)
      holderSeries.setData(trend.holders)
      chart.timeScale().fitContent()

      const resize = () => chart?.applyOptions({ width: container.clientWidth })
      const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null
      observer?.observe(container)
      if (!observer) window.addEventListener('resize', resize)
      return () => {
        observer?.disconnect()
        if (!observer) window.removeEventListener('resize', resize)
        chart?.remove()
      }
    } catch {
      chart?.remove()
      return
    }
  }, [data, palette.up.text, trend.holders, trend.thousand, tr])

  if (!enabled || market !== 'TW') return null

  const latest = data?.latest
  const summaries = latest && groups ? [
    { label: tr('retail'), group: groups.retail },
    { label: tr('mid'), group: groups.mid },
    { label: tr('big'), group: groups.big },
  ] : []

  return (
    <details open className="group mt-4 rounded-lg border border-border/50 bg-card/50">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">{tr('title')}</h3>
          <p className="mt-0.5 text-[11px] text-muted-foreground">{tr('description')}</p>
        </div>
        <ChevronDown aria-hidden className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>

      <div className="space-y-4 border-t border-border/40 px-4 py-4">
        {loading ? (
          <div role="status" className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <RefreshCw className="h-4 w-4 animate-spin" />{tr('loading')}
          </div>
        ) : error ? (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-3 py-5 text-sm text-muted-foreground">
            <span>{tr('failed')}</span>
            <button className="rounded-md border border-border px-3 py-1.5 text-xs text-foreground hover:bg-accent" onClick={() => setRetryCount((count) => count + 1)}>
              {tr('retry')}
            </button>
          </div>
        ) : !latest ? (
          <div className="py-8 text-center text-sm text-muted-foreground">{tr('empty')}</div>
        ) : (
          <>
            <section aria-label={tr('summary')} className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <SummaryMetric label={tr('dataDate')} value={latest.data_date} />
              <SummaryMetric
                label={tr('holders')}
                value={numberText(latest.holder_num, locale)}
                change={latest.holder_num_change}
                changeDigits={0}
              />
              <SummaryMetric
                label={tr('thousandLot')}
                value={`${numberText(latest.thousand_lot_ratio, locale, 2)}%`}
                change={latest.thousand_lot_ratio_change}
                changeDigits={2}
                suffix={` ${tr('percentagePointUnit')}`}
              />
              <SummaryMetric label={tr('bigHolders')} value={`${numberText(latest.big_holder_ratio, locale, 2)}%`} />
            </section>

            <section className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {summaries.map(({ label, group }) => (
                <div key={label} className="rounded-md border border-border/40 bg-background/40 px-3 py-2">
                  <div className="text-[11px] text-muted-foreground">{label}</div>
                  <div className="mt-1 flex items-baseline justify-between gap-2">
                    <span className="font-mono text-sm font-semibold text-foreground">{numberText(group.pct, locale, 2)}%</span>
                    <span className="text-[10px] text-muted-foreground">{numberText(group.holders, locale)} {tr('holderUnit')}</span>
                  </div>
                </div>
              ))}
            </section>

            <section>
              <h4 className="mb-2 text-xs font-semibold text-foreground">{tr('levelsTitle')}</h4>
              <div className="overflow-x-auto scrollbar rounded-md border border-border/40">
                <table className="w-full border-collapse text-left text-[11px] sm:min-w-[590px]">
                  <thead className="bg-accent/40 text-muted-foreground">
                    <tr>
                      <th className="px-2.5 py-2 font-medium">{tr('levelColumn')}</th>
                      <th className="px-2.5 py-2 text-right font-medium">{tr('holdersColumn')}</th>
                      <th className="hidden px-2.5 py-2 text-right font-medium sm:table-cell">{tr('sharesColumn')}</th>
                      <th className="px-2.5 py-2 text-right font-medium sm:w-[34%]">{tr('pctColumn')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {latest.levels.map((row) => {
                      const highlighted = row.level >= 12 && row.level <= 15
                      const label = tr(`level${row.level}`) || LEVEL_LABELS[row.level - 1]
                      return (
                        <tr key={row.level} className={`border-t border-border/30 ${highlighted ? 'bg-primary/[0.06]' : ''}`}>
                          <td className={`whitespace-nowrap px-2.5 py-1.5 ${highlighted ? 'border-l-2 border-primary font-medium text-primary' : 'text-foreground'}`}>{label}</td>
                          <td className="px-2.5 py-1.5 text-right font-mono text-muted-foreground">{numberText(row.holders, locale)}</td>
                          <td className="hidden px-2.5 py-1.5 text-right font-mono text-muted-foreground sm:table-cell">{numberText(row.shares, locale)}</td>
                          <td className="px-2.5 py-1.5">
                            <div className="flex items-center justify-end gap-2">
                              <div className="hidden h-1.5 w-20 overflow-hidden rounded-full bg-accent/60 sm:block">
                                <div className={`h-full rounded-full ${highlighted ? 'bg-primary' : 'bg-muted-foreground/45'}`} style={{ width: `${Math.min(100, Math.max(0, row.pct))}%` }} />
                              </div>
                              <span className="w-14 text-right font-mono text-foreground">{numberText(row.pct, locale, 2)}%</span>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            <section>
              <h4 className="mb-2 text-xs font-semibold text-foreground">{tr('historyTitle')}</h4>
              {data && data.history.length < 2 ? (
                <p className="rounded-md bg-accent/20 px-3 py-5 text-center text-xs text-muted-foreground">
                  {tr('trendAccumulating', {
                    date: data.history.map((point) => point.data_date).sort()[0] ?? latest.data_date,
                    count: data.history.length,
                  })}
                </p>
              ) : (
                <div className="relative">
                  {!chartLibrary()?.createChart && <p className="pb-2 text-[11px] text-muted-foreground">{tr('chartUnavailable')}</p>}
                  <div ref={chartContainerRef} className="h-[240px] w-full" />
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </details>
  )
}

function SummaryMetric({
  label,
  value,
  change,
  changeDigits = 2,
  suffix = '',
}: {
  label: string
  value: string
  change?: number | null
  changeDigits?: number
  suffix?: string
}) {
  const { t } = useTranslation('bizUi')
  const text = (t as unknown as Translate)(`dispersion.weeklyChange`)
  return (
    <div className="rounded-md border border-border/40 bg-background/40 px-3 py-2">
      <div className="text-[10px] leading-4 text-muted-foreground">{label}</div>
      <div className="mt-1 truncate font-mono text-sm font-semibold text-foreground" title={value}>{value}</div>
      {change !== undefined && (
        <div className={`mt-0.5 text-[10px] ${marketSignTextClass(change)}`}>
          {text}: {formatChange(change, changeDigits)}{change == null ? '' : suffix}
        </div>
      )}
    </div>
  )
}
