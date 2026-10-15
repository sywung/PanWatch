export type WatchToPositionAccount = {
  id: number
  positions?: Array<{ id: number; stock_id: number }>
}

export type WatchToPositionPlan =
  | { kind: 'unsupported' }
  | { kind: 'no-account' }
  | { kind: 'add'; accountId: number }
  | { kind: 'edit'; accountId: number; positionId: number }

export function planWatchToPosition(
  stock: { id: number; market: string },
  accounts: WatchToPositionAccount[],
): WatchToPositionPlan {
  if (stock.market.toUpperCase() === 'TWF') return { kind: 'unsupported' }
  if (accounts.length === 0) return { kind: 'no-account' }

  const firstAccountWithoutStock = accounts.find(
    account => !(account.positions ?? []).some(position => position.stock_id === stock.id),
  )
  if (firstAccountWithoutStock) return { kind: 'add', accountId: firstAccountWithoutStock.id }

  const firstHeldAccount = accounts.find(account =>
    (account.positions ?? []).some(position => position.stock_id === stock.id),
  )!
  const position = firstHeldAccount.positions!.find(item => item.stock_id === stock.id)!
  return { kind: 'edit', accountId: firstHeldAccount.id, positionId: position.id }
}

export function isHeldAnywhere(stockId: number, accounts: WatchToPositionAccount[]): boolean {
  return accounts.some(account =>
    (account.positions ?? []).some(position => position.stock_id === stockId),
  )
}
