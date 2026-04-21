import { useState, useEffect, useRef } from 'react'

export default function TutorPage() {
  const [students, setStudents]       = useState([])
  const [selectedId, setSelectedId]   = useState('')
  const [variant, setVariant]         = useState(null)
  const [showAssignment, setShowAssignment] = useState(false)
  const [messages, setMessages]       = useState([])   // [{role, content}]
  const [input, setInput]             = useState('')
  const [streaming, setStreaming]     = useState(false)
  const bottomRef = useRef(null)

  // Load student list on mount
  useEffect(() => {
    fetch('/api/students')
      .then(r => r.json())
      .then(setStudents)
  }, [])

  // Load variant when student changes
  useEffect(() => {
    if (!selectedId) return
    setVariant(null)
    setMessages([])
    setShowAssignment(false)
    fetch(`/api/students/${selectedId}`)
      .then(r => r.json())
      .then(setVariant)
  }, [selectedId])

  // Auto-scroll chat
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function sendMessage() {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')

    const userMsg = { role: 'user', content: text }
    const assistantMsg = { role: 'assistant', content: '' }
    const history = messages  // history before this turn

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setStreaming(true)

    try {
      const res = await fetch(`/api/tutor/${selectedId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history }),
      })

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() // keep incomplete line

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6)
          if (payload === '[DONE]') break
          try {
            const { text: token } = JSON.parse(payload)
            setMessages(prev => {
              const updated = [...prev]
              updated[updated.length - 1] = {
                ...updated[updated.length - 1],
                content: updated[updated.length - 1].content + token,
              }
              return updated
            })
          } catch { /* skip malformed lines */ }
        }
      }
    } finally {
      setStreaming(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="max-w-3xl mx-auto flex flex-col gap-4 h-[calc(100vh-10rem)]">
      {/* Student selector */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-4 shrink-0">
        <label className="text-sm font-medium text-gray-700 whitespace-nowrap">Student</label>
        <select
          value={selectedId}
          onChange={e => setSelectedId(e.target.value)}
          className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">— select a student —</option>
          {students.map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        {variant && (
          <button
            onClick={() => setShowAssignment(v => !v)}
            className="px-3 py-2 text-xs font-medium text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-50 transition-colors whitespace-nowrap"
          >
            {showAssignment ? 'Hide' : 'Show'} Assignment
          </button>
        )}
      </div>

      {/* Assignment accordion */}
      {showAssignment && variant && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shrink-0 space-y-4 overflow-auto max-h-60">
          <h3 className="text-sm font-semibold text-gray-900">
            Assignment — {variant.student_id}
          </h3>
          {variant.questions.map(q => (
            <div key={q.id} className="border-l-2 border-blue-200 pl-4">
              <p className="text-xs font-semibold text-blue-600 mb-1">
                [{q.id}] {q.scenario_theme}
              </p>
              <p className="text-sm text-gray-700">{q.prompt_text}</p>
            </div>
          ))}
        </div>
      )}

      {/* No student selected */}
      {!selectedId && (
        <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
          Select a student to start a tutor session.
        </div>
      )}

      {/* Chat area */}
      {selectedId && (
        <>
          <div className="flex-1 overflow-auto space-y-3 pr-1">
            {messages.length === 0 && variant && (
              <div className="text-center text-sm text-gray-400 mt-8">
                Ask the tutor anything about your assignment.
              </div>
            )}

            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm whitespace-pre-wrap leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white rounded-br-sm'
                      : 'bg-white border border-gray-200 text-gray-800 rounded-bl-sm'
                  }`}
                >
                  {msg.content}
                  {msg.role === 'assistant' && msg.content === '' && (
                    <span className="inline-block w-2 h-4 bg-gray-400 animate-pulse rounded-sm" />
                  )}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          {/* Input bar */}
          <div className="bg-white rounded-xl border border-gray-200 p-3 flex gap-2 shrink-0">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={streaming || !variant}
              placeholder="Ask the tutor… (Enter to send, Shift+Enter for newline)"
              rows={2}
              className="flex-1 resize-none text-sm px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            />
            <button
              onClick={sendMessage}
              disabled={streaming || !input.trim() || !variant}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors self-end"
            >
              {streaming ? '…' : 'Send'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
