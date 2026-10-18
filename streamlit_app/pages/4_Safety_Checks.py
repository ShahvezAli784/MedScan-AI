"""Safety checks: expired, expiring soon, duplicate active ingredients."""
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

import config  # noqa: E402
from src.database import db  # noqa: E402
from src.safety import checks  # noqa: E402
from src.utils.common import format_date  # noqa: E402
from streamlit_app import helpers as ui  # noqa: E402

conn = ui.get_db()
user = ui.require_login()
ui.page_header("Safety Checks", "Automatic checks across your active medicines.", "\U0001F6E1\uFE0F")

active = checks.annotate_items(db.list_cabinet(conn, user["id"], config.STATUS_ACTIVE))
if not active:
    st.info("Your cabinet has no active medicines yet.")
    st.stop()

expired = checks.expired_items(active)
soon = checks.expiring_within(active)
dupes = checks.find_duplicate_ingredients(active)

st.subheader("\U0001F534 Expired")
if not expired:
    ui.alert_box("No expired medicines found.", checks.STATUS_OK)
for i in checks.annotate_items(expired):
    ui.alert_box(f"<b>{html.escape(i['brand_name'])}</b> expired on {format_date(i['expiry_date'])} "
                 f"({-i['days_left']} days ago). Check the leaflet or ask a pharmacist about disposal.",
                 checks.STATUS_EXPIRED)

st.subheader(f"\U0001F7E0 Expiring within {config.EXPIRY_SOON_DAYS} days")
if not soon:
    ui.alert_box("Nothing expires soon.", checks.STATUS_OK)
for i in checks.annotate_items(soon):
    ui.alert_box(f"<b>{html.escape(i['brand_name'])}</b> expires on {format_date(i['expiry_date'])} "
                 f"(in {i['days_left']} days).", checks.STATUS_SOON)

st.subheader("\U0001F7E1 Shared active ingredients")
if not dupes:
    ui.alert_box("No shared active ingredients found in your cabinet.", checks.STATUS_OK)
for g in dupes:
    ui.alert_box(f"<b>{html.escape(g.ingredient.title())}</b>: {html.escape(', '.join(g.brands))}<br>"
                 f"{html.escape(g.message)}", checks.STATUS_SOON)

unknown = [i for i in active if i["expiry_status"] == checks.STATUS_UNKNOWN]
if unknown:
    st.caption("No expiry date recorded for: " + ", ".join(i["brand_name"] for i in unknown))
