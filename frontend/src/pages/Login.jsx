import { useState } from 'react'
import { login } from '../api.js'
import MacPatternBackground from '../components/MacPatternBackground.jsx'

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    if (!username.trim()) return
    if (!password.trim()) return
    setLoading(true)
    setError('')
    try {
      const data = await login(username.trim(), password)
      onLogin({ user_id: data.user_id, username: data.username })
    } catch (err) {
      setError(err.message || '登录失败')
    }
    setLoading(false)
  }

  return (
    <div style={styles.container}>
      <style>{`
        .login-input::placeholder { color: rgba(255,255,255,0.45); }
        .login-input:focus { border-color: rgba(255,255,255,0.5) !important; }
      `}</style>
      <MacPatternBackground />
      <div style={styles.overlay}>
        <div style={styles.card}>
          <h1 style={styles.title}>Ariadne AI</h1>
          <p style={styles.subtitle}>循此红线，洞见万卷</p>
          <form onSubmit={handleSubmit} style={styles.form}>
            <input
              className="login-input"
              style={styles.input}
              type="text"
              placeholder="请输入用户名"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoFocus
            />
            <input
              className="login-input"
              style={styles.input}
              type="password"
              placeholder="请输入密码"
              value={password}
              onChange={e => setPassword(e.target.value)}
            />
            <button style={styles.btn} type="submit" disabled={loading}>
              {loading ? '登录中...' : '进入系统'}
            </button>
          </form>
          {error && <p style={styles.error}>{error}</p>}
        </div>
      </div>
    </div>
  )
}

const styles = {
  container: {
    position: 'relative', width: '100%', height: '100vh', overflow: 'hidden'
  },
  overlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    display: 'flex', justifyContent: 'center', alignItems: 'center',
    zIndex: 1,
  },
  card: {
    background: 'rgba(255,255,255,0.12)',
    backdropFilter: 'blur(20px)',
    WebkitBackdropFilter: 'blur(20px)',
    borderRadius: 16,
    padding: '40px 32px',
    width: 380,
    boxShadow: '0 8px 40px rgba(0,0,0,0.25)',
    border: '1px solid rgba(255,255,255,0.18)',
    textAlign: 'center',
  },
  title: { fontSize: 28, margin: 0, color: '#fff', fontWeight: 700 },
  subtitle: { color: 'rgba(255,255,255,0.7)', margin: '8px 0 24px', fontSize: 14 },
  form: { display: 'flex', flexDirection: 'column', gap: 12 },
  input: {
    padding: '10px 14px', fontSize: 14,
    border: '1px solid rgba(255,255,255,0.25)',
    borderRadius: 8, outline: 'none',
    background: 'rgba(255,255,255,0.1)',
    color: '#fff',
    backdropFilter: 'blur(4px)',
  },
  btn: {
    padding: '10px 0', fontSize: 15,
    background: 'rgba(255,255,255,0.2)',
    color: '#fff',
    border: '1px solid rgba(255,255,255,0.3)',
    borderRadius: 8, cursor: 'pointer', fontWeight: 600,
    transition: 'background 0.2s',
  },
  error: { color: '#fca5a5', fontSize: 13, marginTop: 8 }
}
