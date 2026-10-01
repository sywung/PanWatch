import fs from 'node:fs'
import path from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'

import i18n, { changeLocale } from '@/i18n'
import { formatMarketCurrency, formatMarketName } from '@/i18n/format'
import {
  BASE_CURRENCY,
  DEFAULT_MARKET,
  MARKET_CODES,
  getMarketBadge,
  marketCurrency,
  marketLotSize,
} from '@panwatch/biz-ui'

afterEach(async () => {
  await changeLocale('zh-CN')
})

const t = (code: string) => `label:${code}`

describe('market constants', () => {
  it('defaults to Taiwan and TWD', () => {
    expect(DEFAULT_MARKET).toBe('TW')
    expect(BASE_CURRENCY).toBe('TWD')
    expect(MARKET_CODES).toEqual(['TW', 'CN', 'HK', 'US'])
  })

  it('maps markets to currencies', () => {
    expect(marketCurrency('TW')).toBe('TWD')
    expect(marketCurrency('CN')).toBe('CNY')
    expect(marketCurrency('HK')).toBe('HKD')
    expect(marketCurrency('US')).toBe('USD')
    expect(marketCurrency('tw')).toBe('TWD')
    expect(marketCurrency('XX')).toBe('TWD')
    expect(marketCurrency(undefined)).toBe('TWD')
  })

  it('knows board-lot sizes', () => {
    expect(marketLotSize('TW')).toBe(1000) // 1 张
    expect(marketLotSize('CN')).toBe(100) // 1 手
    expect(marketLotSize('HK')).toBeNull()
    expect(marketLotSize('US')).toBeNull()
  })
})

describe('market badge', () => {
  it('does not label the default market', () => {
    expect(getMarketBadge('TW', t)).toBeNull()
    expect(getMarketBadge('tw', t)).toBeNull()
  })

  it('labels every non-default market explicitly', () => {
    expect(getMarketBadge('CN', t)?.label).toBe('label:CN')
    expect(getMarketBadge('HK', t)?.label).toBe('label:HK')
    expect(getMarketBadge('US', t)?.label).toBe('label:US')
  })

  it('gives each labelled market a distinct style', () => {
    const styles = ['CN', 'HK', 'US'].map((m) => getMarketBadge(m, t)?.style)
    expect(new Set(styles).size).toBe(3)
  })

  it('shows the raw code for unknown markets instead of pretending they are A-shares', () => {
    const badge = getMarketBadge('JP', t)
    expect(badge?.label).toBe('JP')
    expect(badge?.style).not.toBe(getMarketBadge('CN', t)?.style)
  })
})

describe('Taiwan formatting and labels', () => {
  it('formats TW amounts as New Taiwan dollars', async () => {
    await changeLocale('zh-CN')
    expect(formatMarketCurrency(1234, 'TW')).toMatch(/NT\$|新台币|TWD/)
    await changeLocale('en-US')
    expect(formatMarketCurrency(1234, 'TW')).toContain('NT$')
  })

  it('has a TW market name in both locales', async () => {
    await changeLocale('zh-CN')
    expect(formatMarketName('TW')).toBe('台股')
    await changeLocale('en-US')
    expect(formatMarketName('TW')).toBe('Taiwan')
    expect(i18n.exists('common:markets.TW')).toBe(true)
  })
})

// ---------------------------------------------------------------- 源码扫描

const frontendRoot = path.resolve(__dirname, '../..')
const scanRoots = ['src', 'packages/api/src', 'packages/biz-ui/src', 'packages/base-ui/src']

function sourceFiles(): string[] {
  const out: string[] = []
  const walk = (dir: string) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name)
      if (e.isDirectory()) walk(p)
      else if (/\.(ts|tsx)$/.test(e.name) && !p.includes(`${path.sep}i18n${path.sep}locales${path.sep}`)) out.push(p)
    }
  }
  scanRoots.forEach((r) => walk(path.join(frontendRoot, r)))
  return out
}

function hits(patterns: RegExp[]): string[] {
  const out: string[] = []
  for (const f of sourceFiles()) {
    fs.readFileSync(f, 'utf8').split('\n').forEach((line, i) => {
      const trimmed = line.trim()
      if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) return
      if (patterns.some((p) => p.test(line))) out.push(`${path.relative(frontendRoot, f)}:${i + 1}: ${trimmed}`)
    })
  }
  return out
}

const CN_DEFAULTS = [
  /(\|\||\?\?)\s*['"]CN['"]/, // x || 'CN'
  /market:\s*['"]CN['"]/, // { market: 'CN' } 初始值
  /stock_market:\s*['"]CN['"]/,
  /useState(<[^>]*>)?\(\s*['"]CN['"]\s*\)/, // useState('CN')
  /useLocalStorage(<[^>]*>)?\([^)]*,\s*['"]CN['"]\s*\)/, // useLocalStorage('key', 'CN')
]
const FX_LEGACY = [/HKD_CNY|USD_CNY/, /\?\?\s*(0\.92|7\.25)\b/, /[`'"]\$?\{?sign\}?¥/]
const THREE_MARKET_UNION = [/['"]CN['"]\s*\|\s*['"]HK['"]\s*\|\s*['"]US['"]/]

describe('no hard-coded A-share defaults', () => {
  it('scan patterns catch known violations (negative control)', () => {
    expect(CN_DEFAULTS.some((p) => p.test("const m = market || 'CN'"))).toBe(true)
    expect(CN_DEFAULTS.some((p) => p.test("const m = market ?? 'CN'"))).toBe(true)
    expect(CN_DEFAULTS.some((p) => p.test("{ symbol: '', name: '', market: 'CN' }"))).toBe(true)
    expect(CN_DEFAULTS.some((p) => p.test("useState<string>('CN')"))).toBe(true)
    expect(CN_DEFAULTS.some((p) => p.test("useLocalStorage<'CN' | 'HK'>('panwatch_x', 'CN')"))).toBe(true)
    expect(FX_LEGACY.some((p) => p.test('portfolio.exchange_rates?.HKD_CNY ?? 0.92'))).toBe(true)
    expect(FX_LEGACY.some((p) => p.test('return `${sign}¥${formatNumber(v)}`'))).toBe(true)
    expect(THREE_MARKET_UNION.some((p) => p.test("market: 'CN' | 'HK' | 'US'"))).toBe(true)
    expect(CN_DEFAULTS.some((p) => p.test("if (market === 'CN') {"))).toBe(false)
    expect(CN_DEFAULTS.some((p) => p.test('market: DEFAULT_MARKET'))).toBe(false)
  })

  it('has no CN default/fallback literals', () => {
    expect(hits(CN_DEFAULTS)).toEqual([])
  })

  it('has no legacy CNY exchange-rate keys, hard-coded rates or ¥ amount formatting', () => {
    expect(hits(FX_LEGACY)).toEqual([])
  })

  it('has no three-market type unions that exclude TW', () => {
    expect(hits(THREE_MARKET_UNION)).toEqual([])
  })
})
