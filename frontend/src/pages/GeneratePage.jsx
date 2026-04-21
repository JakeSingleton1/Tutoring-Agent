import { useState, useRef } from 'react'

// ── SSE progress event → human-readable label ──────────────────────────────
const EVENT_LABELS = {
  student_start: (e) => `── ${e.student_id} (${e.index}/${e.total}) ──`,
  generating:    (e) => `  [Variation Agent] Generating ${e.student_id}...`,
  validating:    (e) => `  [Validator] Attempt ${e.attempt}/${e.max}...`,
  valid:         (e) => `  ✓ Valid`,
  invalid:       (e) => `  ✗ Issues in [${e.issues?.join(', ')}] — auto-correcting...`,
  saved:         (e) => `  ✓ Saved`,
  done:          (e) => `✓ All ${e.total} variants complete`,
  error:         (e) => `✗ Error: ${e.message}`,
}

// ── Wizard steps ───────────────────────────────────────────────────────────
// IDLE → UPLOADING → PDF_READY → GENERATING_FIRST → AWAITING_APPROVAL → GENERATING_REST → DONE

function StepBadge({ n, label, active, done }) {
  return (
    <div className={`flex items-center gap-2 text-sm ${active ? 'text-blue-600 font-semibold' : done ? 'text-green-600' : 'text-gray-400'}`}>
      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border-2
        ${active ? 'border-blue-600 bg-blue-50 text-blue-600' : done ? 'border-green-500 bg-green-50 text-green-600' : 'border-gray-300 text-gray-400'}`}>
        {done ? '✓' : n}
      </div>
      {label}
    </div>
  )
}

function ProgressLog({ log, running }) {
  return (
    <div className="bg-gray-900 rounded-xl p-4 font-mono text-xs leading-relaxed overflow-auto max-h-64">
      {log.map((entry, i) => (
        <div key={i} className={
          entry.type === 'valid' || entry.type === 'saved' || entry.type === 'done'
            ? 'text-green-400'
            : entry.type === 'invalid' || entry.type === 'error'
            ? 'text-red-400'
            : entry.type === 'student_start'
            ? 'text-blue-300 mt-2 font-semibold'
            : 'text-gray-300'
        }>
          {entry.text}
        </div>
      ))}
      {running && <div className="text-yellow-400 animate-pulse mt-1">…</div>}
    </div>
  )
}

function QuestionPreview({ questions, showAnswers }) {
  const [open, setOpen] = useState(null)
  return (
    <div className="space-y-2">
      {questions.map(q => (
        <div key={q.id} className="border border-gray-200 rounded-lg overflow-hidden">
          <button
            className="w-full text-left px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
            onClick={() => setOpen(open === q.id ? null : q.id)}
          >
            <span className="text-sm font-medium text-gray-800">
              <span className="text-blue-600 mr-2">[{q.id}]</span>
              {q.scenario_theme || q.learning_objective?.slice(0, 60) || 'Question'}
            </span>
            <span className="text-gray-400 text-xs">{open === q.id ? '▲' : '▼'}</span>
          </button>
          {open === q.id && (
            <div className="px-4 pb-4 space-y-3 border-t border-gray-100 bg-gray-50">
              <p className="text-sm text-gray-700 pt-3">{q.prompt_text || q.prompt}</p>
              {showAnswers && q.pre_computed_answer && (
                <div className="bg-white border border-green-200 rounded-lg p-3">
                  <p className="text-xs font-semibold text-green-700 mb-1">Answer Key</p>
                  <p className="text-xs text-gray-600 font-mono">{q.pre_computed_answer.steps}</p>
                  <p className="text-sm font-semibold text-green-800 mt-1">
                    → {q.pre_computed_answer.final_result}
                  </p>
                </div>
              )}
              {showAnswers && q.master_key && (
                <div className="bg-white border border-blue-200 rounded-lg p-3">
                  <p className="text-xs font-semibold text-blue-700 mb-1">Formula Key</p>
                  <p className="text-xs text-gray-600 font-mono">
                    {typeof q.master_key.formula === 'string'
                      ? q.master_key.formula
                      : JSON.stringify(q.master_key.formula, null, 2)}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default function GeneratePage() {
  const [step, setStep]               = useState('IDLE')  // wizard state
  const [numStudents, setNumStudents] = useState(10)
  const [pdfFile, setPdfFile]         = useState(null)
  const [master, setMaster]           = useState(null)    // active master assignment
  const [firstVariant, setFirstVariant] = useState(null)  // STU001 for approval
  const [log, setLog]                 = useState([])
  const [running, setRunning]         = useState(false)
  const [students, setStudents]       = useState([])
  const [error, setError]             = useState('')
  const fileRef = useRef(null)

  function addLog(event) {
    const label = EVENT_LABELS[event.type]?.(event) ?? JSON.stringify(event)
    setLog(prev => [...prev, { type: event.type, text: label }])
  }

  // ── Step 1: Upload PDF ───────────────────────────────────────────────────

  async function handleUploadPdf() {
    if (!pdfFile) return
    setStep('UPLOADING')
    setError('')
    setMaster(null)

    const form = new FormData()
    form.append('file', pdfFile)

    try {
      const res = await fetch('/api/pdf/upload', { method: 'POST', body: form })
      if (!res.ok) {
        const detail = (await res.json()).detail || 'Upload failed'
        throw new Error(detail)
      }
      const m = await res.json()
      setMaster(m)
      setStep('PDF_READY')
    } catch (e) {
      setError(e.message)
      setStep('IDLE')
    }
  }

  async function handleUseExistingMaster() {
    setError('')
    try {
      const res = await fetch('/api/master')
      setMaster(await res.json())
      setStep('PDF_READY')
    } catch (e) {
      setError('Could not load existing master assignment.')
    }
  }

  // ── Step 2: Generate STU001 ──────────────────────────────────────────────

  function handleGenerateFirst() {
    setLog([])
    setFirstVariant(null)
    setStep('GENERATING_FIRST')
    setRunning(true)

    const es = new EventSource('/api/generate/first/stream')
    es.onmessage = (e) => {
      if (e.data === '[DONE]') {
        es.close()
        setRunning(false)
        return
      }
      try {
        const event = JSON.parse(e.data)
        if (event.type === 'first_done') {
          setFirstVariant(event.variant)
          setStep('AWAITING_APPROVAL')
        } else if (event.type === 'error') {
          setError(event.message)
          setStep('PDF_READY')
        } else {
          addLog(event)
        }
      } catch { /* skip */ }
    }
    es.onerror = () => {
      es.close()
      setRunning(false)
      setError('Connection error — is the backend running?')
      setStep('PDF_READY')
    }
  }

  // ── Step 3: Approve → generate remaining ────────────────────────────────

  function handleApprove() {
    setLog([])
    setStep('GENERATING_REST')
    setRunning(true)

    const es = new EventSource(`/api/generate/remaining/stream?n=${numStudents}`)
    es.onmessage = (e) => {
      if (e.data === '[DONE]') {
        es.close()
        setRunning(false)
        setStep('DONE')
        fetch('/api/students').then(r => r.json()).then(setStudents)
        return
      }
      try {
        const event = JSON.parse(e.data)
        if (event.type === 'error') {
          setError(event.message)
          setStep('AWAITING_APPROVAL')
        } else {
          addLog(event)
        }
      } catch { /* skip */ }
    }
    es.onerror = () => {
      es.close()
      setRunning(false)
      setError('Connection error — is the backend running?')
      setStep('AWAITING_APPROVAL')
    }
  }

  function handleRejectFirst() {
    setFirstVariant(null)
    setLog([])
    setStep('PDF_READY')
  }

  // ── Wizard step indicators ───────────────────────────────────────────────

  const stepDefs = [
    { n: 1, label: 'Load Topic',             done: !['IDLE'].includes(step) && step !== 'UPLOADING' },
    { n: 2, label: 'Generate First Variant', done: ['AWAITING_APPROVAL','GENERATING_REST','DONE'].includes(step) },
    { n: 3, label: 'Human Approval',         done: ['GENERATING_REST','DONE'].includes(step) },
    { n: 4, label: 'Generate All',           done: step === 'DONE' },
  ]
  const activeStep =
    ['IDLE','UPLOADING'].includes(step) ? 1 :
    step === 'PDF_READY' ? 2 :
    step === 'GENERATING_FIRST' ? 2 :
    step === 'AWAITING_APPROVAL' ? 3 :
    step === 'GENERATING_REST' ? 4 : 4

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      {/* Step indicators */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 flex gap-6">
        {stepDefs.map(s => (
          <StepBadge key={s.n} {...s} active={activeStep === s.n} />
        ))}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* ── Step 1: Topic source ── */}
      {['IDLE', 'UPLOADING'].includes(step) && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
          <div>
            <h2 className="text-base font-semibold text-gray-900 mb-1">Load Topic Material</h2>
            <p className="text-sm text-gray-500">
              Upload a PDF — the PDF Agent will read it and generate the master assignment.
              Or use the existing master assignment.
            </p>
          </div>

          {/* PDF Upload */}
          <div
            className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors"
            onClick={() => fileRef.current?.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f?.type === 'application/pdf') setPdfFile(f) }}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={e => setPdfFile(e.target.files[0] || null)}
            />
            {pdfFile ? (
              <div className="space-y-1">
                <p className="text-blue-600 font-medium">{pdfFile.name}</p>
                <p className="text-xs text-gray-500">{(pdfFile.size / 1024).toFixed(0)} KB — click to change</p>
              </div>
            ) : (
              <div className="space-y-1">
                <p className="text-gray-500">Drop a PDF here or click to browse</p>
                <p className="text-xs text-gray-400">Textbooks, game manuals, course notes…</p>
              </div>
            )}
          </div>

          <div className="flex gap-3">
            <button
              onClick={handleUploadPdf}
              disabled={!pdfFile || step === 'UPLOADING'}
              className="flex-1 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {step === 'UPLOADING' ? 'Analysing PDF…' : 'Upload & Analyse PDF'}
            </button>
            <button
              onClick={handleUseExistingMaster}
              className="px-4 py-2.5 border border-gray-300 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-50 transition-colors"
            >
              Use Existing Master
            </button>
          </div>
        </div>
      )}

      {/* ── Step 2: Master preview + generate first ── */}
      {step === 'PDF_READY' && master && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-base font-semibold text-gray-900">
                  {master.assignment_metadata?.title || 'Generated Assignment'}
                </h2>
                <p className="text-sm text-gray-500 mt-0.5">
                  {master.questions?.length} questions · {master.assignment_metadata?.course}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <label className="text-xs text-gray-600">Students:</label>
                <input
                  type="number" min={2} max={30} value={numStudents}
                  onChange={e => setNumStudents(Number(e.target.value))}
                  className="w-16 px-2 py-1 border border-gray-300 rounded text-sm text-center focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <QuestionPreview questions={master.questions || []} showAnswers={true} />

            <button
              onClick={handleGenerateFirst}
              className="mt-5 w-full py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
            >
              Generate First Variant (STU001) for Review →
            </button>
          </div>
        </div>
      )}

      {/* ── Generating first: progress log ── */}
      {step === 'GENERATING_FIRST' && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h2 className="text-base font-semibold text-gray-900">Generating STU001…</h2>
          <ProgressLog log={log} running={running} />
        </div>
      )}

      {/* ── Step 3: Human approval gate ── */}
      {step === 'AWAITING_APPROVAL' && firstVariant && (
        <div className="space-y-4">
          <div className="bg-amber-50 border border-amber-300 rounded-xl p-4">
            <p className="text-sm font-semibold text-amber-800">Human Review Required</p>
            <p className="text-sm text-amber-700 mt-1">
              Review the question wording and answer key below before generating the
              remaining {numStudents - 1} variants. Only you can approve — not the AI.
            </p>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
            <h2 className="text-base font-semibold text-gray-900">
              STU001 — First Variant Preview
            </h2>
            <QuestionPreview questions={firstVariant.questions || []} showAnswers={true} />
          </div>

          <div className="flex gap-3">
            <button
              onClick={handleApprove}
              className="flex-1 py-2.5 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 transition-colors"
            >
              ✓ Approve — Generate Remaining {numStudents - 1} Variants
            </button>
            <button
              onClick={handleRejectFirst}
              className="px-5 py-2.5 border border-gray-300 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-50 transition-colors"
            >
              ✗ Regenerate
            </button>
          </div>
        </div>
      )}

      {/* ── Generating remaining: progress log ── */}
      {step === 'GENERATING_REST' && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h2 className="text-base font-semibold text-gray-900">
            Generating STU002 – STU{String(numStudents).padStart(3, '0')}…
          </h2>
          <ProgressLog log={log} running={running} />
        </div>
      )}

      {/* ── Done ── */}
      {step === 'DONE' && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-base font-semibold text-green-700 mb-3">
              ✓ {students.length} variants ready
            </h2>
            <div className="flex flex-wrap gap-2">
              {students.map(s => (
                <span key={s} className="px-3 py-1 bg-blue-50 text-blue-700 rounded-full text-xs font-medium">
                  {s}
                </span>
              ))}
            </div>
            <button
              onClick={() => { setStep('IDLE'); setPdfFile(null); setMaster(null); setLog([]); setStudents([]) }}
              className="mt-5 text-xs text-gray-400 hover:text-gray-600 underline"
            >
              Start over with a new topic
            </button>
          </div>
          <ProgressLog log={log} running={false} />
        </div>
      )}
    </div>
  )
}
