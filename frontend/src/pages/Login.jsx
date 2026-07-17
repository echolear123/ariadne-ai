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

  // 动态迷宫背景 (卡片内)
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
      mCtx.strokeStyle = 'rgba(255, 255, 255, 0.8)'
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
          <div style={styles.cardGlow} />
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
        .login-input { transition: all 0.3s ease; }
        .login-input:focus { outline: none; }
        .login-input:focus ~ .input-line { width: 100% !important; box-shadow: 0 0 10px rgba(255,50,50,0.5); }
        .login-input::placeholder { color: rgba(255,255,255,0.2); font-size: 13px; letter-spacing: 1px; }
        .login-btn:hover {
          background: linear-gradient(90deg, rgba(50,20,20,1), rgba(150,30,30,0.8)) !important;
          color: #fff !important;
          border-color: rgba(255,75,75,0.6) !important;
          box-shadow: 0 0 20px rgba(255,50,50,0.3) !important;
        }
        @keyframes borderGlow {
          0% { filter: hue-rotate(0deg); opacity: 0.5; }
          50% { opacity: 1; }
          100% { filter: hue-rotate(360deg); opacity: 0.5; }
        }
        @keyframes textGradient {
          to { background-position: 200% center; }
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
    borderRadius: 20,
    background: 'linear-gradient(145deg, rgba(30,30,30,0.6) 0%, rgba(10,10,10,0.8) 100%)',
    boxShadow: '0 20px 50px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.1)',
    overflow: 'hidden',
    border: '1px solid transparent',
    backgroundClip: 'padding-box',
  },
  cardGlow: {
    position: 'absolute',
    top: -2, left: -2, right: -2, bottom: -2,
    background: 'linear-gradient(45deg, rgba(255,50,50,0.1), rgba(255,255,255,0.05), rgba(255,50,50,0.2))',
    zIndex: -2,
    borderRadius: 22,
    animation: 'borderGlow 6s linear infinite',
  },
  mazeCanvas: {
    position: 'absolute', top: 0, left: 0,
    width: '100%', height: '100%',
    zIndex: -1, opacity: 0.15,
  },
  content: { position: 'relative', zIndex: 10 },
  header: { textAlign: 'center', marginBottom: 38 },
  title: {
    fontSize: 32,
    fontWeight: 700,
    letterSpacing: 3,
    margin: '0 0 10px 0',
    background: 'linear-gradient(to right, #ffffff, #ff4b4b, #ffffff)',
    backgroundSize: '200% auto',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    animation: 'textGradient 3s linear infinite',
  },
  subtitle: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.5)',
    letterSpacing: 2,
    margin: 0,
  },
  inputGroup: { position: 'relative', marginBottom: 26 },
  input: {
    width: '100%', background: 'transparent', border: 'none',
    borderBottom: '1px solid rgba(255,255,255,0.1)',
    padding: '10px 0', fontSize: 15, color: '#fff', boxSizing: 'border-box',
  },
  inputLine: {
    position: 'absolute', bottom: 0, left: 0, width: '0%', height: 2,
    background: 'linear-gradient(90deg, transparent, #ff3333, #ff8888)',
    transition: 'width 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
  },
  btn: {
    width: '100%', padding: '14px', marginTop: 15,
    background: 'linear-gradient(90deg, rgba(30,30,30,0.8), rgba(50,20,20,0.8))',
    border: '1px solid rgba(255,75,75,0.2)', borderRadius: 8,
    color: 'rgba(255,255,255,0.8)', fontSize: 15, letterSpacing: 2,
    cursor: 'pointer', transition: 'all 0.3s ease',
    position: 'relative', overflow: 'hidden', fontFamily: 'inherit',
  },
  error: {
    color: 'rgba(255,100,100,0.9)', fontSize: 13, marginTop: 15,
    textAlign: 'center', letterSpacing: 1,
  },
}
