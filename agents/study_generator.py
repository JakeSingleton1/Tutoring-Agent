"""
Study Generator
───────────────
Generates a mix of multiple-choice and free-response study questions directly
from extracted text content in one LLM call.
"""

import json
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import VARIATION_MODEL

client = anthropic.Anthropic()

_SYSTEM = (
    "You are an expert educational content designer. "
    "Output a valid JSON array only. Never include markdown code fences."
)


def generate_questions(content_text: str, title: str, num_questions: int = 10) -> list:
    """
    Generate a mix of multiple-choice and free-response questions from content text.
    Returns a list of question dicts.
    """
    mc_count = num_questions // 2
    fr_count = num_questions - mc_count

    prompt = f"""Generate {num_questions} study questions from the material below.
Make exactly {mc_count} multiple-choice questions and {fr_count} free-response questions.

## Material Title
{title}

## Material Content
{content_text}

## Requirements
- Cover {num_questions} distinct concepts — no overlap
- Multiple-choice: 4 plausible options, only one correct. Wrong options should be common misconceptions, not obviously wrong.
- Free-response: require a SHORT answer (1-2 sentences or a number/term). Do NOT expect the student to write an essay.
- answer_key for multiple-choice: the exact text of the correct option
- answer_key for free-response: the concise correct answer only (1 sentence max, or just the value/term)
- explanation: the full reasoning, shown AFTER grading — keep this separate from answer_key
- Range from recall → understanding → application across the set

## Output — strict JSON array, no markdown fences
[
  {{
    "id": "Q1",
    "type": "multiple_choice",
    "topic": "Short topic label (3-5 words)",
    "question_text": "The full question text.",
    "choices": ["Option A", "Option B", "Option C", "Option D"],
    "answer_key": "Option A",
    "explanation": "Option A is correct because... The others are wrong because...",
    "source_reference": {{"page": 3, "section": "Brief section/heading name where concept appears"}},
    "hints": {{
      "conceptual": "What concept is relevant here?",
      "structural": "Which rule or definition applies?",
      "specific": "Narrow it down: think about X."
    }}
  }},
  {{
    "id": "Q2",
    "type": "free_response",
    "topic": "Short topic label (3-5 words)",
    "question_text": "The full question text.",
    "choices": null,
    "answer_key": "Concise correct answer (1 sentence or less).",
    "explanation": "Full explanation of why this is the correct answer.",
    "source_reference": {{"page": 7, "section": "Brief section/heading name where concept appears"}},
    "hints": {{
      "conceptual": "What concept is relevant here?",
      "structural": "Which formula or method applies?",
      "specific": "Concrete nudge with partial steps or values."
    }}
  }}
]

IMPORTANT: source_reference.page must be the actual [Page N] number from the material where the concept for that question appears. Use the [Page N] markers in the content to identify the right page."""

    print(f"  [Study Generator] Generating {num_questions} questions ({mc_count} MC, {fr_count} FR)…")
    response = client.messages.create(
        model=VARIATION_MODEL,
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        raise ValueError("No text in study generator response")

    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        questions = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from study generator: {e}\n{text[:300]}")

    for i, q in enumerate(questions, start=1):
        q["id"] = f"Q{i}"
        if "type" not in q:
            q["type"] = "free_response"
        if "choices" not in q:
            q["choices"] = None

    print(f"  ✓ Generated {len(questions)} questions")
    return questions
