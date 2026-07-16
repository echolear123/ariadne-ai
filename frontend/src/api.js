const API_BASE = '/api'

function authHeaders() {
  const userId = localStorage.getItem('user_id')
  const headers = { 'Content-Type': 'application/json' }
  if (userId) headers['X-User-Id'] = userId
  return headers
}

export async function login(username, password) {
  const res = await fetch(`${API_BASE}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.error || '登录失败')
  }
  const data = await res.json()
  localStorage.setItem('user_id', data.user_id)
  localStorage.setItem('username', data.username)
  return data
}

export async function listConversations() {
  const res = await fetch(`${API_BASE}/conversations`, { headers: authHeaders() })
  if (!res.ok) return []
  return res.json()
}

// ============================================================
// 画布 API
// ============================================================

export async function listCanvases() {
  const res = await fetch(`${API_BASE}/canvases`, { headers: authHeaders() })
  if (!res.ok) return []
  return res.json()
}

export async function getCanvas(canvasId) {
  const res = await fetch(`${API_BASE}/canvas/${canvasId}`, { headers: authHeaders() })
  if (!res.ok) return null
  return res.json()
}

export async function createCanvas(title = '新画布') {
  const res = await fetch(`${API_BASE}/canvas`, {
    method: 'POST', headers: authHeaders(), body: JSON.stringify({ title })
  })
  if (!res.ok) return null
  return res.json()
}

export async function deleteCanvas(canvasId) {
  await fetch(`${API_BASE}/canvas/${canvasId}`, { method: 'DELETE', headers: authHeaders() })
}

export async function getConversation(conversationId) {
  const res = await fetch(`${API_BASE}/conversation/${conversationId}`, { headers: authHeaders() })
  if (!res.ok) return null
  return res.json()
}

export async function deleteConversation(conversationId) {
  await fetch(`${API_BASE}/conversation/${conversationId}`, { method: 'DELETE', headers: authHeaders() })
}

export async function sendMessage(message, conversationId, onToken) {
  const userId = localStorage.getItem('user_id') || 'default'
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      message,
      user_id: userId,
      conversation_id: conversationId || null
    })
  })

  if (!res.ok) throw new Error(`请求失败: ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let fullText = ''
  let resultConversationId = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // 按完整事件解析
    const parts = buffer.split('\n\n')
    buffer = parts.pop()  // 最后一段可能不完整

    for (const part of parts) {
      const lines = part.split('\n')
      let eventType = ''
      let dataStr = ''

      for (const line of lines) {
        if (line.startsWith('event: ')) eventType = line.slice(7)
        if (line.startsWith('data: ')) dataStr = line.slice(6)
      }

      if (!dataStr) continue

      try {
        const data = JSON.parse(dataStr)
        if (eventType === 'token' && data.text) {
          fullText += data.text
          if (onToken) onToken(data.text)
        } else if (eventType === 'done') {
          resultConversationId = data.conversation_id
        }
      } catch {
        // skip unparseable
      }
    }
  }

  return { answer: fullText, conversationId: resultConversationId }
}

// ============================================================
// 插件 API
// ============================================================

export async function listPlugins() {
  const res = await fetch(`${API_BASE}/plugins`, { headers: authHeaders() })
  if (!res.ok) return []
  return res.json()
}

export async function callPlugin(pluginName, toolName, args = {}) {
  const res = await fetch(`${API_BASE}/plugins/${pluginName}/${toolName}`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(args)
  })
  if (!res.ok) return { error: `请求失败: ${res.status}` }
  return res.json()
}

// ============================================================
// 文档管理 API
// ============================================================

export async function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${API_BASE}/upload-document`, {
    method: 'POST',
    headers: { 'X-User-Id': localStorage.getItem('user_id') || 'default' },
    body: formData
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || '上传失败')
  return data
}

export async function listDocuments() {
  const res = await fetch(`${API_BASE}/documents`, { headers: authHeaders() })
  if (!res.ok) return []
  return res.json()
}

export async function deleteDocument(filename) {
  const res = await fetch(`${API_BASE}/document/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
    headers: authHeaders()
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || '删除失败')
  return data
}

export async function updateDocumentNotes(filename, notes) {
  const res = await fetch(`${API_BASE}/document/${encodeURIComponent(filename)}/notes`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify({ notes })
  })
  if (!res.ok) throw new Error('更新备注失败')
  return res.json()
}

export function getDownloadUrl(filename) {
  return `${API_BASE}/document/${encodeURIComponent(filename)}/download`
}

// ============================================================
// 向量库管理 API
// ============================================================

export async function listVectorEntries(source = '') {
  const params = source ? `?source=${encodeURIComponent(source)}` : ''
  const res = await fetch(`${API_BASE}/vector-entries${params}`, { headers: authHeaders() })
  if (!res.ok) return { total: 0, entries: [] }
  return res.json()
}

export async function deleteVectorEntry(docId) {
  const res = await fetch(`${API_BASE}/vector-entry/${encodeURIComponent(docId)}`, {
    method: 'DELETE',
    headers: authHeaders()
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || '删除失败')
  return data
}

export async function getVectorStats() {
  const res = await fetch(`${API_BASE}/vector-stats`, { headers: authHeaders() })
  if (!res.ok) return { total_entries: 0, sources: {} }
  return res.json()
}

export async function vectorOptimize() {
  const res = await fetch(`${API_BASE}/vector-optimize`, { method: 'POST', headers: authHeaders() })
  return res.json()
}
