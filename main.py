"""
main.py — CLI entry point for the Tutor-Agent pipeline.

Commands:
  python main.py generate [--n N]          Generate N student variants (default: 10)
  python main.py tutor <student_id>        Start a tutor session
  python main.py grade <student_id>        Grade a student interactively
  python main.py list                      List all students with generated variants
  python main.py demo                      Run a full demo (generate 2, tutor, grade)
"""

import sys
import json
from dotenv import load_dotenv
load_dotenv()
from pipeline import Pipeline


def cmd_generate(args):
    n = 10
    if "--n" in args:
        idx = args.index("--n")
        n = int(args[idx + 1])
    p = Pipeline()
    p.generate_variants(num_students=n)


def cmd_tutor(args):
    if not args:
        print("Usage: python main.py tutor <student_id>")
        sys.exit(1)
    p = Pipeline()
    p.run_tutor_session(args[0].upper())


def cmd_grade(args):
    if not args:
        print("Usage: python main.py grade <student_id>")
        sys.exit(1)
    student_id = args[0].upper()
    p = Pipeline()
    variant = p._load_variant(student_id)

    print(f"\nEntering answers for {student_id}.")
    print("Type your answer for each question (or press Enter to skip).\n")

    submission = {}
    for q in variant["questions"]:
        print(f"[{q['id']}] {q['prompt_text']}\n")
        answer = input("Your answer: ").strip()
        submission[q["id"]] = answer if answer else "<no answer>"
        print()

    p.grade_submission(student_id, submission)


def cmd_list(_args):
    p = Pipeline()
    students = p.list_students()
    if not students:
        print("No student variants found. Run: python main.py generate")
    else:
        print(f"\nStudents with variants ({len(students)}):")
        for s in students:
            print(f"  {s}")
        print()


def cmd_demo(_args):
    """Full end-to-end demo: generate 2 students, grade one."""
    p = Pipeline()

    print("\n── DEMO: Generating 2 student variants ──")
    p.generate_variants(num_students=2)

    students = p.list_students()
    if not students:
        print("No variants generated.")
        return

    student_id = students[0]
    variant = p._load_variant(student_id)

    print(f"\n── DEMO: Auto-grading {student_id} with sample answers ──")
    # Build a mix of correct-ish and wrong answers to show the evaluator
    q1_vals = variant["questions"][0]["injected_values"]
    correct_q1 = (
        q1_vals.get("TASKS_PER_MINUTE", 10)
        * 60
        * q1_vals.get("TIME_WINDOW_HOURS", 3)
    )

    submission = {
        "Q1": f"{correct_q1} tasks",          # correct
        "Q2": "Tool A is cheaper per task",    # vague
        "Q3": "Sequential is much slower",     # no numbers
        "Q4": "15% retrieval rate",            # rough
        "Q5": "The probability is very small", # no computation
    }

    p.grade_submission(student_id, submission)


COMMANDS = {
    "generate": cmd_generate,
    "tutor": cmd_tutor,
    "grade": cmd_grade,
    "list": cmd_list,
    "demo": cmd_demo,
}


def main():
    args = sys.argv[1:]
    if not args or args[0] not in COMMANDS:
        print(__doc__)
        sys.exit(0)
    COMMANDS[args[0]](args[1:])


if __name__ == "__main__":
    main()
