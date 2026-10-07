import i18n, { getCurrentLocale, type SupportedLocale } from './index'
import { marketCurrency, type MarketCode } from '@panwatch/biz-ui'

const MARKET_CURRENCIES: Record<MarketCode, string> = {
  TW: 'TWD',
  CN: 'CNY',
  HK: 'HKD',
  US: 'USD',
}

function localeOrCurrent(locale?: SupportedLocale): SupportedLocale {
  return locale ?? getCurrentLocale()
}

export function formatNumber(
  value: number,
  options?: Intl.NumberFormatOptions,
  locale?: SupportedLocale,
): string {
  return new Intl.NumberFormat(localeOrCurrent(locale), options).format(value)
}

export function formatPercent(
  value: number,
  options?: Intl.NumberFormatOptions,
  locale?: SupportedLocale,
): string {
  return formatNumber(value, { style: 'percent', maximumFractionDigits: 2, ...options }, locale)
}

export function formatCurrency(
  value: number,
  currency: string,
  options?: Intl.NumberFormatOptions,
  locale?: SupportedLocale,
): string {
  return formatNumber(value, { style: 'currency', currency, ...options }, locale)
}

export function formatMarketCurrency(
  value: number,
  market: MarketCode,
  options?: Intl.NumberFormatOptions,
  locale?: SupportedLocale,
): string {
  return formatCurrency(value, MARKET_CURRENCIES[market] ?? marketCurrency(market), options, locale)
}

export function formatDate(
  value: Date | string | number,
  options?: Intl.DateTimeFormatOptions,
  locale?: SupportedLocale,
): string {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  // 顯示時、分時一律 24 小時制(zh-TW 預設為「下午02:05」);呼叫端明確指定 hour12/hourCycle 時尊重之
  const showsHour = options?.hour !== undefined || options?.timeStyle !== undefined
  const resolved = showsHour && options?.hour12 === undefined && options?.hourCycle === undefined
    ? { ...options, hour12: false }
    : options
  return new Intl.DateTimeFormat(localeOrCurrent(locale), resolved).format(date)
}

export function formatMarketName(market: MarketCode | 'all' | string): string {
  if (market === 'TW' || market === 'CN' || market === 'HK' || market === 'US' || market === 'all') {
    return i18n.t(`common:markets.${market}`)
  }
  return market
}
