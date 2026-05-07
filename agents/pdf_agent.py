"""
PDF Agent
─────────
Reads a PDF file and generates a master_assignment.json from its content.
Extracts text with pypdf and sends it as plain text — avoids Anthropic's
32 MB base64 request limit and works on any text-based PDF.

Output: a master assignment dict matching the pipeline schema.
"""

import json
from pathlib import Path

import anthropic

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import VARIATION_MODEL

client = anthropic.Anthropic()

MAX_CHARS = 80_000  # ~60-80 pages; enough for a chapter, safe within context window

# ── Schema reference shown to Claude ──────────────────────────────────────────

_SCHEMA_EXAMPLE = """
{
  "assignment_metadata": {
    "title": "Assignment title derived from the material",
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
    "You read source material and produce rigorous, well-structured study assignments. "
    "Always output valid JSON exactly as instructed. Never include markdown code fences."
)


# ── Text extraction ────────────────────────────────────────────────────────────

def _extract_text(pdf_path: str) -> tuple[str, list[dict]]:
    """Extract plain text from a PDF using pypdf.

    Returns:
        (full_text, page_index) where full_text has [Page N] markers and
        page_index is a list of {"page": N, "text": "..."} dicts for tool lookup.
    """
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    if reader.is_encrypted:
        raise ValueError("This PDF is encrypted/password-protected. Please use an unlocked PDF.")

    page_index = []
    pages_text = []
    total = 0
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        page_index.append({"page": i + 1, "text": text})
        pages_text.append(f"[Page {i + 1}]\n{text}")
        total += len(text)
        if total >= MAX_CHARS:
            break

    full_text = "\n\n".join(pages_text).strip()

    if not full_text:
        raise ValueError(
            "No text could be extracted from this PDF. "
            "It may be a scanned image — try a text-based PDF or copy-paste the content."
        )

    if len(full_text) > MAX_CHARS:
        full_text = (
            full_text[:MAX_CHARS]
            + f"\n\n[Content truncated at {MAX_CHARS:,} characters. "
            "For best results, upload a single chapter rather than a full textbook.]"
        )

    return full_text, page_index


# ── Main function ──────────────────────────────────────────────────────────────

def generate_master_assignment(pdf_path: str, num_questions: int = 5) -> dict:
    """
    Extract text from a PDF and ask Claude to generate a master assignment.

    Args:
        pdf_path: Absolute path to the PDF file.
        num_questions: Number of questions to generate (default 5).

    Returns:
        Parsed master assignment dict ready for the pipeline.
    """
    print(f"  [PDF Agent] Extracting text from PDF…")
    content_text = _extract_text(pdf_path)
    char_count = len(content_text)
    print(f"  [PDF Agent] Extracted {char_count:,} characters — sending to Claude…")

    prompt = f"""Below is the text content of a study document. Your job is to design a study
assignment that tests students' understanding of the key concepts in this material.

## Source Material
{content_text}

## Requirements
1. Generate exactly {num_questions} questions (Q1 through Q{num_questions}).
2. Each question must:
   - Test a distinct, important concept from the material above.
   - Use [BRACKET] placeholders for ALL variable quantities (numbers, names, thresholds).
   - Have a clear, computable master_key with an explicit formula or procedure.
   - Be answerable with a specific numeric result OR a clearly defined categorical answer.
3. Questions must be varied — a student cannot answer one by copying another.
4. SCENARIO_THEME placeholders let downstream agents swap in domain-specific contexts
   while keeping the underlying logic identical.

## Output Format
Output ONLY the JSON below — no explanation, no markdown fences.

{_SCHEMA_EXAMPLE}"""

    response = client.messages.create(
        model=VARIATION_MODEL,
        max_tokens=8192,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        raise ValueError("No text block in PDF agent response")

    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        master = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from PDF agent: {e}\n{text[:200]}")

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
