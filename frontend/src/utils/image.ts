/**
 * 图片工具函数模块
 *
 * 提供图片 URL 生成、日期格式化、相似度颜色映射和状态标签等 UI 辅助函数。
 */

/** 后端服务基础地址，用于拼接图片静态资源 URL */
const BACKEND_BASE_URL = 'http://127.0.0.1:9090'

/**
 * 生成图片 URL
 * @param filePath 图片文件路径
 * @returns 可访问的图片 URL
 */
export function imgSrc(filePath: string): string {
  if (!filePath) return ''

  // 将反斜杠统一为正斜杠
  const normalized = filePath.replace(/\\/g, '/')

  // 已经是完整 URL
  if (/^https?:\/\//.test(normalized)) {
    return normalized
  }

  // 已经是 /static/... 路径
  if (normalized.startsWith('/static/')) {
    return `${BACKEND_BASE_URL}${normalized}`
  }

  // 包含 storage/ 前缀的后端文件路径
  const idx = normalized.indexOf('storage/')
  if (idx !== -1) {
    return `${BACKEND_BASE_URL}/static/${normalized.slice(idx + 'storage/'.length)}`
  }

  // 兜底：当传入仅文件名或相对路径时，按静态目录拼接
  return `${BACKEND_BASE_URL}/static/${normalized.replace(/^\/+/, '')}`
}

/**
 * 格式化日期
 * @param dateStr ISO 日期字符串
 * @returns 格式化后的日期字符串
 */
export function formatDate(dateStr: string): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString()
}

/**
 * 根据相似度返回颜色
 * @param score 相似度分数 (0-1, 值越大越相似)
 * @returns 霓虹色字符串
 */
export function similarityColor(score: number): string {
  // score 范围通常是 0-1，越大越相似
  // 高相似度: #00d4ff (青色)
  // 低相似度: #7c3aed (紫色)
  const r = Math.round(124 + (0 - 124) * score)
  const g = Math.round(58 + (212 - 58) * score)
  const b = Math.round(237 + (255 - 237) * score)
  return `rgb(${r}, ${g}, ${b})`
}

/**
 * 计算相似度百分比
 * @param score 相似度分数
 * @returns 百分比字符串
 */
export function similarityPercent(score: number): string {
  return `${(score * 100).toFixed(1)}%`
}

/**
 * 获取状态类型对应的颜色
 * @param status 状态字符串
 * @returns Element Plus tag type
 */
export function statusType(status: string): string {
  if (status === 'Completed') return 'success'
  if (status === 'Failed') return 'danger'
  if (status === 'Processing') return 'warning'
  return 'info'
}
