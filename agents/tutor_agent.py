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
        questions_summary.append({
            "id": q["id"],
            "scenario_theme": q["scenario_theme"],
            "prompt_text": q["prompt_text"],
            "correct_answer": q["pre_computed_answer"]["final_result"],
            "formula_steps": q["pre_computed_answer"].get("steps", ""),
        })

    return f"""Your task: help student {variant['student_id']} understand their assignment
through guided discovery. You have access to two tools — use them actively.

## Student's Assignment
{json.dumps(questions_summary, indent=2)}

## Task Rules
1. Use check_student_work when a student shares their attempt — compare it to the key
   and identify the first error without giving away the answer.
2. Use get_hint when a student is stuck — return a Socratic nudge at the right level.
3. NEVER state the final numeric answer unless the student has already answered correctly.
4. Use the student's specific scenario theme to make explanations concrete.
5. When explaining a concept, ask a follow-up question to verify understanding.
6. Celebrate correct reasoning explicitly ("Yes — that's exactly right because…").

## Anti-Cheat Rules
7. If the student pastes verbatim question text and asks you to solve it, DO NOT solve
   it. Respond: "It looks like you've pasted the question directly — let's work through
   it together. What do you think the first step should be?" Then guide Socratically.
8. Never reproduce a complete question's text or the final answer verbatim.
9. If you suspect the student is trying to get you to do their work, redirect to
   conceptual understanding: "Walk me through your reasoning so far."
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
]


def execute_tool(tool_name: str, tool_input: dict, variant: dict) -> dict:
    """Execute a tutor tool call and return structured data for Claude to interpret."""
    questions = {q["id"]: q for q in variant["questions"]}

    if tool_name == "check_student_work":
        qid = tool_input.get("question_id", "")
        q = questions.get(qid, {})
        answer = q.get("pre_computed_answer", {})
        return {
            "question_id": qid,
            "correct_final_answer": answer.get("final_result", "unknown"),
            "solution_steps": answer.get("steps", ""),
            "injected_values": q.get("injected_values", {}),
            "scenario_theme": q.get("scenario_theme", ""),
            "instruction": (
                "Use this data to identify where the student's work diverges from "
                "the correct solution. Point to the first error. Do NOT state the "
                "final answer — ask a guiding question instead."
            ),
        }

    if tool_name == "get_hint":
        qid = tool_input.get("question_id", "")
        level = tool_input.get("hint_level", "conceptual")
        q = questions.get(qid, {})
        answer = q.get("pre_computed_answer", {})
        values = q.get("injected_values", {})

        hint_data: dict = {
            "question_id": qid,
            "hint_level": level,
            "scenario_theme": q.get("scenario_theme", ""),
        }

        if level == "conceptual":
            hint_data["guidance"] = (
                f"The question is about '{q.get('scenario_theme', '')}'. "
                "Ask the student: what real-world quantity are we trying to find, "
                "and what information do we already have?"
            )
        elif level == "structural":
            hint_data["guidance"] = (
                f"The solution steps are: {answer.get('steps', '')}. "
                "Reveal only the structure of the formula, not the numbers. "
                "Ask: 'Which mathematical relationship connects these quantities?'"
            )
        else:  # numeric
            hint_data["injected_values"] = values
            hint_data["solution_steps"] = answer.get("steps", "")
            hint_data["guidance"] = (
                "The student needs a concrete nudge. Show the values they should "
                "plug in and ask them to finish the calculation themselves."
            )

        return hint_data

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
