import { describe, expect, it } from 'vitest'

import {
  canEvaluateAddPosition,
  formatCompactAmount,
  formatMarketCapLabel,
  formatSpotTime,
  futuresBasisLabel,
  futuresNewsTarget,
  futuresUnderlyingName,
} from '@panwatch/biz-ui'

// F6b:股票详情弹窗对期货(TWF)的处理,以及弹窗里写死的简体单位(万/亿/亿新台币)改为依语系显示。
// 浏览器验收(2026-10-01)看到:期货详情显示不相关的 A 股新闻、出现「加仓测算」、成交量显示「1.69万」。

describe('futures underlying for news', () => {
  it('derives the underlying stock name from the futures product name', () => {
    expect(futuresUnderlyingName('台積電期貨')).toBe('台積電')
    expect(futuresUnderlyingName('小型台積電期貨')).toBe('台積電')
    expect(futuresUnderlyingName('元大台灣50ETF期貨')).toBe('元大台灣50ETF')
    expect(futuresUnderlyingName('')).toBe('')
  })

  it('stock futures look up news by the underlying stock', () => {
    expect(futuresNewsTarget({ kind: 'stock', underlying_code: '2330', name: '小型台積電期貨' }))
      .toEqual({ symbol: '2330', name: '台積電', market: 'TW' })
  })

  it('news target carries the underlying market so the backend routes to TW news sources', () => {
    // 2026-10-02:不带市场时后端按 A 股查,详情页出现东财的大陆车市新闻
    expect(futuresNewsTarget({ kind: 'stock', underlying_code: '2330', name: '台積電期貨' })?.market).toBe('TW')
  })

  it('index futures and unknown info have no symbol news target (no unrelated fallback)', () => {
    expect(futuresNewsTarget({ kind: 'index', underlying_code: null, name: '台指期' })).toBeNull()
    expect(futuresNewsTarget(null)).toBeNull()
    expect(futuresNewsTarget(undefined)).toBeNull()
  })
})

describe('add-position calculator', () => {
  it('is not offered for futures (Phase 2a has no futures positions)', () => {
    expect(canEvaluateAddPosition('TWF')).toBe(false)
    expect(canEvaluateAddPosition('twf')).toBe(false)
    expect(canEvaluateAddPosition('TW')).toBe(true)
    expect(canEvaluateAddPosition('US')).toBe(true)
  })
})

describe('basis label', () => {
  it('names contango, backwardation and parity per locale', () => {
    expect(futuresBasisLabel(107.51, 'zh-TW')).toBe('正價差')
    expect(futuresBasisLabel(-3, 'zh-TW')).toBe('逆價差')
    expect(futuresBasisLabel(0, 'zh-TW')).toBe('平價')
    expect(futuresBasisLabel(5, 'zh-CN')).toBe('正价差')
    expect(futuresBasisLabel(-5, 'en-US')).toBe('Backwardation')
    expect(futuresBasisLabel(null, 'zh-TW')).toBe('')
  })
})

describe('compact amounts follow the locale (no hard-coded Simplified units)', () => {
  it('uses 萬/億 in zh-TW and 万/亿 in zh-CN', () => {
    expect(formatCompactAmount(16860, 'zh-TW')).toBe('1.69萬')
    expect(formatCompactAmount(123456789, 'zh-TW')).toBe('1.23億')
    expect(formatCompactAmount(16860, 'zh-CN')).toBe('1.69万')
    expect(formatCompactAmount(999, 'zh-TW')).toBe('999')
  })

  it('uses K/M/B in English', () => {
    expect(formatCompactAmount(16860, 'en-US')).toBe('16.86K')
    expect(formatCompactAmount(123456789, 'en-US')).toBe('123.46M')
    expect(formatCompactAmount(2500000000, 'en-US')).toBe('2.50B')
  })

  it('handles missing values', () => {
    expect(formatCompactAmount(null, 'zh-TW')).toBe('--')
    expect(formatCompactAmount(undefined, 'zh-TW')).toBe('--')
  })
})

describe('market cap label (input is in 億 units)', () => {
  it('uses Traditional units and currency names in zh-TW', () => {
    expect(formatMarketCapLabel(12.345, 'TW', 'zh-TW')).toBe('12.35億新台幣')
    expect(formatMarketCapLabel(3, 'US', 'zh-TW')).toBe('3.00億美元')
  })

  it('keeps Simplified in zh-CN', () => {
    expect(formatMarketCapLabel(12.345, 'TW', 'zh-CN')).toBe('12.35亿新台币')
    expect(formatMarketCapLabel(5, 'CN', 'zh-CN')).toBe('5.00亿元（人民币）')
  })
})

describe('futures spot time', () => {
  // 2026-10-02:后端 spot_time 是 "13:30:00" 纯时间字串,new Date() 解析失败,卡片上时间一直空白
  it('shows HH:MM for a bare time string from the backend', () => {
    expect(formatSpotTime('13:30:00')).toBe('13:30')
    expect(formatSpotTime('09:05:07')).toBe('09:05')
  })

  it('returns empty for missing or unparseable values', () => {
    expect(formatSpotTime(null)).toBe('')
    expect(formatSpotTime(undefined)).toBe('')
    expect(formatSpotTime('')).toBe('')
    expect(formatSpotTime('abc')).toBe('')
  })
})
