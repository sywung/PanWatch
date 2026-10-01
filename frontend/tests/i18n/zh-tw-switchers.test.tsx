import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '@panwatch/base-ui/components/ui/toast'
import AccountMenu from '@/components/AccountMenu'
import { changeLocale, LOCALE_STORAGE_KEY } from '@/i18n'
import LoginPage from '@/pages/Login'

vi.mock('@/hooks/use-avatar', () => ({
  useAvatar: () => null,
}))

vi.mock('@panwatch/api', () => ({
  authApi: {
    status: vi.fn().mockResolvedValue({ initialized: true }),
    login: vi.fn(),
    setup: vi.fn(),
  },
}))

describe('Traditional Chinese in language switchers', () => {
  beforeEach(async () => {
    window.localStorage.clear()
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockReturnValue({ matches: false }),
    })
  })

  it('offers 繁體中文 in the account menu and switches to zh-TW', async () => {
    await changeLocale('en-US')
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <AccountMenu navItems={[]} mode="system" onSetMode={vi.fn()} onOpenSelfCheck={vi.fn()} />
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: 'Account and settings' }))
    await user.click(screen.getByRole('button', { name: '繁體中文' }))

    expect(document.documentElement.lang).toBe('zh-TW')
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('zh-TW')
    expect(screen.getByRole('button', { name: '帳戶與設定' })).toBeTruthy()
  })

  it('cycles the login quick switch zh-TW → zh-CN → en-US → zh-TW', async () => {
    await changeLocale('zh-TW')
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <ToastProvider>
          <LoginPage />
        </ToastProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: '登入' })).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '切換介面語言' }))
    expect(await screen.findByRole('heading', { name: '登录' })).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '切换界面语言' }))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeTruthy()
    await user.click(screen.getByRole('button', { name: /switch.*language/i }))
    expect(await screen.findByRole('heading', { name: '登入' })).toBeTruthy()
  })
})
