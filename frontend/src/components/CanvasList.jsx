import { useState, useEffect } from 'react'
import { listCanvases, createCanvas, deleteCanvas } from '../api.js'

export default function CanvasList({ onSelect }) {
  const [canvases, setCanvases] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { load() }, [])

  async function load() {
    try {
      const list = await listCanvases()
      setCanvases(list)
    } catch (e) { /* ignore */ }
    setLoading(false)
  }

  async function handleCreate() {
    const title = prompt('画布名称:') || '新画布'
    const c = await createCanvas(title)
    if (c && onSelect) onSelect(c.id)
  }

  async function handleDelete(id) {
    if (confirm('确认删除此画布？')) {
      await deleteCanvas(id)
      setCanvases(prev => prev.filter(c => c.id !== id))
    }
  }

  if (loading) return <div style={listStyle}><span style={dim}>加载中...</span></div>

  return (
    <div style={listStyle}>
      <div style={headRow}>
        <span style={{ fontWeight: 600, fontSize: 14, color: '#0f3d2a' }}>画布列表</span>
        <button onClick={handleCreate} style={createBtn}>+ 新建</button>
      </div>
      {canvases.length === 0 && <div style={dim}>暂无画布</div>}
      {canvases.map(c => (
        <div key={c.id} style={row} onClick={() => onSelect && onSelect(c.id)}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 500, color: '#0f3d2a' }}>{c.title}</div>
            <div style={{ fontSize: 11, color: '#555' }}>{c.node_count} 卡片</div>
          </div>
          <button onClick={e => { e.stopPropagation(); handleDelete(c.id) }} style={delBtn}>✕</button>
        </div>
      ))}
    </div>
  )
}

const listStyle = { padding: 12, overflowY: 'auto', flex: 1 }
const headRow = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }
const createBtn = { fontSize: 12, padding: '4px 12px', background: '#178351', color: '#fff', border: '3px solid #0f3d2a', borderRadius: 6, cursor: 'pointer', boxShadow: '2px 2px 0px #0f3d2a' }
const row = { padding: '8px 10px', marginBottom: 4, borderRadius: 6, border: '3px solid #bce1ce', cursor: 'pointer', display: 'flex', alignItems: 'center', background: '#fff' }
const delBtn = { fontSize: 11, padding: '2px 6px', border: '2px solid #0f3d2a', borderRadius: 3, background: '#fee2e2', color: '#dc2626', cursor: 'pointer' }
const dim = { color: '#555', fontSize: 13, textAlign: 'center', padding: 16 }
