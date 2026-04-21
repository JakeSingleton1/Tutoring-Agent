"""
Pipeline Orchestrator
─────────────────────
Wires the agents together in the correct sequence:

  [Optional] PDF Agent → master_assignment
       ↓
  Variation Agent → Validator (IF TRUE gate) → Save STU001
       ↓
  *** HUMAN REVIEWS STU001 KEY — approves before continuing ***
       ↓
  Variation Agent × N → Validator × N → Save STU002…STUN
       ↓
  Tutor Agent  (per student, interactive)
       ↓
  Evaluator Agent (per student, on submission)
"""

import json
import random
from pathlib import Path

from agents.variation_agent import generate_variant
from agents.validator_agent import validate_variant
from agents.tutor_agent import run_interactive_session
from agents.evaluator_agent import evaluate_submission, print_report
from config import (
    MASTER_ASSIGNMENT_PATH,
    VARIANTS_DIR,
    NUM_VARIANTS,
    MAX_VALIDATION_RETRIES,
    SCENARIO_THEMES,
)

# Path for a PDF-generated master (takes precedence over static master_assignment.json)
_ACTIVE_MASTER_PATH = VARIANTS_DIR.parent / "active_master.json"


class Pipeline:
    def __init__(self):
        # Prefer a PDF-generated master if one exists
        if _ACTIVE_MASTER_PATH.exists():
            with open(_ACTIVE_MASTER_PATH) as f:
                self.base_assignment = json.load(f)
        else:
            with open(MASTER_ASSIGNMENT_PATH) as f:
                self.base_assignment = json.load(f)
        self.variants_dir = VARIANTS_DIR

    # ── PDF ingestion ──────────────────────────────────────────────────────────

    def prepare_from_pdf(self, pdf_path: str) -> dict:
        """
        Read a PDF and generate a new master assignment from its content.
        Saves result as active_master.json so subsequent Pipeline instances use it.
        Returns the generated master assignment dict.
        """
        from agents.pdf_agent import generate_master_assignment
        print(f"\n  [PDF Agent] Analysing {Path(pdf_path).name} ...")
        master = generate_master_assignment(pdf_path)
        self.base_assignment = master
        with open(_ACTIVE_MASTER_PATH, "w") as f:
            json.dump(master, f, indent=2)
        print(f"  ✓ Active master saved to active_master.json\n")
        return master

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _emit(self, callback, event: dict):
        if callback:
            callback(event)

    def _generate_and_validate_one(self, student_id: str, themes: list, callback) -> dict:
        """Generate + validate a single student variant. Returns the final (corrected) variant."""
        validation = None
        for attempt in range(1, MAX_VALIDATION_RETRIES + 1):
            self._emit(callback, {"type": "generating", "student_id": student_id})
            variant = generate_variant(student_id, self.base_assignment, themes[:5])

            print(f"  [Validator] Checking {student_id} (attempt {attempt}/{MAX_VALIDATION_RETRIES})...")
            self._emit(callback, {
                "type": "validating", "student_id": student_id,
                "attempt": attempt, "max": MAX_VALIDATION_RETRIES,
            })
            validation = validate_variant(variant)

            if validation["all_valid"]:
                print(f"  ✓ IF TRUE — {student_id} is valid")
                self._emit(callback, {"type": "valid", "student_id": student_id})
                break
            else:
                bad_qs = [
                    qid for qid, r in validation["question_results"].items()
                    if not r.get("valid") or not r.get("answer_matches")
                ]
                print(f"  ✗ IF FALSE — issues in {bad_qs}, auto-correcting...")
                self._emit(callback, {"type": "invalid", "student_id": student_id, "issues": bad_qs})
                if attempt == MAX_VALIDATION_RETRIES:
                    print(f"  ⚠ Max retries reached — using auto-corrected variant")

        return validation["corrected_variant"]

    def _save_variant(self, variant: dict):
        path = self.variants_dir / f"{variant['student_id']}.json"
        with open(path, "w") as f:
            json.dump(variant, f, indent=2)

    def _load_variant(self, student_id: str) -> dict:
        path = self.variants_dir / f"{student_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"No variant for {student_id}. Generate first.")
        with open(path) as f:
            return json.load(f)

    def list_students(self) -> list[str]:
        return sorted(p.stem for p in self.variants_dir.glob("STU*.json"))

    # ── Phase 1a: First variant (human reviews before bulk generation) ─────────

    def generate_first_variant(self, progress_callback=None) -> dict:
        """
        Generate and validate STU001 only. Save it to disk.
        The instructor should review the answer key before calling
        generate_remaining_variants().
        Returns the variant dict (includes pre_computed_answer keys).
        """
        print(f"\n{'='*60}")
        print(f"  PHASE 1a: Generating STU001 for human review")
        print(f"{'='*60}\n")

        themes = SCENARIO_THEMES.copy()
        random.shuffle(themes)
        student_id = "STU001"

        self._emit(progress_callback, {
            "type": "student_start", "student_id": student_id, "index": 1, "total": "?",
        })

        variant = self._generate_and_validate_one(student_id, themes, progress_callback)
        self._save_variant(variant)
        self._emit(progress_callback, {"type": "saved", "student_id": student_id})
        self._emit(progress_callback, {"type": "first_done", "student_id": student_id, "variant": variant})
        print(f"\n  STU001 saved. Awaiting human approval.\n")
        return variant

    # ── Phase 1b: Remaining variants (after human approval) ───────────────────

    def generate_remaining_variants(self, num_students: int, progress_callback=None) -> list[dict]:
        """
        Generate STU002 through STU{num_students} after the instructor has approved STU001.
        STU001 must already exist on disk.
        """
        print(f"\n{'='*60}")
        print(f"  PHASE 1b: Generating STU002–STU{num_students:03d}")
        print(f"{'='*60}\n")

        all_validated = []
        themes = SCENARIO_THEMES.copy()

        for i in range(2, num_students + 1):
            student_id = f"STU{i:03d}"
            print(f"── Student {i}/{num_students}: {student_id} ──")
            self._emit(progress_callback, {
                "type": "student_start", "student_id": student_id, "index": i, "total": num_students,
            })

            random.shuffle(themes)
            variant = self._generate_and_validate_one(student_id, themes, progress_callback)
            self._save_variant(variant)
            all_validated.append(variant)
            self._emit(progress_callback, {"type": "saved", "student_id": student_id})
            print()

        print(f"\n✓ All {num_students} variants saved to {self.variants_dir}/\n")
        self._emit(progress_callback, {"type": "done", "total": num_students})
        return all_validated

    # ── Legacy: generate all at once (CLI usage) ───────────────────────────────

    def generate_variants(self, num_students: int = NUM_VARIANTS, progress_callback=None) -> list[dict]:
        """
        Original single-step generation (no human gate). Used by the CLI.
        For the GUI, prefer generate_first_variant() + generate_remaining_variants().
        """
        def emit(event):
            self._emit(progress_callback, event)

        print(f"\n{'='*60}")
        print(f"  PHASE 1: Generating {num_students} student variants")
        print(f"{'='*60}\n")

        all_validated = []
        themes = SCENARIO_THEMES.copy()

        for i in range(1, num_students + 1):
            student_id = f"STU{i:03d}"
            print(f"── Student {i}/{num_students}: {student_id} ──")
            emit({"type": "student_start", "student_id": student_id, "index": i, "total": num_students})

            random.shuffle(themes)
            variant = self._generate_and_validate_one(student_id, themes, progress_callback)
            self._save_variant(variant)
            all_validated.append(variant)
            emit({"type": "saved", "student_id": student_id})
            print()

        print(f"\n✓ All {num_students} variants saved to {self.variants_dir}/\n")
        emit({"type": "done", "total": num_students})
        return all_validated

    # ── Phase 2: Tutor Session ────────────────────────────────────────────────

    def run_tutor_session(self, student_id: str):
        print(f"\n{'='*60}")
        print(f"  PHASE 2: Tutor Session — {student_id}")
        print(f"{'='*60}")
        variant = self._load_variant(student_id)
        run_interactive_session(variant)

    # ── Phase 3: Grading ──────────────────────────────────────────────────────

    def grade_submission(self, student_id: str, submission: dict) -> dict:
        print(f"\n{'='*60}")
        print(f"  PHASE 3: Evaluating Submission — {student_id}")
        print(f"{'='*60}")
        variant = self._load_variant(student_id)
        result = evaluate_submission(variant, submission)
        print_report(result)
        eval_path = self.variants_dir / f"{student_id}_eval.json"
        with open(eval_path, "w") as f:
            json.dump(result, f, indent=2)
        return result


if __name__ == "__main__":
    p = Pipeline()
    p.generate_variants(num_students=2)
    students = p.list_students()
    print(f"Students: {students}")
