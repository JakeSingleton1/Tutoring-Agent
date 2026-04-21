"""
PDF Agent
─────────
Reads a PDF file and generates a master_assignment.json from its content.
Uses Claude's native PDF document support (base64) so no extra parsing library
is needed — Claude reads the PDF directly.

Output: a master assignment dict matching the pipeline schema:
  {
    "assignment_metadata": { ... },
    "questions": [
      {
        "id": "Q1",
        "learning_objective": "...",
        "scenario_theme": "[SCENARIO_THEME_1]",
        "prompt": "...[PLACEHOLDER]...",
        "variable_placeholders": { ... },
        "master_key": { "formula": "...", "units": "...", "notes": "..." }
      },
      ... (up to 5 questions)
    ],
    "variation_agent_instructions": { ... }
  }
"""

import base64
import json
from pathlib import Path

import anthropic

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import VARIATION_MODEL

client = anthropic.Anthropic()

# ── Schema reference shown to Claude ──────────────────────────────────────────

_SCHEMA_EXAMPLE = """
{
  "assignment_metadata": {
    "title": "Assignment title derived from PDF topic",
    "course": "Course name if identifiable, else 'Unknown Course'",
    "version": "1.0",
    "description": "What this assignment tests",
    "variation_instructions": "Replace all [BRACKET] tokens with student-specific values."
  },
  "questions": [
    {
      "id": "Q1",
      "learning_objective": "What the student learns by answering this question",
      "scenario_theme": "[SCENARIO_THEME_1]",
      "prompt": "In a [SCENARIO_THEME_1] context, given [VAR_A] and [VAR_B], compute X.",
      "variable_placeholders": {
        "SCENARIO_THEME_1": "e.g., 'Hospital Triage', 'Retail Inventory'",
        "VAR_A": "constraint description, e.g., 'integer > 0'",
        "VAR_B": "constraint description"
      },
      "master_key": {
        "formula": "result = VAR_A * VAR_B",
        "units": "appropriate unit",
        "notes": "Brief explanation of the formula."
      }
    }
  ],
  "variation_agent_instructions": {
    "description": "Instructions for downstream variant generation.",
    "steps": [
      "1. Sample a SCENARIO_THEME from examples or generate a domain-appropriate one.",
      "2. Sample numeric values within constraints in variable_placeholders.",
      "3. Substitute all [BRACKET] tokens in prompt.",
      "4. Use master_key formula to pre-compute the correct answer.",
      "5. Output one JSON object per student.",
      "6. Never modify master_key formulas — only inputs change."
    ]
  }
}
"""

_SYSTEM_PROMPT = (
    "You are an expert educational content designer. "
    "You read source material and produce rigorous, well-structured homework assignments. "
    "Always output valid JSON exactly as instructed. Never include markdown code fences."
)


# ── Main function ──────────────────────────────────────────────────────────────

def generate_master_assignment(pdf_path: str, num_questions: int = 5) -> dict:
    """
    Read a PDF and generate a master assignment JSON from its content.

    Args:
        pdf_path: Absolute path to the PDF file.
        num_questions: Number of questions to generate (default 5).

    Returns:
        Parsed master assignment dict ready for the pipeline.
    """
    pdf_bytes = Path(pdf_path).read_bytes()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    prompt = f"""You are given a PDF of course material. Your job is to design a homework assignment
that tests students' understanding of the key concepts in that material.

## Requirements
1. Generate exactly {num_questions} questions (Q1 through Q{num_questions}).
2. Each question must:
   - Test a distinct, important concept from the PDF.
   - Use [BRACKET] placeholders for ALL variable quantities (numbers, names, thresholds).
   - Have a clear, computable master_key with an explicit formula or procedure.
   - Be answerable with a specific numeric result OR a clearly defined categorical/boolean answer.
3. The questions must be varied enough that students cannot answer one by copying another.
4. SCENARIO_THEME placeholders let downstream agents swap in domain-specific contexts while
   keeping the underlying logic identical.

## Output Format
Output ONLY the JSON below — no explanation, no markdown fences.

{_SCHEMA_EXAMPLE}

Now generate the assignment from the PDF provided."""

    print(f"  [PDF Agent] Sending PDF to Claude for analysis...")
    response = client.messages.create(
        model=VARIATION_MODEL,
        max_tokens=8192,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )

    text = next(b.text for b in response.content if b.type == "text")
    text = text.strip().strip("```json").strip("```").strip()
    master = json.loads(text)

    # Ensure Q IDs are consistent
    for i, q in enumerate(master.get("questions", []), start=1):
        q["id"] = f"Q{i}"

    print(f"  ✓ Master assignment generated: {len(master.get('questions', []))} questions")
    return master


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python pdf_agent.py <path/to/file.pdf>")
        sys.exit(1)
    result = generate_master_assignment(sys.argv[1])
    print(json.dumps(result, indent=2))
