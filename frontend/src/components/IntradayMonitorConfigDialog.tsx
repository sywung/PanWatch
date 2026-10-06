import { useEffect, useState } from 'react'
import { Button } from '@panwatch/base-ui/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@panwatch/base-ui/components/ui/dialog'
import { Input } from '@panwatch/base-ui/components/ui/input'
import { Label } from '@panwatch/base-ui/components/ui/label'
import { useTranslation } from 'react-i18next'

export interface IntradayMonitorConfig {
  event_only: boolean
  price_alert_threshold: number
  volume_alert_ratio: number
  stop_loss_warning: number
  take_profit_warning: number
  throttle_minutes: number
}

interface IntradayMonitorConfigDialogProps {
  open: boolean
  config: Record<string, unknown>
  onCancel: () => void
  onSave: (config: IntradayMonitorConfig) => Promise<void> | void
}

interface IntradayMonitorForm {
  event_only: boolean
  price_alert_threshold: string
  volume_alert_ratio: string
  stop_loss_warning: string
  take_profit_warning: string
  throttle_minutes: string
}

type NumericConfigKey = Exclude<keyof IntradayMonitorForm, 'event_only'>

const defaults: IntradayMonitorForm = {
  event_only: true,
  price_alert_threshold: '3',
  volume_alert_ratio: '2',
  stop_loss_warning: '-5',
  take_profit_warning: '10',
  throttle_minutes: '30',
}

function formFromConfig(config: Record<string, unknown>): IntradayMonitorForm {
  return {
    event_only: config.event_only === undefined ? defaults.event_only : config.event_only === true,
    price_alert_threshold: String(config.price_alert_threshold ?? defaults.price_alert_threshold),
    volume_alert_ratio: String(config.volume_alert_ratio ?? defaults.volume_alert_ratio),
    stop_loss_warning: String(config.stop_loss_warning ?? defaults.stop_loss_warning),
    take_profit_warning: String(config.take_profit_warning ?? defaults.take_profit_warning),
    throttle_minutes: String(config.throttle_minutes ?? defaults.throttle_minutes),
  }
}

export default function IntradayMonitorConfigDialog({
  open,
  config,
  onCancel,
  onSave,
}: IntradayMonitorConfigDialogProps) {
  const { t } = useTranslation('configuration')
  const translate = t as unknown as (key: string) => string
  const tr = (key: string) => translate(`agentsPage.intradayConfig.${key}`)
  const [form, setForm] = useState<IntradayMonitorForm>(() => formFromConfig(config))
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  useEffect(() => {
    if (!open) return
    setForm(formFromConfig(config))
    setSaveError('')
  }, [open, config])

  const validateNumeric = (key: NumericConfigKey, raw: string): string => {
    if (!raw.trim()) return tr('errors.required')
    const value = Number(raw)
    if (!Number.isFinite(value)) return tr('errors.number')

    switch (key) {
      case 'take_profit_warning':
        return value > 0 && value <= 1000 ? '' : tr('errors.takeProfit')
      case 'stop_loss_warning':
        return value >= -100 && value < 0 ? '' : tr('errors.stopLoss')
      case 'price_alert_threshold':
        return value > 0 && value <= 50 ? '' : tr('errors.price')
      case 'volume_alert_ratio':
        return value > 0 && value <= 50 ? '' : tr('errors.volume')
      case 'throttle_minutes':
        return Number.isInteger(value) && value >= 0 && value <= 1440 ? '' : tr('errors.throttle')
    }
  }

  const errors: Record<NumericConfigKey, string> = {
    take_profit_warning: validateNumeric('take_profit_warning', form.take_profit_warning),
    stop_loss_warning: validateNumeric('stop_loss_warning', form.stop_loss_warning),
    price_alert_threshold: validateNumeric('price_alert_threshold', form.price_alert_threshold),
    volume_alert_ratio: validateNumeric('volume_alert_ratio', form.volume_alert_ratio),
    throttle_minutes: validateNumeric('throttle_minutes', form.throttle_minutes),
  }
  const hasErrors = Object.values(errors).some(Boolean)

  const updateNumeric = (key: NumericConfigKey, value: string) => {
    setForm(current => ({ ...current, [key]: value }))
    setSaveError('')
  }

  const submit = async () => {
    if (hasErrors || saving) return
    setSaving(true)
    setSaveError('')
    try {
      await onSave({
        event_only: form.event_only,
        price_alert_threshold: Number(form.price_alert_threshold),
        volume_alert_ratio: Number(form.volume_alert_ratio),
        stop_loss_warning: Number(form.stop_loss_warning),
        take_profit_warning: Number(form.take_profit_warning),
        throttle_minutes: Number(form.throttle_minutes),
      })
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : tr('errors.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const numericField = (
    key: NumericConfigKey,
    id: string,
    labelKey: string,
    hintKey: string,
    min: number,
    max: number,
    step: string,
  ) => (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{tr(labelKey)}</Label>
      <Input
        id={id}
        type="number"
        min={min}
        max={max}
        step={step}
        value={form[key]}
        aria-invalid={errors[key] ? 'true' : undefined}
        aria-describedby={`${id}-hint${errors[key] ? ` ${id}-error` : ''}`}
        onChange={event => updateNumeric(key, event.target.value)}
      />
      <p id={`${id}-hint`} className="text-[11px] text-muted-foreground">{tr(hintKey)}</p>
      {errors[key] && <p id={`${id}-error`} className="text-[11px] text-destructive">{errors[key]}</p>}
    </div>
  )

  return (
    <Dialog open={open} onOpenChange={nextOpen => !nextOpen && onCancel()}>
      <DialogContent className="max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{tr('title')}</DialogTitle>
          <DialogDescription>{tr('description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-2">
          {numericField('take_profit_warning', 'imTakeProfit', 'takeProfit', 'takeProfitHint', 0, 1000, 'any')}
          {numericField('stop_loss_warning', 'imStopLoss', 'stopLoss', 'stopLossHint', -100, 0, 'any')}
          {numericField('price_alert_threshold', 'imPrice', 'price', 'priceHint', 0, 50, 'any')}
          {numericField('volume_alert_ratio', 'imVolume', 'volume', 'volumeHint', 0, 50, 'any')}
          {numericField('throttle_minutes', 'imThrottle', 'throttle', 'throttleHint', 0, 1440, '1')}

          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <input
                id="imEventOnly"
                type="checkbox"
                className="h-4 w-4 rounded border-input accent-primary"
                checked={form.event_only}
                onChange={event => {
                  setForm(current => ({ ...current, event_only: event.target.checked }))
                  setSaveError('')
                }}
              />
              <Label htmlFor="imEventOnly">{tr('eventOnly')}</Label>
            </div>
            <p className="text-[11px] text-muted-foreground">{tr('eventOnlyHint')}</p>
          </div>

          {saveError && <p role="alert" className="text-sm text-destructive">{saveError}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={onCancel}>{tr('cancel')}</Button>
            <Button type="button" disabled={hasErrors || saving} onClick={() => void submit()}>
              {saving ? tr('saving') : tr('save')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
