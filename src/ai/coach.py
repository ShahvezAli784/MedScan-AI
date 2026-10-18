"""Groq-powered grounded explanations and a tool-calling cabinet assistant with safe fallbacks."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import config
from src.ai import prompts
from src.database import db
from src.safety import checks
from src.utils.logging_setup import get_logger

log = get_logger(__name__)

NO_KEY_MESSAGE = (
    "AI features are disabled because GROQ_API_KEY is not set. "
    "Scanning, matching, your cabinet and safety checks still work. "
    "Add a key to a .env file (see .env.example) to enable AI explanations."
)

TOOLS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "get_cabinet",
        "description": "Get the signed-in user's medicine cabinet: medicines with database details and expiry status.",
        "parameters": {"type": "object", "properties": {"user_id": {"type": "integer"}}, "required": ["user_id"]},
    }},
    {"type": "function", "function": {
        "name": "check_duplicates",
        "description": "Find medicines in the user's cabinet that share an active ingredient.",
        "parameters": {"type": "object", "properties": {"user_id": {"type": "integer"}}, "required": ["user_id"]},
    }},
]


@dataclass
class AIResult:
    """Outcome of an AI call; ``ok`` is False when text is an error/disabled message."""

    text: str
    ok: bool = True
    tools_used: list[str] = field(default_factory=list)
    used_fallback: bool = False


def ai_enabled() -> bool:
    """True when a Groq API key is configured."""
    return bool(config.get_groq_api_key())


def get_client() -> Any:
    """Create a Groq client (lazy import so the app works without the SDK or a key)."""
    key = config.get_groq_api_key()
    if not key:
        raise RuntimeError("missing_key")
    from groq import Groq
    return Groq(api_key=key)


def friendly_error(exc: Exception) -> str:
    """Translate SDK/network exceptions into a short user-facing message."""
    if str(exc) == "missing_key":
        return NO_KEY_MESSAGE
    name = type(exc).__name__
    if "RateLimit" in name:
        return "The AI service is rate-limited right now. Please wait a minute and try again."
    if "Authentication" in name or "PermissionDenied" in name:
        return "The Groq API key was rejected. Please check GROQ_API_KEY."
    if "Connection" in name or "Timeout" in name:
        return "Could not reach the AI service. Please check your internet connection and try again."
    return "The AI service returned an error. Please try again in a moment."


def _complete(client: Any, messages: list[dict[str, Any]], tools: Optional[list[dict[str, Any]]] = None) -> Any:
    kwargs: dict[str, Any] = dict(
        model=config.GROQ_MODEL, messages=messages,
        temperature=config.GROQ_TEMPERATURE, max_tokens=config.GROQ_MAX_TOKENS)
    if tools:
        kwargs.update(tools=tools, tool_choice="auto")
    return client.chat.completions.create(**kwargs)


# --------------------------------------------------------------------------
# Grounded explanation
# --------------------------------------------------------------------------
def explain_medicine(record: dict[str, Any], language: str, client: Any = None) -> AIResult:
    """Explain one medicine in the chosen language using ONLY its database record."""
    if client is None and not ai_enabled():
        return AIResult(NO_KEY_MESSAGE, ok=False)
    try:
        client = client or get_client()
        resp = _complete(client, prompts.build_explanation_messages(record, language))
        return AIResult((resp.choices[0].message.content or "").strip())
    except Exception as exc:  # noqa: BLE001
        log.warning("explain_medicine failed: %s", exc)
        return AIResult(friendly_error(exc), ok=False)


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------
def _cabinet_payload(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    items = checks.annotate_items(db.list_cabinet(conn, user_id))
    keep = ("brand_name", "generic_name", "active_ingredient", "strength", "category", "uses",
            "warnings", "expiry_date", "expiry_status", "days_left", "status")
    return [{k: i.get(k) for k in keep} for i in items[:50]]


def make_tool_registry(conn: sqlite3.Connection, session_user_id: int) -> dict[str, Callable[..., dict[str, Any]]]:
    """Build the Python tools the LLM may call. The user id is always the signed-in user's."""

    def get_cabinet(user_id: Optional[int] = None) -> dict[str, Any]:
        """Return the user's cabinet (user_id argument is ignored for safety)."""
        return {"medicines": _cabinet_payload(conn, session_user_id)}

    def check_duplicates(user_id: Optional[int] = None) -> dict[str, Any]:
        """Return groups of active cabinet items sharing an active ingredient."""
        groups = checks.find_duplicate_ingredients(db.list_cabinet(conn, session_user_id))
        return {
            "groups": [{"shared_ingredient": g.ingredient, "products": g.brands} for g in groups],
            "note": config.DUPLICATE_WARNING,
        }

    return {"get_cabinet": get_cabinet, "check_duplicates": check_duplicates}


def run_tool(registry: dict[str, Callable[..., dict[str, Any]]], name: str, arguments: str) -> str:
    """Execute a tool call safely and return a JSON string for the model."""
    func = registry.get(name)
    if func is None:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        json.loads(arguments or "{}")  # validate; contents are intentionally ignored
        return json.dumps(func(), default=str)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


def _fallback_context(conn: sqlite3.Connection, user_id: int) -> str:
    registry = make_tool_registry(conn, user_id)
    return json.dumps({k: f() for k, f in registry.items()}, default=str)


# --------------------------------------------------------------------------
# Assistant
# --------------------------------------------------------------------------
def ask_assistant(
    conn: sqlite3.Connection, user_id: int, history: list[dict[str, str]], question: str,
    language: str = config.DEFAULT_LANGUAGE, client: Any = None,
) -> AIResult:
    """Answer a cabinet question with Groq tool calling; fall back to a plain prompt on failure."""
    refusal = prompts.screen_user_question(question, language)
    if refusal:
        return AIResult(refusal)
    if client is None and not ai_enabled():
        return AIResult(NO_KEY_MESSAGE, ok=False)
    past = [{"role": m["role"], "content": m["content"]} for m in history[-config.CHAT_HISTORY_TURNS * 2:]
            if m.get("role") in ("user", "assistant")]
    try:
        client = client or get_client()
    except Exception as exc:  # noqa: BLE001
        return AIResult(friendly_error(exc), ok=False)

    try:
        return _ask_with_tools(conn, user_id, past, question, language, client)
    except Exception as exc:  # noqa: BLE001
        log.warning("Tool calling failed (%s); falling back to plain prompt", exc)
        if "RateLimit" in type(exc).__name__ or "Authentication" in type(exc).__name__:
            return AIResult(friendly_error(exc), ok=False)
    try:
        system = prompts.build_assistant_system_prompt(language, _fallback_context(conn, user_id))
        messages = [{"role": "system", "content": system}, *past, {"role": "user", "content": question}]
        resp = _complete(client, messages)
        return AIResult((resp.choices[0].message.content or "").strip(), used_fallback=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("Fallback prompt failed: %s", exc)
        return AIResult(friendly_error(exc), ok=False, used_fallback=True)


def _ask_with_tools(
    conn: sqlite3.Connection, user_id: int, past: list[dict[str, str]], question: str,
    language: str, client: Any,
) -> AIResult:
    registry = make_tool_registry(conn, user_id)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompts.build_assistant_system_prompt(language)},
        *past, {"role": "user", "content": question},
    ]
    used: list[str] = []
    for _ in range(config.GROQ_MAX_TOOL_ROUNDS):
        msg = _complete(client, messages, TOOLS).choices[0].message
        calls = getattr(msg, "tool_calls", None)
        if not calls:
            return AIResult((msg.content or "").strip(), tools_used=used)
        messages.append({
            "role": "assistant", "content": msg.content or "",
            "tool_calls": [{"id": c.id, "type": "function",
                            "function": {"name": c.function.name, "arguments": c.function.arguments}}
                           for c in calls],
        })
        for call in calls:
            used.append(call.function.name)
            messages.append({"role": "tool", "tool_call_id": call.id, "name": call.function.name,
                             "content": run_tool(registry, call.function.name, call.function.arguments)})
    final = _complete(client, messages)  # no tools: force a final answer
    return AIResult((final.choices[0].message.content or "").strip(), tools_used=used)
