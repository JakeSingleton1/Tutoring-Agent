"""
Evaluator Agent
───────────────
Receives a student's submitted answers and the unique key for their variant.
Produces instant, objective, per-question feedback and an overall score.

Output:
  {
    "student_id": ...,
    "overall_score": 85,
    "max_score": 100,
    "question_scores": [
      {
        "id": "Q1",
        "points_earned": 18,
        "points_possible": 20,
        "correct": true/false,
        "feedback": "..."
      }, ...
    ],
    "summary_feedback": "..."
  }
"""

import json
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import EVALUATOR_MODEL

client = anthropic.Anthropic()

POINTS_PER_QUESTION = 20  # 5 questions × 20 pts = 100 pts total


def _build_evaluation_prompt(variant: dict, student_submission: dict) -> str:
    """
    student_submission format:
      { "Q1": "student answer text", "Q2": "...", ... }
    Supports both new session format and old variant format.
    """
    grading_rubric = []
    for q in variant["questions"]:
        if "answer_key" in q:
            grading_rubric.append({
                "id": q["id"],
                "type": q.get("type", "free_response"),
                "topic": q.get("topic", ""),
                "question_text": q["question_text"],
                "correct_answer": q["answer_key"],  # always concise
                "student_answer": student_submission.get(q["id"], "<no answer submitted>"),
            })
        else:
            grading_rubric.append({
                "id": q["id"],
                "type": "free_response",
                "topic": q.get("scenario_theme", ""),
                "question_text": q.get("prompt_text", ""),
                "correct_answer": q.get("pre_computed_answer", {}).get("final_result", ""),
                "student_answer": student_submission.get(q["id"], "<no answer submitted>"),
            })

    session_id = variant.get("id") or variant.get("student_id", "unknown")
    num_q = len(variant["questions"])

    return f"""You are grading a student's study session submission.

Grade each answer against the answer key. Be fair and concise with feedback.
Each question is worth {POINTS_PER_QUESTION} points.

## Grading Data
{json.dumps(grading_rubric, indent=2)}

## Scoring Rules
- multiple_choice: {POINTS_PER_QUESTION} pts if correct, 0 if wrong. No partial credit.
- free_response:
  - {POINTS_PER_QUESTION}/20: Correct — matches the answer key in substance.
  - 14/20: Mostly correct with a minor error or missing detail.
  - 10/20: Partially correct — right idea but significant gaps.
  -  5/20: Minimal relevance.
  -  0/20: Wrong or blank.
- Do NOT penalise for not showing work unless the question explicitly asks for it.
- Grade free-response on substance, not exact wording.

## Output (strict JSON, no markdown fences)
{{
  "session_id": "{session_id}",
  "overall_score": <sum of question scores>,
  "max_score": {num_q * POINTS_PER_QUESTION},
  "question_scores": [
    {{
      "id": "Q1",
      "points_earned": <0-{POINTS_PER_QUESTION}>,
      "points_possible": {POINTS_PER_QUESTION},
      "correct": true or false,
      "student_answer": "<echo student answer>",
      "correct_answer": "<echo correct answer>",
      "feedback": "<specific feedback — explain what was right/wrong and show the correct reasoning>"
    }}
  ],
  "summary_feedback": "<2-3 sentence overall assessment with study recommendations>"
}}"""


def evaluate_submission(variant: dict, student_submission: dict) -> dict:
    """
    Evaluate a student's submitted answers against their unique variant key.

    Args:
        variant: The validated student variant (from pipeline).
        student_submission: Dict mapping question IDs to student answer strings.
            e.g. { "Q1": "900 tasks", "Q2": "Tool A at $0.12/accurate result", ... }

    Returns:
        Parsed evaluation dict with scores and feedback.
    """
    prompt = _build_evaluation_prompt(variant, student_submission)

    session_label = variant.get("id") or variant.get("student_id", "unknown")
    print(f"  [Evaluator] Grading submission for {session_label}...")

    response = client.messages.create(
        model=EVALUATOR_MODEL,
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=(
            "You are a fair and precise academic evaluator. "
            "Output valid JSON only. Never use markdown fences."
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        raise ValueError(f"No text block in evaluator response for {session_label}")

    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from evaluator for {session_label}: {e}\n{text[:200]}")

    pct = result["overall_score"] / result["max_score"] * 100 if result["max_score"] else 0
    print(
        f"  ✓ Score: {result['overall_score']}/{result['max_score']} "
        f"({pct:.0f}%)"
    )
    return result


def print_report(evaluation: dict):
    """Pretty-print an evaluation result to the console."""
    print(f"\n{'='*60}")
    print(f"  Grade Report — Student {evaluation['student_id']}")
    print(f"  Score: {evaluation['overall_score']} / {evaluation['max_score']}")
    print(f"{'='*60}")

    for qs in evaluation["question_scores"]:
        status = "✓" if qs["correct"] else "✗"
        print(
            f"\n[{qs['id']}] {status}  {qs['points_earned']}/{qs['points_possible']} pts"
        )
        print(f"  Your answer : {qs['student_answer']}")
        print(f"  Correct     : {qs['correct_answer']}")
        print(f"  Feedback    : {qs['feedback']}")

    print(f"\n{'─'*60}")
    print(f"  Summary: {evaluation['summary_feedback']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    # Quick test
    dummy_variant = {
        "student_id": "STU001",
        "questions": [
            {
                "id": "Q1",
                "scenario_theme": "Hospital Triage",
                "prompt_text": "An AI agent processes 12 tasks/min. How many in 4 hours?",
                "pre_computed_answer": {
                    "steps": "12 * 60 * 4 = 2880",
                    "final_result": "2,880 tasks",
                },
            }
        ],
    }
    dummy_submission = {"Q1": "2880 tasks"}
    result = evaluate_submission(dummy_variant, dummy_submission)
    print_report(result)
