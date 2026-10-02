import { useEffect, useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { fetchAPI } from '@panwatch/api'
import { futuresPositionsApi, type FuturesPosition, type FuturesPositionOptions } from '@panwatch/api/futures-positions'
import { Button } from '@panwatch/base-ui/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@panwatch/base-ui/components/ui/dialog'
import { Input } from '@panwatch/base-ui/components/ui/input'
import { Label } from '@panwatch/base-ui/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@panwatch/base-ui/components/ui/select'
import { useToast } from '@panwatch/base-ui/components/ui/toast'
import { getCurrentLocale } from '@/i18n'
import { useTranslation } from 'react-i18next'

interface ProductSearchResult {
  symbol: string
  name: string
  market: string
}

interface FuturesPositionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  accountId: number
  position?: FuturesPosition | null
  onSaved: () => Promise<void> | void
}

type MonthOption = FuturesPositionOptions['months'][number]

function monthLabel(month: MonthOption, locale: string): string {
  const year = month.contract_month.slice(0, 4)
  const number = month.contract_month.slice(4, 6)
  const settlement = month.settlement_date ? new Date(`${month.settlement_date}T00:00:00`).toLocaleDateString(locale, { month: '2-digit', day: '2-digit' }) : ''
  return `${year}/${number} (${month.contract_symbol}${settlement ? `, ${settlement}` : ''})`
}

export function FuturesPositionDialog({ open, onOpenChange, accountId, position, onSaved }: FuturesPositionDialogProps) {
  const { t } = useTranslation('configuration')
  const translate = t as unknown as (key: string, options?: Record<string, unknown>) => string
  const tr = (key: string, options?: Record<string, unknown>) => translate(`stocksPage.futuresPositions.${key}`, options)
  const { toast } = useToast()
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [products, setProducts] = useState<ProductSearchResult[]>([])
  const [product, setProduct] = useState<ProductSearchResult | null>(null)
  const [options, setOptions] = useState<FuturesPositionOptions | null>(null)
  const [contractMonth, setContractMonth] = useState('')
  const [direction, setDirection] = useState<'long' | 'short'>('long')
  const [lots, setLots] = useState('1')
  const [entryPrice, setEntryPrice] = useState('')
  const [multiplier, setMultiplier] = useState('')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)

  const locale = getCurrentLocale()
  const months = useMemo(() => {
    const rows = options?.months || []
    if (position && contractMonth && !rows.some(row => row.contract_month === contractMonth)) {
      return [{
        contract_month: contractMonth,
        contract_symbol: position.contract_symbol,
        settlement_date: position.settlement_date || '',
      }, ...rows]
    }
    return rows
  }, [contractMonth, options, position])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setOptions(null)
    setProducts([])
    if (position) {
      setProduct({ symbol: position.product_code, name: position.product_name, market: 'TWF' })
      setQuery(`${position.product_code} ${position.product_name}`)
      setContractMonth(position.contract_month)
      setDirection(position.direction)
      setLots(String(position.lots))
      setEntryPrice(String(position.entry_price))
      setMultiplier(String(position.multiplier ?? ''))
      setNote(position.note || '')
      futuresPositionsApi.options(position.product_code).then(data => {
        if (cancelled) return
        setOptions(data)
        if (!position.multiplier) setMultiplier(String(data.multiplier))
      }).catch(() => undefined)
    } else {
      setProduct(null)
      setQuery('')
      setContractMonth('')
      setDirection('long')
      setLots('1')
      setEntryPrice('')
      setMultiplier('')
      setNote('')
    }
    return () => { cancelled = true }
  }, [open, position])

  useEffect(() => {
    if (!open || position || product || query.trim().length < 1) {
      setProducts([])
      return
    }
    let cancelled = false
    const timer = setTimeout(async () => {
      setSearching(true)
      try {
        const rows = await fetchAPI<ProductSearchResult[]>(`/stocks/search?q=${encodeURIComponent(query.trim())}&market=TWF`)
        if (!cancelled) setProducts((rows || []).filter(row => row.market === 'TWF'))
      } catch {
        if (!cancelled) setProducts([])
      } finally {
        if (!cancelled) setSearching(false)
      }
    }, 300)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [open, position, product, query])

  const selectProduct = async (item: ProductSearchResult) => {
    setProduct(item)
    setQuery(`${item.symbol} ${item.name}`)
    setProducts([])
    setContractMonth('')
    setOptions(null)
    try {
      const data = await futuresPositionsApi.options(item.symbol)
      setOptions(data)
      setMultiplier(String(data.multiplier))
      setContractMonth(data.months[0]?.contract_month || '')
    } catch (error) {
      toast(error instanceof Error ? error.message : tr('loadOptionsFailed'), 'error')
    }
  }

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!product) return
    setSaving(true)
    try {
      const payload = {
        contract_month: contractMonth,
        direction,
        lots: Number(lots),
        entry_price: Number(entryPrice),
        multiplier: multiplier.trim() ? Number(multiplier) : null,
        note: note.trim() || null,
      }
      if (position) {
        await futuresPositionsApi.update(position.id, payload)
      } else {
        await futuresPositionsApi.create({ account_id: accountId, product_code: product.symbol, ...payload })
      }
      await onSaved()
      onOpenChange(false)
      toast(position ? tr('updated') : tr('created'), 'success')
    } catch (error) {
      const code = error instanceof Error ? (error as Error & { errorCode?: string }).errorCode : undefined
      const knownCodes = [
        'futures_product_not_found', 'invalid_direction', 'invalid_lots', 'invalid_entry_price',
        'invalid_multiplier', 'invalid_contract_month', 'contract_expired', 'account_not_found',
      ]
      toast(code && knownCodes.includes(code) ? tr(`errors.${code}`) : error instanceof Error ? error.message : tr('saveFailed'), 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{tr(position ? 'editTitle' : 'addTitle')}</DialogTitle>
          <DialogDescription>{tr('description')}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label>{tr('product')}</Label>
            {position ? (
              <Input value={`${position.product_code} ${position.product_name}`} readOnly />
            ) : (
              <div className="relative">
                <Search className="absolute left-3 top-3 w-4 h-4 text-muted-foreground" />
                <Input value={query} onChange={event => { setQuery(event.target.value); setProduct(null); setOptions(null) }} placeholder={tr('productSearchPlaceholder')} className="pl-9" autoComplete="off" />
                {searching && <span className="absolute right-3 top-3 w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />}
                {products.length > 0 && (
                  <div className="absolute z-50 w-full mt-1 max-h-52 overflow-auto rounded-xl border border-border bg-card shadow-lg">
                    {products.map(item => (
                      <button key={item.symbol} type="button" onClick={() => void selectProduct(item)} className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-accent/50">
                        <span className="font-mono text-xs text-muted-foreground">{item.symbol}</span>
                        <span className="text-sm">{item.name}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>{tr('contractMonth')}</Label>
              <Select value={contractMonth} onValueChange={setContractMonth} disabled={!options || months.length === 0}>
                <SelectTrigger><SelectValue placeholder={tr('selectContractMonth')} /></SelectTrigger>
                <SelectContent>
                  {months.map(month => <SelectItem key={month.contract_month} value={month.contract_month}>{monthLabel(month, locale)}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>{tr('direction')}</Label>
              <Select value={direction} onValueChange={value => setDirection(value as 'long' | 'short')}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="long">{tr('long')}</SelectItem>
                  <SelectItem value="short">{tr('short')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="futures-lots">{tr('lots')}</Label>
              <Input id="futures-lots" type="number" min="1" step="1" value={lots} onChange={event => setLots(event.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="futures-entry-price">{tr('entryPrice')}</Label>
              <Input id="futures-entry-price" type="number" min="0.0001" step="any" value={entryPrice} onChange={event => setEntryPrice(event.target.value)} required />
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="futures-multiplier">{tr('multiplier')}</Label>
              <Input id="futures-multiplier" type="number" min="0.0001" step="any" value={multiplier} onChange={event => setMultiplier(event.target.value)} required />
              <p className="text-[11px] text-muted-foreground">{tr('multiplierHint')}</p>
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="futures-note">{tr('note')}</Label>
              <Input id="futures-note" value={note} onChange={event => setNote(event.target.value)} maxLength={500} />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>{tr('cancel')}</Button>
            <Button type="submit" disabled={saving || !product || !contractMonth || !lots || !entryPrice || !multiplier}>{saving ? tr('saving') : tr('save')}</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
