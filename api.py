"""
FastAPI backend — session-based study tool.

Endpoints:
  GET  /api/sessions                    → list all sessions
  GET  /api/sessions/{id}               → full session data
  POST /api/sessions/{id}               → update session fields (messages, answers, result)
  DELETE /api/sessions/{id}             → delete session
  POST /api/sessions/generate/stream    → SSE: upload PDF, generate questions, create session
  POST /api/tutor/{id}/chat             → SSE tutor chat stream
  POST /api/grade/{id}                  → grade answers, save result to session
"""

import json
import os
import queue
import tempfile
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
from agents.pdf_agent import _extract_text
from agents.study_generator import generate_questions
from session_store import (
    list_sessions, create_session, get_session, update_session, delete_session,
)
from config import TUTOR_MODEL

app = FastAPI(title="Tutor Agent API")

_ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_session(session_id: str) -> dict:
    try:
        return get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")


def _sse_thread(target_fn, q: queue.Queue):
    def run():
        try:
            target_fn()
        except Exception as e:
            q.put({"type": "error", "message": str(e)})
        finally:
            q.put(None)
    threading.Thread(target=run, daemon=True).start()


def _sse_stream(q: queue.Queue):
    while True:
        event = q.get()
        if event is None:
            yield "data: [DONE]\n\n"
            break
        yield f"data: {json.dumps(event)}\n\n"


# ── Sessions ───────────────────────────────────────────────────────────────────

@app.get("/api/sessions")
def api_list_sessions():
    return list_sessions()


@app.get("/api/sessions/{session_id}")
def api_get_session(session_id: str):
    return _load_session(session_id)


class SessionUpdate(BaseModel):
    messages: list | None = None
    answers: dict | None = None
    result: dict | None = None


@app.post("/api/sessions/{session_id}")
def api_update_session(session_id: str, body: SessionUpdate):
    _load_session(session_id)  # 404 if missing
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    return update_session(session_id, **fields)


@app.delete("/api/sessions/{session_id}")
def api_delete_session(session_id: str):
    _load_session(session_id)
    delete_session(session_id)
    return {"ok": True}


@app.get("/api/sessions/{session_id}/regenerate/stream")
def regenerate_session_stream(session_id: str):
    """
    Generate a fresh set of questions from the same source text as an existing session.
    Creates a new session (preserves the original). Streams SSE progress.
    """
    session = _load_session(session_id)
    source_text = session.get("source_text", "")
    page_index = session.get("page_index", [])

    q: queue.Queue = queue.Queue()

    def run():
        if not source_text:
            q.put({"type": "error", "message": "This session has no stored source text — please upload the PDF again to generate new questions."})
            return
        q.put({"type": "status", "message": "Generating new questions from the same material…"})
        questions = generate_questions(source_text, session["title"], num_questions=10)
        q.put({"type": "status", "message": f"Generated {len(questions)} questions. Saving…"})
        new_session = create_session(
            title=session["title"],
            source=session["source"],
            questions=questions,
            source_text=source_text,
            page_index=page_index,
        )
        q.put({"type": "done", "session": new_session})

    _sse_thread(run, q)
    return StreamingResponse(_sse_stream(q), media_type="text/event-stream")


# ── Generate study session from PDF ───────────────────────────────────────────

@app.post("/api/sessions/generate/stream")
async def generate_session_stream(file: UploadFile = File(...)):
    """
    Accept a PDF, extract text, generate 10 questions, save as a new session.
    Streams SSE progress events; final event is {'type':'done','session': <full session>}.
    """
    safe_name = Path(file.filename).name
    if not safe_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    q: queue.Queue = queue.Queue()

    def run():
        try:
            q.put({"type": "status", "message": "Extracting text from PDF…"})
            text, page_index = _extract_text(tmp_path)
            char_count = len(text)
            q.put({"type": "status", "message": f"Extracted {char_count:,} characters. Generating questions…"})

            # Derive a title from the filename
            title = Path(safe_name).stem.replace("_", " ").replace("-", " ").title()

            questions = generate_questions(text, title, num_questions=10)
            q.put({"type": "status", "message": f"Generated {len(questions)} questions. Saving session…"})

            session = create_session(title=title, source=safe_name, questions=questions, source_text=text, page_index=page_index)
            q.put({"type": "done", "session": session})
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    _sse_thread(run, q)
    return StreamingResponse(_sse_stream(q), media_type="text/event-stream")


# ── Tutor chat ─────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/api/tutor/{session_id}/chat")
def tutor_chat(session_id: str, req: ChatRequest):
    session = _load_session(session_id)
    system_prompt = _build_system_prompt(session)
    messages = req.history + [{"role": "user", "content": req.message}]

    def stream():
        current = list(messages)

        # Tool-use loop
        while True:
            response = client.messages.create(
                model=TUTOR_MODEL,
                max_tokens=1024,
                system=system_prompt,
                tools=TUTOR_TOOLS,
                messages=current,
            )
            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input, session)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

            current.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
            current.append({"role": "user", "content": tool_results})

        # Stream final response
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


@app.post("/api/grade/{session_id}")
def grade_submission(session_id: str, req: GradeRequest):
    session = _load_session(session_id)
    try:
        result = evaluate_submission(session, req.answers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    update_session(session_id, answers=req.answers, result=result)
    return result
