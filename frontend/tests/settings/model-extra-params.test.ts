import { describe, expect, it } from 'vitest'

import { formatModelExtraParams, parseModelExtraParams } from '@/lib/model-extra-params'

// 模型「额外参数」栏:使用者输入 JSON 物件,以 extra_body 随请求送出
// (例:oMLX 的 Qwen3.x 要 {"chat_template_kwargs": {"enable_thinking": false}} 才不会把思考写进回覆)。

describe('parseModelExtraParams', () => {
  it('treats blank input as no extra params', () => {
    expect(parseModelExtraParams('')).toEqual({ ok: true, value: {} })
    expect(parseModelExtraParams('   ')).toEqual({ ok: true, value: {} })
  })

  it('accepts a JSON object', () => {
    expect(parseModelExtraParams('{"chat_template_kwargs": {"enable_thinking": false}}')).toEqual({
      ok: true,
      value: { chat_template_kwargs: { enable_thinking: false } },
    })
  })

  it('rejects invalid JSON and non-objects', () => {
    expect(parseModelExtraParams('{bad').ok).toBe(false)
    expect(parseModelExtraParams('["x"]').ok).toBe(false)
    expect(parseModelExtraParams('"text"').ok).toBe(false)
    expect(parseModelExtraParams('null').ok).toBe(false)
  })

  it('rejects keys that would override the request itself', () => {
    for (const key of ['model', 'messages', 'stream', 'tools']) {
      const result = parseModelExtraParams(JSON.stringify({ [key]: 'x' }))
      expect(result.ok).toBe(false)
    }
  })
})

describe('formatModelExtraParams', () => {
  it('shows nothing for empty params and pretty JSON otherwise', () => {
    expect(formatModelExtraParams({})).toBe('')
    expect(formatModelExtraParams(undefined)).toBe('')
    expect(formatModelExtraParams(null)).toBe('')
    expect(formatModelExtraParams({ a: 1 })).toBe('{\n  "a": 1\n}')
  })
})
