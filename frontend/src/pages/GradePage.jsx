import { useState, useEffect } from 'react'

export default function GradePage() {
  const [students, setStudents]   = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [variant, setVariant]     = useState(null)
  const [answers, setAnswers]     = useState({})
  const [grading, setGrading]     = useState(false)
  const [result, setResult]       = useState(null)
  const [error, setError]         = useState('')

  useEffect(() => {
    fetch('/api/students')
      .then(r => r.json())
      .then(setStudents)
  }, [])

  useEffect(() => {
    if (!selectedId) return
    setVariant(null)
    setAnswers({})
    setResult(null)
    setError('')
    fetch(`/api/students/${selectedId}`)
      .then(r => r.json())
      .then(v => {
        setVariant(v)
        // init empty answers
        const init = {}
        v.questions.forEach(q => { init[q.id] = '' })
        setAnswers(init)
      })
  }, [selectedId])

  async function handleSubmit() {
    setGrading(true)
    setResult(null)
    setError('')
    try {
      const res = await fetch(`/api/grade/${selectedId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers }),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      setResult(await res.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setGrading(false)
    }
  }

  const scorePercent = result
    ? Math.round((result.overall_score / result.max_score) * 100)
    : 0

  const scoreColor =
    scorePercent >= 80 ? 'text-green-600' :
    scorePercent >= 60 ? 'text-yellow-600' :
    'text-red-600'

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      {/* Student selector */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-4">
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
      </div>

      {/* Answer form */}
      {variant && !result && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-6">
          <h2 className="text-base font-semibold text-gray-900">
            Submit Answers — {variant.student_id}
          </h2>

          {variant.questions.map(q => (
            <div key={q.id} className="space-y-2">
              <div className="border-l-2 border-blue-200 pl-4">
                <p className="text-xs font-semibold text-blue-600 mb-1">
                  [{q.id}] {q.scenario_theme}
                </p>
                <p className="text-sm text-gray-700">{q.prompt_text}</p>
              </div>
              <textarea
                rows={3}
                value={answers[q.id] ?? ''}
                onChange={e => setAnswers(prev => ({ ...prev, [q.id]: e.target.value }))}
                placeholder={`Your answer for ${q.id}…`}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          ))}

          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}

          <button
            onClick={handleSubmit}
            disabled={grading}
            className="w-full py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {grading ? 'Grading…' : 'Submit for Grading'}
          </button>
        </div>
      )}

      {/* Grade report */}
      {result && (
        <div className="space-y-4">
          {/* Overall score banner */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-500 mb-1">Overall Score</p>
              <p className={`text-4xl font-bold ${scoreColor}`}>
                {result.overall_score}
                <span className="text-xl font-normal text-gray-400">/{result.max_score}</span>
              </p>
              <p className={`text-sm font-medium mt-1 ${scoreColor}`}>{scorePercent}%</p>
            </div>
            <button
              onClick={() => { setResult(null) }}
              className="text-xs text-gray-400 hover:text-gray-600 underline"
            >
              Edit answers
            </button>
          </div>

          {/* Per-question results */}
          {result.question_scores.map(qs => (
            <div
              key={qs.id}
              className={`bg-white rounded-xl border p-5 space-y-3 ${
                qs.correct ? 'border-green-200' : 'border-red-200'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`text-lg ${qs.correct ? 'text-green-500' : 'text-red-500'}`}>
                    {qs.correct ? '✓' : '✗'}
                  </span>
                  <span className="font-semibold text-gray-900">{qs.id}</span>
                </div>
                <span className={`text-sm font-semibold ${
                  qs.points_earned === qs.points_possible ? 'text-green-600' :
                  qs.points_earned >= qs.points_possible * 0.7 ? 'text-yellow-600' :
                  'text-red-600'
                }`}>
                  {qs.points_earned}/{qs.points_possible} pts
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <p className="font-medium text-gray-500 mb-1">Your answer</p>
                  <p className="text-gray-700 bg-gray-50 rounded p-2">{qs.student_answer}</p>
                </div>
                <div>
                  <p className="font-medium text-gray-500 mb-1">Correct answer</p>
                  <p className="text-gray-700 bg-green-50 rounded p-2">{qs.correct_answer}</p>
                </div>
              </div>

              <div className="text-xs text-gray-600 bg-blue-50 rounded p-3">
                <span className="font-medium text-blue-700">Feedback: </span>
                {qs.feedback}
              </div>
            </div>
          ))}

          {/* Summary */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <p className="text-xs font-semibold text-gray-500 mb-2">Summary</p>
            <p className="text-sm text-gray-700">{result.summary_feedback}</p>
          </div>
        </div>
      )}

      {!selectedId && (
        <div className="text-center text-sm text-gray-400 mt-12">
          Select a student to submit and grade their answers.
        </div>
      )}
    </div>
  )
}
