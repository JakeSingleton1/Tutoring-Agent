import { useEffect, useRef, useState } from 'react'

function QuestionSidebar({ questions, activeId, onSelect, onRegenerate, regenerating }) {
  return (
    <div className="w-52 shrink-0 flex flex-col gap-1">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide px-2 mb-1">Questions</p>
      {questions.map(q => (
        <button key={q.id} onClick={() => onSelect(q.id)}
          className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
            activeId === q.id ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-600 hover:bg-gray-100'
          }`}>
          <span className="font-mono text-xs mr-1.5 text-gray-400">{q.id}</span>
          <span className="line-clamp-2 leading-snug">{q.topic}</span>
        </button>
      ))}
      <button
        onClick={onRegenerate}
        disabled={regenerating}
        className="mt-3 w-full text-xs text-blue-600 border border-blue-200 rounded-lg px-3 py-2 hover:bg-blue-50 disabled:opacity-40 transition-colors"
      >
        {regenerating ? 'Generating…' : '↺ New questions'}
      </button>
    </div>
  )
}

export default function StudyPage({ session, messages, onMessagesChange, onGoToReview, onSessionUpdate }) {
  const [activeQ,      setActiveQ]      = useState(null)
  const [showQ,        setShowQ]        = useState(false)
  const [input,        setInput]        = useState('')
  const [streaming,    setStreaming]     = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [saveError,    setSaveError]    = useState('')
  const bottomRef = useRef(null)

  useEffect(() => {
    if (session && !activeQ) setActiveQ(session.questions[0]?.id ?? null)
  }, [session?.id])

  function handleRegenerate() {
    if (!session || regenerating) return
    setRegenerating(true)
    setSaveError('')

    const es = new EventSource(`/api/sessions/${session.id}/regenerate/stream`)
    es.onmessage = (e) => {
      if (e.data === '[DONE]') { es.close(); setRegenerating(false); return }
      try {
        const ev = JSON.parse(e.data)
        if (ev.type === 'done') {
          es.close()
          setRegenerating(false)
          setActiveQ(ev.session.questions[0]?.id ?? null)
          onMessagesChange([])
          if (onSessionUpdate) onSessionUpdate(ev.session)
        } else if (ev.type === 'error') {
          setSaveError(ev.message)
          es.close()
          setRegenerating(false)
        }
      } catch { /* skip */ }
    }
    es.onerror = () => {
      setSaveError('Connection error during regeneration.')
      es.close()
      setRegenerating(false)
    }
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function saveMessages(updated) {
    if (!session) return
    try {
      await fetch(`/api/sessions/${session.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: updated }),
      })
    } catch {
      setSaveError('Could not auto-save chat history.')
    }
  }

  async function sendMessage() {
    const text = input.trim()
    if (!text || streaming || !session) return
    setInput('')
    setSaveError('')

    const userMsg      = { role: 'user',      content: text }
    const assistantMsg = { role: 'assistant', content: '' }
    const history      = messages

    const withUser = [...history, userMsg, assistantMsg]
    onMessagesChange(withUser)
    setStreaming(true)

    let fullResponse = ''
    try {
      const res = await fetch(`/api/tutor/${session.id}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history }),
      })

      const reader  = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6)
          if (payload === '[DONE]') break
          try {
            const { text: token } = JSON.parse(payload)
            fullResponse += token
            onMessagesChange(prev => {
              const updated = [...prev]
              updated[updated.length - 1] = { ...updated[updated.length - 1], content: updated[updated.length - 1].content + token }
              return updated
            })
          } catch { /* skip */ }
        }
      }
    } finally {
      setStreaming(false)
      // Auto-save the completed exchange
      const final = [...history, userMsg, { role: 'assistant', content: fullResponse }]
      onMessagesChange(final)
      saveMessages(final)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  if (!session) {
    return (
      <div className="max-w-lg mx-auto mt-20 text-center text-gray-400 text-sm space-y-2">
        <p>No active session.</p>
        <p>Go to <strong>My Sessions</strong> to open or create one.</p>
      </div>
    )
  }

  const activeQuestion = session.questions.find(q => q.id === activeQ)

  return (
    <div className="max-w-5xl mx-auto flex gap-5" style={{ height: 'calc(100vh - 10rem)' }}>
      <QuestionSidebar questions={session.questions} activeId={activeQ}
        onSelect={id => { setActiveQ(id); setShowQ(true) }}
        onRegenerate={handleRegenerate}
        regenerating={regenerating}
      />

      <div className="flex-1 flex flex-col gap-3 min-w-0">
        {activeQuestion && (
          <div className="bg-white rounded-xl border border-gray-200 shrink-0">
            <button className="w-full text-left px-5 py-3 flex items-center justify-between"
              onClick={() => setShowQ(v => !v)}>
              <span className="text-sm font-semibold text-blue-700">
                [{activeQuestion.id}] {activeQuestion.topic}
              </span>
              <span className="text-xs text-gray-400">{showQ ? 'hide ▲' : 'show ▼'}</span>
            </button>
            {showQ && (
              <div className="px-5 pb-4 border-t border-gray-100 pt-3 text-sm text-gray-700 leading-relaxed">
                {activeQuestion.question_text}
              </div>
            )}
          </div>
        )}

        <div className="flex-1 overflow-auto space-y-3 pr-1">
          {messages.length === 0 && (
            <div className="text-center text-sm text-gray-400 mt-10 space-y-1">
              <p>Ask the tutor a question, share your working, or say "I'm stuck on Q1".</p>
              <p className="text-xs">Your conversation is saved automatically.</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm whitespace-pre-wrap leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-sm'
                  : 'bg-white border border-gray-200 text-gray-800 rounded-bl-sm'
              }`}>
                {msg.content}
                {msg.role === 'assistant' && msg.content === '' && (
                  <span className="inline-block w-2 h-4 bg-gray-400 animate-pulse rounded-sm" />
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {saveError && <p className="text-xs text-red-500 text-center">{saveError}</p>}

        <div className="bg-white rounded-xl border border-gray-200 p-3 flex gap-2 shrink-0">
          <textarea value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKeyDown}
            disabled={streaming}
            placeholder="Ask the tutor… (Enter to send, Shift+Enter for newline)"
            rows={2}
            className="flex-1 resize-none text-sm px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          />
          <div className="flex flex-col gap-2 justify-end">
            <button onClick={sendMessage} disabled={streaming || !input.trim()}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
              {streaming ? '…' : 'Send'}
            </button>
            <button onClick={onGoToReview}
              className="px-4 py-2 border border-gray-300 text-gray-600 text-xs font-medium rounded-lg hover:bg-gray-50 transition-colors whitespace-nowrap">
              Submit answers →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
