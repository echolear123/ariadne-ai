import { useState, useEffect } from 'react'
import { listPlugins, callPlugin } from '../api.js'

export default function PluginLibrary({ onClose, onInsert }) {
  const [plugins, setPlugins] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState(null)
  const [results, setResults] = useState({})
  const [running, setRunning] = useState({})

  useEffect(() => {
    loadPlugins()
  }, [])

  async function loadPlugins() {
    setLoading(true)
    try {
      const list = await listPlugins()
      setPlugins(list)
    } catch (err) {
      setError('加载失败: ' + err.message)
    }
    setLoading(false)
  }

  async function runTool(pluginName, toolName, inputSchema) {
    const key = `${pluginName}.${toolName}`
    setRunning(prev => ({ ...prev, [key]: true }))

    // 构建参数: 如果有必填参数，弹出简易输入
    const required = inputSchema?.required || []
    let args = {}
    if (required.length > 0) {
      const props = inputSchema.properties || {}
      for (const r of required) {
        const desc = props[r]?.description || r
        const val = prompt(`请输入 ${desc}:`)
        if (!val) { setRunning(prev => ({ ...prev, [key]: false })); return }
        args[r] = isNaN(val) ? val : Number(val)
      }
    }

    try {
      const result = await callPlugin(pluginName, toolName, args)
      setResults(prev => ({
        ...prev,
        [key]: JSON.stringify(result, null, 2)
      }))
    } catch (err) {
      setResults(prev => ({
        ...prev,
        [key]: '调用失败: ' + err.message
      }))
    }
    setRunning(prev => ({ ...prev, [key]: false }))
  }

  function insertTool(pluginName, toolName) {
    const text = `[PLUGIN:${pluginName}.${toolName}:{}]`
    if (onInsert) onInsert(text)
    if (onClose) onClose()
  }

  return (
    <div style={overlay}>
      <div style={modal}>
        <div style={header}>
          <span style={{ fontSize: 16, fontWeight: 600 }}>插件库</span>
          <button onClick={onClose} style={closeBtn}>x</button>
        </div>

        <div style={body}>
          {loading && <div style={status}>加载中...</div>}
          {error && <div style={{ ...status, color: '#dc2626' }}>{error}</div>}

          {plugins.map(p => (
            <div key={p.name} style={pluginCard}>
              <div
                style={pluginHead}
                onClick={() => setExpanded(expanded === p.name ? null : p.name)}
              >
                <span style={arrow}>{expanded === p.name ? 'v' : '>'}</span>
                <span style={pluginName}>{p.name}</span>
                <span style={badge}>{p.version}</span>
                <span style={desc}>{p.description}</span>
              </div>

              {expanded === p.name && (
                <div style={toolsList}>
                  {p.tools?.map(t => {
                    const key = `${p.name}.${t.name}`
                    return (
                      <div key={t.name} style={toolItem}>
                        <div style={toolHead}>
                          <code style={toolName}>{p.name}.{t.name}</code>
                          <div style={toolActions}>
                            <button
                              style={runBtn}
                              disabled={running[key]}
                              onClick={() => runTool(p.name, t.name, t.inputSchema)}
                            >
                              {running[key] ? '...' : '运行'}
                            </button>
                            <button
                              style={insertBtn}
                              onClick={() => insertTool(p.name, t.name)}
                            >
                              插入对话
                            </button>
                          </div>
                        </div>
                        <div style={toolDesc}>{t.description}</div>
                        {t.inputSchema?.properties && (
                          <div style={params}>
                            参数: {Object.entries(t.inputSchema.properties).map(([k, v]) => (
                              <code key={k} style={paramTag}>{k}: {v.description}</code>
                            ))}
                          </div>
                        )}
                        {results[key] && (
                          <pre style={resultPre}>{results[key]}</pre>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          ))}

          {!loading && plugins.length === 0 && (
            <div style={status}>暂无插件, 请在 plugins/ 目录下添加</div>
          )}
        </div>
      </div>
    </div>
  )
}

const overlay = {
  position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
  background: 'rgba(0,0,0,0.3)', display: 'flex',
  alignItems: 'center', justifyContent: 'center', zIndex: 1000,
}
const modal = {
  width: 620, maxHeight: '80vh', background: '#fff',
  borderRadius: 10, overflow: 'hidden', display: 'flex', flexDirection: 'column',
  boxShadow: '0 8px 30px rgba(0,0,0,0.15)',
}
const header = {
  padding: '12px 16px', borderBottom: '1px solid #e5e7eb',
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
}
const closeBtn = { border: 'none', background: 'none', fontSize: 18, cursor: 'pointer', color: '#9ca3af' }
const body = { padding: 12, overflowY: 'auto', flex: 1 }
const status = { textAlign: 'center', color: '#9ca3af', padding: 20, fontSize: 13 }
const pluginCard = { marginBottom: 8, border: '1px solid #e5e7eb', borderRadius: 6 }
const pluginHead = { padding: '8px 12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }
const arrow = { fontSize: 10, color: '#9ca3af', width: 12 }
const pluginName = { fontWeight: 600, fontSize: 14 }
const badge = { fontSize: 10, background: '#e0e7ff', color: '#3730a3', padding: '1px 6px', borderRadius: 3 }
const desc = { fontSize: 12, color: '#6b7280', flex: 1, textAlign: 'right' }
const toolsList = { borderTop: '1px solid #f3f4f6', padding: '6px 12px 8px' }
const toolItem = { padding: '6px 0', borderBottom: '1px solid #f9fafb' }
const toolHead = { display: 'flex', justifyContent: 'space-between', alignItems: 'center' }
const toolName = { fontSize: 12, background: '#f3f4f6', padding: '1px 6px', borderRadius: 3 }
const toolDesc = { fontSize: 12, color: '#6b7280', margin: '4px 0' }
const toolActions = { display: 'flex', gap: 6 }
const runBtn = { fontSize: 11, padding: '2px 10px', background: '#2563eb', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }
const insertBtn = { fontSize: 11, padding: '2px 10px', background: '#f3f4f6', color: '#374151', border: '1px solid #d1d5db', borderRadius: 4, cursor: 'pointer' }
const params = { fontSize: 11, color: '#9ca3af', marginTop: 2 }
const paramTag = { fontSize: 10, background: '#fef3c7', padding: '1px 4px', borderRadius: 2, marginLeft: 4 }
const resultPre = { background: '#1e293b', color: '#e2e8f0', padding: '8px 10px', borderRadius: 4, fontSize: 11, marginTop: 6, maxHeight: 120, overflowY: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }
