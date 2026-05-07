import { useState } from 'react'
import SessionsPage from './pages/SessionsPage'
import StudyPage from './pages/StudyPage'
import ReviewPage from './pages/ReviewPage'

const TABS = [
  { id: 'sessions', label: 'My Sessions' },
  { id: 'study',    label: 'Study'       },
  { id: 'review',   label: 'Review'      },
]

export default function App() {
  const [tab, setTab]               = useState('sessions')
  const [session, setSession]       = useState(null)   // active session object
  const [messages, setMessages]     = useState([])     // chat history (kept in sync with session)

  function openSession(s) {
    setSession(s)
    setMessages(s.messages || [])
    setTab('study')
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-3">
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
          <span className="text-white font-bold text-sm">TA</span>
        </div>
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Tutor Agent</h1>
          <p className="text-xs text-gray-500">AI-powered study assistant</p>
        </div>
        {session && (
          <span className="ml-4 px-3 py-1 bg-blue-50 text-blue-700 text-xs font-medium rounded-full">
            {session.title}
          </span>
        )}
      </header>

      <nav className="bg-white border-b border-gray-200 px-6">
        <div className="flex gap-1">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                tab === t.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}>
              {t.label}
            </button>
          ))}
        </div>
      </nav>

      <main className="flex-1 p-6">
        <div style={{ display: tab === 'sessions' ? 'block' : 'none' }}>
          <SessionsPage onOpenSession={openSession} />
        </div>
        <div style={{ display: tab === 'study' ? 'flex' : 'none', flexDirection: 'column', height: '100%' }}>
          <StudyPage
            session={session}
            messages={messages}
            onMessagesChange={setMessages}
            onGoToReview={() => setTab('review')}
            onSessionUpdate={(s) => { setSession(s); setMessages([]); setAnswers({}); setResult(null) }}
          />
        </div>
        <div style={{ display: tab === 'review' ? 'block' : 'none' }}>
          <ReviewPage
            session={session}
            onSessionUpdate={setSession}
          />
        </div>
      </main>
    </div>
  )
}
