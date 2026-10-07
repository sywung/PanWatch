import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'
import { formatDate } from '@/i18n/format'

// 2026-10-07：使用者要求時間一律 24 小時制。zh-TW 的 Intl 預設是 12 小時制（「下午02:05」）。

const ROOTS = [join(__dirname, '../../src'), join(__dirname, '../../packages')]

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (name === 'node_modules' || name === 'dist') return []
    if (statSync(path).isDirectory()) return sourceFiles(path)
    return /\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : []
  })
}

/** 取出從 open 位置開始、括號平衡的呼叫參數字串。 */
function callArgs(text: string, open: number): string {
  let depth = 0
  for (let i = open; i < text.length; i++) {
    if (text[i] === '(') depth++
    else if (text[i] === ')' && --depth === 0) return text.slice(open + 1, i)
  }
  return text.slice(open + 1)
}

describe('24-hour time display', () => {
  it('formatDate defaults to 24-hour when hours are shown', () => {
    const d = new Date('2026-10-07T14:05:00+08:00')
    const out = formatDate(d, { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Taipei' }, 'zh-TW')
    expect(out).toContain('14:05')
    expect(out).not.toMatch(/上午|下午|AM|PM/i)
  })

  it('formatDate keeps midnight as 00, not 24', () => {
    const d = new Date('2026-10-07T00:05:00+08:00')
    expect(formatDate(d, { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Taipei' }, 'zh-TW')).toContain('00:05')
  })

  it('every date/time formatting call that shows hours forces 24-hour', () => {
    const offenders: string[] = []
    const pattern = /(toLocaleTimeString|toLocaleString|Intl\.DateTimeFormat)\s*\(/g
    for (const file of ROOTS.flatMap(sourceFiles)) {
      const text = readFileSync(file, 'utf8')
      for (const m of text.matchAll(pattern)) {
        const args = callArgs(text, m.index! + m[0].length - 1)
        const line = text.slice(0, m.index).split('\n').length
        const where = `${relative(join(__dirname, '../..'), file)}:${line}`
        const prefix = text.slice(Math.max(0, m.index! - 80), m.index)
        if (m[1] === 'toLocaleTimeString' && !/hour12|hourCycle/.test(args)) offenders.push(where)
        // 無參數的 Date#toLocaleString() 會帶出 locale 預設的 12 小時制
        else if (m[1] === 'toLocaleString' && /new Date\([^)]*\)\.$/.test(prefix) && args.trim() === '')
          offenders.push(where)
        else if (/\bhour\s*:/.test(args) && !/hour12|hourCycle/.test(args)) offenders.push(where)
      }
    }
    expect(offenders).toEqual([])
  })
})
