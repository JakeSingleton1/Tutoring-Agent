"""
Simple file-based session store.
Each session lives in sessions/<id>.json.
sessions/index.json is a lightweight list of summaries for the UI.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

SESSIONS_DIR = Path(__file__).parent / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

_INDEX = SESSIONS_DIR / "index.json"


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def _read_index() -> list:
    if not _INDEX.exists():
        return []
    return json.loads(_INDEX.read_text())


def _write_index(index: list):
    _INDEX.write_text(json.dumps(index, indent=2))


def list_sessions() -> list:
    """Return session summaries, newest first."""
    return _read_index()


def create_session(title: str, source: str, questions: list, source_text: str = "", page_index: list | None = None) -> dict:
    session_id = uuid.uuid4().hex[:8]
    now = datetime.now().isoformat()
    session = {
        "id": session_id,
        "title": title,
        "source": source,
        "created_at": now,
        "source_text": source_text,  # stored so questions can be regenerated without re-upload
        "page_index": page_index or [],  # per-page text for tutor textbook references
        "questions": questions,
        "messages": [],
        "answers": {},
        "result": None,
    }
    _session_path(session_id).write_text(json.dumps(session, indent=2))

    index = _read_index()
    index.insert(0, {
        "id": session_id,
        "title": title,
        "source": source,
        "created_at": now,
        "question_count": len(questions),
        "score": None,
    })
    _write_index(index)
    return session


def get_session(session_id: str) -> dict:
    path = _session_path(session_id)
    if not path.exists():
        raise FileNotFoundError(f"Session {session_id} not found")
    return json.loads(path.read_text())


def update_session(session_id: str, **fields) -> dict:
    """Merge fields into the session and persist."""
    session = get_session(session_id)
    session.update(fields)
    _session_path(session_id).write_text(json.dumps(session, indent=2))

    # If a result was saved, update the score in the index too
    if "result" in fields and fields["result"]:
        score = fields["result"].get("overall_score")
        max_score = fields["result"].get("max_score")
        index = _read_index()
        for entry in index:
            if entry["id"] == session_id:
                entry["score"] = f"{score}/{max_score}" if score is not None else None
                break
        _write_index(index)

    return session


def delete_session(session_id: str):
    _session_path(session_id).unlink(missing_ok=True)
    _write_index([s for s in _read_index() if s["id"] != session_id])
