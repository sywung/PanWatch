const RESERVED_KEYS = new Set([
  'model',
  'messages',
  'stream',
  'tools',
  'tool_choice',
  'max_tokens',
  'temperature',
])

type ParseResult =
  | { ok: true; value: Record<string, unknown> }
  | { ok: false; error: string }

export function parseModelExtraParams(text: string): ParseResult {
  if (!text.trim()) return { ok: true, value: {} }

  let value: unknown
  try {
    value = JSON.parse(text)
  } catch {
    return { ok: false, error: 'extraParamsInvalid' }
  }

  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return { ok: false, error: 'extraParamsInvalid' }
  }

  if (Object.keys(value).some(key => RESERVED_KEYS.has(key))) {
    return { ok: false, error: 'extraParamsInvalid' }
  }

  return { ok: true, value: value as Record<string, unknown> }
}

export function formatModelExtraParams(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === 0) {
    return ''
  }
  return JSON.stringify(value, null, 2)
}
