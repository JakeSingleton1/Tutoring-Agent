import { useState, useEffect, useRef } from 'react'

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function SessionCard({ s, onOpen, onRegenerate, onDelete, regenerating }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 flex items-start justify-between hover:border-blue-300 transition-colors">
      <button className="flex-1 text-left" onClick={() => onOpen(s.id)}>
        <p className="text-sm font-semibold text-gray-900">{s.title}</p>
        <p className="text-xs text-gray-400 mt-0.5">{s.source} · {formatDate(s.created_at)}</p>
        <div className="flex items-center gap-3 mt-2">
          <span className="text-xs text-gray-500">{s.question_count} questions</span>
          {s.score && (
            <span className="text-xs font-medium text-green-700 bg-green-50 px-2 py-0.5 rounded-full">
              {s.score} pts
            </span>
          )}
        </div>
      </button>
      <div className="flex items-center gap-2 ml-4 shrink-0">
        <button
          onClick={() => onRegenerate(s.id)}
          disabled={regenerating === s.id}
          title="Generate new questions from the same material"
          className="text-xs text-blue-500 hover:text-blue-700 disabled:opacity-40 transition-colors px-2 py-1 rounded hover:bg-blue-50"
        >
          {regenerating === s.id ? '…' : '↺ New questions'}
        </button>
        <button onClick={() => onDelete(s.id)}
          className="text-gray-300 hover:text-red-400 transition-colors text-lg leading-none">
          ×
        </button>
      </div>
    </div>
  )
}

export default function SessionsPage({ onOpenSession }) {
  const [sessions,     setSessions]     = useState([])
  const [uploading,    setUploading]    = useState(false)
  const [regenerating, setRegenerating] = useState(null)  // session id being regenerated
  const [progress,     setProgress]     = useState([])
  const [error,        setError]        = useState('')
  const fileRef = useRef(null)

  useEffect(() => { loadSessions() }, [])

  async function loadSessions() {
    try {
      const res = await fetch('/api/sessions')
      setSessions(await res.json())
    } catch { /* backend not yet up */ }
  }

  async function openSession(id) {
    try {
      const res = await fetch(`/api/sessions/${id}`)
      if (!res.ok) throw new Error('Could not load session')
      onOpenSession(await res.json())
    } catch (e) {
      setError(e.message)
    }
  }

  function regenerateSession(id) {
    setRegenerating(id)
    setError('')

    const es = new EventSource(`/api/sessions/${id}/regenerate/stream`)
    es.onmessage = (e) => {
      if (e.data === '[DONE]') { es.close(); setRegenerating(null); return }
      try {
        const ev = JSON.parse(e.data)
        if (ev.type === 'done') {
          setSessions(prev => [
            { id: ev.session.id, title: ev.session.title, source: ev.session.source,
              created_at: ev.session.created_at, question_count: ev.session.questions.length, score: null },
            ...prev,
          ])
          es.close()
          setRegenerating(null)
          onOpenSession(ev.session)
        } else if (ev.type === 'error') {
          setError(ev.message)
          es.close()
          setRegenerating(null)
        }
      } catch { /* skip */ }
    }
    es.onerror = () => {
      setError('Connection error during regeneration.')
      es.close()
      setRegenerating(null)
    }
  }

  async function deleteSession(id) {
    await fetch(`/api/sessions/${id}`, { method: 'DELETE' })
    setSessions(prev => prev.filter(s => s.id !== id))
  }

  function handleFilePick(file) {
    if (!file || !file.name.toLowerCase().endsWith('.pdf')) {
      setError('Please select a PDF file.')
      return
    }
    startGeneration(file)
  }

  function startGeneration(file) {
    setUploading(true)
    setProgress([])
    setError('')

    const form = new FormData()
    form.append('file', file)

    fetch('/api/sessions/generate/stream', { method: 'POST', body: form })
      .then(res => {
        if (!res.ok) return res.text().then(t => { throw new Error(t) })
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        function pump() {
          return reader.read().then(({ done, value }) => {
            if (done) { setUploading(false); return }
            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop()

            for (const line of lines) {
              if (!line.startsWith('data: ')) continue
              const payload = line.slice(6)
              if (payload === '[DONE]') { setUploading(false); return }
              try {
                const ev = JSON.parse(payload)
                if (ev.type === 'status') {
                  setProgress(p => [...p, ev.message])
                } else if (ev.type === 'done') {
                  setSessions(prev => [
                    { id: ev.session.id, title: ev.session.title, source: ev.session.source,
                      created_at: ev.session.created_at, question_count: ev.session.questions.length, score: null },
                    ...prev,
                  ])
                  setUploading(false)
                  onOpenSession(ev.session)
                } else if (ev.type === 'error') {
                  setError(ev.message)
                  setUploading(false)
                }
              } catch { /* skip */ }
            }
            return pump()
          })
        }
        return pump()
      })
      .catch(e => { setError(e.message); setUploading(false) })
  }

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">{error}</div>
      )}

      {/* Upload card */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <div>
          <h2 className="text-base font-semibold text-gray-900">New Study Session</h2>
          <p className="text-sm text-gray-500 mt-1">
            Upload a PDF and the AI will generate 10 study questions from it.
          </p>
        </div>

        {uploading ? (
          <div className="space-y-2">
            {progress.map((msg, i) => (
              <p key={i} className="text-sm text-gray-600 flex items-center gap-2">
                <span className="inline-block w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                {msg}
              </p>
            ))}
          </div>
        ) : (
          <>
            <div
              className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors"
              onClick={() => fileRef.current?.click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); handleFilePick(e.dataTransfer.files[0]) }}
            >
              <input ref={fileRef} type="file" accept=".pdf" className="hidden"
                onChange={e => handleFilePick(e.target.files[0])} />
              <p className="text-gray-500 text-sm">Drop a PDF here or click to browse</p>
              <p className="text-xs text-gray-400 mt-1">Textbooks, lecture notes, articles…</p>
            </div>
          </>
        )}
      </div>

      {/* Past sessions */}
      {sessions.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide px-1">
            Past Sessions
          </h3>
          {sessions.map(s => (
            <SessionCard key={s.id} s={s}
              onOpen={openSession}
              onRegenerate={regenerateSession}
              onDelete={deleteSession}
              regenerating={regenerating}
            />
          ))}
        </div>
      )}

      {sessions.length === 0 && !uploading && (
        <p className="text-center text-sm text-gray-400 mt-6">
          No sessions yet — upload a PDF to get started.
        </p>
      )}
    </div>
  )
}
