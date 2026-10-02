import { BASE_CURRENCY, marketCurrency } from '@panwatch/biz-ui'

export interface PortfolioPosition {
  id: number
  stock_id: number
  sort_order?: number
  symbol: string
  name: string
  market: string
  cost_price: number
  quantity: number
  invested_amount: number | null
  trading_style: string
  current_price: number | null
  current_price_cny: number | null
  change_pct: number | null
  market_value: number | null
  market_value_cny: number | null
  pnl: number | null
  pnl_pct: number | null
  daily_pnl: number | null
  daily_pnl_pct: number | null
  exchange_rate: number | null
}

export interface AccountSummary {
  id: number
  name: string
  available_funds: number
  total_market_value: number
  total_cost: number
  total_pnl: number
  total_pnl_pct: number
  total_daily_pnl: number
  total_assets: number
  futures_unrealized_pnl?: number
  futures_margin_used?: number
  futures_margin_call?: boolean
  positions: PortfolioPosition[]
}

export interface PortfolioSummary {
  accounts: AccountSummary[]
  total: {
    total_market_value: number
    total_cost: number
    total_pnl: number
    total_pnl_pct: number
    total_daily_pnl: number
    available_funds: number
    total_assets: number
    futures_unrealized_pnl?: number
    futures_margin_used?: number
  }
  exchange_rates?: {
    USD_TWD?: number | null
    HKD_TWD?: number | null
    CNY_TWD?: number | null
  }
  quotes?: Record<string, { current_price: number | null; change_pct: number | null }>
}

export const round2 = (value: number) => Math.round(value * 100) / 100

export const mergePortfolioQuotes = (
  portfolio: PortfolioSummary | null,
  quotes: Record<string, { current_price: number | null; change_pct: number | null }>,
): PortfolioSummary | null => {
  if (!portfolio) return null

  const rates = portfolio.exchange_rates
  let grandMarketValue = 0
  let grandCost = 0
  let grandAvailable = 0
  let grandDailyPnl = 0
  let grandFuturesPnl = 0
  let grandFuturesMargin = 0

  const accounts = portfolio.accounts.map(account => {
    let accMarketValue = 0
    let accCost = 0
    let accDailyPnl = 0

    const positions = account.positions.map(pos => {
      const quote = quotes[`${pos.market}:${pos.symbol}`]
      const current_price = quote?.current_price ?? pos.current_price ?? null
      const change_pct = quote?.change_pct ?? pos.change_pct ?? null
      const currency = marketCurrency(pos.market)
      const rate = currency === BASE_CURRENCY ? 1 : rates?.[`${currency}_${BASE_CURRENCY}` as 'USD_TWD' | 'HKD_TWD' | 'CNY_TWD'] ?? null

      const cost = rate == null ? 0 : pos.cost_price * pos.quantity * rate
      accCost += cost

      let market_value: number | null = null
      let market_value_cny: number | null = null
      let pnl: number | null = null
      let pnl_pct: number | null = null
      let daily_pnl: number | null = null
      let daily_pnl_pct: number | null = null

      if (current_price != null && rate != null) {
        market_value = current_price * pos.quantity
        market_value_cny = market_value * rate
        accMarketValue += market_value_cny
        pnl = market_value_cny - cost
        pnl_pct = cost > 0 ? pnl / cost * 100 : 0
      }

      if (current_price != null && rate != null && change_pct != null && change_pct !== -100) {
        const prev = current_price / (1 + change_pct / 100)
        if (Number.isFinite(prev) && prev > 0) {
          daily_pnl = round2((current_price - prev) * pos.quantity * rate)
          daily_pnl_pct = round2(change_pct)
          accDailyPnl += daily_pnl
        }
      }

      return {
        ...pos,
        current_price,
        current_price_cny: current_price != null && rate != null ? current_price * rate : null,
        change_pct,
        market_value,
        market_value_cny,
        pnl,
        pnl_pct,
        daily_pnl,
        daily_pnl_pct,
        exchange_rate: currency === BASE_CURRENCY ? null : rate,
      }
    })

    const accPnl = accMarketValue - accCost
    const accPnlPct = accCost > 0 ? accPnl / accCost * 100 : 0
    const futuresPnl = account.futures_unrealized_pnl ?? 0
    const futuresMargin = account.futures_margin_used ?? 0
    const accTotalAssets = accMarketValue + account.available_funds + futuresPnl

    grandMarketValue += accMarketValue
    grandCost += accCost
    grandAvailable += account.available_funds
    grandDailyPnl += accDailyPnl
    grandFuturesPnl += futuresPnl
    grandFuturesMargin += futuresMargin

    return {
      ...account,
      total_market_value: round2(accMarketValue),
      total_cost: round2(accCost),
      total_pnl: round2(accPnl),
      total_pnl_pct: round2(accPnlPct),
      total_daily_pnl: round2(accDailyPnl),
      total_assets: round2(accTotalAssets),
      positions,
    }
  })

  const grandPnl = grandMarketValue - grandCost
  const grandPnlPct = grandCost > 0 ? grandPnl / grandCost * 100 : 0

  return {
    ...portfolio,
    accounts,
    total: {
      total_market_value: round2(grandMarketValue),
      total_cost: round2(grandCost),
      total_pnl: round2(grandPnl),
      total_pnl_pct: round2(grandPnlPct),
      total_daily_pnl: round2(grandDailyPnl),
      available_funds: round2(grandAvailable),
      total_assets: round2(grandMarketValue + grandAvailable + grandFuturesPnl),
      futures_unrealized_pnl: round2(grandFuturesPnl),
      futures_margin_used: round2(grandFuturesMargin),
    },
  }
}
