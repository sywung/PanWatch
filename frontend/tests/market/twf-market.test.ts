import { afterEach, describe, expect, it } from 'vitest'

import i18n, { changeLocale } from '@/i18n'
import {
  FUTURES_MARKET,
  MARKET_CODES,
  futuresContractMonth,
  getMarketBadge,
  isFuturesMarket,
  marketCurrency,
  marketLotSize,
} from '@panwatch/biz-ui'

// F5b:台湾期货(TWF)在前端的市场常量、徽章与合约月份。
// MARKET_CODES 代表「股票市场」(模拟盘、机会发现等股票专属功能在用),期货不放进去。

afterEach(async () => {
  await changeLocale('zh-CN')
})

const t = (code: string) => `label:${code}`

describe('TWF market constants', () => {
  it('keeps futures out of the stock market list', () => {
    expect(FUTURES_MARKET).toBe('TWF')
    expect(MARKET_CODES).toEqual(['TW', 'CN', 'HK', 'US'])
  })

  it('recognises futures market case-insensitively', () => {
    expect(isFuturesMarket('TWF')).toBe(true)
    expect(isFuturesMarket('twf')).toBe(true)
    expect(isFuturesMarket('TW')).toBe(false)
    expect(isFuturesMarket(undefined)).toBe(false)
  })

  it('prices in TWD and has no board lot', () => {
    expect(marketCurrency('TWF')).toBe('TWD')
    expect(marketLotSize('TWF')).toBeNull()
  })

  it('shows a futures badge (unlike TW stocks, which are unlabelled)', () => {
    const badge = getMarketBadge('TWF', t)
    expect(badge).not.toBeNull()
    expect(badge?.label).toBe('label:TWF')
    expect(badge?.style).not.toBe(getMarketBadge('XX', t)?.style)   // 不能落到未知市场的灰色
    expect(getMarketBadge('TW', t)).toBeNull()
  })
})

describe('futuresContractMonth', () => {
  it('decodes the month letter of a contract code', () => {
    expect(futuresContractMonth('TXFJ6')).toBe(10)
    expect(futuresContractMonth('RLFL6')).toBe(12)   // 近月没挂牌时改用的远月
    expect(futuresContractMonth('CDFA7')).toBe(1)
  })

  it('returns null for anything that is not a contract code', () => {
    expect(futuresContractMonth('TXF')).toBeNull()
    expect(futuresContractMonth('TXFM6')).toBeNull()
    expect(futuresContractMonth('')).toBeNull()
    expect(futuresContractMonth(undefined)).toBeNull()
    expect(futuresContractMonth(null)).toBeNull()
  })
})

describe('TWF labels', () => {
  it('has Taiwan Traditional labels', async () => {
    await changeLocale('zh-TW')
    expect(i18n.t('configuration:stocksPage.markets.twf')).toBe('期貨')
    expect(i18n.t('bizUi:markets.TWF')).toBe('期貨')
    expect(i18n.t('configuration:stocksPage.futures.night')).toBe('夜盤')
    expect(i18n.t('configuration:stocksPage.futures.untraded')).toBe('未成交')
    expect(i18n.t('configuration:stocksPage.futures.contractMonth', { month: 12 })).toBe('12 月')
    expect(i18n.t('configuration:stocksPage.messages.futuresPositionUnsupported')).toContain('期貨')
  })

  it('has English labels', async () => {
    await changeLocale('en-US')
    expect(i18n.t('configuration:stocksPage.markets.twf')).toBe('Futures')
    expect(i18n.t('configuration:stocksPage.futures.night')).toBe('Night')
  })
})
