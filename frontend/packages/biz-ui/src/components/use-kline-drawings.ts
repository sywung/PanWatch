import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchAPI } from '@panwatch/api'
import type { KlineDrawing, NewDrawing } from './kline-drawings'

type DrawingListResponse = KlineDrawing[]
type DrawingMutationResponse = KlineDrawing

function productPath(symbol: string, market: string): string {
  return `/chart-drawings?symbol=${encodeURIComponent(symbol)}&market=${encodeURIComponent(market)}`
}

export function useKlineDrawings(symbol: string, market: string) {
  const [storedDrawings, setStoredDrawings] = useState<KlineDrawing[]>([])
  const [storedKey, setStoredKey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const drawingsRef = useRef<KlineDrawing[]>([])
  const generationRef = useRef(0)
  const optimisticIdRef = useRef(-1)
  const key = `${market}\u0000${symbol}`

  const writeDrawings = useCallback((drawings: KlineDrawing[]) => {
    drawingsRef.current = drawings
    setStoredDrawings(drawings)
  }, [])

  useEffect(() => {
    const generation = ++generationRef.current
    writeDrawings([])
    setStoredKey(key)
    setError(null)
    if (!symbol || !market) return
    void fetchAPI<DrawingListResponse>(productPath(symbol, market))
      .then(drawings => {
        if (generation === generationRef.current) writeDrawings(drawings)
      })
      .catch(cause => {
        if (generation === generationRef.current) {
          writeDrawings([])
          setError(cause instanceof Error ? cause.message : String(cause))
        }
      })
    return () => {
      if (generation === generationRef.current) generationRef.current += 1
    }
  }, [key, market, symbol, writeDrawings])

  const addDrawing = useCallback(async (drawing: NewDrawing): Promise<KlineDrawing | null> => {
    const generation = generationRef.current
    const optimisticId = optimisticIdRef.current--
    const optimistic = {
      id: optimisticId,
      symbol,
      market,
      ...drawing,
    } as KlineDrawing
    setError(null)
    writeDrawings([...drawingsRef.current, optimistic])
    try {
      const created = await fetchAPI<DrawingMutationResponse>('/chart-drawings', {
        method: 'POST',
        body: JSON.stringify({ symbol, market, ...drawing }),
      })
      if (generation === generationRef.current) {
        writeDrawings(drawingsRef.current.map(item => item.id === optimisticId ? created : item))
      }
      return created
    } catch (cause) {
      if (generation === generationRef.current) {
        writeDrawings(drawingsRef.current.filter(item => item.id !== optimisticId))
        setError(cause instanceof Error ? cause.message : String(cause))
      }
      return null
    }
  }, [market, symbol, writeDrawings])

  const deleteDrawing = useCallback(async (id: number): Promise<boolean> => {
    // 負數是還在 POST 中的暫時 id：此時刪除會讓伺服器那筆在重新整理後復活，等存好再刪
    if (id < 0) return false
    const generation = generationRef.current
    const removed = drawingsRef.current.find(item => item.id === id)
    setError(null)
    writeDrawings(drawingsRef.current.filter(item => item.id !== id))
    try {
      await fetchAPI<{ deleted: number }>(`/chart-drawings/${id}`, { method: 'DELETE' })
      return true
    } catch (cause) {
      if (generation === generationRef.current) {
        if (removed) writeDrawings([...drawingsRef.current, removed].sort((a, b) => a.id - b.id))
        setError(cause instanceof Error ? cause.message : String(cause))
      }
      return false
    }
  }, [writeDrawings])

  const clearDrawings = useCallback(async (): Promise<boolean> => {
    const generation = generationRef.current
    const snapshot = drawingsRef.current
    setError(null)
    writeDrawings([])
    try {
      await fetchAPI<{ deleted: number }>(productPath(symbol, market), { method: 'DELETE' })
      return true
    } catch (cause) {
      if (generation === generationRef.current) {
        writeDrawings(snapshot)
        setError(cause instanceof Error ? cause.message : String(cause))
      }
      return false
    }
  }, [market, symbol, writeDrawings])

  const clearError = useCallback(() => setError(null), [])
  return {
    drawings: storedKey === key ? storedDrawings : [],
    error,
    addDrawing,
    deleteDrawing,
    clearDrawings,
    clearError,
  }
}
