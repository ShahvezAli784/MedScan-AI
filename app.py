"""MediScan AI - entry point for Hugging Face Spaces (Docker) and local runs.

Run with:  streamlit run app.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

import config  # noqa: E402
from streamlit_app import helpers as ui  # noqa: E402

st.set_page_config(page_title=config.APP_NAME, page_icon="\U0001F48A", layout="wide")
ui.inject_css()
ui.get_db()  # create schema, seed medicines, ensure demo user

account = st.Page("streamlit_app/Account.py", title="Account", icon="\U0001F464", url_path="account",
                  default=not ui.is_logged_in())
if ui.is_logged_in():
    pages = [
        st.Page("streamlit_app/Home.py", title="Home", icon="\U0001F3E0", url_path="home", default=True),
        st.Page("streamlit_app/pages/1_Scan_Medicine.py", title="Scan Medicine", icon="\U0001F4F7", url_path="scan"),
        st.Page("streamlit_app/pages/2_Medicine_Info.py", title="Medicine Info", icon="\U0001F50E", url_path="info"),
        st.Page("streamlit_app/pages/3_My_Cabinet.py", title="My Cabinet", icon="\U0001F5C4\uFE0F", url_path="cabinet"),
        st.Page("streamlit_app/pages/4_Safety_Checks.py", title="Safety Checks", icon="\U0001F6E1\uFE0F", url_path="safety"),
        st.Page("streamlit_app/pages/5_Ask_Assistant.py", title="Ask Assistant", icon="\U0001F4AC", url_path="assistant"),
        st.Page("streamlit_app/pages/6_User_Profile.py", title="User Profile", icon="\u2699\uFE0F", url_path="profile"),
        account,
    ]
    ui.sidebar_user()
else:
    pages = [account]

page = st.navigation(pages)
ui.disclaimer_banner()
page.run()
