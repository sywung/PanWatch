import { describe, expect, it, vi } from 'vitest'

import { refreshAddedWatchlistItem } from '@/lib/portfolio-page-data'

describe('refreshAddedWatchlistItem', () => {
  it('重載清單，並以伺服器回傳的代碼與市場立刻抓報價', async () => {
    const reloadStocks = vi.fn(async () => undefined)
    const loadQuotes = vi.fn(async () => [{ symbol: 'TXFK6', market: 'TWF', current_price: 23000 }])

    const quotes = await refreshAddedWatchlistItem({ symbol: 'TXFK6', market: 'TWF' }, { reloadStocks, loadQuotes })

    expect(reloadStocks).toHaveBeenCalledTimes(1)
    expect(loadQuotes).toHaveBeenCalledWith([{ symbol: 'TXFK6', market: 'TWF' }])
    expect(quotes).toEqual([{ symbol: 'TXFK6', market: 'TWF', current_price: 23000 }])
  })
})
