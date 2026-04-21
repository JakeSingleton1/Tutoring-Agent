import { useState } from 'react'
import GeneratePage from './pages/GeneratePage'
import TutorPage from './pages/TutorPage'
import GradePage from './pages/GradePage'

const TABS = [
  { id: 'generate', label: 'Generate Variants' },
  { id: 'tutor',    label: 'Tutor Session'     },
  { id: 'grade',    label: 'Grade Submission'   },
]

export default function App() {
  const [tab, setTab] = useState('generate')

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-3">
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
          <span className="text-white font-bold text-sm">TA</span>
        </div>
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Tutor Agent</h1>
          <p className="text-xs text-gray-500">Agentics — Spring 2026</p>
        </div>
      </header>

      {/* Tab bar */}
      <nav className="bg-white border-b border-gray-200 px-6">
        <div className="flex gap-1">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                tab === t.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </nav>

      {/* Page content */}
      <main className="flex-1 p-6">
        {tab === 'generate' && <GeneratePage />}
        {tab === 'tutor'    && <TutorPage    />}
        {tab === 'grade'    && <GradePage    />}
      </main>
    </div>
  )
}
