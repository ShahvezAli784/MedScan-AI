"""Profile: display name and language preference."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

import config  # noqa: E402
from src.database import db  # noqa: E402
from streamlit_app import helpers as ui  # noqa: E402

conn = ui.get_db()
user = ui.require_login()
ui.page_header("User Profile", "Update how the app addresses you and your preferred language.", "\u2699\uFE0F")

options = list(config.LANGUAGES)
with st.form("profile_form"):
    st.text_input("Email", value=user["email"], disabled=True)
    name = st.text_input("Name", value=user["name"])
    language = st.selectbox("Language preference", options,
                            index=options.index(user["language_pref"]) if user["language_pref"] in options else 0)
    saved = st.form_submit_button("Save changes", type="primary")
if saved:
    try:
        db.update_user_profile(conn, user["id"], name, language)
        ui.refresh_user()
        st.success("Profile updated.")
    except ValueError as exc:
        st.error(str(exc))
st.caption(f"Member since {user['created_at'][:10]}")
