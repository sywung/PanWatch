import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import { resources } from './resources'

export const DEFAULT_LOCALE = 'zh-TW' as const
// v2:上游原版在同一网址自动写入的 zh-CN 不再沿用,新版预设繁中才会生效
export const LOCALE_STORAGE_KEY = 'panwatch-locale-v2'
export const SUPPORTED_LOCALES = ['zh-TW', 'zh-CN', 'en-US'] as const

export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number]

export function isSupportedLocale(value: string | null | undefined): value is SupportedLocale {
  return SUPPORTED_LOCALES.includes(value as SupportedLocale)
}

export function normalizeLocale(value: string | null | undefined): SupportedLocale {
  if (isSupportedLocale(value)) return value
  const normalized = value?.toLowerCase() || ''
  if (normalized.startsWith('en')) return 'en-US'
  if (normalized === 'zh-cn' || normalized.startsWith('zh-hans') || normalized === 'zh-sg' || normalized === 'zh') return 'zh-CN'
  if (normalized === 'zh-tw' || normalized.startsWith('zh-hant') || normalized === 'zh-hk' || normalized === 'zh-mo') return 'zh-TW'
  return DEFAULT_LOCALE
}

export function detectInitialLocale(
  storedLocale: string | null | undefined,
  _browserLanguages: readonly string[] = [],
): SupportedLocale {
  if (isSupportedLocale(storedLocale)) return storedLocale
  return DEFAULT_LOCALE
}

function readInitialLocale(): SupportedLocale {
  if (typeof window === 'undefined') return DEFAULT_LOCALE
  return detectInitialLocale(window.localStorage.getItem(LOCALE_STORAGE_KEY))
}

function applyLocale(locale: string) {
  const normalized = normalizeLocale(locale)
  if (typeof document !== 'undefined') {
    const metadata = resources[normalized].common.product
    document.documentElement.lang = normalized
    document.title = metadata.pageTitle
    document.querySelector<HTMLMetaElement>('meta[name="description"]')?.setAttribute('content', metadata.description)
    document.querySelector<HTMLMetaElement>('meta[name="apple-mobile-web-app-title"]')?.setAttribute('content', metadata.shortTitle)
    document.querySelector<HTMLLinkElement>('link[rel="manifest"]')?.setAttribute('href', normalized === 'zh-TW' ? '/manifest.zh-TW.json' : normalized === 'zh-CN' ? '/manifest.zh-CN.json' : '/manifest.json')
  }
  if (typeof window !== 'undefined') window.localStorage.setItem(LOCALE_STORAGE_KEY, normalized)
}

i18n.on('languageChanged', applyLocale)

void i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: readInitialLocale(),
    fallbackLng: ['zh-TW'],
    supportedLngs: [...SUPPORTED_LOCALES],
    defaultNS: 'common',
    ns: ['common', 'auth', 'navigation', 'settings', 'configuration', 'bizUi'],
    interpolation: {
      escapeValue: false,
    },
    returnNull: false,
    initAsync: false,
  })

export function getCurrentLocale(): SupportedLocale {
  return normalizeLocale(i18n.resolvedLanguage || i18n.language)
}

export async function changeLocale(locale: SupportedLocale): Promise<void> {
  await i18n.changeLanguage(locale)
}

export default i18n
