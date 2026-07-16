import { useState, useEffect, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { uploadImage, createImageNode, calcViewportCenter, uploadAndCreateNode, verifyImageAccessible, markdownImageSyntax } from '../imageManager'
import { sendMessage, getConversation } from '../api.js'

const API_BASE = '/api'

function authHeaders() {
  const userId = localStorage.getItem('user_id') || 'default'
  return { 'Content-Type': 'application/json', 'X-User-Id': userId }
}

const DRAW_COLORS = ['#ef4444','#f97316','#eab308','#22c55e','#3b82f6','#8b5cf6','#ec4899','#ffffff']
const STROKE_WIDTHS = [{ label: '细', value: 1.5 },{ label: '中', value: 3 },{ label: '粗', value: 5 }]

// 判断点击坐标是否在某个 drawing 的包围盒内
function hitTestDrawing(d, cx, cy) {
  const pad = 8
  switch (d.type) {
    case 'rect': {
      return cx >= d.x - pad && cx <= d.x + d.width + pad && cy >= d.y - pad && cy <= d.y + d.height + pad
    }
    case 'circle': {
      const ecx = d.x + d.width / 2, ecy = d.y + d.height / 2
      const rx = d.width / 2 + pad, ry = d.height / 2 + pad
      if (rx <= 0 || ry <= 0) return false
      return ((cx - ecx) ** 2) / (rx ** 2) + ((cy - ecy) ** 2) / (ry ** 2) <= 1
    }
    case 'arrow': {
      // 线段距离判断
      const dx = d.x2 - d.x1, dy = d.y2 - d.y1
      const len2 = dx * dx + dy * dy
      if (len2 === 0) return Math.hypot(cx - d.x1, cy - d.y1) < pad
      let t = ((cx - d.x1) * dx + (cy - d.y1) * dy) / len2
      t = Math.max(0, Math.min(1, t))
      const px = d.x1 + t * dx, py = d.y1 + t * dy
      return Math.hypot(cx - px, cy - py) < pad + 4
    }
    case 'pen': {
      if (!d.points || d.points.length < 2) return false
      for (let i = 1; i < d.points.length; i++) {
        const p1 = d.points[i - 1], p2 = d.points[i]
        const dx = p2.x - p1.x, dy = p2.y - p1.y
        const len2 = dx * dx + dy * dy
        let t = len2 === 0 ? 0 : ((cx - p1.x) * dx + (cy - p1.y) * dy) / len2
        t = Math.max(0, Math.min(1, t))
        const px = p1.x + t * dx, py = p1.y + t * dy
        if (Math.hypot(cx - px, cy - py) < pad + d.strokeWidth) return true
      }
      return false
    }
    default: return false
  }
}

// 获取 drawing 的包围盒中心
function drawingCenter(d) {
  switch (d.type) {
    case 'rect': return { x: d.x + d.width / 2, y: d.y + d.height / 2 }
    case 'circle': return { x: d.x + d.width / 2, y: d.y + d.height / 2 }
    case 'arrow': return { x: (d.x1 + d.x2) / 2, y: (d.y1 + d.y2) / 2 }
    case 'pen': {
      if (!d.points || d.points.length === 0) return { x: 0, y: 0 }
      const sum = d.points.reduce((a, p) => ({ x: a.x + p.x, y: a.y + p.y }), { x: 0, y: 0 })
      return { x: sum.x / d.points.length, y: sum.y / d.points.length }
    }
    default: return { x: 0, y: 0 }
  }
}

// 平移 drawing
function moveDrawing(d, dx, dy) {
  switch (d.type) {
    case 'rect': return { ...d, x: d.x + dx, y: d.y + dy }
    case 'circle': return { ...d, x: d.x + dx, y: d.y + dy }
    case 'arrow': return { ...d, x1: d.x1 + dx, y1: d.y1 + dy, x2: d.x2 + dx, y2: d.y2 + dy }
    case 'pen': return { ...d, points: d.points.map(p => ({ x: p.x + dx, y: p.y + dy })) }
    default: return d
  }
}

// ================================================================
// CanvasPage - Markdown 画布主组件（含绘图/标注/图片）
// ================================================================

export default function CanvasPage({ canvasId, onBack }) {
  const [canvas, setCanvas] = useState({ id: canvasId, title: '', nodes: [], edges: [], drawings: [] })
  const [loading, setLoading] = useState(true)
  const [scale, setScale] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [selectedNode, setSelectedNode] = useState(null)
  const [selectedEdge, setSelectedEdge] = useState(null)
  const [contextMenu, setContextMenu] = useState(null) // { edgeId, x, y }
  const [editingNode, setEditingNode] = useState(null)
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')

  // 连线创建状态
  const [connecting, setConnecting] = useState(null)
  const connectingRef = useRef(null)
  const [dragNode, setDragNode] = useState(null)

  // 绘图工具状态
  const [activeTool, setActiveTool] = useState('select') // select | pen | eraser | rect | circle | arrow
  const [drawColor, setDrawColor] = useState('#ef4444')
  const [strokeWidth, setStrokeWidth] = useState(3)
  const [currentDrawing, setCurrentDrawing] = useState(null)

  // 选中标注 + 拖拽
  const [selectedDrawing, setSelectedDrawing] = useState(null)
  const [dragDrawing, setDragDrawing] = useState(null)
  const drawDragOffset = useRef({ x: 0, y: 0 })

  // AI 面板
  const [showAI, setShowAI] = useState(false)
  const [aiInput, setAiInput] = useState('')
  const [aiMessages, setAiMessages] = useState([])
  const [aiLoading, setAiLoading] = useState(false)
  const aiStreamingRef = useRef('')
  const aiConvIdRef = useRef(null)  // 画布对应的 AI 对话 ID

  // 总结弹窗
  const [showSummary, setShowSummary] = useState(false)
  const [summaryContent, setSummaryContent] = useState('')

  const canvasRef = useRef(null)
  const dragOffset = useRef({ x: 0, y: 0 })
  const currentDrawingRef = useRef(null)
  const canvasStateRef = useRef(canvas)
  const panRef = useRef(pan)
  const scaleRef = useRef(scale)

  useEffect(() => { canvasStateRef.current = canvas }, [canvas])
  useEffect(() => { panRef.current = pan }, [pan])
  useEffect(() => { scaleRef.current = scale }, [scale])

  const imageInputRef = useRef(null)
  const embedImageInputRef = useRef(null)

  // --- Load / Save ---
  async function loadCanvas() {
    try {
      const res = await fetch(`${API_BASE}/canvas/${canvasId}`, { headers: authHeaders() })
      const data = await res.json()
      if (!data.drawings) data.drawings = []
      if (data.nodes) data.nodes.forEach(n => { if (!n.type) n.type = 'markdown' })
      setCanvas(data)
    } catch (e) { /* */ }
    setLoading(false)
  }

  useEffect(() => { loadCanvas() }, [canvasId])

  async function saveCanvas(data) {
    setCanvas(data)
    canvasStateRef.current = data
    try {
      await fetch(`${API_BASE}/canvas/${canvasId}`, {
        method: 'PUT', headers: authHeaders(), body: JSON.stringify(data)
      })
    } catch (e) { /* */ }
  }

  // --- Node CRUD ---
  function addNode() {
    const id = 'n_' + Date.now().toString(36)
    const newNode = {
      id, type: 'markdown',
      x: -pan.x / scale + 200 + Math.random() * 200,
      y: -pan.y / scale + 150 + Math.random() * 120,
      width: 320, height: 'auto',
      data: { title: '新卡片', content: '双击或右键编辑 Markdown 内容...' }
    }
    const newCanvas = { ...canvas, nodes: [...canvas.nodes, newNode] }
    saveCanvas(newCanvas)
  }

  function deleteNode(nodeId) {
    const newNodes = canvas.nodes.filter(n => n.id !== nodeId)
    const newEdges = canvas.edges.filter(e => e.source !== nodeId && e.target !== nodeId)
    saveCanvas({ ...canvas, nodes: newNodes, edges: newEdges })
  }

  function updateNode(id, updates) {
    const newNodes = canvas.nodes.map(n => n.id === id ? { ...n, ...updates } : n)
    saveCanvas({ ...canvas, nodes: newNodes })
  }

  function startEdit(node) {
    setEditingNode(node.id)
    setEditTitle(node.data?.title || '')
    setEditContent(node.data?.content || '')
  }

  function saveEdit() {
    if (!editingNode) return
    updateNode(editingNode, { data: { title: editTitle, content: editContent } })
    setEditingNode(null)
  }

  // --- Edge CRUD ---
  function addEdge(sourceId, targetId) {
    if (sourceId === targetId) return
    const exists = canvas.edges.some(e => e.source === sourceId && e.target === targetId)
    if (exists) return
    const newEdges = [...canvas.edges, { id: 'e_' + Date.now().toString(36), source: sourceId, target: targetId, label: '' }]
    saveCanvas({ ...canvas, edges: newEdges })
  }

  function deleteEdge(edgeId) {
    saveCanvas({ ...canvas, edges: canvas.edges.filter(e => e.id !== edgeId) })
  }

  // --- Drawing CRUD ---
  function screenToCanvas(clientX, clientY) {
    const rect = canvasRef.current.getBoundingClientRect()
    return {
      x: (clientX - rect.left - pan.x) / scale,
      y: (clientY - rect.top - pan.y) / scale
    }
  }

  function finalizeDrawing(drawing) {
    const id = 'd_' + Date.now().toString(36)
    let drawingData

    if (drawing.type === 'pen') {
      if (drawing.points.length < 2) return
      drawingData = { id, type: 'pen', color: drawing.color, strokeWidth: drawing.strokeWidth, points: drawing.points }
    } else if (drawing.type === 'rect') {
      const x = Math.min(drawing.startX, drawing.endX)
      const y = Math.min(drawing.startY, drawing.endY)
      const w = Math.abs(drawing.endX - drawing.startX)
      const h = Math.abs(drawing.endY - drawing.startY)
      if (w < 5 && h < 5) return
      drawingData = { id, type: 'rect', color: drawing.color, strokeWidth: drawing.strokeWidth, x, y, width: w, height: h }
    } else if (drawing.type === 'circle') {
      const x = Math.min(drawing.startX, drawing.endX)
      const y = Math.min(drawing.startY, drawing.endY)
      const w = Math.abs(drawing.endX - drawing.startX)
      const h = Math.abs(drawing.endY - drawing.startY)
      if (w < 5 && h < 5) return
      drawingData = { id, type: 'circle', color: drawing.color, strokeWidth: drawing.strokeWidth, x, y, width: w, height: h }
    } else if (drawing.type === 'arrow') {
      const dist = Math.hypot(drawing.endX - drawing.startX, drawing.endY - drawing.startY)
      if (dist < 5) return
      drawingData = { id, type: 'arrow', color: drawing.color, strokeWidth: drawing.strokeWidth, x1: drawing.startX, y1: drawing.startY, x2: drawing.endX, y2: drawing.endY }
    }

    if (drawingData) {
      const drawings = [...(canvasStateRef.current.drawings || []), drawingData]
      saveCanvas({ ...canvasStateRef.current, drawings })
    }
  }

  function undoDrawing() {
    const drawings = canvas.drawings || []
    if (drawings.length === 0) return
    saveCanvas({ ...canvas, drawings: drawings.slice(0, -1) })
  }

  function clearDrawings() {
    saveCanvas({ ...canvas, drawings: [] })
  }

  function deleteDrawing(drawId) {
    saveCanvas({ ...canvas, drawings: (canvas.drawings || []).filter(d => d.id !== drawId) })
    if (selectedDrawing === drawId) setSelectedDrawing(null)
  }

  function updateDrawing(drawId, updated) {
    const drawings = (canvas.drawings || []).map(d => d.id === drawId ? updated : d)
    saveCanvas({ ...canvas, drawings })
  }

  // --- 图片上传（使用 imageManager 函数式模块） ---
  async function handleImageUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    console.log('[CanvasPage] handleImageUpload 开始, file:', file.name, file.size, 'bytes')
    try {
      const node = await uploadAndCreateNode(file, pan, scale)
      console.log('[CanvasPage] 图片节点创建成功:', node.id, node.data.src)
      // 验证图片是否可访问
      verifyImageAccessible(node.data.src)
      saveCanvas({ ...canvasStateRef.current, nodes: [...canvasStateRef.current.nodes, node] })
    } catch (err) {
      console.error('[CanvasPage] 上传图片失败:', err)
    }
    e.target.value = ''
  }

  async function handleEmbedImage(e) {
    const file = e.target.files?.[0]
    if (!file || !editingNode) return
    console.log('[CanvasPage] handleEmbedImage 开始, file:', file.name)
    try {
      const result = await uploadImage(file)
      console.log('[CanvasPage] 嵌入图片上传成功:', result.url)
      setEditContent(prev => prev + markdownImageSyntax(result.url, file.name))
    } catch (err) {
      console.error('[CanvasPage] 嵌入图片失败:', err)
    }
    e.target.value = ''
  }

  // --- Mouse Handlers ---
  function onNodeMouseDown(e, nodeId) {
    if (activeTool !== 'select' && activeTool !== 'eraser') return
    if (e.button === 2) { setSelectedNode(nodeId); return }
    if (e.target.closest('[data-action]') || e.target.tagName === 'TEXTAREA') return
    e.stopPropagation()
    if (activeTool === 'eraser') return // 橡皮擦不作用于卡片
    setDragNode(nodeId)
    dragOffset.current = { x: e.clientX, y: e.clientY }
  }

  function onCanvasMouseDown(e) {
    if (e.button !== 0) return
    if (e.target.closest('[data-action]') || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON') return

    const { x: cx, y: cy } = screenToCanvas(e.clientX, e.clientY)

    // --- 橡皮擦模式：点击删除标注 ---
    if (activeTool === 'eraser') {
      e.stopPropagation()
      const drawings = canvas.drawings || []
      // 从后往前检测（后画的在上面）
      for (let i = drawings.length - 1; i >= 0; i--) {
        if (hitTestDrawing(drawings[i], cx, cy)) {
          deleteDrawing(drawings[i].id)
          return
        }
      }
      return
    }

    // --- 绘图模式 ---
    if (activeTool !== 'select') {
      e.stopPropagation()

      if (activeTool === 'pen') {
        const d = { type: 'pen', color: drawColor, strokeWidth, points: [{ x: cx, y: cy }] }
        currentDrawingRef.current = d
        setCurrentDrawing(d)
      } else {
        const d = { type: activeTool, color: drawColor, strokeWidth, startX: cx, startY: cy, endX: cx, endY: cy }
        currentDrawingRef.current = d
        setCurrentDrawing(d)
      }

      function onMove(ev) {
        const { x: nx, y: ny } = screenToCanvas(ev.clientX, ev.clientY)
        const ref = currentDrawingRef.current
        if (!ref) return

        if (ref.type === 'pen') {
          ref.points.push({ x: nx, y: ny })
          setCurrentDrawing({ ...ref, points: [...ref.points] })
        } else {
          ref.endX = nx; ref.endY = ny
          setCurrentDrawing({ ...ref })
        }
      }

      function onUp() {
        const d = currentDrawingRef.current
        if (d) finalizeDrawing(d)
        currentDrawingRef.current = null
        setCurrentDrawing(null)
        window.removeEventListener('mousemove', onMove)
        window.removeEventListener('mouseup', onUp)
      }

      window.addEventListener('mousemove', onMove)
      window.addEventListener('mouseup', onUp)
      return
    }

    // --- 选择模式 ---
    // 先检测是否点中了某个 drawing
    const drawings = canvas.drawings || []
    for (let i = drawings.length - 1; i >= 0; i--) {
      if (hitTestDrawing(drawings[i], cx, cy)) {
        e.stopPropagation()
        const d = drawings[i]
        setSelectedDrawing(d.id)
        setSelectedNode(null)
        setDragDrawing(d.id)
        const center = drawingCenter(d)
        drawDragOffset.current = { x: cx - center.x, y: cy - center.y }
        return
      }
    }

    // 没有点中 drawing：平移画布
    setSelectedDrawing(null)
    const startX = e.clientX - pan.x
    const startY = e.clientY - pan.y
    function onMove(ev) {
      setPan({ x: ev.clientX - startX, y: ev.clientY - startY })
    }
    function onUp() {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    setSelectedNode(null)
    setSelectedEdge(null)
  }

  // --- 拖拽节点 ---
  useEffect(() => {
    if (!dragNode) return
    function move(e) {
      const node = canvas.nodes.find(n => n.id === dragNode)
      if (!node) return
      const dx = e.clientX - dragOffset.current.x
      const dy = e.clientY - dragOffset.current.y
      dragOffset.current = { x: e.clientX, y: e.clientY }
      updateNode(dragNode, {
        x: node.x + dx / scale,
        y: node.y + dy / scale
      })
    }
    function up() { setDragNode(null) }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
    return () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
    }
  }, [dragNode, canvas, scale])

  // --- 拖拽标注形状 ---
  useEffect(() => {
    if (!dragDrawing) return
    function move(e) {
      const { x: cx, y: cy } = screenToCanvas(e.clientX, e.clientY)
      const d = (canvas.drawings || []).find(dr => dr.id === dragDrawing)
      if (!d) return
      const center = drawingCenter(d)
      const dx = cx - drawDragOffset.current.x - center.x
      const dy = cy - drawDragOffset.current.y - center.y
      const updated = moveDrawing(d, dx, dy)
      updateDrawing(dragDrawing, updated)
    }
    function up() { setDragDrawing(null) }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
    return () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
    }
  }, [dragDrawing, canvas, scale])

  function onWheel(e) {
    e.preventDefault()
    const dir = e.deltaY > 0 ? -0.08 : 0.08
    setScale(prev => Math.max(0.2, Math.min(3, prev + dir)))
  }

  // 开始连线
  function startConnecting(e, nodeId) {
    e.stopPropagation(); e.preventDefault()
    const sourceId = nodeId
    setConnecting({ sourceId, mx: e.clientX, my: e.clientY })
    connectingRef.current = sourceId

    function move(ev) {
      setConnecting(prev => prev ? { ...prev, mx: ev.clientX, my: ev.clientY } : null)
    }
    function up(ev) {
      const sid = connectingRef.current
      if (!sid) { cleanup(); return }

      // 用坐标碰撞检测替代 elementFromPoint（更可靠，不受 SVG 层干扰）
      const rect = canvasRef.current.getBoundingClientRect()
      const p = panRef.current
      const s = scaleRef.current
      const cx = (ev.clientX - rect.left - p.x) / s
      const cy = (ev.clientY - rect.top - p.y) / s

      const nodes = canvasStateRef.current.nodes
      for (const node of nodes) {
        if (node.id === sid) continue
        const nw = node.width || 320
        const nh = typeof node.height === 'number' ? node.height : 160
        if (cx >= node.x && cx <= node.x + nw && cy >= node.y && cy <= node.y + nh) {
          addEdge(sid, node.id)
          break
        }
      }
      cleanup()
    }
    function cleanup() {
      setConnecting(null); connectingRef.current = null
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
    }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }

  // --- AI Chat ---
  async function sendAIMessage() {
    const q = aiInput.trim()
    if (!q) return

    const cardsDesc = canvas.nodes.map((n, i) => {
      const title = n.data?.title || '未命名'
      const content = n.data?.content || '(空)'
      return `### 卡片${i + 1}: ${title}\n${content}`
    }).join('\n\n')

    const edgesDesc = canvas.edges.length > 0
      ? canvas.edges.map(e => {
          const src = canvas.nodes.find(n => n.id === e.source)
          const tgt = canvas.nodes.find(n => n.id === e.target)
          return `- 「${src?.data?.title || e.source}」→ 「${tgt?.data?.title || e.target}」${e.label ? ` (${e.label})` : ''}`
        }).join('\n')
      : '无连线'

    const contextStr = [
      `画布名称: ${canvas.title || '未命名'}`,
      `卡片数量: ${canvas.nodes.length}`,
      `连线数量: ${canvas.edges.length}`,
      '',
      '--- 卡片内容 ---',
      cardsDesc,
      '',
      '--- 连线关系 ---',
      edgesDesc,
    ].join('\n')

    const finalQuery = `画布「${canvas.title || '未命名'}」\n\n请基于以下画布完整上下文回答，忽略知识库检索结果：\n\n${contextStr}\n\n---\n用户问题: ${q}`

    setAiInput('')
    setAiMessages(prev => [...prev, { role: 'user', content: q }, { role: 'agent', content: '思考中...' }])
    setAiLoading(true)
    aiStreamingRef.current = ''

    try {
      const { answer, conversationId: cid } = await sendMessage(finalQuery, aiConvIdRef.current, (token) => {
        aiStreamingRef.current += token
        setAiMessages(prev => {
          const msgs = [...prev]
          msgs[msgs.length - 1] = { role: 'agent', content: aiStreamingRef.current + ' |' }
          return msgs
        })
      })
      // 保存对话 ID 到 localStorage，下次打开恢复
      if (cid) {
        aiConvIdRef.current = cid
        localStorage.setItem(`ai_conv_${canvasId}`, cid)
      }
      setAiMessages(prev => {
        const msgs = [...prev]
        msgs[msgs.length - 1] = { role: 'agent', content: answer }
        return msgs
      })
    } catch (e) {
      setAiMessages(prev => [...prev, { role: 'agent', content: '请求失败: ' + e.message }])
    }
    setAiLoading(false)
  }

  // 打开 AI 面板时加载已有对话历史
  async function loadAIConversation() {
    const savedId = localStorage.getItem(`ai_conv_${canvasId}`)
    if (!savedId) return
    aiConvIdRef.current = savedId
    try {
      const data = await getConversation(savedId)
      if (data && data.turns) {
        const msgs = []
        for (const t of data.turns) {
          msgs.push({ role: 'user', content: t.query })
          msgs.push({ role: 'agent', content: t.answer })
        }
        setAiMessages(msgs)
      }
    } catch (e) { /* */ }
  }

  // --- 总结卡片 ---
  async function summarizeCards() {
    try {
      const res = await fetch(`${API_BASE}/plugins/canvas_md/summarize_cards`, {
        method: 'POST', headers: authHeaders(),
        body: JSON.stringify({ canvas_id: canvasId })
      })
      const r = await res.json()
      if (r.content) {
        const data = JSON.parse(r.content[0].text)
        setSummaryContent(data.summary)
        setShowSummary(true)
      }
    } catch (e) {
      setSummaryContent('总结失败: ' + e.message)
      setShowSummary(true)
    }
  }

  // --- 右键菜单自动关闭 ---
  useEffect(() => {
    if (!contextMenu) return
    function close() { setContextMenu(null) }
    window.addEventListener('click', close)
    return () => window.removeEventListener('click', close)
  }, [contextMenu])

  // 打开 AI 面板时恢复对话
  useEffect(() => {
    if (showAI) loadAIConversation()
  }, [showAI])

  // --- Keyboard ---
  useEffect(() => {
    function key(e) {
      if (e.key === 'Delete') {
        if (selectedNode && editingNode !== selectedNode) {
          deleteNode(selectedNode)
          setSelectedNode(null)
        }
        if (selectedDrawing) {
          deleteDrawing(selectedDrawing)
          setSelectedDrawing(null)
        }
        if (selectedEdge) {
          deleteEdge(selectedEdge)
          setSelectedEdge(null)
        }
      }
      if (e.key === 'Enter' && selectedNode && editingNode !== selectedNode) {
        const node = canvas.nodes.find(n => n.id === selectedNode)
        if (node) startEdit(node)
      }
      if (e.key === 'Escape') { setSelectedNode(null); setSelectedEdge(null); setEditingNode(null); setActiveTool('select'); setSelectedDrawing(null); setCurrentDrawing(null); currentDrawingRef.current = null }
      if (e.key === 'n' && e.ctrlKey) { e.preventDefault(); addNode() }
      if ((e.key === 'z' || e.key === 'Z') && (e.ctrlKey || e.metaKey)) { e.preventDefault(); undoDrawing() }
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [selectedNode, selectedEdge, editingNode, selectedDrawing, canvas])

  // --- Edge path ---
  function edgePath(src, tgt) {
    if (!src || !tgt) return ''
    const sh = typeof src.height === 'number' ? src.height : 160
    const th = typeof tgt.height === 'number' ? tgt.height : 160
    const sx = src.x + (src.width || 320) / 2, sy = src.y + sh / 2
    const tx = tgt.x + (tgt.width || 320) / 2, ty = tgt.y + th / 2
    const cx1 = sx + Math.abs(tx - sx) * 0.4, cy1 = sy
    const cx2 = tx - Math.abs(tx - sx) * 0.4, cy2 = ty
    return `M${sx},${sy} C${cx1},${cy1} ${cx2},${cy2} ${tx},${ty}`
  }

  // --- 绘制渲染 ---
  function renderDrawing(d, isPreview = false) {
    const isSelected = !isPreview && selectedDrawing === d.id
    const isDragged = !isPreview && dragDrawing === d.id
    const common = {
      opacity: isPreview ? 0.7 : 1,
      style: { pointerEvents: 'auto', cursor: activeTool === 'eraser' ? 'pointer' : (activeTool === 'select' ? 'move' : 'crosshair') },
      onClick: activeTool === 'eraser' ? (() => !isPreview && deleteDrawing(d.id)) : undefined,
    }

    // 选中时的高亮边框
    const selectedStroke = isSelected ? { filter: 'drop-shadow(0 0 4px rgba(129,140,248,0.8))' } : {}
    const dragStroke = isDragged ? { filter: 'drop-shadow(0 0 3px rgba(99,102,241,0.6))' } : {}

    switch (d.type) {
      case 'pen':
        return <polyline key={d.id} points={d.points.map(p => `${p.x},${p.y}`).join(' ')} fill="none" stroke={d.color} strokeWidth={d.strokeWidth + (isSelected ? 1 : 0)} strokeLinecap="round" strokeLinejoin="round" {...common} {...selectedStroke} {...dragStroke} />
      case 'rect':
        return <rect key={d.id} x={d.x} y={d.y} width={d.width} height={d.height} fill={isSelected ? 'rgba(99,102,241,0.08)' : 'none'} stroke={d.color} strokeWidth={d.strokeWidth + (isSelected ? 1 : 0)} rx={3} {...common} {...selectedStroke} {...dragStroke} />
      case 'circle':
        return <ellipse key={d.id} cx={d.x + d.width / 2} cy={d.y + d.height / 2} rx={d.width / 2} ry={d.height / 2} fill={isSelected ? 'rgba(99,102,241,0.08)' : 'none'} stroke={d.color} strokeWidth={d.strokeWidth + (isSelected ? 1 : 0)} {...common} {...selectedStroke} {...dragStroke} />
      case 'arrow': {
        const dx = d.x2 - d.x1, dy = d.y2 - d.y1
        const len = Math.hypot(dx, dy) || 1
        const headLen = Math.min(14, len * 0.3)
        const ux = dx / len, uy = dy / len
        const ax = d.x2 - ux * headLen, ay = d.y2 - uy * headLen
        const px = -uy * headLen * 0.4, py = ux * headLen * 0.4
        return (
          <g key={d.id} {...common} {...selectedStroke} {...dragStroke}>
            <line x1={d.x1} y1={d.y1} x2={d.x2} y2={d.y2} stroke={d.color} strokeWidth={d.strokeWidth + (isSelected ? 1 : 0)} strokeLinecap="round" />
            <polygon points={`${d.x2},${d.y2} ${ax + px},${ay + py} ${ax - px},${ay - py}`} fill={d.color} />
          </g>
        )
      }
      default: return null
    }
  }

  // ============================================================
  // 渲染
  // ============================================================

  if (loading) return (
    <div style={styles.container}>
      <div style={{ color: '#94a3b8', textAlign: 'center', paddingTop: 100, fontSize: 14 }}>加载画布...</div>
    </div>
  )

  const toolCursors = { select: 'grab', pen: 'crosshair', eraser: 'pointer', rect: 'crosshair', circle: 'crosshair', arrow: 'crosshair' }
  const viewportCursor = toolCursors[activeTool] || 'grab'

  return (
    <div style={styles.container}>
      <style>{`
        .canvas-md h1 { font-size: 15px; font-weight: 700; color: #f1f5f9; margin: 6px 0; }
        .canvas-md h2 { font-size: 13px; font-weight: 600; color: #e2e8f0; margin: 5px 0; border-bottom: 1px solid #334155; padding-bottom: 3px; }
        .canvas-md h3 { font-size: 12px; font-weight: 600; color: #cbd5e1; margin: 4px 0; }
        .canvas-md p { margin: 3px 0; color: #cbd5e1; }
        .canvas-md ul, .canvas-md ol { padding-left: 16px; margin: 3px 0; }
        .canvas-md li { margin: 1px 0; color: #cbd5e1; }
        .canvas-md code { background: #334155; color: #f472b6; padding: 1px 5px; border-radius: 3px; font-size: 11px; font-family: monospace; }
        .canvas-md pre { background: #0f172a; padding: 8px 10px; border-radius: 6px; overflow-x: auto; margin: 4px 0; }
        .canvas-md pre code { background: none; padding: 0; color: #e2e8f0; }
        .canvas-md blockquote { border-left: 3px solid #6366f1; padding-left: 10px; margin: 4px 0; color: #94a3b8; }
        .canvas-md table { border-collapse: collapse; width: 100%; margin: 4px 0; font-size: 11px; }
        .canvas-md th { background: #334155; color: #e2e8f0; padding: 3px 6px; border: 1px solid #475569; text-align: left; }
        .canvas-md td { padding: 3px 6px; border: 1px solid #475569; color: #cbd5e1; }
        .canvas-md a { color: #818cf8; }
        .canvas-md strong { color: #f1f5f9; }
        .canvas-md hr { border: none; border-top: 1px solid #334155; margin: 6px 0; }
        .canvas-md em { color: #fbbf24; font-style: italic; }
        .canvas-md img { max-width: 100%; border-radius: 6px; margin: 4px 0; }
      `}</style>

      {/* 工具栏 */}
      <div style={styles.toolbar}>
        <button onClick={() => { saveCanvas(canvas); onBack() }} style={tbBtn}>← 聊天</button>
        <div style={{ flex: 1, textAlign: 'center', fontWeight: 600, fontSize: 14, color: '#f1f5f9' }}>
          {canvas.title || '画布'}
        </div>
        <span style={tbInfo}>{canvas.nodes.length} 节点 · {canvas.edges.length} 连线 · {(canvas.drawings || []).length} 标注</span>
        <button onClick={addNode} style={{ ...tbBtn, background: '#059669' }}>+ 卡片</button>
        <button onClick={() => imageInputRef.current?.click()} style={{ ...tbBtn, background: '#0284c7' }}>📷 图片</button>
        <input ref={imageInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleImageUpload} />
        <button onClick={summarizeCards} style={{ ...tbBtn, background: '#f59e0b' }}>📝 总结</button>
        <button onClick={() => setShowAI(!showAI)} style={{ ...tbBtn, background: showAI ? '#7c3aed' : '#4f46e5' }}>
          🤖 AI
        </button>
        <button onClick={() => setScale(s => Math.min(3, s + 0.15))} style={tbBtn}>+</button>
        <span style={{ color: '#94a3b8', fontSize: 12, minWidth: 36, textAlign: 'center' }}>{Math.round(scale * 100)}%</span>
        <button onClick={() => setScale(s => Math.max(0.2, s - 0.15))} style={tbBtn}>-</button>
      </div>

      {/* 画布主区域 */}
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        {/* 工具面板 */}
        <div style={styles.toolPalette}>
          {[
            { id: 'select', icon: '↖', tip: '选择/平移/拖动标注' },
            { id: 'pen', icon: '✏', tip: '画笔' },
            { id: 'eraser', icon: '⊘', tip: '橡皮擦（点击删除标注）' },
            { id: 'rect', icon: '□', tip: '矩形' },
            { id: 'circle', icon: '○', tip: '椭圆' },
            { id: 'arrow', icon: '→', tip: '箭头' },
          ].map(t => (
            <button key={t.id} title={t.tip}
              onClick={() => { setActiveTool(t.id); if (t.id !== 'select') { setSelectedNode(null); setEditingNode(null); setSelectedDrawing(null) } }}
              style={{
                ...toolBtn,
                background: activeTool === t.id ? '#4f46e5' : '#1e293b',
                color: activeTool === t.id ? '#fff' : '#94a3b8',
                boxShadow: activeTool === t.id ? '0 0 0 2px #818cf8' : 'none',
              }}
            >{t.icon}</button>
          ))}

          <div style={styles.toolDivider} />

          {/* 颜色选择 */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, justifyContent: 'center', padding: '0 2px' }}>
            {DRAW_COLORS.map(c => (
              <div key={c} title={c}
                onClick={() => setDrawColor(c)}
                style={{
                  width: 18, height: 18, borderRadius: 4, background: c, cursor: 'pointer',
                  border: drawColor === c ? '2px solid #fff' : '2px solid #475569',
                  boxShadow: drawColor === c ? '0 0 6px rgba(255,255,255,0.3)' : 'none',
                }}
              />
            ))}
          </div>

          <div style={styles.toolDivider} />

          {/* 线宽选择 */}
          {STROKE_WIDTHS.map(sw => (
            <button key={sw.value} title={`线宽: ${sw.label}`}
              onClick={() => setStrokeWidth(sw.value)}
              style={{
                ...toolBtn,
                background: strokeWidth === sw.value ? '#4f46e5' : '#1e293b',
                color: strokeWidth === sw.value ? '#fff' : '#94a3b8',
                fontSize: 10,
              }}
            >{sw.label}</button>
          ))}

          <div style={styles.toolDivider} />

          {/* 撤销/清除 */}
          <button title="撤销标注 (Ctrl+Z)" onClick={undoDrawing} style={{ ...toolBtn, color: '#94a3b8', fontSize: 12 }}>↩</button>
          <button title="清除所有标注" onClick={clearDrawings} style={{ ...toolBtn, color: '#f87171', fontSize: 12 }}>🗑</button>
        </div>

        {/* 画布视口 */}
        <div
          ref={canvasRef}
          style={{ ...styles.viewport, cursor: viewportCursor }}
          onMouseDown={onCanvasMouseDown}
          onWheel={onWheel}
          onContextMenu={e => e.preventDefault()}
        >
          <div style={{
            ...styles.canvas,
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
            transformOrigin: '0 0'
          }}>
            {/* 网格背景 */}
            <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 0 }}>
              <defs>
                <pattern id="grid" width={30} height={30} patternUnits="userSpaceOnUse">
                  <path d="M 30 0 L 0 0 0 30" fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth={0.5} />
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#grid)" />
            </svg>

            {/* 绘图/标注 SVG 层 */}
            <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 1, overflow: 'visible' }}>
              {(canvas.drawings || []).map(d => renderDrawing(d))}
              {currentDrawing && renderDrawing({ ...currentDrawing, id: '__preview__' }, true)}
            </svg>

            {/* Edges (SVG layer) */}
            <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 2, overflow: 'visible' }}>
              {canvas.edges.map(e => {
                const src = canvas.nodes.find(n => n.id === e.source)
                const tgt = canvas.nodes.find(n => n.id === e.target)
                if (!src || !tgt) return null
                const pathD = edgePath(src, tgt)
                const sh = typeof src.height === 'number' ? src.height : 160
                const th = typeof tgt.height === 'number' ? tgt.height : 160
                const mx = (src.x + (src.width || 320) / 2 + tgt.x + (tgt.width || 320) / 2) / 2
                const my = (src.y + sh / 2 + tgt.y + th / 2) / 2
                return (
                  <g key={e.id} style={{ pointerEvents: 'auto', cursor: 'pointer' }}
                    onMouseDown={ev => { ev.stopPropagation(); setSelectedEdge(e.id); setSelectedNode(null); setContextMenu(null) }}
                    onContextMenu={ev => { ev.preventDefault(); ev.stopPropagation(); setContextMenu({ edgeId: e.id, x: ev.clientX, y: ev.clientY }) }}>
                    {/* 透明宽路径作为点击热区 */}
                    <path d={pathD} fill="none" stroke="transparent" strokeWidth={14} />
                    <path d={pathD} fill="none"
                      stroke={selectedEdge === e.id ? '#f59e0b' : '#6366f1'}
                      strokeWidth={selectedEdge === e.id ? 3 : 2}
                      opacity={selectedEdge === e.id ? 1 : 0.7}
                      style={selectedEdge === e.id ? { filter: 'drop-shadow(0 0 6px rgba(245,158,11,0.8))' } : {}} />
                    <defs><marker id={`arrow-${e.id}`} viewBox="0 0 10 10" refX={8} refY={5} markerWidth={6} markerHeight={6} orient="auto-start-reverse">
                      <path d="M 0 0 L 10 5 L 0 10 z" fill={selectedEdge === e.id ? '#f59e0b' : '#6366f1'} />
                    </marker></defs>
                    <path d={pathD} fill="none"
                      stroke={selectedEdge === e.id ? '#f59e0b' : '#6366f1'}
                      strokeWidth={selectedEdge === e.id ? 3 : 2}
                      opacity={selectedEdge === e.id ? 1 : 0.7}
                      markerEnd={`url(#arrow-${e.id})`} />
                    {e.label && (
                      <rect x={mx - 30} y={my - 13} width={60} height={18} rx={4} fill="rgba(30,30,60,0.9)" stroke="#4f46e5" strokeWidth={0.5} />
                    )}
                    {e.label && <text x={mx} y={my} textAnchor="middle" fill="#a5b4fc" fontSize={10} dominantBaseline="middle">{e.label}</text>}
                  </g>
                )
              })}

              {/* 连线拖拽预览 */}
              {connecting && (() => {
                const src = canvas.nodes.find(n => n.id === connecting.sourceId)
                if (!src) return null
                const sh = typeof src.height === 'number' ? src.height : 160
                const sx = src.x + (src.width || 320) / 2
                const sy = src.y + sh / 2
                const tx = (connecting.mx - pan.x) / scale
                const ty = (connecting.my - pan.y) / scale
                return (
                  <line x1={sx} y1={sy} x2={tx} y2={ty}
                    stroke="#818cf8" strokeWidth={2 / scale} strokeDasharray={`${5 / scale},${5 / scale}`} opacity={0.6} />
                )
              })()}
            </svg>

            {/* Nodes */}
            {canvas.nodes.map(node => {
              if (node.type === 'image') {
                return (
                  <div
                    key={node.id}
                    data-node-id={node.id}
                    style={{
                      ...styles.imgCard,
                      left: node.x, top: node.y,
                      width: node.width || 320,
                      borderColor: selectedNode === node.id ? '#818cf8' : dragNode === node.id ? '#6366f1' : 'transparent',
                      boxShadow: selectedNode === node.id
                        ? '0 0 0 2px #818cf8, 0 8px 25px rgba(0,0,0,0.5)'
                        : dragNode === node.id
                          ? '0 12px 30px rgba(0,0,0,0.6)'
                          : '0 2px 10px rgba(0,0,0,0.4)',
                      zIndex: dragNode === node.id || selectedNode === node.id ? 100 : 10,
                      cursor: activeTool === 'select' ? (dragNode === node.id ? 'grabbing' : 'grab') : 'crosshair',
                    }}
                    onMouseDown={e => onNodeMouseDown(e, node.id)}
                    onDoubleClick={() => {
                      setEditingNode(node.id)
                      setEditTitle(node.data?.caption || '')
                      setEditContent('')
                    }}
                    onContextMenu={e => { e.preventDefault(); setSelectedNode(node.id) }}
                  >
                    <div style={styles.cardHead}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, minWidth: 0 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: '#94a3b8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          📷 {editingNode === node.id ? (
                            <input style={styles.titleInput} value={editTitle} onChange={e => setEditTitle(e.target.value)} autoFocus data-action="edit" onClick={e => e.stopPropagation()} />
                          ) : (node.data?.caption || '图片')}
                        </span>
                      </div>
                      <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                        <button data-action="connect" onMouseDown={e => startConnecting(e, node.id)} style={{ ...actionBtn, background: '#4f46e5' }} title="拖拽连线">○</button>
                        <button data-action="edit" onClick={() => { setEditingNode(node.id); setEditTitle(node.data?.caption || ''); setEditContent('') }} style={actionBtn} title="编辑标题">✎</button>
                        <button data-action="delete" onClick={() => deleteNode(node.id)} style={{ ...actionBtn, color: '#f87171' }} title="删除">✕</button>
                      </div>
                    </div>
                    <div style={{ padding: 4 }}>
                      <img
                        src={node.data?.src}
                        alt={node.data?.caption || ''}
                        style={{ width: '100%', display: 'block', borderRadius: 6, pointerEvents: 'none' }}
                        onLoad={(e) => console.log('[IMG] <img> onload ✓', node.data?.src, { w: e.target.naturalWidth, h: e.target.naturalHeight })}
                        onError={(e) => console.error('[IMG] <img> onerror ✗', node.data?.src, e)}
                      />
                    </div>
                    {editingNode === node.id && (
                      <div style={{ padding: '6px 10px', borderTop: '1px solid #334155', display: 'flex', gap: 6 }}>
                        <button data-action="save" onClick={() => { updateNode(node.id, { data: { ...node.data, caption: editTitle } }); setEditingNode(null) }} style={{ ...actionBtn, background: '#059669', color: '#fff', padding: '4px 12px' }}>保存</button>
                        <button data-action="cancel" onClick={() => setEditingNode(null)} style={{ ...actionBtn, padding: '4px 12px' }}>取消</button>
                      </div>
                    )}
                  </div>
                )
              }

              return (
                <div
                  key={node.id}
                  data-node-id={node.id}
                  style={{
                    ...styles.nodeCard,
                    left: node.x, top: node.y,
                    width: node.width || 320,
                    borderColor: selectedNode === node.id ? '#818cf8' : dragNode === node.id ? '#6366f1' : 'transparent',
                    boxShadow: selectedNode === node.id
                      ? '0 0 0 2px #818cf8, 0 8px 25px rgba(0,0,0,0.5)'
                      : dragNode === node.id
                        ? '0 12px 30px rgba(0,0,0,0.6)'
                        : '0 2px 10px rgba(0,0,0,0.4)',
                    zIndex: dragNode === node.id || selectedNode === node.id ? 100 : 10,
                    cursor: activeTool === 'select' ? (dragNode === node.id ? 'grabbing' : 'grab') : 'crosshair',
                  }}
                  onMouseDown={e => onNodeMouseDown(e, node.id)}
                  onDoubleClick={() => startEdit(node)}
                  onContextMenu={e => { e.preventDefault(); setSelectedNode(node.id) }}
                >
                  <div style={styles.cardHead}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                      <span style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {editingNode === node.id ? (
                          <input style={styles.titleInput} value={editTitle} onChange={e => setEditTitle(e.target.value)} autoFocus data-action="edit" onClick={e => e.stopPropagation()} />
                        ) : node.data?.title || '卡片'}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                      <button data-action="connect" onMouseDown={e => startConnecting(e, node.id)} style={{ ...actionBtn, background: '#4f46e5' }} title="拖拽连线">○</button>
                      <button data-action="edit" onClick={() => startEdit(node)} style={actionBtn} title="编辑">✎</button>
                      <button data-action="delete" onClick={() => deleteNode(node.id)} style={{ ...actionBtn, color: '#f87171' }} title="删除">✕</button>
                    </div>
                  </div>

                  <div style={styles.cardBody}>
                    {editingNode === node.id ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        <textarea
                          data-action="edit" style={styles.mdTextarea} value={editContent}
                          onChange={e => setEditContent(e.target.value)}
                          onKeyDown={e => { if (e.key === 'Escape') setEditingNode(null) }}
                        />
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                          <button data-action="save" onClick={saveEdit} style={{ ...actionBtn, background: '#059669', color: '#fff', padding: '4px 12px' }}>保存</button>
                          <button data-action="cancel" onClick={() => setEditingNode(null)} style={{ ...actionBtn, padding: '4px 12px' }}>取消</button>
                          <button data-action="embedImg" onClick={() => embedImageInputRef.current?.click()} style={{ ...actionBtn, padding: '4px 8px' }} title="插入图片">📷</button>
                          <input ref={embedImageInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleEmbedImage} />
                        </div>
                      </div>
                    ) : (
                      <div className="canvas-md" style={{ fontSize: 12, lineHeight: 1.7 }}>
                        {node.data?.content ? (
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{node.data.content}</ReactMarkdown>
                        ) : (
                          <span style={{ color: '#64748b', fontStyle: 'italic' }}>空卡片，双击编辑</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* 右键上下文菜单 */}
      {contextMenu && (
        <div style={{
          position: 'fixed', left: contextMenu.x, top: contextMenu.y, zIndex: 200,
          background: '#1e293b', border: '1px solid #475569', borderRadius: 6,
          boxShadow: '0 4px 16px rgba(0,0,0,0.5)', padding: 4, minWidth: 100
        }}>
          <button
            onClick={() => { deleteEdge(contextMenu.edgeId); setContextMenu(null); setSelectedEdge(null) }}
            style={{ ...actionBtn, background: '#dc2626', color: '#fff', width: '100%', padding: '6px 12px', fontSize: 12, textAlign: 'left' }}
          >
            🗑 删除连线
          </button>
        </div>
      )}

      {/* AI 面板 */}
      {showAI && (
        <div style={styles.aiPanel}>
          <div style={styles.aiPanelHead}>
            <span style={{ fontWeight: 600, color: '#e2e8f0', fontSize: 13 }}>AI 画布助手</span>
            <span style={{ fontSize: 11, color: '#94a3b8' }}>已加载画布上下文</span>
            <button onClick={() => setShowAI(false)} style={{ ...actionBtn, marginLeft: 'auto' }}>✕</button>
          </div>
          <div style={styles.aiMessages}>
            {aiMessages.map((m, i) => (
              <div key={i} style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 10, color: m.role === 'user' ? '#818cf8' : '#34d399', marginBottom: 2 }}>
                  {m.role === 'user' ? '你' : 'AI'}
                </div>
                <div className="canvas-md" style={{ fontSize: 12, lineHeight: 1.6 }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                </div>
              </div>
            ))}
          </div>
          <div style={styles.aiInput}>
            <input style={styles.aiTextInput} placeholder="对画布提问: 帮我扩展卡片/总结内容..." value={aiInput} onChange={e => setAiInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && sendAIMessage()} />
            <button onClick={sendAIMessage} style={{ ...actionBtn, background: '#4f46e5', color: '#fff', padding: '6px 12px' }}>发送</button>
          </div>
        </div>
      )}

      {/* 快捷键提示 */}
      <div style={styles.shortcuts}>
        <span>Ctrl+N 新建 | Delete 删除选中 | 右键 选中卡 | 滚轮 缩放 | ESC 回到选择 | Ctrl+Z 撤销标注 | 选择模式下拖动标注</span>
      </div>

      {/* 总结弹窗 */}
      {showSummary && (
        <div style={styles.summaryOverlay} onClick={() => setShowSummary(false)}>
          <div style={styles.summaryModal} onClick={e => e.stopPropagation()}>
            <div style={styles.summaryHead}>
              <span style={{ fontWeight: 600, color: '#e2e8f0' }}>📝 卡片内容总结</span>
              <button onClick={() => setShowSummary(false)} style={{ ...actionBtn, marginLeft: 'auto' }}>✕</button>
            </div>
            <div className="canvas-md" style={styles.summaryContent}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{summaryContent}</ReactMarkdown>
            </div>
            <div style={styles.summaryFoot}>
              <button onClick={() => { navigator.clipboard.writeText(summaryContent) }} style={{ ...actionBtn, background: '#4f46e5', color: '#fff', padding: '6px 16px' }}>复制</button>
              <button onClick={() => setShowSummary(false)} style={{ ...actionBtn, padding: '6px 16px' }}>关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ================================================================
// 样式
// ================================================================

const styles = {
  container: { width: '100%', height: '100%', background: '#0f172a', display: 'flex', flexDirection: 'column', fontFamily: '-apple-system,"Microsoft YaHei",sans-serif', position: 'relative', overflow: 'hidden' },
  viewport: { width: '100%', height: '100%', overflow: 'hidden', position: 'relative' },
  canvas: { position: 'absolute', top: 0, left: 0, minWidth: 6000, minHeight: 6000 },

  toolbar: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px',
    background: 'rgba(15,23,42,0.95)', borderBottom: '1px solid #1e293b',
    zIndex: 50, backdropFilter: 'blur(8px)',
  },

  toolPalette: {
    position: 'absolute', left: 10, top: 10, zIndex: 60,
    display: 'flex', flexDirection: 'column', gap: 4, padding: 8,
    background: 'rgba(15,23,42,0.92)', borderRadius: 10,
    border: '1px solid #334155', backdropFilter: 'blur(8px)',
    boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
  },

  toolDivider: {
    height: 1, background: '#334155', margin: '3px 0',
  },

  nodeCard: {
    position: 'absolute',
    width: 320,
    background: '#1e293b',
    borderRadius: 10,
    border: '2px solid transparent',
    overflow: 'hidden',
    transition: 'box-shadow 0.15s, border-color 0.15s',
    display: 'flex', flexDirection: 'column',
  },

  imgCard: {
    position: 'absolute',
    width: 320,
    background: '#1e293b',
    borderRadius: 10,
    border: '2px solid transparent',
    overflow: 'hidden',
    transition: 'box-shadow 0.15s, border-color 0.15s',
    display: 'flex', flexDirection: 'column',
  },

  cardHead: {
    padding: '8px 12px',
    borderBottom: '1px solid #334155',
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    background: 'rgba(30,41,59,0.8)',
    cursor: 'grab',
    minHeight: 36,
  },
  cardBody: {
    padding: '10px 14px',
    maxHeight: 360,
    overflowY: 'auto',
    flex: 1,
  },
  titleInput: {
    background: 'transparent', border: 'none', borderBottom: '1px solid #6366f1',
    color: '#e2e8f0', fontSize: 14, fontWeight: 600, padding: '2px 4px', outline: 'none', width: '100%',
  },
  mdTextarea: {
    width: '100%', minHeight: 160, background: '#0f172a', color: '#e2e8f0',
    border: '1px solid #6366f1', borderRadius: 6, padding: 10, fontSize: 12,
    fontFamily: '"JetBrains Mono","Fira Code",monospace', resize: 'vertical',
    lineHeight: 1.6,
  },

  aiPanel: {
    position: 'absolute', right: 0, top: 0, bottom: 0, width: 340,
    background: '#1e293b', borderLeft: '1px solid #334155',
    display: 'flex', flexDirection: 'column', zIndex: 80,
    boxShadow: '-4px 0 20px rgba(0,0,0,0.4)',
  },
  aiPanelHead: {
    padding: '10px 14px', borderBottom: '1px solid #334155',
    display: 'flex', alignItems: 'center', gap: 10,
  },
  aiMessages: { flex: 1, overflowY: 'auto', padding: '12px 14px' },
  aiInput: {
    padding: '10px 14px', borderTop: '1px solid #334155',
    display: 'flex', gap: 8,
  },
  aiTextInput: {
    flex: 1, padding: '7px 10px', background: '#0f172a', border: '1px solid #334155',
    borderRadius: 6, color: '#e2e8f0', fontSize: 12, outline: 'none',
  },

  shortcuts: {
    position: 'absolute', bottom: 8, left: '50%', transform: 'translateX(-50%)',
    fontSize: 10, color: '#475569', background: 'rgba(15,23,42,0.8)',
    padding: '4px 14px', borderRadius: 6, pointerEvents: 'none', zIndex: 90,
  },

  summaryOverlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 100,
  },
  summaryModal: {
    width: 560, maxHeight: '70vh', background: '#1e293b', borderRadius: 12,
    border: '1px solid #334155', boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  },
  summaryHead: {
    padding: '12px 16px', borderBottom: '1px solid #334155',
    display: 'flex', alignItems: 'center', gap: 10,
  },
  summaryContent: {
    padding: '16px 20px', flex: 1, overflowY: 'auto', fontSize: 13, lineHeight: 1.8,
  },
  summaryFoot: {
    padding: '12px 16px', borderTop: '1px solid #334155',
    display: 'flex', justifyContent: 'flex-end', gap: 8,
  },
}

const tbBtn = { padding: '5px 12px', fontSize: 12, border: 'none', borderRadius: 6, cursor: 'pointer', background: '#334155', color: '#e2e8f0' }
const tbInfo = { color: '#64748b', fontSize: 11 }
const actionBtn = { fontSize: 11, padding: '2px 6px', border: 'none', borderRadius: 4, cursor: 'pointer', background: '#334155', color: '#94a3b8' }
const toolBtn = { width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 14, transition: 'background 0.15s' }
