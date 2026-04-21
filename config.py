"""Central configuration for the Tutor-Agent pipeline."""

import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
MASTER_ASSIGNMENT_PATH = BASE_DIR / "master_assignment.json"
VARIANTS_DIR = BASE_DIR / "student_variants"
VARIANTS_DIR.mkdir(exist_ok=True)

# ── Models ────────────────────────────────────────────────────────────────────
# Heavy reasoning tasks → Opus with adaptive thinking
ARCHITECT_MODEL = "claude-opus-4-6"
VARIATION_MODEL = "claude-opus-4-6"
# Validator only checks math → cheaper model is fine
VALIDATOR_MODEL = "claude-haiku-4-5"
# Student-facing → Opus for best tutoring quality
TUTOR_MODEL = "claude-opus-4-6"
EVALUATOR_MODEL = "claude-opus-4-6"

# ── Pipeline settings ─────────────────────────────────────────────────────────
NUM_VARIANTS = 10
MAX_VALIDATION_RETRIES = 3

# ── Scenario themes pool (Variation Agent draws from these) ───────────────────
SCENARIO_THEMES = [
    "Hospital Emergency Triage",
    "Space Exploration Data Processing",
    "Retail Inventory Management",
    "Financial Fraud Detection",
    "Autonomous Vehicle Navigation",
    "News Summarization Pipeline",
    "E-Commerce Order Fulfillment",
    "Legal Document Review",
    "Academic Research Assistant",
    "Supply Chain Optimization",
    "Customer Support Automation",
    "Climate Data Analysis",
]
