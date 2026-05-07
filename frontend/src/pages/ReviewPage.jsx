import { useState, useEffect } from 'react'

export default function ReviewPage({ session, onSessionUpdate }) {
  const [answers,  setAnswers]  = useState({})
  const [grading,  setGrading]  = useState(false)
  const [error,    setError]    = useState('')

  useEffect(() => {
    if (!session) return
    setAnswers(
      session.answers && Object.keys(session.answers).length > 0
        ? session.answers
        : Object.fromEntries(session.questions.map(q => [q.id, '']))
    )
  }, [session?.id])

  const result = session?.result ?? null

  if (!session) {
    return (
      <div className="max-w-lg mx-auto mt-20 text-center text-gray-400 text-sm space-y-2">
        <p>No active session.</p>
        <p>Go to <strong>My Sessions</strong> to open or create one.</p>
      </div>
    )
  }

  async function handleSubmit() {
    setGrading(true)
    setError('')
    try {
      const res = await fetch(`/api/grade/${session.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers }),
      })
      if (!res.ok) {
        const msg = await res.text().catch(() => `Server error: ${res.status}`)
        throw new Error(msg)
      }
      const gradeResult = await res.json()
      onSessionUpdate({ ...session, answers, result: gradeResult })
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
    scorePercent >= 60 ? 'text-yellow-600' : 'text-red-600'

  // Build a lookup from question id → question for rendering results
  const qMap = Object.fromEntries(session.questions.map(q => [q.id, q]))

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      {!result ? (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-7">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Submit Your Answers</h2>
            <p className="text-sm text-gray-500 mt-1">
              Answer all questions then submit. The AI will grade each one and explain what you missed.
            </p>
          </div>

          {session.questions.map(q => (
            <div key={q.id} className="space-y-3">
              <div className="border-l-2 border-blue-200 pl-4">
                <p className="text-xs font-semibold text-blue-600 mb-1">
                  [{q.id}] {q.topic}
                  <span className="ml-2 text-gray-400 font-normal">
                    {q.type === 'multiple_choice' ? '· multiple choice' : '· free response'}
                  </span>
                </p>
                <p className="text-sm text-gray-700">{q.question_text}</p>
              </div>

              {q.type === 'multiple_choice' && q.choices ? (
                <div className="space-y-2 pl-1">
                  {q.choices.map((choice, i) => (
                    <label key={i}
                      className={`flex items-center gap-3 px-4 py-2.5 rounded-lg border cursor-pointer transition-colors ${
                        answers[q.id] === choice
                          ? 'border-blue-500 bg-blue-50 text-blue-900'
                          : 'border-gray-200 hover:border-gray-300 text-gray-700'
                      }`}>
                      <input
                        type="radio"
                        name={q.id}
                        value={choice}
                        checked={answers[q.id] === choice}
                        onChange={() => setAnswers(prev => ({ ...prev, [q.id]: choice }))}
                        className="accent-blue-600"
                      />
                      <span className="text-sm">{choice}</span>
                    </label>
                  ))}
                </div>
              ) : (
                <textarea rows={2} value={answers[q.id] ?? ''}
                  onChange={e => setAnswers(prev => ({ ...prev, [q.id]: e.target.value }))}
                  placeholder="Your answer…"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              )}
            </div>
          ))}

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button onClick={handleSubmit} disabled={grading}
            className="w-full py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
            {grading ? 'Grading…' : 'Submit for Grading'}
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Score banner */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-500 mb-1">Your Score</p>
              <p className={`text-4xl font-bold ${scoreColor}`}>
                {result.overall_score}
                <span className="text-xl font-normal text-gray-400">/{result.max_score}</span>
              </p>
              <p className={`text-sm font-medium mt-1 ${scoreColor}`}>{scorePercent}%</p>
            </div>
            <button onClick={() => onSessionUpdate({ ...session, result: null })}
              className="text-xs text-gray-400 hover:text-gray-600 underline">
              Edit answers
            </button>
          </div>

          {/* Per-question results */}
          {result.question_scores.map(qs => {
            const q = qMap[qs.id]
            return (
              <div key={qs.id}
                className={`bg-white rounded-xl border p-5 space-y-3 ${qs.correct ? 'border-green-200' : 'border-red-200'}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`text-lg ${qs.correct ? 'text-green-500' : 'text-red-500'}`}>
                      {qs.correct ? '✓' : '✗'}
                    </span>
                    <span className="font-semibold text-gray-900">{qs.id}</span>
                    {q?.type === 'multiple_choice' && (
                      <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">MC</span>
                    )}
                  </div>
                  <span className={`text-sm font-semibold ${
                    qs.points_earned === qs.points_possible ? 'text-green-600' :
                    qs.points_earned >= qs.points_possible * 0.7 ? 'text-yellow-600' : 'text-red-600'
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

                {/* Explanation from question data (richer than answer_key) */}
                {q?.explanation && !qs.correct && (
                  <div className="text-xs text-gray-600 bg-amber-50 border border-amber-100 rounded p-3">
                    <span className="font-medium text-amber-700">Explanation: </span>
                    {q.explanation}
                  </div>
                )}

                <div className="text-xs text-gray-600 bg-blue-50 rounded p-3">
                  <span className="font-medium text-blue-700">Feedback: </span>
                  {qs.feedback}
                </div>
              </div>
            )
          })}

          {/* Summary */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <p className="text-xs font-semibold text-gray-500 mb-2">Summary & Study Recommendations</p>
            <p className="text-sm text-gray-700">{result.summary_feedback}</p>
          </div>
        </div>
      )}
    </div>
  )
}
