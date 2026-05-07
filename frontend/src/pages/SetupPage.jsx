import { useState, useRef } from 'react'

async function getErrorMessage(res, fallback = 'Request failed') {
  try {
    const data = await res.json()
    return data.detail || data.message || fallback
  } catch {
    const text = await res.text().catch(() => '')
    return text || fallback
  }
}

function ProgressLog({ log, running }) {
  return (
    <div className="bg-gray-900 rounded-xl p-4 font-mono text-xs leading-relaxed overflow-auto max-h-52">
      {log.map((entry, i) => (
        <div key={i} className={
          entry.ok  ? 'text-green-400' :
          entry.err ? 'text-red-400'   :
          entry.dim ? 'text-gray-400'  :
                      'text-gray-200'
        }>
          {entry.text}
        </div>
      ))}
      {running && <div className="text-yellow-400 animate-pulse mt-1">…</div>}
    </div>
  )
}

function QuestionCard({ q }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        className="w-full text-left px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
        onClick={() => setOpen(v => !v)}
      >
        <span className="text-sm font-medium text-gray-800">
          <span className="text-blue-600 mr-2">[{q.id}]</span>
          {q.scenario_theme || q.learning_objective?.slice(0, 70) || 'Question'}
        </span>
        <span className="text-gray-400 text-xs">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 pt-3 border-t border-gray-100 bg-gray-50 text-sm text-gray-700">
          {q.prompt_text || q.prompt}
        </div>
      )}
    </div>
  )
}

// IDLE → UPLOADING → TOPIC_READY → GENERATING → DONE
export default function SetupPage({ variant, onVariantReady, onStartStudying }) {
  const [step, setStep]       = useState(() => variant ? 'DONE' : 'IDLE')
  const [pdfFile, setPdfFile] = useState(null)
  const [topic, setTopic]     = useState(null)
  const [log, setLog]         = useState([])
  const [running, setRunning] = useState(false)
  const [error, setError]     = useState('')
  const fileRef = useRef(null)

  // Use the already-generated variant if we have one
  const questions = variant?.questions ?? []

  function addLog(text, kind = 'normal') {
    setLog(prev => [...prev, { text, ok: kind === 'ok', err: kind === 'err', dim: kind === 'dim' }])
  }

  async function handleUploadPdf() {
    if (!pdfFile) return
    setStep('UPLOADING')
    setError('')
    setTopic(null)
    addLog(`Analysing ${pdfFile.name}…`, 'dim')

    const form = new FormData()
    form.append('file', pdfFile)

    try {
      const res = await fetch('/api/pdf/upload', { method: 'POST', body: form })
      if (!res.ok) throw new Error(await getErrorMessage(res, 'Upload failed'))
      const master = await res.json()
      setTopic(master)
      setStep('TOPIC_READY')
      addLog(`✓ Extracted ${master.questions?.length} topics from PDF`, 'ok')
    } catch (e) {
      setError(e.message)
      setStep('IDLE')
    }
  }

  async function handleUseExisting() {
    setError('')
    try {
      const res = await fetch('/api/master')
      if (!res.ok) throw new Error('Could not load topic material')
      const master = await res.json()
      setTopic(master)
      setStep('TOPIC_READY')
    } catch (e) {
      setError(e.message)
    }
  }

  function handleGenerate() {
    setLog([])
    setStep('GENERATING')
    setRunning(true)
    addLog('Generating your study questions…', 'dim')

    const es = new EventSource('/api/generate/first/stream')
    es.onmessage = (e) => {
      if (e.data === '[DONE]') { es.close(); setRunning(false); return }
      try {
        const ev = JSON.parse(e.data)
        if (ev.type === 'first_done') {
          onVariantReady(ev.variant)
          setStep('DONE')
          addLog('✓ Study questions ready!', 'ok')
        } else if (ev.type === 'valid') {
          addLog('✓ Questions validated', 'ok')
        } else if (ev.type === 'validating') {
          addLog(`Validating… (attempt ${ev.attempt}/${ev.max})`, 'dim')
        } else if (ev.type === 'generating') {
          addLog('Building questions from your material…', 'dim')
        } else if (ev.type === 'error') {
          setError(ev.message)
          setStep('TOPIC_READY')
          addLog(`✗ ${ev.message}`, 'err')
        }
      } catch { /* skip malformed */ }
    }
    es.onerror = () => {
      es.close(); setRunning(false)
      setError('Connection error — is the backend running?')
      setStep('TOPIC_READY')
    }
  }

  function handleReset() {
    setStep('IDLE'); setPdfFile(null); setTopic(null); setLog([]); setError('')
  }

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">{error}</div>
      )}

      {/* Step 1 — Load material */}
      {['IDLE', 'UPLOADING'].includes(step) && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Load Study Material</h2>
            <p className="text-sm text-gray-500 mt-1">
              Upload a PDF (textbook chapter, lecture notes, article) and the AI will
              generate study questions tailored to that material.
            </p>
          </div>

          <div
            className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors"
            onClick={() => fileRef.current?.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f?.type === 'application/pdf') setPdfFile(f) }}
          >
            <input ref={fileRef} type="file" accept=".pdf" className="hidden"
              onChange={e => setPdfFile(e.target.files[0] || null)} />
            {pdfFile ? (
              <div className="space-y-1">
                <p className="text-blue-600 font-medium">{pdfFile.name}</p>
                <p className="text-xs text-gray-400">{(pdfFile.size / 1024).toFixed(0)} KB · click to change</p>
              </div>
            ) : (
              <div className="space-y-1">
                <p className="text-gray-500">Drop a PDF here or click to browse</p>
                <p className="text-xs text-gray-400">Textbooks, lecture notes, articles…</p>
              </div>
            )}
          </div>

          <div className="flex gap-3">
            <button onClick={handleUploadPdf} disabled={!pdfFile || step === 'UPLOADING'}
              className="flex-1 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
              {step === 'UPLOADING' ? 'Reading PDF…' : 'Upload & Analyse PDF'}
            </button>
            <button onClick={handleUseExisting}
              className="px-4 py-2.5 border border-gray-300 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-50 transition-colors whitespace-nowrap">
              Use Existing Material
            </button>
          </div>
        </div>
      )}

      {/* Step 2 — Topic preview + generate */}
      {step === 'TOPIC_READY' && topic && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <div>
            <h2 className="text-base font-semibold text-gray-900">
              {topic.assignment_metadata?.title || 'Study Material'}
            </h2>
            <p className="text-sm text-gray-500 mt-0.5">
              {topic.questions?.length} topics identified
              {topic.assignment_metadata?.course ? ` · ${topic.assignment_metadata.course}` : ''}
            </p>
          </div>
          <div className="space-y-2">
            {(topic.questions || []).map(q => <QuestionCard key={q.id} q={q} />)}
          </div>
          <button onClick={handleGenerate}
            className="w-full py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors">
            Generate My Study Questions →
          </button>
        </div>
      )}

      {/* Generating */}
      {step === 'GENERATING' && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h2 className="text-base font-semibold text-gray-900">Generating study questions…</h2>
          <ProgressLog log={log} running={running} />
        </div>
      )}

      {/* Done */}
      {step === 'DONE' && questions.length > 0 && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-900">Your study questions are ready</h2>
              <button onClick={handleReset} className="text-xs text-gray-400 hover:text-gray-600 underline">
                Start over
              </button>
            </div>
            <div className="space-y-2">
              {questions.map(q => <QuestionCard key={q.id} q={q} />)}
            </div>
            <button onClick={onStartStudying}
              className="w-full py-2.5 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 transition-colors">
              Start Studying →
            </button>
          </div>
          {log.length > 0 && <ProgressLog log={log} running={false} />}
        </div>
      )}
    </div>
  )
}
