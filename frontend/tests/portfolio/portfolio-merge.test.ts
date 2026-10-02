import { describe, expect, it } from 'vitest'

import { mergePortfolioQuotes } from '@/lib/portfolio-merge'

// Phase 2b B3:持仓页会用即时报价重算账户汇总(原本写在 Stocks.tsx 里)。
// B2 起后端 total_assets 已含期货未实现损益,前端重算时不能把它丢掉。
const portfolio = {
  accounts: [
    {
      id: 1, name: '主帳戶', available_funds: 1_000_000,
      total_market_value: 0, total_cost: 0, total_pnl: 0, total_pnl_pct: 0,
      total_daily_pnl: 0, total_assets: 0,
      futures_unrealized_pnl: 80_000, futures_margin_used: 680_400, futures_margin_call: false,
      positions: [
        { id: 11, stock_id: 1, symbol: '2330', name: '台積電', market: 'TW', cost_price: 900, quantity: 1000,
          current_price: 990, change_pct: 0 },
      ],
    },
    {
      id: 2, name: '舊帳戶', available_funds: 500,
      total_market_value: 0, total_cost: 0, total_pnl: 0, total_pnl_pct: 0,
      total_daily_pnl: 0, total_assets: 0,
      positions: [],
    },
  ],
  total: {
    total_market_value: 0, total_cost: 0, total_pnl: 0, total_pnl_pct: 0, total_daily_pnl: 0,
    available_funds: 0, total_assets: 0, futures_unrealized_pnl: 80_000, futures_margin_used: 680_400,
  },
  exchange_rates: {},
}

describe('mergePortfolioQuotes', () => {
  it('returns null for null portfolio', () => {
    expect(mergePortfolioQuotes(null, {})).toBeNull()
  })

  it('recomputes stock figures from live quotes', () => {
    const out = mergePortfolioQuotes(portfolio as never, { 'TW:2330': { current_price: 1000, change_pct: 1 } })!
    const acc = out.accounts[0]
    expect(acc.total_market_value).toBe(1_000_000)
    expect(acc.total_cost).toBe(900_000)
    expect(acc.total_pnl).toBe(100_000)
  })

  it('keeps futures unrealized pnl in total assets', () => {
    const out = mergePortfolioQuotes(portfolio as never, { 'TW:2330': { current_price: 1000, change_pct: 1 } })!
    expect(out.accounts[0].total_assets).toBe(1_000_000 + 1_000_000 + 80_000)
    expect(out.accounts[0].futures_unrealized_pnl).toBe(80_000)
    expect(out.accounts[0].futures_margin_used).toBe(680_400)
  })

  it('treats missing futures fields as zero (older backend)', () => {
    const out = mergePortfolioQuotes(portfolio as never, {})!
    expect(out.accounts[1].total_assets).toBe(500)
  })

  it('grand total includes futures pnl but stock pnl stays stock-only', () => {
    const out = mergePortfolioQuotes(portfolio as never, { 'TW:2330': { current_price: 1000, change_pct: 1 } })!
    expect(out.total.total_pnl).toBe(100_000)
    expect(out.total.total_assets).toBe(1_000_000 + 1_000_500 + 80_000)
    expect(out.total.futures_unrealized_pnl).toBe(80_000)
  })
})
