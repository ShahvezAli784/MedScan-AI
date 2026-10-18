"""Shared Streamlit helpers: styling, session handling, cached resources, UI components."""
from __future__ import annotations

import html
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

import config  # noqa: E402
from src.database import db  # noqa: E402
from src.safety import checks  # noqa: E402

C = config.COLORS
STATUS_META = {
    checks.STATUS_OK: ("OK", C["ok"], C["ok_bg"]),
    checks.STATUS_SOON: ("Expiring soon", C["soon"], C["soon_bg"]),
    checks.STATUS_EXPIRED: ("Expired", C["expired"], C["expired_bg"]),
    checks.STATUS_UNKNOWN: ("No expiry date", C["unknown"], C["unknown_bg"]),
}

_CSS = f"""
<style>
.block-container {{ padding-top: 1.4rem; max-width: 1150px; }}
.ms-disclaimer {{ background:#FFF8E1; border-left:5px solid #F5A623; border-radius:8px;
  padding:.6rem 1rem; margin-bottom:1rem; color:#5B4300; font-size:.92rem; }}
.ms-card {{ background:#fff; border:1px solid #E3EAEF; border-radius:14px; padding:1rem 1.2rem;
  box-shadow:0 1px 3px rgba(15,40,60,.06); margin-bottom:.7rem; }}
.ms-card h4 {{ margin:0 0 .25rem 0; color:#12343B; }}
.ms-muted {{ color:#5F6F7A; font-size:.88rem; }}
.ms-chip {{ display:inline-block; padding:.12rem .6rem; border-radius:999px; font-size:.78rem;
  font-weight:600; margin-left:.4rem; }}
.ms-metric {{ background:#fff; border:1px solid #E3EAEF; border-radius:14px; padding:.9rem 1.1rem;
  box-shadow:0 1px 3px rgba(15,40,60,.06); }}
.ms-metric .v {{ font-size:2rem; font-weight:700; line-height:1.1; }}
.ms-metric .l {{ color:#5F6F7A; font-size:.85rem; }}
.ms-title {{ color:{C['primary']}; margin-bottom:0; }}
.ms-alert {{ border-radius:10px; padding:.7rem 1rem; margin:.4rem 0; border-left:5px solid; }}
</style>
"""


# --------------------------------------------------------------------------
# Cached resources
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_db() -> Any:
    """Shared SQLite connection; schema created and seeded on first run."""
    conn = db.connect()
    db.init_db(conn)
    return conn


@st.cache_resource(show_spinner="Loading the OCR model (first run only)...")
def get_ocr_reader() -> Any:
    """EasyOCR reader, loaded once per server process."""
    from src.vision.ocr import load_reader
    return load_reader()


# --------------------------------------------------------------------------
# Session handling
# --------------------------------------------------------------------------
def is_logged_in() -> bool:
    """True when a user is signed in this session."""
    return st.session_state.get("user") is not None


def current_user() -> Optional[dict[str, Any]]:
    """The signed-in user record (without password hash), or None."""
    return st.session_state.get("user")


def login_user(user: dict[str, Any]) -> None:
    """Store the user in the session and reset per-user state."""
    st.session_state.clear()
    st.session_state["user"] = user


def logout() -> None:
    """Clear the session."""
    st.session_state.clear()


def refresh_user() -> None:
    """Reload the signed-in user from the database (e.g. after a profile edit)."""
    user = current_user()
    if user:
        fresh = db.get_user(get_db(), user["id"])
        if fresh:
            st.session_state["user"] = fresh


def require_login() -> dict[str, Any]:
    """Return the signed-in user or stop the page with a friendly message."""
    user = current_user()
    if user is None:
        st.info("Please sign in from the Account page first.")
        st.stop()
    return user


# --------------------------------------------------------------------------
# UI components
# --------------------------------------------------------------------------
def inject_css() -> None:
    """Inject the shared stylesheet."""
    st.markdown(_CSS, unsafe_allow_html=True)


def disclaimer_banner() -> None:
    """Persistent safety disclaimer shown on every page."""
    st.markdown(f'<div class="ms-disclaimer">&#9888;&#65039; <b>{html.escape(config.DISCLAIMER)}</b></div>',
                unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", icon: str = "") -> None:
    """Consistent page title."""
    st.markdown(f'<h2 class="ms-title">{icon} {html.escape(title)}</h2>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<p class="ms-muted">{html.escape(subtitle)}</p>', unsafe_allow_html=True)


def status_chip(status: str) -> str:
    """HTML chip for an expiry status (green OK / amber soon / red expired)."""
    label, fg, bg = STATUS_META.get(status, STATUS_META[checks.STATUS_UNKNOWN])
    return f'<span class="ms-chip" style="color:{fg};background:{bg}">{label}</span>'


def metric_card(label: str, value: Any, color: str = C["primary"]) -> None:
    """A single big-number card."""
    st.markdown(f'<div class="ms-metric"><div class="v" style="color:{color}">{value}</div>'
                f'<div class="l">{html.escape(label)}</div></div>', unsafe_allow_html=True)


def alert_box(text_html: str, status: str) -> None:
    """Colour-coded alert row; ``text_html`` must already be escaped."""
    _, fg, bg = STATUS_META[status]
    st.markdown(f'<div class="ms-alert" style="background:{bg};border-color:{fg}">{text_html}</div>',
                unsafe_allow_html=True)


def item_card(item: dict[str, Any]) -> None:
    """Card for a cabinet item with brand, ingredient, expiry and status chip."""
    from src.utils.common import format_date
    days = item.get("days_left")
    when = "" if days is None else (f" ({-days} days ago)" if days < 0 else f" (in {days} days)")
    st.markdown(
        f'<div class="ms-card"><h4>{html.escape(str(item["brand_name"]))}'
        f'{status_chip(item.get("expiry_status", checks.STATUS_UNKNOWN))}</h4>'
        f'<div class="ms-muted">{html.escape(str(item.get("active_ingredient", "")))} &middot; '
        f'Expiry: {format_date(item.get("expiry_date"))}{when}</div></div>', unsafe_allow_html=True)


def language_select(label: str = "Explanation language", key: str = "lang") -> str:
    """Language selector defaulting to the user's saved preference."""
    user = current_user() or {}
    options = list(config.LANGUAGES)
    default = user.get("language_pref", config.DEFAULT_LANGUAGE)
    index = options.index(default) if default in options else 0
    return st.selectbox(label, options, index=index, key=key)


def ai_disabled_notice() -> None:
    """Message shown in place of AI output when no API key is configured."""
    from src.ai.coach import NO_KEY_MESSAGE
    st.warning(NO_KEY_MESSAGE, icon="\U0001F512")


def sidebar_user() -> None:
    """Signed-in user box with a sign-out button."""
    user = current_user()
    if not user:
        return
    with st.sidebar:
        st.markdown(f"**{html.escape(user['name'])}**  \n<span class='ms-muted'>{html.escape(user['email'])}</span>",
                    unsafe_allow_html=True)
        if st.button("Sign out", width="stretch"):
            logout()
            st.rerun()
