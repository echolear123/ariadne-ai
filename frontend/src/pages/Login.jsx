import { useState, useEffect, useRef } from 'react'
import { login } from '../api.js'
import MacPatternBackground from '../components/MacPatternBackground.jsx'

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const threadCanvasRef = useRef(null)
  const mazeCanvasRef = useRef(null)

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

  // 动态迷宫背景 (卡片内) - 复用自 logincard.html
  useEffect(() => {
    const mazeCanvas = mazeCanvasRef.current
    if (!mazeCanvas) return
    const card = mazeCanvas.parentElement
    const mCtx = mazeCanvas.getContext('2d')

    function resizeMaze() {
      if (!card) return
      mazeCanvas.width = card.offsetWidth
      mazeCanvas.height = card.offsetHeight
    }
    resizeMaze()

    const gridSize = 20
    let cols = Math.ceil(mazeCanvas.width / gridSize)
    let rows = Math.ceil(mazeCanvas.height / gridSize)
    let mazeData = []
    for (let i = 0; i < cols * rows; i++) {
      mazeData.push(Math.random() > 0.5 ? 1 : 0)
    }

    function drawMaze() {
      mCtx.clearRect(0, 0, mazeCanvas.width, mazeCanvas.height)
      mCtx.strokeStyle = 'rgba(100, 80, 60, 0.7)'
      mCtx.lineWidth = 2
      mCtx.lineCap = 'round'
      for (let y = 0; y < rows; y++) {
        for (let x = 0; x < cols; x++) {
          let idx = x + y * cols
          let px = x * gridSize
          let py = y * gridSize
          mCtx.beginPath()
          if (mazeData[idx] === 1) {
            mCtx.moveTo(px, py)
            mCtx.lineTo(px + gridSize, py + gridSize)
          } else {
            mCtx.moveTo(px + gridSize, py)
            mCtx.lineTo(px, py + gridSize)
          }
          mCtx.stroke()
        }
      }
    }
    drawMaze()

    const mazeInterval = setInterval(() => {
      for (let i = 0; i < 3; i++) {
        let randomIdx = Math.floor(Math.random() * mazeData.length)
        mazeData[randomIdx] = mazeData[randomIdx] === 1 ? 0 : 1
      }
      drawMaze()
    }, 100)

    return () => clearInterval(mazeInterval)
  }, [])

  // 婉约红线跟随鼠标
  useEffect(() => {
    const threadCanvas = threadCanvasRef.current
    if (!threadCanvas) return
    const tCtx = threadCanvas.getContext('2d')

    function resizeThread() {
      threadCanvas.width = window.innerWidth
      threadCanvas.height = window.innerHeight
    }
    window.addEventListener('resize', resizeThread)
    resizeThread()

    let mouse = { x: window.innerWidth / 2, y: window.innerHeight / 2 }
    let trail = []
    const maxTrail = 90

    function onMouseMove(e) {
      mouse.x = e.clientX
      mouse.y = e.clientY
    }
    window.addEventListener('mousemove', onMouseMove)

    let animId
    function renderThread() {
      tCtx.clearRect(0, 0, threadCanvas.width, threadCanvas.height)
      trail.push({ x: mouse.x, y: mouse.y })
      if (trail.length > maxTrail) trail.shift()

      if (trail.length > 2) {
        tCtx.lineCap = 'round'
        tCtx.lineJoin = 'round'
        for (let i = 1; i < trail.length - 1; i++) {
          const ratio = i / trail.length
          const alpha = Math.pow(ratio, 2)
          const prevXc = (trail[i - 1].x + trail[i].x) / 2
          const prevYc = (trail[i - 1].y + trail[i].y) / 2
          const xc = (trail[i].x + trail[i + 1].x) / 2
          const yc = (trail[i].y + trail[i + 1].y) / 2

          tCtx.beginPath()
          tCtx.moveTo(prevXc, prevYc)
          tCtx.quadraticCurveTo(trail[i].x, trail[i].y, xc, yc)
          tCtx.strokeStyle = `rgba(255, 30, 50, ${alpha * 0.35})`
          tCtx.lineWidth = 14 * ratio
          tCtx.stroke()

          tCtx.beginPath()
          tCtx.moveTo(prevXc, prevYc)
          tCtx.quadraticCurveTo(trail[i].x, trail[i].y, xc, yc)
          tCtx.strokeStyle = `rgba(255, 150, 150, ${alpha * 0.9})`
          tCtx.lineWidth = 2.5 * ratio
          tCtx.stroke()
        }
        const last = trail.length - 1
        const prevXc = (trail[last - 1].x + trail[last].x) / 2
        const prevYc = (trail[last - 1].y + trail[last].y) / 2
        tCtx.beginPath()
        tCtx.moveTo(prevXc, prevYc)
        tCtx.lineTo(trail[last].x, trail[last].y)
        tCtx.strokeStyle = 'rgba(255, 30, 50, 0.35)'
        tCtx.lineWidth = 14
        tCtx.stroke()
        tCtx.beginPath()
        tCtx.moveTo(prevXc, prevYc)
        tCtx.lineTo(trail[last].x, trail[last].y)
        tCtx.strokeStyle = 'rgba(255, 150, 150, 0.9)'
        tCtx.lineWidth = 2.5
        tCtx.stroke()
      }
      animId = requestAnimationFrame(renderThread)
    }
    renderThread()

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('resize', resizeThread)
    }
  }, [])

  return (
    <div style={styles.container}>
      <MacPatternBackground />
      <canvas ref={threadCanvasRef} style={styles.threadCanvas} />
      <div style={styles.overlay}>
        <div style={styles.cardOuter}>
          <canvas ref={mazeCanvasRef} style={styles.mazeCanvas} />
          <div style={styles.content}>
            <div style={styles.header}>
              <h1 style={styles.title}>Ariadne</h1>
              <p style={styles.subtitle}>循此红线，洞见万卷</p>
            </div>
            <form onSubmit={handleSubmit}>
              <div style={styles.inputGroup}>
                <input
                  className="login-input"
                  style={styles.input}
                  type="text"
                  placeholder="输入行者名称"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  autoFocus
                />
                <div className="input-line" style={styles.inputLine} />
              </div>
              <div style={styles.inputGroup}>
                <input
                  className="login-input"
                  style={styles.input}
                  type="password"
                  placeholder="输入通路密钥"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                />
                <div className="input-line" style={styles.inputLine} />
              </div>
              <button type="submit" className="login-btn" style={styles.btn} disabled={loading}>
                {loading ? '正在探寻...' : '循线破局'}
              </button>
            </form>
            {error && <p style={styles.error}>{error}</p>}
          </div>
        </div>
      </div>
      <style>{`
        .login-input { transition: all 0.2s ease; }
        .login-input:focus { outline: none; border-color: #0f3d2a !important; }
        .login-input::placeholder { color: rgba(15,61,42,0.3); font-size: 13px; }
        .login-btn:hover {
          background: #1a9a5e !important;
        }
        .login-btn:active {
          transform: translate(4px, 4px); box-shadow: 0px 0px 0px #0f3d2a !important;
        }
      `}</style>
    </div>
  )
}

const styles = {
  container: {
    position: 'relative', width: '100%', height: '100vh', overflow: 'hidden',
    display: 'flex', justifyContent: 'center', alignItems: 'center',
    backgroundColor: '#050505',
  },
  threadCanvas: {
    position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
    pointerEvents: 'none', zIndex: 999,
  },
  overlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    display: 'flex', justifyContent: 'center', alignItems: 'center',
    zIndex: 1,
  },
  cardOuter: {
    position: 'relative',
    width: 340,
    padding: '40px 32px',
    borderRadius: 12,
    background: '#ffffff',
    border: '4px solid #0f3d2a',
    boxShadow: '8px 8px 0px #0f3d2a',
    overflow: 'hidden',
  },
  mazeCanvas: {
    position: 'absolute', top: 0, left: 0,
    width: '100%', height: '100%',
    zIndex: 0, opacity: 0.2,
  },
  content: { position: 'relative', zIndex: 1 },
  header: { textAlign: 'center', marginBottom: 38 },
  title: {
    fontSize: 32,
    fontWeight: 700,
    letterSpacing: 2,
    margin: '0 0 10px 0',
    color: '#eb7a7a',
    textShadow: '2px 2px 0px #bce1ce',
  },
  subtitle: {
    fontSize: 14,
    color: '#555',
    letterSpacing: 1,
    margin: 0,
    fontWeight: 'bold',
  },
  inputGroup: { position: 'relative', marginBottom: 24 },
  input: {
    width: '85%', background: '#fff', border: '3px solid #bce1ce',
    borderRadius: 6, padding: '12px', fontSize: 15,
    color: '#0f3d2a', boxSizing: 'border-box', outline: 'none',
    boxShadow: 'inset 2px 2px 0px #eaf6f0',
    margin: '0 auto', display: 'block',
  },
  inputLine: {
    display: 'none',
  },
  btn: {
    width: '100%', padding: '15px', marginTop: 10,
    background: '#178351', color: '#fff',
    border: '3px solid #0f3d2a', borderRadius: 6,
    boxShadow: '4px 4px 0px #0f3d2a',
    fontSize: 18, letterSpacing: 1,
    cursor: 'pointer', transition: 'all 0.1s',
    fontFamily: 'inherit',
  },
  error: {
    color: '#dc2626', fontSize: 13, marginTop: 15,
    textAlign: 'center', letterSpacing: 1,
  },
}
