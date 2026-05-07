"""
Tutor Agent  (student-facing interface)
────────────────────────────────────────
Task-based design: the tutor is given a specific task (help student X understand
concept Y) and has access to two tools — check_student_work and get_hint — so its
actions are explicit and auditable rather than hidden in a monolithic system prompt.

Anti-cheat: the tutor detects verbatim question pasting and redirects to Socratic
guidance without solving the problem directly.

Streaming: the CLI path streams to stdout; the API path uses stream_response().
"""

import json
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import TUTOR_MODEL

client = anthropic.Anthropic()


# ── Task description (not a "role" — a specific task with constraints) ─────────

def _build_system_prompt(variant: dict) -> str:
    questions_summary = []
    for q in variant["questions"]:
        # Support both old variant format and new session format
        if "answer_key" in q:
            entry = {
                "id": q["id"],
                "topic": q.get("topic", ""),
                "question_text": q["question_text"],
                "answer_key": q["answer_key"],
            }
            if q.get("source_reference"):
                entry["source_reference"] = q["source_reference"]
            questions_summary.append(entry)
        else:
            questions_summary.append({
                "id": q["id"],
                "topic": q.get("scenario_theme", ""),
                "question_text": q.get("prompt_text", ""),
                "answer_key": q.get("pre_computed_answer", {}).get("final_result", ""),
            })

    has_page_index = bool(variant.get("page_index"))
    ref_instruction = (
        "\n- When you check a student's work or explain a concept, use get_textbook_section "
        "to pull the relevant page and cite it: e.g. 'As the textbook explains on page 4…'. "
        "Always tell the student which page to read for more detail."
        if has_page_index else ""
    )

    return f"""You are a patient, encouraging study tutor helping a student genuinely learn the material.
You have tools — use them actively and often.

## The Student's Study Questions
{json.dumps(questions_summary, indent=2)}

## How to Teach

**When the student shares an attempt:**
Use check_student_work to compare their work against the answer key. Respond in two parts:
- Address what they got right or where the first error is (don't give away the answer).
- Explain the *underlying concept* in plain language — not just "that step is wrong" but
  *why* the correct approach makes sense. End with a guiding question that moves them forward.
- If the question has a source_reference, use get_textbook_section to fetch that page and
  quote the relevant passage so the student knows exactly where to study.

**When the student gets it right:**
Confirm clearly, then go deeper: explain WHY the method works and what would change if a
key variable were different. Use get_textbook_section to point them to the source material
for further reading.

**When the student is stuck:**
Use get_hint at the appropriate level. Lead with the concept before the mechanics —
"The key idea here is X. Given that, what do you think the first step should be?"
Then use get_textbook_section to show them where this concept is explained.

**When a student asks a conceptual question:**
Answer it directly and thoroughly. Use get_textbook_section to ground your answer in the
actual source material and cite the page.

## Core Constraints
- Never state the final answer to a question the student hasn't solved yet.
- If the student pastes a question verbatim asking you to solve it, redirect warmly.
- Keep explanations conversational — one concept at a time.{ref_instruction}
"""


# ── Tools (task-based: explicit actions with defined inputs/outputs) ───────────

TUTOR_TOOLS = [
    {
        "name": "check_student_work",
        "description": (
            "Check whether the student's partial or complete work on a specific question "
            "is on the right track. Returns the correct answer key data so you can identify "
            "errors and give targeted feedback. Use this whenever a student shares a calculation "
            "or answer attempt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question_id": {
                    "type": "string",
                    "description": "The question ID, e.g. 'Q1'",
                },
                "student_work": {
                    "type": "string",
                    "description": "The student's work, calculation, or answer as they wrote it",
                },
            },
            "required": ["question_id", "student_work"],
        },
    },
    {
        "name": "get_hint",
        "description": (
            "Retrieve structured hint data for a specific question at a specific level. "
            "Use this to craft a Socratic nudge — not to give away the answer. "
            "hint_level controls how much scaffolding to reveal: "
            "'conceptual' = big-picture idea, 'structural' = which formula applies, "
            "'numeric' = what values to plug in."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question_id": {
                    "type": "string",
                    "description": "The question ID, e.g. 'Q2'",
                },
                "hint_level": {
                    "type": "string",
                    "enum": ["conceptual", "structural", "numeric"],
                    "description": "Level of hint detail",
                },
            },
            "required": ["question_id", "hint_level"],
        },
    },
    {
        "name": "get_textbook_section",
        "description": (
            "Retrieve the actual textbook text from a specific page number. "
            "Use this to ground your explanations in the source material and cite "
            "specific pages when giving feedback or answering conceptual questions. "
            "The page number comes from source_reference in the question data or "
            "from check_student_work results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "integer",
                    "description": "The page number to retrieve from the textbook",
                },
            },
            "required": ["page"],
        },
    },
]


def execute_tool(tool_name: str, tool_input: dict, variant: dict) -> dict:
    """Execute a tutor tool call and return structured data for Claude to interpret."""
    questions = {q["id"]: q for q in variant["questions"]}

    if tool_name == "check_student_work":
        qid = tool_input.get("question_id", "")
        q = questions.get(qid, {})
        # Support both new session format and old variant format
        if "answer_key" in q:
            result = {
                "question_id": qid,
                "answer_key": q["answer_key"],
                "instruction": (
                    "Compare the student's work to the answer key. Identify the first "
                    "error or gap without stating the final answer. Ask a guiding question."
                ),
            }
            ref = q.get("source_reference")
            if ref:
                result["source_reference"] = ref
                result["instruction"] += (
                    f" The concept is covered on page {ref.get('page')} of the textbook "
                    f"({ref.get('section', '')}). Use get_textbook_section to fetch it and cite it."
                )
            return result
        answer = q.get("pre_computed_answer", {})
        return {
            "question_id": qid,
            "correct_final_answer": answer.get("final_result", "unknown"),
            "solution_steps": answer.get("steps", ""),
            "instruction": (
                "Identify where the student's work diverges from the correct solution. "
                "Point to the first error. Do NOT state the final answer — ask a guiding question."
            ),
        }

    if tool_name == "get_hint":
        qid = tool_input.get("question_id", "")
        level = tool_input.get("hint_level", "conceptual")
        q = questions.get(qid, {})

        # New session format has a hints dict
        if "hints" in q:
            hint_map = {"conceptual": "conceptual", "structural": "structural", "numeric": "specific"}
            hint_text = q["hints"].get(hint_map.get(level, "conceptual"), "")
            result = {
                "question_id": qid,
                "hint_level": level,
                "hint": hint_text,
                "guidance": "Deliver this hint in your own words as a Socratic nudge, not a direct statement.",
            }
            # For MC questions, list the choices so the tutor can reference them
            if q.get("type") == "multiple_choice" and q.get("choices"):
                result["choices"] = q["choices"]
            return result

        # Old variant format
        answer = q.get("pre_computed_answer", {})
        values = q.get("injected_values", {})
        hint_data: dict = {"question_id": qid, "hint_level": level}
        if level == "conceptual":
            hint_data["guidance"] = (
                f"The question is about '{q.get('scenario_theme', '')}'. "
                "Ask: what are we trying to find, and what do we already know?"
            )
        elif level == "structural":
            hint_data["guidance"] = (
                f"Solution steps: {answer.get('steps', '')}. "
                "Reveal only the structure, not the numbers."
            )
        else:
            hint_data["injected_values"] = values
            hint_data["solution_steps"] = answer.get("steps", "")
            hint_data["guidance"] = "Show the values to plug in; ask the student to finish."
        return hint_data

    if tool_name == "get_textbook_section":
        page_num = tool_input.get("page")
        page_index = variant.get("page_index", [])
        for entry in page_index:
            if entry.get("page") == page_num:
                text = entry.get("text", "")
                return {
                    "page": page_num,
                    "text": text[:3000] if len(text) > 3000 else text,
                    "truncated": len(text) > 3000,
                }
        return {"error": f"Page {page_num} not found. Available pages: 1–{len(page_index)}"}

    return {"error": f"Unknown tool: {tool_name}"}


# ── TutorSession (stateful, used by CLI) ──────────────────────────────────────

class TutorSession:
    def __init__(self, variant: dict):
        self.variant = variant
        self.student_id = variant["student_id"]
        self.system_prompt = _build_system_prompt(variant)
        self.history: list[dict] = []

    def _run_tool_loop(self, messages: list) -> list:
        """
        Run the agentic tool-use loop (non-streaming).
        Returns the updated messages list ready for the final streaming response.
        """
        current = list(messages)
        while True:
            response = client.messages.create(
                model=TUTOR_MODEL,
                max_tokens=1024,
                system=self.system_prompt,
                tools=TUTOR_TOOLS,
                messages=current,
            )
            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input, self.variant)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

            current.append({
                "role": "assistant",
                "content": [b.model_dump() for b in response.content],
            })
            current.append({"role": "user", "content": tool_results})

        return current

    def chat(self, student_message: str) -> str:
        """Send a student message, run tool loop, stream final response to stdout."""
        messages = self.history + [{"role": "user", "content": student_message}]
        messages = self._run_tool_loop(messages)

        full_response = ""
        print(f"\n[Tutor → {self.student_id}] ", end="", flush=True)

        with client.messages.stream(
            model=TUTOR_MODEL,
            max_tokens=1024,
            thinking={"type": "adaptive"},
            system=self.system_prompt,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                full_response += text

        print()

        # Persist the user turn and final assistant response in history
        self.history.append({"role": "user", "content": student_message})
        self.history.append({"role": "assistant", "content": full_response})
        return full_response

    def stream_response(self, student_message: str):
        """
        Generator that yields text tokens for streaming in a GUI.
        Runs tool loop first (blocking), then yields streaming tokens.
        Also appends both turns to self.history.
        """
        messages = self.history + [{"role": "user", "content": student_message}]
        messages = self._run_tool_loop(messages)

        full_response = ""
        with client.messages.stream(
            model=TUTOR_MODEL,
            max_tokens=1024,
            thinking={"type": "adaptive"},
            system=self.system_prompt,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                yield text

        self.history.append({"role": "user", "content": student_message})
        self.history.append({"role": "assistant", "content": full_response})

    def show_assignment(self):
        print(f"\n{'='*60}")
        print(f"  Assignment — Student {self.student_id}")
        print(f"{'='*60}")
        for q in self.variant["questions"]:
            print(f"\n[{q['id']}] Scenario: {q['scenario_theme']}")
            print(q["prompt_text"])
        print(f"\n{'='*60}\n")


# ── CLI interactive session ────────────────────────────────────────────────────

def run_interactive_session(variant: dict):
    session = TutorSession(variant)
    session.show_assignment()
    print("Type your question or 'quit' to exit.\n")

    while True:
        try:
            user_input = input(f"[{session.student_id}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye! Good luck with your assignment.")
            break

        if not user_input:
            continue

        session.chat(user_input)
