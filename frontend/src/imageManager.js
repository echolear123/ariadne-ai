/**
 * imageManager.js - 图片上传与管理（函数式，带详细日志）
 *
 * 所有函数都是纯函数或返回 Promise，不依赖 React 状态。
 * 日志前缀 [IMG] 方便在控制台中过滤。
 */

const API_BASE = '/api'

// ================================================================
// 日志工具
// ================================================================

function log(...args) {
  console.log('%c[IMG]', 'color:#0284c7;font-weight:bold', ...args)
}

function logError(...args) {
  console.error('%c[IMG]', 'color:#ef4444;font-weight:bold', ...args)
}

function logWarn(...args) {
  console.warn('%c[IMG]', 'color:#eab308;font-weight:bold', ...args)
}

// ================================================================
// 1. 上传图片文件到服务器
// ================================================================

/**
 * 将 File 对象上传到 /api/upload，返回 { url, filename } 或抛出错误
 * @param {File} file - 用户选择的文件
 * @returns {Promise<{url: string, filename: string}>}
 */
export async function uploadImage(file) {
  const tag = 'uploadImage'
  log(tag, '开始上传', { name: file.name, size: file.size, type: file.type })

  if (!file) {
    logError(tag, '文件为空')
    throw new Error('没有选择文件')
  }

  // 构建 FormData（注意：不能设置 Content-Type，浏览器自动设置 multipart boundary）
  const formData = new FormData()
  formData.append('file', file)

  const userId = localStorage.getItem('user_id') || 'default'
  log(tag, 'fetch /api/upload ...', { userId })

  let response
  try {
    response = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      headers: { 'X-User-Id': userId },  // 不设 Content-Type
      body: formData,
    })
  } catch (fetchErr) {
    logError(tag, 'fetch 网络错误:', fetchErr)
    throw fetchErr
  }

  log(tag, '响应状态:', response.status, response.statusText)

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    logError(tag, 'HTTP 错误:', response.status, text)
    throw new Error(`上传失败 HTTP ${response.status}: ${text}`)
  }

  let data
  try {
    data = await response.json()
  } catch (parseErr) {
    logError(tag, 'JSON 解析失败:', parseErr)
    throw parseErr
  }

  log(tag, '服务器返回:', data)

  if (!data.url) {
    logError(tag, '返回数据缺少 url 字段:', data)
    throw new Error('上传响应缺少 url: ' + JSON.stringify(data))
  }

  log(tag, '上传成功 ✓', data.url)
  return data  // { url: "/uploads/xxx.png", filename: "xxx.png" }
}

// ================================================================
// 2. 创建图像节点数据
// ================================================================

/**
 * 生成一个 type='image' 的画布节点对象（纯函数）
 * @param {string} src - 图片 URL（如 /uploads/xxx.png）
 * @param {string} caption - 图片标题
 * @param {{ x: number, y: number }} position - 画布坐标
 * @returns {{ id: string, type: 'image', x: number, y: number, width: number, data: { src: string, caption: string } }}
 */
export function createImageNode(src, caption = '', position = { x: 300, y: 200 }) {
  const id = 'img_' + Date.now().toString(36)
  const node = {
    id,
    type: 'image',
    x: position.x,
    y: position.y,
    width: 320,
    data: { src, caption },
  }
  log('createImageNode', '创建节点:', node.id, { src, caption })
  return node
}

// ================================================================
// 3. 计算新节点在当前视口中的位置
// ================================================================

/**
 * 根据当前 pan/scale 计算一个视口中央偏随机的画布坐标
 * @param {{ x: number, y: number }} pan
 * @param {number} scale
 * @returns {{ x: number, y: number }}
 */
export function calcViewportCenter(pan, scale) {
  return {
    x: -pan.x / scale + 250 + Math.random() * 150,
    y: -pan.y / scale + 200 + Math.random() * 100,
  }
}

// ================================================================
// 4. 完整的上传+添加流程（组合函数）
// ================================================================

/**
 * 上传图片文件并返回可添加到画布的 image 节点
 * @param {File} file
 * @param {{ x: number, y: number }} pan
 * @param {number} scale
 * @returns {Promise<object>} - 画布节点对象
 */
export async function uploadAndCreateNode(file, pan, scale) {
  const tag = 'uploadAndCreateNode'
  log(tag, '开始流程', { fileName: file?.name })

  const result = await uploadImage(file)
  const position = calcViewportCenter(pan, scale)
  const node = createImageNode(result.url, file.name, position)

  log(tag, '流程完成 ✓', { nodeId: node.id, src: node.data.src })
  return node
}

// ================================================================
// 5. 验证图片 URL 是否可访问
// ================================================================

/**
 * 验证图片 URL 是否可以正常加载
 * @param {string} src
 * @returns {Promise<boolean>}
 */
export function verifyImageAccessible(src) {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      log('verifyImageAccessible', '✓ 可访问:', src, { w: img.width, h: img.height })
      resolve(true)
    }
    img.onerror = (e) => {
      logError('verifyImageAccessible', '✗ 不可访问:', src, e)
      resolve(false)
    }
    img.src = src
  })
}

// ================================================================
// 6. 生成 Markdown 嵌入语法
// ================================================================

/**
 * 生成 Markdown 图片嵌入文本
 * @param {string} url
 * @param {string} alt
 * @returns {string}
 */
export function markdownImageSyntax(url, alt = '') {
  return `\n![${alt}](${url})\n`
}
