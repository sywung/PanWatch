import { useState } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { settlementUrgency } from '@panwatch/biz-ui'
import { type FuturesPosition, futuresPositionsApi } from '@panwatch/api/futures-positions'
import { Badge } from '@panwatch/base-ui/components/ui/badge'
import { Button } from '@panwatch/base-ui/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@panwatch/base-ui/components/ui/dialog'
import { useToast } from '@panwatch/base-ui/components/ui/toast'
import { useTranslation } from 'react-i18next'
import { marketSignTextClass } from '@/lib/market-colors'
import { FuturesPositionDialog } from './FuturesPositionDialog'

interface FuturesPositionsSectionProps {
  accountId: number
  positions: FuturesPosition[]
  formatMoney: (value: number) => string
  formatPrice: (value: number) => string
  onChanged: () => Promise<void> | void
}

export function FuturesPositionsSection({ accountId, positions, formatMoney, formatPrice, onChanged }: FuturesPositionsSectionProps) {
  const { t } = useTranslation('configuration')
  const translate = t as unknown as (key: string, options?: Record<string, unknown>) => string
  const tr = (key: string, options?: Record<string, unknown>) => translate(`stocksPage.futuresPositions.${key}`, options)
  const { toast } = useToast()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<FuturesPosition | null>(null)
  const [deleting, setDeleting] = useState<FuturesPosition | null>(null)
  const [deletingBusy, setDeletingBusy] = useState(false)

  const openAdd = () => { setEditing(null); setDialogOpen(true) }
  const openEdit = (position: FuturesPosition) => { setEditing(position); setDialogOpen(true) }
  const urgencyText = (position: FuturesPosition) => {
    const urgency = settlementUrgency(position.days_to_settlement)
    if (urgency === 'expired') return tr('settlementExpired')
    if (urgency === 'today') return tr('settlementToday')
    if (urgency === 'soon') return tr('settlementInDays', { count: position.days_to_settlement })
    return position.days_to_settlement == null ? '' : tr('settlementDaysLeft', { count: position.days_to_settlement })
  }
  const urgencyClass = (position: FuturesPosition) => {
    const urgency = settlementUrgency(position.days_to_settlement)
    if (urgency === 'expired') return 'text-destructive'
    if (urgency === 'today' || urgency === 'soon') return 'text-amber-600'
    return 'text-muted-foreground'
  }

  const confirmDelete = async () => {
    if (!deleting) return
    setDeletingBusy(true)
    try {
      await futuresPositionsApi.remove(deleting.id)
      setDeleting(null)
      toast(tr('deleted'), 'success')
      void onChanged()
    } catch (error) {
      toast(error instanceof Error ? error.message : tr('deleteFailed'), 'error')
    } finally {
      setDeletingBusy(false)
    }
  }

  return (
    <>
      <section className={`border-t border-border/30 px-3 md:px-4 ${positions.length > 0 ? 'py-3' : 'py-1'}`} aria-label={tr('title')}>
        <div className="flex items-center justify-between gap-2 mb-2">
          {positions.length > 0 && <h3 className="text-[12px] font-semibold text-foreground">{tr('title')}</h3>}
          <Button variant="outline" size="sm" className={`h-7 px-2.5 text-[11px] ${positions.length === 0 ? 'ml-auto' : ''}`} onClick={openAdd}>
            <Plus className="w-3 h-3" />{tr('add')}
          </Button>
        </div>
        {positions.length === 0 ? null : (
          <>
            <div className="hidden xl:block overflow-x-auto">
              <table className="w-full min-w-[1120px]">
                <thead>
                  <tr className="border-b border-border/30 bg-accent/20">
                    {['product', 'direction', 'lots', 'entryPrice', 'currentPrice', 'unrealizedPnl', 'marginUsed', 'equity', 'settlement', 'actions'].map((key, index) => (
                      <th key={key} className={`px-2 py-2 text-[10px] font-semibold text-muted-foreground ${index === 0 ? 'text-left' : index === 9 ? 'text-center' : 'text-right'}`}>{tr(key)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {positions.map(position => (
                    <tr key={position.id} className="border-b border-border/20 last:border-0 text-[12px]">
                      <td className="px-2 py-2.5">
                        <div className="font-medium text-[12px]">{position.product_name} <span className="font-mono text-muted-foreground">{position.contract_symbol}</span></div>
                        {position.margin_call && <Badge variant="destructive" className="mt-1 text-[9px]">{tr('marginCall')}</Badge>}
                      </td>
                      <td className={`px-2 py-2.5 text-right ${marketSignTextClass(position.direction === 'long' ? 1 : -1)}`}>{tr(position.direction)}</td>
                      <td className="px-2 py-2.5 text-right font-mono">{position.lots}</td>
                      <td className="px-2 py-2.5 text-right font-mono">{formatPrice(position.entry_price)}</td>
                      <td className="px-2 py-2.5 text-right font-mono">{position.current_price == null ? '—' : formatPrice(position.current_price)}</td>
                      <td className={`px-2 py-2.5 text-right font-mono ${marketSignTextClass(position.unrealized_pnl)}`}>{position.unrealized_pnl == null ? '—' : `${position.unrealized_pnl >= 0 ? '+' : ''}${formatMoney(position.unrealized_pnl)}`}</td>
                      <td className="px-2 py-2.5 text-right font-mono">{position.margin_used == null ? '—' : formatMoney(position.margin_used)}</td>
                      <td className="px-2 py-2.5 text-right font-mono">{position.equity == null ? '—' : formatMoney(position.equity)}</td>
                      <td className={`px-2 py-2.5 text-right text-[11px] ${urgencyClass(position)}`}>
                        <div>{position.settlement_date || '—'}</div><div>{urgencyText(position)}</div>
                      </td>
                      <td className="px-2 py-2.5 text-center">
                        <div className="inline-flex items-center">
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(position)} aria-label={tr('edit')}><Pencil className="w-3 h-3" /></Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7 hover:text-destructive" onClick={() => setDeleting(position)} aria-label={tr('delete')}><Trash2 className="w-3 h-3" /></Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:hidden gap-2">
              {positions.map(position => (
                <article key={position.id} className="rounded-xl border border-border/40 bg-accent/10 p-3 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-[12px] font-semibold truncate">{position.product_name} <span className="font-mono text-muted-foreground">{position.contract_symbol}</span></div>
                      <div className="flex flex-wrap items-center gap-1.5 mt-1">
                        <Badge variant="outline" className={`text-[10px] ${marketSignTextClass(position.direction === 'long' ? 1 : -1)}`}>{tr(position.direction)}</Badge>
                        <span className="text-[11px] text-muted-foreground">{position.lots} {tr('lotsUnit')}</span>
                        {position.margin_call && <Badge variant="destructive" className="text-[9px]">{tr('marginCall')}</Badge>}
                      </div>
                    </div>
                    <div className="flex shrink-0">
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(position)} aria-label={tr('edit')}><Pencil className="w-3 h-3" /></Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7 hover:text-destructive" onClick={() => setDeleting(position)} aria-label={tr('delete')}><Trash2 className="w-3 h-3" /></Button>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-2 mt-3 text-[11px]">
                    <Metric label={tr('entryPrice')} value={formatPrice(position.entry_price)} />
                    <Metric label={tr('currentPrice')} value={position.current_price == null ? '—' : formatPrice(position.current_price)} />
                    <Metric label={tr('unrealizedPnl')} value={position.unrealized_pnl == null ? '—' : `${position.unrealized_pnl >= 0 ? '+' : ''}${formatMoney(position.unrealized_pnl)}`} className={marketSignTextClass(position.unrealized_pnl)} />
                    <Metric label={tr('marginUsed')} value={position.margin_used == null ? '—' : formatMoney(position.margin_used)} />
                    <Metric label={tr('equity')} value={position.equity == null ? '—' : formatMoney(position.equity)} />
                    <Metric label={tr('settlement')} value={`${position.settlement_date || '—'} · ${urgencyText(position)}`} className={urgencyClass(position)} wide />
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </section>

      <FuturesPositionDialog open={dialogOpen} onOpenChange={setDialogOpen} accountId={accountId} position={editing} onSaved={onChanged} />
      <Dialog open={!!deleting} onOpenChange={open => { if (!open && !deletingBusy) setDeleting(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{tr('deleteTitle')}</DialogTitle>
            <DialogDescription>{tr('deleteDescription', { product: deleting?.product_name, contract: deleting?.contract_symbol })}</DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDeleting(null)} disabled={deletingBusy}>{tr('cancel')}</Button>
            <Button variant="destructive" onClick={() => void confirmDelete()} disabled={deletingBusy}>{deletingBusy ? tr('deleting') : tr('delete')}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

function Metric({ label, value, className = '', wide = false }: { label: string; value: string; className?: string; wide?: boolean }) {
  return <div className={`flex justify-between gap-2 min-w-0${wide ? ' col-span-2' : ''}`}><span className="text-muted-foreground shrink-0">{label}</span><span className={`font-mono text-right truncate ${className}`}>{value}</span></div>
}
