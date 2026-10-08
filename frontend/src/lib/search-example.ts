// 搜尋框 placeholder 的範例代碼；「全部」以台股為主（本 fork 預設市場是 TW）
const SEARCH_EXAMPLES: Record<string, string> = {
  TW: '2330 or 台積電',
  TWF: 'TXF、台指期 或 2330',
  CN: '600519 or Kweichow Moutai',
  HK: '00700 or Tencent',
  US: 'AAPL or Apple',
}

const ALL_MARKETS_EXAMPLE = '2330 / TXF / AAPL'

export function searchExampleFor(market: string): string {
  return SEARCH_EXAMPLES[market] ?? ALL_MARKETS_EXAMPLE
}
