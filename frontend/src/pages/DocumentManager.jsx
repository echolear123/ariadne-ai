import { useState, useEffect, useRef } from 'react'
import {
  listDocuments, uploadDocument, deleteDocument, updateDocumentNotes, getDownloadUrl,
  listVectorEntries, deleteVectorEntry, getVectorStats, vectorOptimize
} from '../api.js'

const s = {
  container: { padding: '24px 32px', maxWidth: 1200, margin: '0 auto' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  title: { fontSize: 22, fontWeight: 600, color: '#1e293b', margin: 0 },
  backBtn: { padding: '6px 14px', fontSize: 12, background: '#f1f5f9', color: '#475569', border: 'none', borderRadius: 6, cursor: 'pointer' },
  tabs: { display: 'flex', gap: 0, marginBottom: 20, borderBottom: '2px solid #e2e8f0' },
  tab: { padding: '8px 20px', fontSize: 13, border: 'none', background: 'none', cursor: 'pointer', color: '#64748b', borderBottom: '2px solid transparent', marginBottom: -2 },
  tabActive: { padding: '8px 20px', fontSize: 13, border: 'none', background: 'none', cursor: 'pointer', color: '#2563eb', borderBottom: '2px solid #2563eb', marginBottom: -2, fontWeight: 600 },
  table: { width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 8, overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,.06)' },
  th: { textAlign: 'left', padding: '8px 12px', background: '#f8fafc', borderBottom: '2px solid #e2e8f0', fontSize: 12, fontWeight: 600, color: '#64748b' },
  td: { padding: '8px 12px', borderBottom: '1px solid #f1f5f9', fontSize: 12, color: '#334155', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  actionBtn: { padding: '3px 8px', fontSize: 11, border: 'none', borderRadius: 3, cursor: 'pointer', marginRight: 3 },
  uploadBtn: { padding: '8px 18px', background: '#059669', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 500 },
  statsBar: { display: 'flex', gap: 20, marginBottom: 14, fontSize: 12, color: '#64748b' },
  empty: { textAlign: 'center', padding: 40, color: '#94a3b8', fontSize: 13 },
  notesInput: { width: '100%', padding: '3px 6px', fontSize: 11, border: '1px solid #d1d5db', borderRadius: 3, outline: 'none' },
  sourceGroup: { marginBottom: 16 },
  sourceTitle: { fontSize: 13, fontWeight: 600, color: '#1e293b', marginBottom: 6, padding: '4px 8px', background: '#f1f5f9', borderRadius: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
}

export default function DocumentManager({ onBack }) {
  const [tab, setTab] = useState('docs') // 'docs' | 'vectors'
  const [docs, setDocs] = useState([])
  const [uploading, setUploading] = useState(false)
  const [editingNotes, setEditingNotes] = useState(null)
  const [vectorEntries, setVectorEntries] = useState([])
  const [vectorStats, setVectorStats] = useState({ total_entries: 0, sources: {} })
  const [vectorSourceFilter, setVectorSourceFilter] = useState('')
  const [loadingVectors, setLoadingVectors] = useState(false)
  const selectedRef = useRef(new Set())
  const [, forceUpdate] = useState(0)
  const fileInputRef = useRef(null)

  function isSelected(id) { return selectedRef.current.has(id) }
  function selectedCount() { return selectedRef.current.size }
  function selectedArray() { return Array.from(selectedRef.current) }
  function clearSelection() { selectedRef.current.clear(); forceUpdate(n => n + 1) }

  useEffect(() => { loadDocs() }, [])
  useEffect(() => { if (tab === 'vectors') { loadVectorData() } }, [tab, vectorSourceFilter])

  async function loadDocs() {
    const list = await listDocuments()
    setDocs(list)
  }

  async function loadVectorData() {
    setLoadingVectors(true)
    const [entriesRes, statsRes] = await Promise.all([
      listVectorEntries(vectorSourceFilter),
      getVectorStats()
    ])
    setVectorEntries(entriesRes.entries || [])
    setVectorStats(statsRes)
    setLoadingVectors(false)
  }

  async function handleUpload(e) {
    const file = e.target.files[0]
    if (!file) return
    setUploading(true)
    try {
      await uploadDocument(file)
      await loadDocs()
    } catch (err) {
      alert('上传失败: ' + err.message)
    }
    setUploading(false)
    e.target.value = ''
  }

  async function handleDelete(filename) {
    if (!confirm(`确定要删除 "${filename}" 吗？`)) return
    try {
      await deleteDocument(filename)
      await loadDocs()
    } catch (err) {
      alert('删除失败: ' + err.message)
    }
  }

  async function handleSaveNotes(filename, notes) {
    try {
      await updateDocumentNotes(filename, notes)
      setEditingNotes(null)
      await loadDocs()
    } catch (err) {
      alert('保存备注失败: ' + err.message)
    }
  }

  async function handleDeleteVector(docId) {
    if (!confirm(`确定要删除向量条目 "${docId}" 吗？`)) return
    try {
      await deleteVectorEntry(docId)
      await loadVectorData()
    } catch (err) {
      alert('删除失败: ' + err.message)
    }
  }

  async function handleDeleteSource(source) {
    if (!confirm(`确定要删除来源 "${source}" 的所有向量条目吗？`)) return
    try {
      const entries = await listVectorEntries(source)
      for (const e of (entries.entries || [])) {
        await deleteVectorEntry(e.id)
      }
      await vectorOptimize()
      clearSelection()
      await loadVectorData()
    } catch (err) {
      alert('删除失败: ' + err.message)
    }
  }

  function toggleSelect(id) {
    const s = selectedRef.current
    if (s.has(id)) s.delete(id)
    else s.add(id)
    forceUpdate(n => n + 1)
  }

  function toggleSelectAll(entries) {
    const s = selectedRef.current
    const allSelected = entries.every(e => s.has(e.id))
    if (allSelected) {
      for (const e of entries) s.delete(e.id)
    } else {
      for (const e of entries) s.add(e.id)
    }
    forceUpdate(n => n + 1)
  }

  function toggleSelectAllGlobal() {
    const s = selectedRef.current
    const allIds = vectorEntries.map(e => e.id)
    const allSelected = allIds.length > 0 && allIds.every(id => s.has(id))
    if (allSelected) {
      for (const id of allIds) s.delete(id)
    } else {
      for (const id of allIds) s.add(id)
    }
    forceUpdate(n => n + 1)
  }

  async function handleBatchDelete() {
    const ids = selectedArray()
    if (ids.length === 0) { alert('请先选中要删除的条目'); return }
    if (!confirm(`确定要删除选中的 ${ids.length} 条向量条目吗？`)) return
    try {
      for (const id of ids) {
        await deleteVectorEntry(id)
      }
      await vectorOptimize()
      clearSelection()
      await loadVectorData()
    } catch (err) {
      alert('删除失败: ' + err.message)
    }
  }

  // 按 source 分组向量条目
  const groupedEntries = {}
  for (const e of vectorEntries) {
    const src = e.source || '(unknown)'
    if (!groupedEntries[src]) groupedEntries[src] = []
    groupedEntries[src].push(e)
  }

  return (
    <div style={s.container}>
      <div style={s.header}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button style={s.backBtn} onClick={onBack}>← 返回对话</button>
          <h2 style={s.title}>知识库管理</h2>
        </div>
        {tab === 'docs' && (
          <div>
            <input type="file" ref={fileInputRef} onChange={handleUpload} accept=".pdf,.docx,.txt,.md" style={{ display: 'none' }} />
            <button style={s.uploadBtn} onClick={() => fileInputRef.current?.click()} disabled={uploading}>
              {uploading ? '上传中...' : '+ 上传文档'}
            </button>
          </div>
        )}
      </div>

      <div style={s.tabs}>
        <button style={tab === 'docs' ? s.tabActive : s.tab} onClick={() => setTab('docs')}>
          文档管理 ({docs.length})
        </button>
        <button style={tab === 'vectors' ? s.tabActive : s.tab} onClick={() => setTab('vectors')}>
          向量库 ({vectorStats.total_entries})
        </button>
      </div>

      {/* === 文档管理 Tab === */}
      {tab === 'docs' && (
        docs.length === 0 ? (
          <div style={s.empty}>暂无文档，点击"上传文档"添加</div>
        ) : (
          <table style={s.table}>
            <thead>
              <tr>
                <th style={s.th}>文件名</th>
                <th style={{ ...s.th, width: 80 }}>大小</th>
                <th style={{ ...s.th, width: 120 }}>修改时间</th>
                <th style={{ ...s.th, width: 180 }}>备注</th>
                <th style={{ ...s.th, width: 130 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {docs.map(doc => (
                <tr key={doc.filename}>
                  <td style={s.td}>{doc.filename}</td>
                  <td style={s.td}>{doc.size_display}</td>
                  <td style={s.td}>{doc.modified}</td>
                  <td style={s.td}>
                    {editingNotes === doc.filename ? (
                      <input style={s.notesInput} defaultValue={doc.notes} autoFocus
                        onBlur={e => handleSaveNotes(doc.filename, e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') handleSaveNotes(doc.filename, e.target.value)
                          if (e.key === 'Escape') setEditingNotes(null)
                        }} />
                    ) : (
                      <span style={{ color: doc.notes ? '#334155' : '#cbd5e1', cursor: 'pointer' }}
                        onClick={() => setEditingNotes(doc.filename)} title={doc.notes || '点击添加备注'}>
                        {doc.notes || '点击添加备注'}
                      </span>
                    )}
                  </td>
                  <td style={s.td}>
                    <a href={getDownloadUrl(doc.filename)} style={{ ...s.actionBtn, background: '#e0e7ff', color: '#3730a3', textDecoration: 'none', display: 'inline-block' }}>下载</a>
                    <button style={{ ...s.actionBtn, background: '#fee2e2', color: '#dc2626' }} onClick={() => handleDelete(doc.filename)}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}

      {/* === 向量库 Tab === */}
      {tab === 'vectors' && (
        <>
          <div style={s.statsBar}>
            <span>总条目: <strong>{vectorStats.total_entries}</strong></span>
            <span>来源数: <strong>{vectorStats.total_sources || Object.keys(vectorStats.sources).length}</strong></span>
            <button style={{ ...s.actionBtn, background: '#e0e7ff', color: '#3730a3' }}
              onClick={toggleSelectAllGlobal}>
              {vectorEntries.length > 0 && vectorEntries.every(e => isSelected(e.id)) ? '取消全选' : '全选'}
            </button>
            {selectedCount() > 0 && (
              <span>已选: <strong>{selectedCount()}</strong>
                <button style={{ ...s.actionBtn, marginLeft: 6, background: '#dc2626', color: '#fff' }}
                  onClick={handleBatchDelete}>删除选中</button>
              </span>
            )}
            {vectorSourceFilter && (
              <span>过滤: <strong>{vectorSourceFilter}</strong>
                <button style={{ ...s.actionBtn, marginLeft: 6, background: '#fee2e2', color: '#dc2626' }}
                  onClick={() => setVectorSourceFilter('')}>清除</button>
              </span>
            )}
            <button style={{ ...s.actionBtn, background: '#e0e7ff', color: '#3730a3', marginLeft: 'auto' }}
              onClick={loadVectorData} disabled={loadingVectors}>
              {loadingVectors ? '刷新中...' : '刷新'}
            </button>
          </div>

          {Object.keys(groupedEntries).length === 0 ? (
            <div style={s.empty}>向量库为空</div>
          ) : (
            Object.entries(groupedEntries).map(([source, entries]) => (
              <div key={source} style={s.sourceGroup}>
                <div style={s.sourceTitle}>
                  <span>{source} ({entries.length} 条)</span>
                  <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                    <button style={{ ...s.actionBtn, background: '#e0e7ff', color: '#3730a3' }}
                      onClick={() => toggleSelectAll(entries)}>
                      {entries.every(e => isSelected(e.id)) ? '取消全选' : '全选'}
                    </button>
                    <button style={{ ...s.actionBtn, background: '#fee2e2', color: '#dc2626' }}
                      onClick={() => handleDeleteSource(source)}>删除全部</button>
                  </div>
                </div>
                <table style={s.table}>
                  <thead>
                    <tr>
                      <th style={{ ...s.th, width: 30 }}>
                        <input type="checkbox"
                          checked={entries.every(e => isSelected(e.id))}
                          onChange={() => toggleSelectAll(entries)}
                          style={{ cursor: 'pointer' }} />
                      </th>
                      <th style={{ ...s.th, width: 220 }}>条目 ID</th>
                      <th style={s.th}>内容预览</th>
                      <th style={{ ...s.th, width: 50 }}>#</th>
                      <th style={{ ...s.th, width: 60 }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map(e => (
                      <tr key={e.id}>
                        <td style={s.td}>
                          <input type="checkbox"
                            checked={isSelected(e.id)}
                            onChange={() => toggleSelect(e.id)}
                            style={{ cursor: 'pointer' }} />
                        </td>
                        <td style={{ ...s.td, fontFamily: 'monospace', fontSize: 11 }}>{e.id}</td>
                        <td style={s.td}>{e.text_preview}</td>
                        <td style={s.td}>{e.chunk_index}</td>
                        <td style={s.td}>
                          <button style={{ ...s.actionBtn, background: '#fee2e2', color: '#dc2626' }}
                            onClick={() => handleDeleteVector(e.id)}>删除</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))
          )}

          {/* 来源统计摘要 */}
          {Object.keys(vectorStats.sources).length > 0 && (
            <div style={{ marginTop: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#1e293b', marginBottom: 8 }}>来源统计</div>
              <table style={s.table}>
                <thead>
                  <tr>
                    <th style={s.th}>来源</th>
                    <th style={{ ...s.th, width: 80 }}>条目数</th>
                    <th style={{ ...s.th, width: 80 }}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(vectorStats.sources).sort((a, b) => b[1] - a[1]).map(([src, count]) => (
                    <tr key={src}>
                      <td style={s.td}>{src}</td>
                      <td style={s.td}>{count}</td>
                      <td style={s.td}>
                        <button style={{ ...s.actionBtn, background: '#e0e7ff', color: '#3730a3' }}
                          onClick={() => setVectorSourceFilter(src)}>查看</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
