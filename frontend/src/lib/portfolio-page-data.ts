export interface PortfolioPageCoreLoaderApi<StockData, PortfolioData> {
  loadStocks: (signal: AbortSignal) => Promise<StockData>
  loadPortfolio: (signal: AbortSignal) => Promise<PortfolioData>
}

export interface PortfolioPageBackgroundLoaderApi<StockData, PortfolioData, MarketStatusData, SuggestionData, AlertData, KlineData> {
  loadMarketStatus: (signal: AbortSignal) => Promise<MarketStatusData>
  buildQuoteItems: (stocks: StockData, portfolio: PortfolioData) => Array<{ symbol: string; market: string }>
  loadSuggestions: (items: Array<{ symbol: string; market: string }>, signal: AbortSignal) => Promise<SuggestionData>
  loadPriceAlerts: (items: Array<{ symbol: string; market: string }>, signal: AbortSignal) => Promise<AlertData>
  loadKlines: (items: Array<{ symbol: string; market: string }>, signal: AbortSignal) => Promise<KlineData>
}

export interface PortfolioPageBackgroundData<MarketStatusData, SuggestionData, AlertData, KlineData> {
  marketStatus: MarketStatusData
  suggestions: SuggestionData
  priceAlerts: AlertData
  klines: KlineData
}

export interface PortfolioPageQuoteLoaderApi<StockData, PortfolioData, QuoteData> {
  buildQuoteItems: (stocks: StockData, portfolio: PortfolioData) => Array<{ symbol: string; market: string }>
  loadQuotes: (items: Array<{ symbol: string; market: string }>, signal: AbortSignal) => Promise<QuoteData>
}

export function buildPortfolioStockKeys(items: Array<{ symbol: string; market: string }>): string {
  return items.map(item => `${item.market}:${item.symbol}`).join(',')
}

export async function loadPortfolioPageCoreData<StockData, PortfolioData>(
  api: PortfolioPageCoreLoaderApi<StockData, PortfolioData>,
  signal: AbortSignal,
): Promise<{ stocks: StockData; portfolio: PortfolioData }> {
  const [stocks, portfolio] = await Promise.all([
    api.loadStocks(signal),
    api.loadPortfolio(signal),
  ])

  return { stocks, portfolio }
}

export async function loadPortfolioPageQuoteData<StockData, PortfolioData, QuoteData>(
  api: PortfolioPageQuoteLoaderApi<StockData, PortfolioData, QuoteData>,
  stocks: StockData,
  portfolio: PortfolioData,
  signal: AbortSignal,
): Promise<{ quotes: QuoteData }> {
  const items = api.buildQuoteItems(stocks, portfolio)
  return { quotes: await api.loadQuotes(items, signal) }
}

export async function loadPortfolioPageBackgroundData<
  StockData,
  PortfolioData,
  MarketStatusData,
  SuggestionData,
  AlertData,
  KlineData,
>(
  api: PortfolioPageBackgroundLoaderApi<StockData, PortfolioData, MarketStatusData, SuggestionData, AlertData, KlineData>,
  stocks: StockData,
  portfolio: PortfolioData,
  signal: AbortSignal,
): Promise<PortfolioPageBackgroundData<MarketStatusData, SuggestionData, AlertData, KlineData>> {
  const items = api.buildQuoteItems(stocks, portfolio)
  const [marketStatus, suggestions, priceAlerts, klines] = await Promise.all([
    api.loadMarketStatus(signal),
    api.loadSuggestions(items, signal),
    api.loadPriceAlerts(items, signal),
    api.loadKlines(items, signal),
  ])

  return { marketStatus, suggestions, priceAlerts, klines }
}

export interface AddedWatchlistItemApi<QuoteData> {
  reloadStocks: () => Promise<unknown> | unknown
  loadQuotes: (items: Array<{ symbol: string; market: string }>) => Promise<QuoteData>
}

// 新增自選後立刻補抓這一檔的報價；只重載清單的話，要等下一輪自動刷新才會有價格（畫面先顯示 --）
export async function refreshAddedWatchlistItem<QuoteData>(
  created: { symbol: string; market: string },
  api: AddedWatchlistItemApi<QuoteData>,
): Promise<QuoteData> {
  const [, quotes] = await Promise.all([
    api.reloadStocks(),
    api.loadQuotes([{ symbol: created.symbol, market: created.market }]),
  ])
  return quotes
}
