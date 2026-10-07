import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  dashboardApi: {
    indices: vi.fn(),
    intradayScan: vi.fn(),
    overview: vi.fn(),
    portfolioSummary: vi.fn(),
    marketStatus: vi.fn(),
    brief: vi.fn(),
    curate: vi.fn(),
  },
  portfolioApi: {
    diagnostics: vi.fn(),
    benchmark: vi.fn(),
    attribution: vi.fn(),
  },
  recommendationsApi: { listStrategySignals: vi.fn() },
  homeApi: { alertHitsToday: vi.fn(), todos: vi.fn() },
}))

vi.mock('@panwatch/api', () => mocks)
vi.mock('@/components/DiscoveryPanel', () => ({ default: () => null }))
vi.mock('@/components/Sparkline', () => ({ default: () => null }))
vi.mock('@/components/BenchChart', () => ({ default: () => null }))
vi.mock('@/components/BenchmarkShareCard', () => ({ default: () => null }))
vi.mock('@/components/DiagnosticsShareCard', () => ({ default: () => null }))
vi.mock('@/components/DigestShareCard', () => ({ default: () => null }))
vi.mock('@panwatch/biz-ui/components/onboarding', () => ({ Onboarding: () => null }))
vi.mock('@panwatch/biz-ui/components/stock-insight-modal', () => ({ default: () => null }))

import DashboardPage from '@/pages/Dashboard'

describe('DashboardPage loading', () => {
  beforeEach(() => {
    window.localStorage.setItem('panwatch_onboarding_completed', 'true')

    mocks.dashboardApi.indices.mockResolvedValue([])
    mocks.dashboardApi.intradayScan.mockResolvedValue({ stocks: [] })
    mocks.dashboardApi.overview.mockResolvedValue({
      action_center: {
        opportunities: [{
          stock_market: 'TW',
          stock_symbol: 'FAST',
          stock_name: 'Overview arrives first',
          rank_score: 87,
        }],
      },
    })
    mocks.dashboardApi.portfolioSummary.mockReturnValue(new Promise(() => {}))
    mocks.dashboardApi.marketStatus.mockResolvedValue([])
    mocks.dashboardApi.brief.mockResolvedValue({ empty: true })
    mocks.dashboardApi.curate.mockResolvedValue({ items: [] })

    mocks.portfolioApi.diagnostics.mockResolvedValue({
      position_count: 0,
      total_market_value: 0,
      total_unrealized_pnl: 0,
      by_market: {},
      max_weight: 0,
      alerts: [],
      alert_details: [],
    })
    mocks.portfolioApi.benchmark.mockResolvedValue({ empty: true, curve: [] })
    mocks.portfolioApi.attribution.mockResolvedValue({ items: [] })
    mocks.recommendationsApi.listStrategySignals.mockResolvedValue({ items: [] })
    mocks.homeApi.alertHitsToday.mockResolvedValue([])
    mocks.homeApi.todos.mockResolvedValue({ todos: [] })
  })

  it('renders overview content while portfolio summary is still pending', async () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    expect((await screen.findAllByText('Overview arrives first')).length).toBeGreaterThan(0)
  })
})
