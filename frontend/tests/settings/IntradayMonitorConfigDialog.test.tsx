import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import IntradayMonitorConfigDialog from '@/components/IntradayMonitorConfigDialog'
import { changeLocale } from '@/i18n'

// 2026-10-06：盤中監測的「浮盈達標」門檻原本只能改 DB，改成在 Agent 頁設定。
const LABELS = {
  takeProfit: '止盈提醒門檻（%）',
  stopLoss: '止損預警門檻（%）',
  price: '價格異動門檻（%）',
  volume: '量比異動門檻',
  throttle: '同一檔通知間隔（分鐘）',
  eventOnly: '啟用事件偵測',
}

const input = (label: string) => screen.getByLabelText(label) as HTMLInputElement
const saveButton = () => screen.getByRole('button', { name: '儲存' })

function setup(config: Record<string, unknown> = {}, onSave = vi.fn()) {
  const onCancel = vi.fn()
  const utils = render(
    <IntradayMonitorConfigDialog open config={config} onCancel={onCancel} onSave={onSave} />,
  )
  return { ...utils, onSave, onCancel }
}

describe('盤中監測參數設定', () => {
  beforeEach(async () => {
    await changeLocale('zh-TW')
  })

  it('顯示現有設定值', () => {
    setup({
      event_only: false,
      price_alert_threshold: 4.5,
      volume_alert_ratio: 2.5,
      stop_loss_warning: -8,
      take_profit_warning: 25,
      throttle_minutes: 45,
    })
    expect(input(LABELS.takeProfit).value).toBe('25')
    expect(input(LABELS.stopLoss).value).toBe('-8')
    expect(input(LABELS.price).value).toBe('4.5')
    expect(input(LABELS.volume).value).toBe('2.5')
    expect(input(LABELS.throttle).value).toBe('45')
    expect(input(LABELS.eventOnly).checked).toBe(false)
  })

  it('缺少的欄位用系統預設值', () => {
    setup({})
    expect(input(LABELS.takeProfit).value).toBe('10')
    expect(input(LABELS.stopLoss).value).toBe('-5')
    expect(input(LABELS.price).value).toBe('3')
    expect(input(LABELS.volume).value).toBe('2')
    expect(input(LABELS.throttle).value).toBe('30')
    expect(input(LABELS.eventOnly).checked).toBe(true)
  })

  it('儲存時送出完整 6 個欄位、數字型別，且不夾帶其他鍵', async () => {
    const { onSave } = setup({ take_profit_warning: 10, legacy_key: 'x', output_language: 'zh-TW' })
    fireEvent.change(input(LABELS.takeProfit), { target: { value: '25' } })
    fireEvent.click(input(LABELS.eventOnly))
    fireEvent.click(saveButton())
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
    expect(onSave).toHaveBeenCalledWith({
      event_only: false,
      price_alert_threshold: 3,
      volume_alert_ratio: 2,
      stop_loss_warning: -5,
      take_profit_warning: 25,
      throttle_minutes: 30,
    })
  })

  it.each([
    [LABELS.takeProfit, '0'],
    [LABELS.takeProfit, '-3'],
    [LABELS.takeProfit, '1001'],
    [LABELS.takeProfit, ''],
    [LABELS.stopLoss, '5'],
    [LABELS.stopLoss, '0'],
    [LABELS.stopLoss, '-101'],
    [LABELS.price, '0'],
    [LABELS.price, '51'],
    [LABELS.volume, '0'],
    [LABELS.throttle, '1.5'],
    [LABELS.throttle, '-1'],
    [LABELS.throttle, '1441'],
  ])('%s 填 "%s" 時不能儲存並顯示錯誤', async (label, value) => {
    const { onSave } = setup({})
    fireEvent.change(input(label), { target: { value } })
    expect(input(label).getAttribute('aria-invalid')).toBe('true')
    expect((saveButton() as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(saveButton())
    await new Promise((r) => setTimeout(r, 0))
    expect(onSave).not.toHaveBeenCalled()
  })

  it('改回合法值後可以儲存', async () => {
    const { onSave } = setup({})
    fireEvent.change(input(LABELS.takeProfit), { target: { value: '0' } })
    expect((saveButton() as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(input(LABELS.takeProfit), { target: { value: '15' } })
    expect(input(LABELS.takeProfit).getAttribute('aria-invalid')).not.toBe('true')
    fireEvent.click(saveButton())
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
    expect(onSave.mock.calls[0][0].take_profit_warning).toBe(15)
  })

  it('取消不會儲存', () => {
    const { onSave, onCancel } = setup({})
    fireEvent.change(input(LABELS.takeProfit), { target: { value: '25' } })
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onSave).not.toHaveBeenCalled()
  })

  it('換一份 config 重新開啟時表單跟著更新', () => {
    const onSave = vi.fn()
    const onCancel = vi.fn()
    const { rerender } = render(
      <IntradayMonitorConfigDialog open config={{ take_profit_warning: 12 }} onCancel={onCancel} onSave={onSave} />,
    )
    fireEvent.change(input(LABELS.takeProfit), { target: { value: '99' } })
    rerender(
      <IntradayMonitorConfigDialog open={false} config={{ take_profit_warning: 12 }} onCancel={onCancel} onSave={onSave} />,
    )
    rerender(
      <IntradayMonitorConfigDialog open config={{ take_profit_warning: 30 }} onCancel={onCancel} onSave={onSave} />,
    )
    expect(input(LABELS.takeProfit).value).toBe('30')
  })

  it('儲存失敗時顯示錯誤訊息且對話框保持開啟', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('take_profit_warning 必須介於 0 到 1000'))
    setup({}, onSave)
    fireEvent.click(saveButton())
    expect(await screen.findByText('take_profit_warning 必須介於 0 到 1000')).toBeTruthy()
    expect(input(LABELS.takeProfit)).toBeTruthy()
  })
})
