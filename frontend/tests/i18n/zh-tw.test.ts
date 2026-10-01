import fs from 'node:fs'
import path from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'

import i18n, {
  changeLocale,
  DEFAULT_LOCALE,
  detectInitialLocale,
  normalizeLocale,
  SUPPORTED_LOCALES,
} from '@/i18n'
import { formatMarketName } from '@/i18n/format'
import { resources } from '@/i18n/resources'

afterEach(async () => {
  await changeLocale(DEFAULT_LOCALE)
})

describe('Traditional Chinese locale', () => {
  it('is supported and is the default', () => {
    expect(SUPPORTED_LOCALES).toContain('zh-TW')
    expect(DEFAULT_LOCALE).toBe('zh-TW')
  })

  it('normalizes Chinese variants', () => {
    expect(normalizeLocale('zh-TW')).toBe('zh-TW')
    expect(normalizeLocale('zh-Hant')).toBe('zh-TW')
    expect(normalizeLocale('zh-Hant-TW')).toBe('zh-TW')
    expect(normalizeLocale('zh-HK')).toBe('zh-TW')
    expect(normalizeLocale('zh-CN')).toBe('zh-CN')
    expect(normalizeLocale('zh-Hans-CN')).toBe('zh-CN')
    expect(normalizeLocale('en-GB')).toBe('en-US')
    expect(normalizeLocale('ja-JP')).toBe('zh-TW')
    expect(normalizeLocale(null)).toBe('zh-TW')
  })

  it('starts new visitors in Traditional Chinese regardless of browser language', () => {
    expect(detectInitialLocale(null, [])).toBe('zh-TW')
    expect(detectInitialLocale(null, ['en-US'])).toBe('zh-TW')
    expect(detectInitialLocale(null, ['zh-CN'])).toBe('zh-TW')
  })

  it('keeps a saved preference', () => {
    expect(detectInitialLocale('zh-CN', ['zh-TW'])).toBe('zh-CN')
    expect(detectInitialLocale('en-US', [])).toBe('en-US')
    expect(detectInitialLocale('zh-TW', ['en-US'])).toBe('zh-TW')
  })
})

// 递归取出 key 路径与字符串值
function flatten(obj: unknown, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {}
  if (obj && typeof obj === 'object') {
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      const key = prefix ? `${prefix}.${k}` : k
      if (typeof v === 'string') out[key] = v
      else Object.assign(out, flatten(v, key))
    }
  }
  return out
}

describe('zh-TW resources', () => {
  const zhCN = flatten((resources as Record<string, unknown>)['zh-CN'])
  const zhTW = flatten((resources as Record<string, unknown>)['zh-TW'])

  it('has exactly the same keys as zh-CN', () => {
    expect(Object.keys(zhTW).sort()).toEqual(Object.keys(zhCN).sort())
  })

  it('keeps interpolation placeholders intact', () => {
    const ph = (s: string) => (s.match(/\{\{\s*[\w.]+\s*\}\}/g) || []).sort().join('|')
    const mismatched = Object.keys(zhCN).filter((k) => ph(zhCN[k]) !== ph(zhTW[k] ?? ''))
    expect(mismatched).toEqual([])
  })

  it('contains no Simplified-only characters', () => {
    // 常见简体专用字(繁体中不会出现)。注意:告/搜/航 等繁简共用字不能列入,否则会逼出错误的替换
    const simplified = /[们这个时为数据设认账户资产仓盘价涨买卖风险报关闭开启删编辑应该选择输载错误络务号码页览导显图让对还过从发现实际]/
    const offenders = Object.entries(zhTW)
      .filter(([, v]) => simplified.test(v))
      .map(([k, v]) => `${k}: ${v}`)
    expect(offenders).toEqual([])
  })

  it('uses Taiwan wording', () => {
    const all = Object.values(zhTW).join('\n')
    expect(all).not.toMatch(/臺股|新臺幣|賬戶/)
    expect(zhTW['common.markets.TW']).toBe('台股')
  })

  it('formats market names in zh-TW', async () => {
    await changeLocale('zh-TW')
    expect(formatMarketName('TW')).toBe('台股')
    expect(i18n.resolvedLanguage).toBe('zh-TW')
  })
})

describe('zh-TW web app manifest', () => {
  it('ships a zh-TW manifest', () => {
    const p = path.resolve(__dirname, '../../public/manifest.zh-TW.json')
    const m = JSON.parse(fs.readFileSync(p, 'utf8'))
    expect(m.lang).toBe('zh-TW')
  })

  it('sets the zh-TW manifest when the locale is zh-TW', async () => {
    document.head.innerHTML = '<link rel="manifest" href="/manifest.json">'
    await changeLocale('zh-TW')
    expect(document.querySelector('link[rel="manifest"]')?.getAttribute('href')).toBe('/manifest.zh-TW.json')
    expect(document.documentElement.lang).toBe('zh-TW')
  })
})
