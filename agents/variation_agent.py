"""
Variation Agent
───────────────
Takes the Base Assignment (master_assignment.json) and produces N student-specific
variants. Each variant injects real numeric values into the placeholders and picks
a unique scenario theme — keeping the underlying logic materially identical.

Output per variant:
  {
    "student_id": "STU001",
    "questions": [
      {
        "id": "Q1",
        "scenario_theme": "Hospital Triage",
        "prompt_text": "<fully resolved question text>",
        "injected_values": { "TASKS_PER_MINUTE": 12, "TIME_WINDOW_HOURS": 4 },
        "pre_computed_answer": { ... }   ← filled in by the agent
      }, ...
    ]
  }
"""

import json
import random
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    VARIATION_MODEL,
    MASTER_ASSIGNMENT_PATH,
    SCENARIO_THEMES,
    NUM_VARIANTS,
)

client = anthropic.Anthropic()


# ── Value samplers per question ────────────────────────────────────────────────

def _sample_q1_values() -> dict:
    return {
        "TASKS_PER_MINUTE": random.randint(5, 50),
        "TIME_WINDOW_HOURS": random.randint(1, 12),
    }

def _sample_q2_values() -> dict:
    cost_a = round(random.uniform(0.01, 0.50), 2)
    cost_b = round(random.uniform(0.01, 0.50), 2)
    acc_a  = random.randint(60, 98)
    acc_b  = random.randint(60, 98)
    # ensure they're meaningfully different
    while abs(acc_a - acc_b) < 5:
        acc_b = random.randint(60, 98)
    return {
        "COST_A": cost_a,
        "ACCURACY_A": acc_a,
        "COST_B": cost_b,
        "ACCURACY_B": acc_b,
        "NUM_CALLS": random.randint(100, 10_000),
    }

def _sample_q3_values() -> dict:
    return {
        "NUM_AGENTS": random.randint(3, 10),
        "AGENT_LATENCY_SECONDS": round(random.uniform(1.0, 15.0), 1),
    }

def _sample_q4_values() -> dict:
    total = random.randint(500, 5000)
    threshold = round(random.uniform(0.6, 0.95), 2)
    retrieved = random.randint(int(total * 0.05), int(total * 0.40))
    return {
        "TOTAL_DOCUMENTS": total,
        "THRESHOLD": threshold,
        "RETRIEVED_DOCS": retrieved,
        "COST_PER_DOC": round(random.uniform(0.001, 0.05), 3),
    }

def _sample_q5_values() -> dict:
    return {
        "NUM_STEPS": random.randint(3, 8),
        "SUCCESS_RATE": random.randint(75, 99),
        "NUM_RUNS": random.randint(100, 1000),
    }

VALUE_SAMPLERS = {
    "Q1": _sample_q1_values,
    "Q2": _sample_q2_values,
    "Q3": _sample_q3_values,
    "Q4": _sample_q4_values,
    "Q5": _sample_q5_values,
}


# ── Prompt builder ─────────────────────────────────────────────────────────────

def _build_variation_prompt(base_questions: list, student_id: str, themes: list[str]) -> str:
    theme_pool = json.dumps(themes, indent=2)
    questions_json = json.dumps(base_questions, indent=2)
    return f"""You are the Variation Agent in an educational agentic pipeline.

Your job: produce one student-specific variant for student "{student_id}".

## Base Questions (with placeholder logic)
{questions_json}

## Available Scenario Themes
{theme_pool}

## Pre-Sampled Values (already injected for you)
These values have been sampled and must be used verbatim — do NOT change them:
{{PRE_SAMPLED_VALUES}}

## Instructions
For EACH of the 5 questions:
1. Pick a UNIQUE scenario theme from the pool (no repeats across questions).
2. Replace ALL [BRACKET] placeholders in the prompt with the pre-sampled values.
3. Write "prompt_text": the fully resolved question a student will see (no brackets).
4. Write "pre_computed_answer": compute the correct answer using the master_key formula.
   - Show intermediate steps.
   - Give the final numeric result(s).
5. Keep "injected_values" exactly as pre-sampled.

## Output format (strict JSON, no markdown fences)
{{
  "student_id": "{student_id}",
  "questions": [
    {{
      "id": "Q1",
      "scenario_theme": "<chosen theme>",
      "prompt_text": "<fully resolved question text>",
      "injected_values": {{ ... }},
      "pre_computed_answer": {{
        "steps": "<show your work>",
        "final_result": "<numeric answer(s) with units>"
      }}
    }},
    ... (Q2 through Q5)
  ]
}}"""


# ── Main generation function ───────────────────────────────────────────────────

def generate_variant(student_id: str, base_assignment: dict, theme_pool: list[str]) -> dict:
    """
    Ask the Variation Agent to produce one student-specific variant.
    Returns the parsed variant dict.
    """
    base_questions = base_assignment["questions"]

    # Sample values for each question deterministically before calling Claude
    sampled = {q["id"]: VALUE_SAMPLERS[q["id"]]() for q in base_questions}

    # Build a prompt that includes the pre-sampled values
    prompt = _build_variation_prompt(base_questions, student_id, theme_pool)

    # Inject the sampled values into the prompt
    sampled_block = json.dumps(sampled, indent=2)
    prompt = prompt.replace("{PRE_SAMPLED_VALUES}", sampled_block)

    print(f"  [Variation Agent] Generating variant for {student_id}...")

    response = client.messages.create(
        model=VARIATION_MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=(
            "You are an expert educational content generator. "
            "Always output valid JSON exactly as instructed. "
            "Never include markdown code fences."
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract the text block (thinking blocks are separate)
    text = next(b.text for b in response.content if b.type == "text")

    # Parse JSON — strip any accidental fences
    text = text.strip().strip("```json").strip("```").strip()
    variant = json.loads(text)

    # Attach the sampled values to each question for the validator
    for q in variant["questions"]:
        if q["id"] in sampled:
            q["injected_values"] = sampled[q["id"]]

    return variant


def run(num_variants: int = NUM_VARIANTS) -> list[dict]:
    """Generate `num_variants` student variants from the master assignment."""
    with open(MASTER_ASSIGNMENT_PATH) as f:
        base_assignment = json.load(f)

    variants = []
    themes = SCENARIO_THEMES.copy()

    for i in range(1, num_variants + 1):
        student_id = f"STU{i:03d}"
        # Give each student a shuffled theme pool so they get different themes
        random.shuffle(themes)
        variant = generate_variant(student_id, base_assignment, themes[:5])
        variants.append(variant)
        print(f"  ✓ Variant {i}/{num_variants} created for {student_id}")

    return variants


if __name__ == "__main__":
    result = run(num_variants=2)  # quick test
    print(json.dumps(result[0], indent=2))
