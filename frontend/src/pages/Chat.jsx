import { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import Sidebar from '../components/Sidebar.jsx'
import PluginLibrary from '../components/PluginLibrary.jsx'
import CanvasList from '../components/CanvasList.jsx'
import CanvasPage from './CanvasPage.jsx'
import { listConversations, getConversation, deleteConversation, sendMessage } from '../api.js'

// --- 样式定义 (放在顶层，组件和渲染函数都可引用) ---

const s = {
  layout: { display: 'flex', height: '100vh', fontFamily: '-apple-system, "Microsoft YaHei", sans-serif' },
  main: { flex: 1, display: 'flex', flexDirection: 'column', background: '#f0f2f5' },
  topBar: { padding: '10px 20px', background: '#fff', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: 12 },
  logoutBtn: { marginLeft: 'auto', padding: '4px 12px', fontSize: 12, background: '#fee2e2', color: '#dc2626', border: 'none', borderRadius: 4, cursor: 'pointer' },
  chatArea: { flex: 1, overflowY: 'auto', padding: '16px 24px' },
  welcome: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%' },
  row: { display: 'flex', marginBottom: 12 },
  bubble: { maxWidth: '75%', padding: '10px 14px', borderRadius: 10, boxShadow: '0 1px 3px rgba(0,0,0,.06)', overflowX: 'auto' },
  inputBar: { padding: '10px 20px', background: '#fff', borderTop: '1px solid #e2e8f0', display: 'flex', gap: 8 },
  textInput: { flex: 1, padding: '9px 14px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13, outline: 'none' },
  sendBtn: { padding: '9px 18px', background: '#2563eb', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 500 },
}

const pluginBtn = { padding: '4px 12px', fontSize: 12, background: '#e0e7ff', color: '#3730a3', border: 'none', borderRadius: 4, cursor: 'pointer' }
const canvasBtn = { padding: '4px 12px', fontSize: 12, background: '#fef3c7', color: '#92400e', border: 'none', borderRadius: 4, cursor: 'pointer' }
const docMgrBtn = { padding: '4px 12px', fontSize: 12, background: '#d1fae5', color: '#065f46', border: 'none', borderRadius: 4, cursor: 'pointer' }

const md = {
  table: { borderCollapse: 'collapse', width: '100%', margin: '8px 0', fontSize: 13 },
  th: { border: '1px solid #d1d5db', padding: '6px 10px', textAlign: 'left', background: '#f3f4f6', fontWeight: 600 },
  td: { border: '1px solid #d1d5db', padding: '6px 10px' },
  h1: { fontSize: 18, margin: '12px 0 6px', borderBottom: '1px solid #e5e7eb', paddingBottom: 4 },
  h2: { fontSize: 16, margin: '10px 0 5px' },
  h3: { fontSize: 15, margin: '8px 0 4px' },
  h4: { fontSize: 14, margin: '6px 0 3px' },
  p: { margin: '4px 0', lineHeight: 1.6 },
  ul: { paddingLeft: 22, margin: '4px 0' },
  ol: { paddingLeft: 22, margin: '4px 0' },
  li: { margin: '2px 0' },
  inlineCode: { background: '#f3f4f6', padding: '2px 6px', borderRadius: 3, fontSize: 12, fontFamily: 'monospace' },
  codeBlock: { fontSize: 13, lineHeight: 1.5 },
  pre: { background: '#1e293b', color: '#e2e8f0', padding: '12px 14px', borderRadius: 6, overflowX: 'auto', margin: '8px 0' },
  blockquote: { borderLeft: '3px solid #2563eb', padding: '4px 12px', margin: '8px 0', color: '#6b7280', background: '#f9fafb', borderRadius: '0 4px 4px 0' },
  a: { color: '#2563eb', textDecoration: 'underline' },
  hr: { border: 'none', borderTop: '1px solid #e5e7eb', margin: '10px 0' },
  strong: { fontWeight: 600 },
}

// --- Markdown 组件映射 ---

const mdComponents = {
  table: ({ children }) => <table style={md.table}>{children}</table>,
  th: ({ children }) => <th style={md.th}>{children}</th>,
  td: ({ children }) => <td style={md.td}>{children}</td>,
  h1: ({ children }) => <h1 style={md.h1}>{children}</h1>,
  h2: ({ children }) => <h2 style={md.h2}>{children}</h2>,
  h3: ({ children }) => <h3 style={md.h3}>{children}</h3>,
  h4: ({ children }) => <h4 style={md.h4}>{children}</h4>,
  p: ({ children }) => <p style={md.p}>{children}</p>,
  ul: ({ children }) => <ul style={md.ul}>{children}</ul>,
  ol: ({ children }) => <ol style={md.ol}>{children}</ol>,
  li: ({ children }) => <li style={md.li}>{children}</li>,
  code: ({ children, className }) =>
    !className
      ? <code style={md.inlineCode}>{children}</code>
      : <code className={className} style={md.codeBlock}>{children}</code>,
  pre: ({ children }) => <pre style={md.pre}>{children}</pre>,
  blockquote: ({ children }) => <blockquote style={md.blockquote}>{children}</blockquote>,
  a: ({ children, href }) => <a href={href} style={md.a} target="_blank" rel="noopener noreferrer">{children}</a>,
  hr: () => <hr style={md.hr} />,
  strong: ({ children }) => <strong style={md.strong}>{children}</strong>,
}

// --- 消息气泡组件 ---

function MessageBubble({ role, content }) {
  if (role === 'user') {
    return (
      <div style={{ ...s.bubble, background: '#2563eb', color: '#fff', borderBottomRightRadius: 3 }}>
        <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 13.5, lineHeight: 1.65 }}>
          {content}
        </div>
      </div>
    )
  }
  return (
    <div style={{ ...s.bubble, background: '#fff', color: '#1f2937', borderBottomLeftRadius: 3 }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
        {content}
      </ReactMarkdown>
    </div>
  )
}

// --- 聊天主页面 ---

const blinkStyle = {
  display: 'inline-block', width: 6, height: 13, background: '#2563eb',
  marginLeft: 1, verticalAlign: 'middle', animation: 'blink 1s infinite',
}

export default function Chat({ user, onLogout, onGoToManager }) {
  const [conversations, setConversations] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [streaming, setStreaming] = useState('')
  const [showPlugins, setShowPlugins] = useState(false)
  const [activeCanvas, setActiveCanvas] = useState(null)
  const [showCanvases, setShowCanvases] = useState(false)
  const messagesEnd = useRef(null)

  useEffect(() => { loadConversations() }, [])
  useEffect(() => { messagesEnd.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, streaming])

  async function loadConversations() {
    const list = await listConversations()
    setConversations(list)
  }

  async function selectConversation(id) {
    setActiveId(id)
    setMessages([])
    setStreaming('')
    const data = await getConversation(id)
    if (data && data.turns) {
      const msgs = []
      for (const t of data.turns) {
        msgs.push({ role: 'user', content: t.query, turnId: t.turn_id })
        msgs.push({ role: 'agent', content: t.answer, turnId: t.turn_id })
      }
      setMessages(msgs)
    }
  }

  function handleNewChat() {
    setActiveId(null)
    setMessages([])
    setStreaming('')
  }

  async function handleDelete(id) {
    await deleteConversation(id)
    if (id === activeId) { setActiveId(null); setMessages([]) }
    loadConversations()
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setSending(true)
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setStreaming('')

    try {
      let streamText = ''
      const { conversationId: cid } = await sendMessage(text, activeId, (token) => {
        streamText += token
        setStreaming(streamText)
      })
      setStreaming('')
      setMessages(prev => [...prev, { role: 'agent', content: streamText }])

      if (!activeId && cid) setActiveId(cid)
      loadConversations()
    } catch (err) {
      setStreaming('')
      setMessages(prev => [...prev, { role: 'agent', content: '请求失败: ' + err.message }])
    }
    setSending(false)
  }

  return (
    <div style={activeCanvas ? { width: '100vw', height: '100vh', overflow: 'hidden' } : s.layout}>
      {activeCanvas ? (
        <CanvasPage canvasId={activeCanvas} onBack={() => setActiveCanvas(null)} />
      ) : (
        <>
          <Sidebar
            conversations={conversations}
            activeId={activeId}
            onSelect={selectConversation}
            onDelete={handleDelete}
            onNew={handleNewChat}
          />
          <div style={s.main}>
            <div style={s.topBar}>
              <span style={{ fontWeight: 600, color: '#1e293b' }}>Ariadne AI</span>
              <button style={pluginBtn} onClick={() => setShowPlugins(true)}>插件库</button>
              <button style={canvasBtn} onClick={() => setShowCanvases(!showCanvases)}>画布</button>
              <button style={docMgrBtn} onClick={onGoToManager}>知识库管理</button>
              <span style={{ fontSize: 12, color: '#94a3b8', marginLeft: 'auto' }}>{user.username}</span>
              <button style={s.logoutBtn} onClick={onLogout}>退出</button>
            </div>
            {showPlugins && (
              <PluginLibrary
                onClose={() => setShowPlugins(false)}
                onInsert={(text) => { setInput(prev => prev + text) }}
              />
            )}
            {showCanvases && (
              <div style={{
                position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 999,
                background: 'rgba(0,0,0,0.3)', display: 'flex', justifyContent: 'center', alignItems: 'center'
              }}>
                <div style={{ width: 400, maxHeight: '70vh', background: '#fff', borderRadius: 10, overflow: 'hidden', display: 'flex', flexDirection: 'column', boxShadow: '0 8px 30px rgba(0,0,0,0.15)' }}>
                  <div style={{ padding: '10px 14px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>Markdown 画布</span>
                    <button onClick={() => setShowCanvases(false)} style={{ border: 'none', background: 'none', fontSize: 16, cursor: 'pointer', color: '#9ca3af' }}>x</button>
                  </div>
                  <CanvasList onSelect={id => { setShowCanvases(false); setActiveCanvas(id) }} />
                </div>
              </div>
            )}
        <div style={s.chatArea}>
          {messages.length === 0 && !streaming && (
            <div style={s.welcome}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>Ariadne AI</div>
              <div style={{ color: '#94a3b8', fontSize: 14 }}>循此红线，洞见万卷</div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} style={{ ...s.row, justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <MessageBubble role={m.role} content={m.content} />
            </div>
          ))}
          {streaming && (
            <div style={{ ...s.row, justifyContent: 'flex-start' }}>
              <div style={{ ...s.bubble, background: '#fff', color: '#1f2937', borderBottomLeftRadius: 3 }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                  {streaming}
                </ReactMarkdown>
                <span style={blinkStyle} />
              </div>
            </div>
          )}
          <div ref={messagesEnd} />
        </div>
        <div style={s.inputBar}>
          <input
            style={s.textInput}
            placeholder="输入问题..."
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSend()}
            disabled={sending}
            autoFocus
          />
          <button style={s.sendBtn} onClick={handleSend} disabled={sending}>
            {sending ? '...' : '发送'}
          </button>
        </div>
      </div>
        </>
      )}
    </div>
  )
}
