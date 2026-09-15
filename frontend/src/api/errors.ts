import axios from 'axios'

type ApiErrorDetail = string | { msg?: string }[]

export function getApiErrorMessage(error: unknown, fallback = '请求失败，请稍后再试') {
  if (!axios.isAxiosError(error)) return fallback

  const detail = error.response?.data?.detail as ApiErrorDetail | undefined
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => item.msg).filter((message): message is string => Boolean(message))
    if (messages.length) return messages.join('；')
  }
  if (typeof detail === 'string' && detail) return detail

  switch (error.response?.status) {
    case 400:
      return '请求数据无法被服务器接受，请检查输入'
    case 401:
      return '登录已失效，请重新登录'
    case 413:
      return '提交内容过大，请精简后重试'
    case 404:
      return '请求的内容不存在'
    default:
      return error.message === 'Network Error' ? '无法连接服务器，请确认后端服务已启动' : fallback
  }
}

