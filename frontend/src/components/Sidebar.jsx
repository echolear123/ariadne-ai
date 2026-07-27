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
    width: 260, minWidth: 260, background: '#fff', borderRight: '4px solid #0f3d2a',
    display: 'flex', flexDirection: 'column', height: '100vh'
  },
  header: {
    padding: '16px', borderBottom: '4px solid #0f3d2a',
    display: 'flex', alignItems: 'center', justifyContent: 'space-between'
  },
  userName: { fontSize: 15, fontWeight: 600, color: '#0f3d2a' },
  newBtn: {
    margin: '8px 12px', padding: '10px 0', background: '#476aed', color: '#fff',
    border: '3px solid #0f3d2a', borderRadius: 6, cursor: 'pointer', fontSize: 14, fontWeight: 500,
    boxShadow: '3px 3px 0px #0f3d2a',
  },
  list: { flex: 1, overflowY: 'auto', padding: '0 8px' },
  item: {
    padding: '10px 12px', borderRadius: 6, cursor: 'pointer', marginBottom: 3,
    border: '2px solid transparent',
  },
  active: { background: '#c3ebd5', border: '2px solid #0f3d2a', boxShadow: '2px 2px 0px #0f3d2a' },
  itemTitle: { fontSize: 13, color: '#0f3d2a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  itemMeta: { fontSize: 11, color: '#555', marginTop: 4, display: 'flex', justifyContent: 'space-between' },
  delBtn: { color: '#dc2626', cursor: 'pointer' }
}
