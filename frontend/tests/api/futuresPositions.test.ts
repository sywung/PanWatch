import { afterEach, describe, expect, it, vi } from 'vitest'

import { futuresPositionsApi } from '@panwatch/api/futures-positions'

// Phase 2b B3:期货持仓 API client(后端 /api/futures-positions,B2)
const ok = (data: unknown) => new Response(
  JSON.stringify({ code: 0, success: true, data, message: '' }),
  { status: 200, headers: { 'Content-Type': 'application/json' } },
)

describe('futuresPositionsApi', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('lists positions, optionally by account', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ok([]))
    await futuresPositionsApi.list()
    await futuresPositionsApi.list(3)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/futures-positions')
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/futures-positions?account_id=3')
  })

  it('creates with POST and the full payload', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ok({ id: 1 }))
    const payload = {
      account_id: 1, product_code: 'CDF', contract_month: '202610', direction: 'long' as const,
      lots: 2, entry_price: 2500, multiplier: 2000, note: null,
    }
    await futuresPositionsApi.create(payload)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/futures-positions')
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('POST')
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual(payload)
  })

  it('updates with PUT and deletes with DELETE by id', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ok({ success: true }))
    await futuresPositionsApi.update(5, { lots: 3 })
    await futuresPositionsApi.remove(5)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/futures-positions/5')
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('PUT')
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ lots: 3 })
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/futures-positions/5')
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe('DELETE')
  })

  it('loads form options for a product', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ok({ months: [] }))
    await futuresPositionsApi.options('CDF')
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/futures-positions/options?product_code=CDF')
  })
})
