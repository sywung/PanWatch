import { describe, expect, it } from 'vitest'
import { loggerOptions, mapLoggerName } from './logger-map'

describe('logger-map language selection', () => {
  it('shows Taiwan Traditional names for zh-TW', () => {
    expect(mapLoggerName('src.agents.intraday_monitor', 'zh-TW')).toBe('盤中監測')
    expect(mapLoggerName('src.agents.intraday_monitor.run', 'zh-TW')).toBe('盤中監測')
  })

  it('keeps Simplified names for zh-CN and English for en-US', () => {
    expect(mapLoggerName('src.agents.intraday_monitor', 'zh-CN')).toBe('盘中监测')
    expect(mapLoggerName('src.agents.intraday_monitor', 'en-US')).not.toMatch(/[一-鿿]/)
  })

  it('defaults to zh-TW and offers the same modules in every Chinese locale', () => {
    expect(mapLoggerName('src.agents.intraday_monitor')).toBe('盤中監測')
    const tw = loggerOptions('zh-TW').map((o) => o.key)
    expect(tw).toEqual(loggerOptions('zh-CN').map((o) => o.key))
    expect(loggerOptions('zh-TW').map((o) => o.label).join('')).not.toContain('监')
  })
})
