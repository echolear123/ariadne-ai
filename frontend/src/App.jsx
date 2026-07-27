import { Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login.jsx'
import Chat from './pages/Chat.jsx'
import DocumentManager from './pages/DocumentManager.jsx'
import { useState, useEffect } from 'react'

// 全局像素风格 CSS
const GLOBAL_CSS = `
  * { box-sizing: border-box; }
  :root {
    --bg: #eaf6f0;
    --bg-alt: #f4f9f4;
    --card-bg: #ffffff;
    --green-dark: #0f3d2a;
    --green-mid: #208a5e;
    --green-light: #bce1ce;
    --green-bright: #6ddb9f;
    --green-btn: #178351;
    --blue-btn: #476aed;
    --red-accent: #eb7a7a;
    --text: #0f3d2a;
    --text-secondary: #555;
    --border-sm: 3px solid #0f3d2a;
    --border-md: 4px solid #0f3d2a;
    --shadow-sm: 3px 3px 0px #0f3d2a;
    --shadow-md: 4px 4px 0px #0f3d2a;
    --shadow-lg: 6px 6px 0px #0f3d2a;
  }
  html, body, #root { height: 100%; }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: var(--green-dark); border-radius: 3px; }
  input, textarea, button { font-family: inherit; }
`

export default function App() {
  const [user, setUser] = useState(null)
  const [showManager, setShowManager] = useState(false)

  useEffect(() => {
    const uid = localStorage.getItem('user_id')
    const uname = localStorage.getItem('username')
    if (uid && uname) setUser({ user_id: uid, username: uname })
  }, [])

  function handleLogin(userData) {
    setUser(userData)
  }

  function handleLogout() {
    localStorage.removeItem('user_id')
    localStorage.removeItem('username')
    setUser(null)
  }

  if (!user) {
    return <><style>{GLOBAL_CSS}</style><Login onLogin={handleLogin} /></>
  }

  if (showManager) {
    return <><style>{GLOBAL_CSS}</style><DocumentManager onBack={() => setShowManager(false)} /></>
  }

  return (
    <><style>{GLOBAL_CSS}</style>
    <Routes>
      <Route path="/" element={
        <Chat user={user} onLogout={handleLogout} onGoToManager={() => setShowManager(true)} />
      } />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </>
  )
}
