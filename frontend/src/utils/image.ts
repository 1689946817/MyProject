/**
 * 图片工具函数
 */

/**
 * 生成图片 URL
 * @param filePath 图片文件路径
 * @returns 可访问的图片 URL
 */
export function imgSrc(filePath: string): string {
  // 将反斜杠统一为正斜杠，取 storage/ 之后的部分
  const normalized = filePath.replace(/\\/g, '/')
  const idx = normalized.indexOf('storage/')
  if (idx !== -1) {
    return `http://localhost:9090/static/${normalized.slice(idx + 'storage/'.length)}`
  }
  return ''
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
  if (status === 'Completed' || status === 'Completed') return 'success'
  if (status === 'Failed') return 'danger'
  if (status === 'Processing') return 'warning'
  return 'info'
}
