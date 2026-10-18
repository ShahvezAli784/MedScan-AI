"""Central configuration for MediScan AI: paths, thresholds, model names, languages."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR: Path = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

APP_NAME = "MediScan AI"
APP_TAGLINE = "Medicine packaging recognition and safety assistant"

# ---- Paths ---------------------------------------------------------------
DATA_DIR: Path = BASE_DIR / "data"
DB_PATH: Path = Path(os.getenv("MEDISCAN_DB_PATH", str(DATA_DIR / "mediscan.db")))
SEED_CSV_PATH: Path = DATA_DIR / "medicines_seed.csv"
SCHEMA_PATH: Path = BASE_DIR / "src" / "database" / "schema.sql"
SEED_SOURCE = "seed - verify against official leaflet"

# ---- Vision / OCR ----------------------------------------------------------
MAX_IMAGE_SIDE = 1400          # larger images are downscaled to this longest side
MIN_IMAGE_SIDE = 800           # smaller images are upscaled to this longest side
BLANK_IMAGE_STD_THRESHOLD = 6.0  # grayscale std-dev below this = blank image
OCR_LANGUAGES = ["en"]
OCR_MIN_LINE_CONFIDENCE = 0.25  # EasyOCR lines below this are discarded

# ---- Matching / safety thresholds -----------------------------------------
MATCH_CONFIDENCE_THRESHOLD = 80.0  # percent; below this the user must choose manually
TOP_K_MATCHES = 3
EXPIRY_SOON_DAYS = 60

# ---- Auth ------------------------------------------------------------------
PBKDF2_ITERATIONS = 200_000
MIN_PASSWORD_LENGTH = 8
DEMO_EMAIL = "demo@mediscan.local"
DEMO_NAME = "Demo User"

# ---- Cabinet status values -------------------------------------------------
STATUS_ACTIVE = "active"
STATUS_USED_UP = "used_up"

# ---- LLM (Groq) -------------------------------------------------------------
# ---- LLM (Groq) -------------------------------------------------------------
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_TEMPERATURE = 0.2
GROQ_MAX_TOKENS = 700
GROQ_MAX_TOOL_ROUNDS = 3
CHAT_HISTORY_TURNS = 10


def get_groq_api_key() -> str:
    """Return the Groq API key from the environment (empty string if unset)."""
    return os.getenv("GROQ_API_KEY", "").strip()


# ---- Languages -------------------------------------------------------------
LANGUAGES: dict[str, str] = {
    "English": "Reply in simple, clear English.",
    "Urdu": "Reply in simple Urdu written in Urdu (Arabic) script.",
    "Roman Urdu": "Reply in simple Roman Urdu (Urdu written with English letters).",
}
DEFAULT_LANGUAGE = "English"

DISCLAIMER = (
    "Educational information only. Not medical advice. "
    "Always consult a pharmacist or doctor."
)
DUPLICATE_WARNING = (
    "These products may contain the same active ingredient. Check with a pharmacist."
)

# ---- UI colours ------------------------------------------------------------
COLORS = {
    "primary": "#0E7C86",
    "ok": "#1E8E4E",
    "ok_bg": "#E6F5EC",
    "soon": "#B7791F",
    "soon_bg": "#FFF4D6",
    "expired": "#C53030",
    "expired_bg": "#FDE8E8",
    "unknown": "#4A5568",
    "unknown_bg": "#EDF2F7",
}
