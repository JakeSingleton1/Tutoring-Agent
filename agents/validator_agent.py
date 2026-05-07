"""
Validator Agent  (the "IF TRUE" gate)
──────────────────────────────────────
Receives a generated variant and verifies:
  1. All placeholder brackets are resolved (no [BRACKET] tokens remain).
  2. The pre_computed_answer is mathematically correct given the injected values
     and the master_key formula.
  3. The question is logically solvable.

Returns:
  { "valid": True/False, "issues": [...], "corrected_question": <dict or None> }

Uses claude-haiku-4-5 (simple math + structural checks — no deep reasoning needed).
"""

import json
import re
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import VALIDATOR_MODEL, MASTER_ASSIGNMENT_PATH, VARIANTS_DIR

client = anthropic.Anthropic()

_ACTIVE_MASTER_PATH = VARIANTS_DIR.parent / "active_master.json"


def _has_unresolved_brackets(text: str) -> bool:
    return bool(re.search(r"\[[A-Z_]+\]", text))


def _load_master_keys() -> dict:
    # Prefer PDF-generated master if present (mirrors Pipeline logic)
    path = _ACTIVE_MASTER_PATH if _ACTIVE_MASTER_PATH.exists() else MASTER_ASSIGNMENT_PATH
    with open(path) as f:
        data = json.load(f)
    return {q["id"]: q.get("master_key", {}) for q in data["questions"]}


def _build_validation_prompt(question: dict, master_key: dict) -> str:
    return f"""You are the Validator Agent in an educational pipeline.

Check whether this student assignment question is correct and solvable.

## Question to Validate
{json.dumps(question, indent=2)}

## Master Key Formula (ground truth)
{json.dumps(master_key, indent=2)}

## Your Tasks
1. Verify NO unresolved [BRACKET] placeholders remain in "prompt_text".
2. Using the "injected_values" and the master_key formula, recompute the answer independently.
3. Compare your recomputed answer to "pre_computed_answer.final_result".
4. Check that the scenario is coherent and the question is clearly worded.

## Output (strict JSON, no markdown fences)
{{
  "valid": true or false,
  "issues": ["list any problems found, empty if none"],
  "recomputed_answer": "<your independent calculation result>",
  "answer_matches": true or false,
  "corrected_pre_computed_answer": {{
    "steps": "<corrected steps if answer was wrong, else null>",
    "final_result": "<corrected final result if answer was wrong, else null>"
  }}
}}"""


def validate_question(question: dict, master_key: dict) -> dict:
    """Run the IF TRUE gate on a single question. Returns validation result."""

    # Fast structural check first (no LLM needed)
    prompt_text = question.get("prompt_text", "")
    if _has_unresolved_brackets(prompt_text):
        return {
            "valid": False,
            "issues": [f"Unresolved placeholders found: {re.findall(r'\\[[A-Z_]+\\]', prompt_text)}"],
            "recomputed_answer": None,
            "answer_matches": False,
            "corrected_pre_computed_answer": {"steps": None, "final_result": None},
        }

    prompt = _build_validation_prompt(question, master_key)

    response = client.messages.create(
        model=VALIDATOR_MODEL,
        max_tokens=1024,
        system=(
            "You are a precise mathematical validator. "
            "Output valid JSON only. Never use markdown fences."
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        raise ValueError(f"No text block in validator response for question {question.get('id')}")

    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from validator for question {question.get('id')}: {e}\n{text[:200]}")


def validate_variant(variant: dict) -> dict:
    """
    Validate all 5 questions in a variant.

    Returns:
      {
        "student_id": ...,
        "all_valid": True/False,
        "question_results": { "Q1": {...}, ... },
        "corrected_variant": <variant with any answers fixed>
      }
    """
    master_keys = _load_master_keys()
    results = {}
    corrected_questions = []
    all_valid = True

    for q in variant["questions"]:
        qid = q["id"]
        mk = master_keys.get(qid, {})
        result = validate_question(q, mk)
        results[qid] = result

        corrected_q = dict(q)
        if not result["valid"] or not result["answer_matches"]:
            all_valid = False
            # Patch the pre_computed_answer with the validator's recomputed version
            if result["corrected_pre_computed_answer"]["final_result"]:
                corrected_q["pre_computed_answer"] = result["corrected_pre_computed_answer"]
                corrected_q["pre_computed_answer"]["auto_corrected"] = True

        corrected_questions.append(corrected_q)

    corrected_variant = dict(variant)
    corrected_variant["questions"] = corrected_questions

    return {
        "student_id": variant["student_id"],
        "all_valid": all_valid,
        "question_results": results,
        "corrected_variant": corrected_variant,
    }


if __name__ == "__main__":
    # Quick smoke test with a dummy variant
    dummy = {
        "student_id": "STU001",
        "questions": [
            {
                "id": "Q1",
                "scenario_theme": "Hospital Triage",
                "prompt_text": (
                    "An AI agent operating in a Hospital Triage system processes "
                    "12 tasks per minute. How many tasks will it complete in 4 hours, "
                    "assuming zero downtime?"
                ),
                "injected_values": {"TASKS_PER_MINUTE": 12, "TIME_WINDOW_HOURS": 4},
                "pre_computed_answer": {
                    "steps": "12 * 60 * 4 = 2880",
                    "final_result": "2880 tasks",
                },
            }
        ],
    }

    result = validate_variant(dummy)
    print(json.dumps(result, indent=2))
