import userEvent from '@testing-library/user-event'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAPI } from '@panwatch/api'
import { AssistantStockPicker } from '@/components/assistant/AssistantStockPicker'

vi.mock('@panwatch/api', () => ({
  fetchAPI: vi.fn(),
}))

describe('AssistantStockPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('searches the selected market and returns the chosen stock', async () => {
    vi.mocked(fetchAPI).mockResolvedValue([
      { symbol: '2330', name: '台積電', market: 'TW' },
    ])
    const onSelect = vi.fn()
    const user = userEvent.setup()

    render(<AssistantStockPicker onSelect={onSelect} onCancel={vi.fn()} />)

    await user.type(screen.getByRole('searchbox', { name: '搜索股票' }), '台積電')
    await waitFor(() => expect(fetchAPI).toHaveBeenCalledWith(
      '/stocks/search?q=%E5%8F%B0%E7%A9%8D%E9%9B%BB&market=TW',
      expect.any(Object),
    ))
    await user.click(await screen.findByRole('button', { name: /台積電/ }))

    expect(onSelect).toHaveBeenCalledWith({ symbol: '2330', name: '台積電', market: 'TW' })
  })
})
