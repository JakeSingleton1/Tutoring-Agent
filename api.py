"""
FastAPI backend for the Tutor-Agent GUI.

Endpoints:
  POST /api/pdf/upload                 → analyse PDF, return generated master assignment
  GET  /api/master                     → return the active master assignment
  GET  /api/students                   → list student IDs with generated variants
  GET  /api/students/{id}              → variant JSON for one student
  GET  /api/generate/first/stream      → SSE: generate STU001 for human review
  GET  /api/generate/remaining/stream  → SSE: generate STU002-N after approval
  POST /api/tutor/{id}/chat            → SSE token stream (task-based tool loop)
  POST /api/grade/{id}                 → evaluation JSON
"""

import json
import queue
import threading
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

from agents.tutor_agent import _build_system_prompt, TUTOR_TOOLS, execute_tool
from agents.evaluator_agent import evaluate_submission
from pipeline import Pipeline, _ACTIVE_MASTER_PATH
from config import VARIANTS_DIR, TUTOR_MODEL, MASTER_ASSIGNMENT_PATH

app = FastAPI(title="Tutor Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_variant(student_id: str) -> dict:
    path = VARIANTS_DIR / f"{student_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No variant for {student_id}")
    return json.loads(path.read_text())


def _make_pipeline() -> Pipeline:
    """Create a Pipeline that uses the active master (PDF-generated if available)."""
    return Pipeline()


def _sse_thread(target_fn, q: queue.Queue):
    """Run target_fn in a daemon thread; sentinel None signals completion."""
    def run():
        try:
            target_fn()
        except Exception as e:
            q.put({"type": "error", "message": str(e)})
        finally:
            q.put(None)
    threading.Thread(target=run, daemon=True).start()


def _sse_stream(q: queue.Queue):
    """Drain an event queue and yield SSE-formatted strings."""
    while True:
        event = q.get()
        if event is None:
            yield "data: [DONE]\n\n"
            break
        yield f"data: {json.dumps(event)}\n\n"


# ── PDF ingestion ──────────────────────────────────────────────────────────────

@app.post("/api/pdf/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Accept a PDF upload, run the PDF Agent to generate a master assignment,
    save it as active_master.json, and return the master for preview.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    tmp_path = Path("/tmp") / file.filename
    tmp_path.write_bytes(await file.read())

    p = _make_pipeline()
    master = p.prepare_from_pdf(str(tmp_path))
    tmp_path.unlink(missing_ok=True)
    return master


@app.get("/api/master")
def get_master():
    """Return whichever master assignment is currently active."""
    if _ACTIVE_MASTER_PATH.exists():
        return json.loads(_ACTIVE_MASTER_PATH.read_text())
    return json.loads(MASTER_ASSIGNMENT_PATH.read_text())


# ── Students ───────────────────────────────────────────────────────────────────

@app.get("/api/students")
def list_students():
    return sorted(p.stem for p in VARIANTS_DIR.glob("STU*.json"))


@app.get("/api/students/{student_id}")
def get_variant(student_id: str):
    return _load_variant(student_id)


# ── Generation: first variant (human review gate) ─────────────────────────────

@app.get("/api/generate/first/stream")
def generate_first_stream():
    """
    SSE stream that generates only STU001 and emits a 'first_done' event
    containing the full variant (including answer key) for the instructor to review.
    """
    q: queue.Queue = queue.Queue()

    def run():
        p = _make_pipeline()
        p.generate_first_variant(progress_callback=q.put)

    _sse_thread(run, q)
    return StreamingResponse(_sse_stream(q), media_type="text/event-stream")


# ── Generation: remaining variants (after human approval) ─────────────────────

@app.get("/api/generate/remaining/stream")
def generate_remaining_stream(n: int = 10):
    """
    SSE stream that generates STU002 through STU{n} after the instructor has
    approved STU001. STU001 must already exist on disk.
    """
    if not (VARIANTS_DIR / "STU001.json").exists():
        raise HTTPException(
            status_code=400,
            detail="STU001 not found. Generate and approve the first variant first.",
        )

    q: queue.Queue = queue.Queue()

    def run():
        p = _make_pipeline()
        p.generate_remaining_variants(num_students=n, progress_callback=q.put)

    _sse_thread(run, q)
    return StreamingResponse(_sse_stream(q), media_type="text/event-stream")


# ── Tutor chat: task-based tool loop + streaming final response ────────────────

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/api/tutor/{student_id}/chat")
def tutor_chat(student_id: str, req: ChatRequest):
    """
    Task-based tutor endpoint:
      1. Run agentic tool-use loop (non-streaming) to resolve check_student_work /
         get_hint tool calls.
      2. Stream the final text response to the client.
    """
    variant = _load_variant(student_id)
    system_prompt = _build_system_prompt(variant)
    messages = req.history + [{"role": "user", "content": req.message}]

    def stream():
        current = list(messages)

        # ── Tool-use loop (non-streaming, may iterate multiple times) ──
        while True:
            response = client.messages.create(
                model=TUTOR_MODEL,
                max_tokens=1024,
                system=system_prompt,
                tools=TUTOR_TOOLS,
                messages=current,
            )

            if response.stop_reason != "tool_use":
                break  # No more tools needed

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input, variant)
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

        # ── Stream the final pedagogical response ──────────────────────
        with client.messages.stream(
            model=TUTOR_MODEL,
            max_tokens=1024,
            thinking={"type": "adaptive"},
            system=system_prompt,
            messages=current,
        ) as s:
            for text in s.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Grading ────────────────────────────────────────────────────────────────────

class GradeRequest(BaseModel):
    answers: dict[str, str]


@app.post("/api/grade/{student_id}")
def grade_submission(student_id: str, req: GradeRequest):
    variant = _load_variant(student_id)
    return evaluate_submission(variant, req.answers)
