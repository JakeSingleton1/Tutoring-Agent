# Tutor Agent

An agentic tutoring pipeline for the **Agentics — Spring 2026** course. Instructors upload a PDF of course material; the system generates a unique, personalized assignment for every student, tutors them interactively using the Socratic method, and grades their submissions — all powered by Claude.

---

## How It Works

```
PDF / Course Material
        │
        ▼
  [PDF Agent] ──────────────────── Reads PDF, generates master assignment
        │
        ▼
  [Variation Agent] ─────────────── Generates STU001 with unique numbers + scenario
        │
        ▼
  [Validator Agent] ─────────────── IF TRUE: proceed │ IF FALSE: auto-correct + retry
        │
        ▼
  *** INSTRUCTOR REVIEWS STU001 KEY — human approval required ***
        │
        ▼
  [Variation + Validator] × N ────── Generates STU002–STUN (materially identical)
        │
        ├──▶ [Tutor Agent]    ──── Socratic chat, anti-cheat, task-based tool use
        │
        └──▶ [Evaluator Agent] ─── Grades submission, returns per-question feedback
```

**Key design decisions:**
- Every student gets **different numbers and scenario themes** but the same underlying concepts — preventing answer sharing.
- The **instructor validates the first answer key** before bulk generation. The AI never self-approves.
- The tutor uses **task-based tool use** (`check_student_work`, `get_hint`) so its actions are explicit and auditable, not hidden in a monolithic prompt.
- **Anti-cheat**: the tutor detects verbatim question pasting and redirects to guided discovery rather than solving.

---

## Project Structure

```
Tutor-Agent/
├── agents/
│   ├── pdf_agent.py          # Reads a PDF → generates master_assignment JSON
│   ├── variation_agent.py    # Fills in placeholders to produce student variants
│   ├── validator_agent.py    # IF TRUE gate — checks math correctness
│   ├── tutor_agent.py        # Socratic tutor with tool use + anti-cheat
│   └── evaluator_agent.py    # Grades student submissions against the answer key
├── frontend/                 # Vite + React + Tailwind GUI
│   └── src/pages/
│       ├── GeneratePage.jsx  # PDF upload → approval wizard → bulk generate
│       ├── TutorPage.jsx     # Streaming chat interface
│       └── GradePage.jsx     # Answer submission + grade report
├── pipeline.py               # Orchestrates all agents; exposes generate/tutor/grade
├── api.py                    # FastAPI backend (SSE streams + REST endpoints)
├── config.py                 # Model selection, paths, scenario themes
├── main.py                   # CLI entry point
├── master_assignment.json    # Built-in assignment template (Agentic Workflows)
└── student_variants/         # Generated per-student JSON files (gitignored)
```

---

## Models Used

| Agent     | Model              | Why |
|-----------|--------------------|-----|
| PDF       | claude-opus-4-6    | Needs deep reading comprehension |
| Variation | claude-opus-4-6    | Creative + accurate math for novel scenarios |
| Validator | claude-haiku-4-5   | Only checks arithmetic — fast and cheap |
| Tutor     | claude-opus-4-6    | Best quality for student-facing interaction |
| Evaluator | claude-opus-4-6    | Nuanced grading and feedback generation |

---

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- An Anthropic API key

### Install

```bash
# Python dependencies
pip install -r requirements.txt

# Frontend dependencies
cd frontend && npm install
```

### Configure

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Running

Start both servers (two terminals):

```bash
# Terminal 1 — FastAPI backend (port 8000)
uvicorn api:app --reload

# Terminal 2 — Vite dev server (port 5173)
cd frontend && npm run dev
```

Open **http://localhost:5173**.

---

## GUI Walkthrough

### Generate Tab — 4-step wizard

1. **Load Topic** — drag-and-drop a PDF (textbook chapter, game manual, course notes) or click "Use Existing Master" to work with the built-in Agentic Workflows assignment.
2. **Generate First Variant** — the pipeline generates STU001 and streams live progress. The answer key is shown in an expandable panel.
3. **Human Approval** — you review the question wording and answer key. Click **Approve** to proceed or **Regenerate** to try again. The AI cannot approve its own output.
4. **Generate All** — the remaining variants (STU002–N) are generated in bulk with a live progress log.

### Tutor Tab

Select a student, optionally expand their assignment, then type in the chat. The tutor streams responses token-by-token and uses two tools under the hood:
- `check_student_work` — compares the student's attempt against the key and identifies the first error
- `get_hint` — returns a conceptual, structural, or numeric Socratic hint

The full conversation history is maintained client-side and sent with each message.

### Grade Tab

Select a student, fill in answers for each question, and submit. The evaluator returns a score out of 100 with per-question feedback showing the correct answer alongside the student's answer.

---

## CLI Usage

The original command-line interface is still fully functional:

```bash
# Generate 10 student variants (skips human approval gate)
python main.py generate --n 10

# Start an interactive tutor session
python main.py tutor STU001

# Grade a student (prompts for answers interactively)
python main.py grade STU001

# List all students with generated variants
python main.py list
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/pdf/upload` | Upload a PDF → generate + save master assignment |
| `GET`  | `/api/master` | Return the active master assignment |
| `GET`  | `/api/students` | List student IDs with generated variants |
| `GET`  | `/api/students/{id}` | Return a student's variant JSON |
| `GET`  | `/api/generate/first/stream` | SSE: generate STU001, emits `first_done` with full variant |
| `GET`  | `/api/generate/remaining/stream?n=10` | SSE: generate STU002–N after human approval |
| `POST` | `/api/tutor/{id}/chat` | SSE: task-based tool loop + streaming tutor response |
| `POST` | `/api/grade/{id}` | Grade a submission, return evaluation JSON |

---

## Extending the Assignment

The built-in `master_assignment.json` covers five Agentic Workflows concepts (throughput, tool cost-efficiency, parallel vs sequential latency, RAG retrieval, pipeline reliability). To use different material, upload any PDF through the GUI — the PDF Agent will derive new questions from it automatically.

To add scenario themes to the pool, edit `SCENARIO_THEMES` in [config.py](config.py).
