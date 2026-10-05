import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchAPI } from '@panwatch/api'
import { useKlineDrawings } from '@panwatch/biz-ui/components/use-kline-drawings'

vi.mock('@panwatch/api', () => ({ fetchAPI: vi.fn() }))

const existing = { id: 11, symbol: '2330', market: 'TW', kind: 'hline', data: { price: 900 } } as const
const created = { id: 12, symbol: '2330', market: 'TW', kind: 'hline', data: { price: 950 } } as const

describe('useKlineDrawings', () => {
  beforeEach(() => vi.mocked(fetchAPI).mockReset())

  it('loads drawings for the requested product', async () => {
    vi.mocked(fetchAPI).mockResolvedValueOnce([existing] as never)
    const { result } = renderHook(() => useKlineDrawings('2330', 'TW'))
    await waitFor(() => expect(result.current.drawings).toEqual([existing]))
    expect(fetchAPI).toHaveBeenCalledWith('/chart-drawings?symbol=2330&market=TW')
  })

  it('optimistically creates and replaces a drawing with the server row', async () => {
    vi.mocked(fetchAPI)
      .mockResolvedValueOnce([] as never)
      .mockResolvedValueOnce(created as never)
    const { result } = renderHook(() => useKlineDrawings('2330', 'TW'))
    await waitFor(() => expect(fetchAPI).toHaveBeenCalledTimes(1))
    let response
    await act(async () => {
      response = await result.current.addDrawing({ kind: 'hline', data: { price: 950 } })
    })
    expect(response).toEqual(created)
    expect(result.current.drawings).toEqual([created])
    expect(fetchAPI).toHaveBeenLastCalledWith('/chart-drawings', {
      method: 'POST',
      body: JSON.stringify({ symbol: '2330', market: 'TW', kind: 'hline', data: { price: 950 } }),
    })
  })

  it('rolls back an optimistic create when the API request fails', async () => {
    vi.mocked(fetchAPI)
      .mockResolvedValueOnce([existing] as never)
      .mockRejectedValueOnce(new Error('write failed'))
    const { result } = renderHook(() => useKlineDrawings('2330', 'TW'))
    await waitFor(() => expect(result.current.drawings).toEqual([existing]))
    await act(async () => {
      expect(await result.current.addDrawing({ kind: 'hline', data: { price: 950 } })).toBeNull()
    })
    expect(result.current.drawings).toEqual([existing])
    expect(result.current.error).toBe('write failed')
  })

  it('does not delete a drawing whose create request is still pending', async () => {
    let resolveCreate!: (value: unknown) => void
    vi.mocked(fetchAPI)
      .mockResolvedValueOnce([] as never)
      .mockReturnValueOnce(new Promise(resolve => { resolveCreate = resolve }) as never)
    const { result } = renderHook(() => useKlineDrawings('2330', 'TW'))
    await waitFor(() => expect(fetchAPI).toHaveBeenCalledTimes(1))
    let pending!: Promise<unknown>
    act(() => { pending = result.current.addDrawing({ kind: 'hline', data: { price: 950 } }) })
    const temporaryId = result.current.drawings[0].id
    expect(temporaryId).toBeLessThan(0)
    await act(async () => {
      expect(await result.current.deleteDrawing(temporaryId)).toBe(false)
    })
    expect(vi.mocked(fetchAPI).mock.calls.some(([path]) => String(path).startsWith('/chart-drawings/'))).toBe(false)
    await act(async () => { resolveCreate(created); await pending })
    expect(result.current.drawings).toEqual([created])
  })

  it('discards an older product load after switching symbols', async () => {
    let resolveOld!: (value: unknown) => void
    const oldRequest = new Promise(resolve => { resolveOld = resolve })
    vi.mocked(fetchAPI)
      .mockReturnValueOnce(oldRequest as never)
      .mockResolvedValueOnce([{ ...existing, symbol: '2317', id: 22 }] as never)
    const { result, rerender } = renderHook(
      ({ symbol }: { symbol: string }) => useKlineDrawings(symbol, 'TW'),
      { initialProps: { symbol: '2330' } },
    )
    rerender({ symbol: '2317' })
    await waitFor(() => expect(result.current.drawings[0]?.symbol).toBe('2317'))
    await act(async () => { resolveOld([existing]) })
    expect(result.current.drawings).toEqual([{ ...existing, symbol: '2317', id: 22 }])
  })
})
