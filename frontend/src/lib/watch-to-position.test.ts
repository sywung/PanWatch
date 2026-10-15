import { describe, expect, it } from 'vitest'
import { isHeldAnywhere, planWatchToPosition } from './watch-to-position'

const tsmc = { id: 7, market: 'TW' }
const acct = (id: number, held: number[] = []) => ({
  id,
  positions: held.map((stock_id, i) => ({ id: id * 100 + i, stock_id })),
})

describe('planWatchToPosition', () => {
  it('台指期等期貨（TWF）不走股票持倉對話框', () => {
    expect(planWatchToPosition({ id: 7, market: 'TWF' }, [acct(1)])).toEqual({ kind: 'unsupported' })
    expect(planWatchToPosition({ id: 7, market: 'twf' }, [acct(1)])).toEqual({ kind: 'unsupported' })
  })

  it('沒有任何帳戶 → no-account（且優先於其他判斷以外的所有情況，只輸給 unsupported）', () => {
    expect(planWatchToPosition(tsmc, [])).toEqual({ kind: 'no-account' })
    expect(planWatchToPosition({ id: 7, market: 'TWF' }, [])).toEqual({ kind: 'unsupported' })
  })

  it('單一帳戶、尚未持有 → add 到該帳戶', () => {
    expect(planWatchToPosition(tsmc, [acct(1, [3, 4])])).toEqual({ kind: 'add', accountId: 1 })
  })

  it('單一帳戶、已持有 → edit 現有持倉，不重複建倉', () => {
    expect(planWatchToPosition(tsmc, [acct(1, [3, 7])])).toEqual({ kind: 'edit', accountId: 1, positionId: 101 })
  })

  it('多帳戶：預設選「第一個還沒持有這檔」的帳戶', () => {
    const accounts = [acct(1, [7]), acct(2, []), acct(3, [])]
    expect(planWatchToPosition(tsmc, accounts)).toEqual({ kind: 'add', accountId: 2 })
  })

  it('多帳戶都已持有 → edit 第一個帳戶的那筆', () => {
    const accounts = [acct(1, [9, 7]), acct(2, [7])]
    expect(planWatchToPosition(tsmc, accounts)).toEqual({ kind: 'edit', accountId: 1, positionId: 101 })
  })

  it('以 stock_id 比對，不是用代號；別檔同代號不同市場不算持有', () => {
    expect(planWatchToPosition({ id: 8, market: 'US' }, [acct(1, [7])])).toEqual({ kind: 'add', accountId: 1 })
  })

  it('positions 缺值（undefined）視為空，不丟例外', () => {
    expect(planWatchToPosition(tsmc, [{ id: 5 } as never])).toEqual({ kind: 'add', accountId: 5 })
  })

  it('不修改傳入的帳戶陣列', () => {
    const accounts = [acct(1, [7]), acct(2, [])]
    const snapshot = JSON.stringify(accounts)
    planWatchToPosition(tsmc, accounts)
    expect(JSON.stringify(accounts)).toBe(snapshot)
  })
})

describe('isHeldAnywhere', () => {
  it('任一帳戶有就是 true', () => {
    expect(isHeldAnywhere(7, [acct(1, []), acct(2, [7])])).toBe(true)
    expect(isHeldAnywhere(7, [acct(1, [3])])).toBe(false)
    expect(isHeldAnywhere(7, [])).toBe(false)
    expect(isHeldAnywhere(7, [{ id: 1 } as never])).toBe(false)
  })
})
