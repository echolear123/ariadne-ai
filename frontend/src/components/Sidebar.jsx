export default function Sidebar({ conversations, activeId, onSelect, onDelete, onNew }) {
  return (
    <div style={styles.sidebar}>
      <div style={styles.header}>
        <span style={styles.userName}>{localStorage.getItem('username') || '用户'}</span>
      </div>
      <button style={styles.newBtn} onClick={onNew}>+ 新对话</button>
      <div style={styles.list}>
        {conversations.map(c => (
          <div
            key={c.conversation_id}
            style={{
              ...styles.item,
              ...(c.conversation_id === activeId ? styles.active : {})
            }}
            onClick={() => onSelect(c.conversation_id)}
          >
            <div style={styles.itemTitle}>{c.title || c.conversation_id.slice(5, 20)}</div>
            <div style={styles.itemMeta}>
              <span>{c.turn_count} 轮</span>
              <span style={styles.delBtn} onClick={e => { e.stopPropagation(); onDelete(c.conversation_id) }}>删除</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

const styles = {
  sidebar: {
    width: 260, minWidth: 260, background: '#f8fafc', borderRight: '1px solid #e2e8f0',
    display: 'flex', flexDirection: 'column', height: '100vh'
  },
  header: {
    padding: '16px', borderBottom: '1px solid #e2e8f0',
    display: 'flex', alignItems: 'center', justifyContent: 'space-between'
  },
  userName: { fontSize: 14, fontWeight: 600, color: '#1e293b' },
  newBtn: {
    margin: '8px 12px', padding: '8px 0', background: '#2563eb', color: '#fff',
    border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 500
  },
  list: { flex: 1, overflowY: 'auto', padding: '0 8px' },
  item: {
    padding: '10px 12px', borderRadius: 6, cursor: 'pointer', marginBottom: 2
  },
  active: { background: '#e0e7ff' },
  itemTitle: { fontSize: 13, color: '#334155', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  itemMeta: { fontSize: 11, color: '#94a3b8', marginTop: 4, display: 'flex', justifyContent: 'space-between' },
  delBtn: { color: '#ef4444', cursor: 'pointer' }
}
