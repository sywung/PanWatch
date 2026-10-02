import { describe, expect, it } from 'vitest'

import { settlementUrgency } from '@panwatch/biz-ui'

// Phase 2b B3:期货部位的结算提示(B4 会在结算前 3 个交易日推播转仓提醒)
describe('settlementUrgency', () => {
  it('flags expired, today and soon', () => {
    expect(settlementUrgency(-1)).toBe('expired')
    expect(settlementUrgency(0)).toBe('today')
    expect(settlementUrgency(1)).toBe('soon')
    expect(settlementUrgency(5)).toBe('soon')
    expect(settlementUrgency(6)).toBe('none')
  })

  it('handles missing values', () => {
    expect(settlementUrgency(null)).toBe('none')
    expect(settlementUrgency(undefined)).toBe('none')
  })
})
