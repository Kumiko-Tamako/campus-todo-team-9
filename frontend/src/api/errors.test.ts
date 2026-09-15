import { describe, expect, it } from 'vitest'
import { getApiErrorMessage } from './errors'

describe('getApiErrorMessage', () => {
  it('extracts messages from FastAPI validation detail arrays', () => {
    const error = {
      isAxiosError: true,
      response: { status: 422, data: { detail: [{ msg: '标题过短' }, { msg: '正文为空' }] } },
    }

    expect(getApiErrorMessage(error)).toBe('标题过短；正文为空')
  })

  it('returns a clear message for network failures', () => {
    const error = { isAxiosError: true, message: 'Network Error' }

    expect(getApiErrorMessage(error)).toBe('无法连接服务器，请确认后端服务已启动')
  })
})

