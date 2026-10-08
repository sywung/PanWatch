import { describe, expect, it } from 'vitest'
import { searchExampleFor } from './search-example'

describe('searchExampleFor', () => {
  it('「全部」與台股不再以 A 股為例', () => {
    expect(searchExampleFor('')).not.toContain('600519')
    expect(searchExampleFor('')).toContain('2330')
    expect(searchExampleFor('TW')).toContain('2330')
  })

  it('各市場用自己的範例', () => {
    expect(searchExampleFor('TWF')).toContain('TXF')
    expect(searchExampleFor('CN')).toContain('600519')
    expect(searchExampleFor('HK')).toContain('00700')
    expect(searchExampleFor('US')).toContain('AAPL')
  })
})
