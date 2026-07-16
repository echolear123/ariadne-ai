import { Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login.jsx'
import Chat from './pages/Chat.jsx'
import DocumentManager from './pages/DocumentManager.jsx'
import { useState, useEffect } from 'react'

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
    return <Login onLogin={handleLogin} />
  }

  if (showManager) {
    return <DocumentManager onBack={() => setShowManager(false)} />
  }

  return (
    <Routes>
      <Route path="/" element={
        <Chat user={user} onLogout={handleLogout} onGoToManager={() => setShowManager(true)} />
      } />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
