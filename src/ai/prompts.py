"""Prompt templates and deterministic guardrails for the grounded medicine assistant."""
from __future__ import annotations

import re
from typing import Any, Optional

import config

Record = dict[str, Any]

SAFETY_RULES = """SAFETY RULES (non-negotiable):
1. Answer ONLY from the DATABASE RECORD(S) or tool results provided. Never use outside medical knowledge.
   If the answer is not in the record, say so plainly and refer the user to the package leaflet, a pharmacist, or a doctor.
2. Never give dosing, frequency, or duration advice. Never diagnose. Never say a medicine "can be taken together with" another.
   Never recommend a treatment. Politely decline these requests and redirect to a pharmacist or doctor.
3. For duplicate active ingredients, only say: "These products may contain the same active ingredient. Check with a pharmacist."
   Do not add dosing or safety verdicts.
4. Be brief, neutral and friendly. This is educational information, not medical advice."""

_DISCLAIMER_LINE = f"End with this exact sentence: {config.DISCLAIMER}"


def language_instruction(language: str) -> str:
    """Return the reply-language instruction for a supported language (English fallback)."""
    return config.LANGUAGES.get(language, config.LANGUAGES[config.DEFAULT_LANGUAGE])


def format_record(record: Record) -> str:
    """Render a medicine database record as plain text for the prompt."""
    fields = [
        ("Brand name", "brand_name"), ("Generic name", "generic_name"),
        ("Active ingredient", "active_ingredient"), ("Strength", "strength"),
        ("Category", "category"), ("Uses", "uses"), ("Warnings", "warnings"), ("Source", "source"),
    ]
    return "\n".join(f"{label}: {record.get(key) or 'not in database'}" for label, key in fields)


def build_explanation_messages(record: Record, language: str) -> list[dict[str, str]]:
    """Messages asking for a simple explanation of one medicine, grounded in its record."""
    system = (
        "You are MediScan AI, an educational assistant that explains medicines in simple words.\n"
        f"{SAFETY_RULES}\n{language_instruction(language)}\n{_DISCLAIMER_LINE}"
    )
    user = (
        "DATABASE RECORD:\n" + format_record(record) + "\n\n"
        "Explain this medicine for a non-expert in 4-6 short sentences: what it is, what it is "
        "generally used for, and the main warnings listed in the record. Mention that the data "
        "comes from a seed database and should be checked against the official leaflet."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_assistant_system_prompt(language: str, cabinet_context: Optional[str] = None) -> str:
    """System prompt for the cabinet chat assistant (tool-calling or plain-prompt fallback)."""
    base = (
        "You are MediScan AI, an educational assistant for the user's personal medicine cabinet.\n"
        "You can call two tools: get_cabinet (the user's medicines with database details and expiry dates) "
        "and check_duplicates (medicines sharing an active ingredient). Call a tool whenever the question "
        "is about the user's cabinet; do not guess its contents.\n"
        f"{SAFETY_RULES}\n{language_instruction(language)}\n{_DISCLAIMER_LINE}"
    )
    if cabinet_context:
        base += "\n\nCABINET DATA (retrieved by the app; the only source you may use):\n" + cabinet_context
    return base


# --------------------------------------------------------------------------
# Deterministic guardrail: blocks dosing / combination / diagnosis questions before any LLM call
# --------------------------------------------------------------------------
_BLOCKED = re.compile(
    r"\b(dose|doses|dosage|dosing|overdose|how (many|much)|how often|how long (should|can)|"
    r"(can|may|could|should) i (take|use|give|mix|combine)|safe to (take|use|combine|mix)|"
    r"(take|use|mix|combine)\b.{0,40}\b(together|along with|at the same time)|"
    r"together with|mix(ed|ing)? with|combine with|diagnos\w*|what do i have|"
    r"prescribe|treat my|cure my|which (medicine|tablet|drug) should i|"
    r"kitni|kitna|khurak|khuraak|ek sath)\b",
    re.I,
)

_REFUSALS = {
    "English": (
        "I can't help with dosing, diagnosis, combining medicines, or treatment choices. "
        "Please ask a pharmacist or doctor, and check the package leaflet. "
        "I can explain what a medicine is generally used for, or review your cabinet's expiry dates."
    ),
    "Urdu": (
        "میں خوراک، تشخیص، دواؤں کو ملا کر لینے یا علاج کے انتخاب میں مدد نہیں کر سکتا۔ "
        "براہِ کرم کسی فارماسسٹ یا ڈاکٹر سے پوچھیں اور دوا کے پرچے کو دیکھیں۔"
    ),
    "Roman Urdu": (
        "Main dose, tashkhees, dawaon ko mila kar lene ya ilaj ke intikhab mein madad nahi kar sakta. "
        "Meherbani karke pharmacist ya doctor se poochein aur dawa ka leaflet dekhein."
    ),
}


def screen_user_question(question: str, language: str = config.DEFAULT_LANGUAGE) -> Optional[str]:
    """Return a refusal message if the question asks for dosing/diagnosis/combination advice, else None."""
    if _BLOCKED.search(question or ""):
        return f"{_REFUSALS.get(language, _REFUSALS['English'])}\n\n{config.DISCLAIMER}"
    return None
