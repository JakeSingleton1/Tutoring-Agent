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
    """
    grading_rubric = []
    for q in variant["questions"]:
        grading_rubric.append({
            "id": q["id"],
            "scenario_theme": q["scenario_theme"],
            "question_text": q["prompt_text"],
            "correct_answer": q["pre_computed_answer"]["final_result"],
            "formula_steps": q["pre_computed_answer"].get("steps", ""),
            "student_answer": student_submission.get(q["id"], "<no answer submitted>"),
        })

    return f"""You are the Evaluator Agent for student {variant['student_id']}.

Grade the student's submission against the unique answer key below.
Be fair, specific, and constructive. Each question is worth {POINTS_PER_QUESTION} points.

## Grading Data
{json.dumps(grading_rubric, indent=2)}

## Scoring Rubric (per question, {POINTS_PER_QUESTION} pts each)
- {POINTS_PER_QUESTION}/20: Correct final answer AND correct method/units shown.
- 14/20: Correct method, minor arithmetic error in final result.
- 10/20: Correct formula identified but significant arithmetic errors.
-  5/20: Partially correct approach, major errors or missing steps.
-  0/20: Incorrect or blank.

## Output (strict JSON, no markdown fences)
{{
  "student_id": "{variant['student_id']}",
  "overall_score": <sum of question scores>,
  "max_score": {len(variant['questions']) * POINTS_PER_QUESTION},
  "question_scores": [
    {{
      "id": "Q1",
      "points_earned": <0-{POINTS_PER_QUESTION}>,
      "points_possible": {POINTS_PER_QUESTION},
      "correct": true or false,
      "student_answer": "<echo student answer>",
      "correct_answer": "<echo correct answer>",
      "feedback": "<specific, constructive feedback — show the correct solution if wrong>"
    }},
    ... (Q2 through Q5)
  ],
  "summary_feedback": "<2-3 sentence overall assessment>"
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

    print(f"  [Evaluator] Grading submission for {variant['student_id']}...")

    response = client.messages.create(
        model=EVALUATOR_MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=(
            "You are a fair and precise academic evaluator. "
            "Output valid JSON only. Never use markdown fences."
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    text = next(b.text for b in response.content if b.type == "text")
    text = text.strip().strip("```json").strip("```").strip()
    result = json.loads(text)

    print(
        f"  ✓ Score: {result['overall_score']}/{result['max_score']} "
        f"({result['overall_score']}%)"
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
