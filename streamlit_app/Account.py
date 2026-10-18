"""Login, registration and demo access."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

import config  # noqa: E402
from src.database import db  # noqa: E402
from streamlit_app import helpers as ui  # noqa: E402

conn = ui.get_db()
ui.page_header(config.APP_NAME, config.APP_TAGLINE, "\U0001F48A")

if ui.is_logged_in():
    user = ui.current_user()
    st.success(f"You are signed in as **{user['name']}** ({user['email']}).")
    if st.button("Sign out"):
        ui.logout()
        st.rerun()
    st.stop()

st.markdown("Scan a medicine box, build your **medicine cabinet**, and get expiry and duplicate-ingredient alerts.")
login_tab, register_tab = st.tabs(["Sign in", "Create account"])

with login_tab:
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")
    if submitted:
        user = db.authenticate(conn, email, password)
        if user:
            ui.login_user(user)
            st.rerun()
        st.error("Incorrect email or password.")

with register_tab:
    with st.form("register_form"):
        name = st.text_input("Name")
        email_r = st.text_input("Email", key="reg_email")
        password_r = st.text_input(f"Password (min {config.MIN_PASSWORD_LENGTH} characters)", type="password", key="reg_pw")
        confirm = st.text_input("Confirm password", type="password")
        language = st.selectbox("Preferred language", list(config.LANGUAGES))
        created = st.form_submit_button("Create account", type="primary")
    if created:
        if password_r != confirm:
            st.error("Passwords do not match.")
        else:
            try:
                uid = db.create_user(conn, name, email_r, password_r, language)
                ui.login_user(db.get_user(conn, uid))
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

st.divider()
if st.button("Continue as Demo User", width="stretch"):
    ui.login_user(db.ensure_demo_user(conn))
    st.rerun()
st.caption("The demo account comes with a small sample cabinet so you can try every feature.")
