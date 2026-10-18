"""Medicine cabinet table with filters, delete and mark-as-used-up."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import config  # noqa: E402
from src.database import db  # noqa: E402
from src.safety import checks  # noqa: E402
from src.utils.common import format_date  # noqa: E402
from streamlit_app import helpers as ui  # noqa: E402

conn = ui.get_db()
user = ui.require_login()
ui.page_header("My Cabinet", "Everything you have scanned and saved.", "\U0001F5C4\uFE0F")

items = checks.annotate_items(db.list_cabinet(conn, user["id"]))
if not items:
    st.info("Your cabinet is empty. Use **Scan Medicine** to add items.")
    st.stop()

f1, f2, f3, f4 = st.columns(4)
status_f = f1.selectbox("Status", ["Active", "Used up", "All"])
expiry_f = f2.selectbox("Expiry", ["All", "OK", "Expiring soon", "Expired", "No expiry date"])
cat_f = f3.multiselect("Category", sorted({i["category"] for i in items if i["category"]}))
text_f = f4.text_input("Search")

label_to_key = {v[0]: k for k, v in ui.STATUS_META.items()}
view = [i for i in items
        if (status_f == "All" or i["status"] == (config.STATUS_ACTIVE if status_f == "Active" else config.STATUS_USED_UP))
        and (expiry_f == "All" or i["expiry_status"] == label_to_key[expiry_f])
        and (not cat_f or i["category"] in cat_f)
        and (not text_f or text_f.lower() in f"{i['brand_name']} {i['generic_name']} {i['active_ingredient']}".lower())]

if not view:
    st.warning("No items match these filters.")
    st.stop()

df = pd.DataFrame([{
    "ID": i["id"], "Medicine": i["brand_name"], "Active ingredient": i["active_ingredient"],
    "Category": i["category"], "Expiry": format_date(i["expiry_date"]),
    "Expiry status": ui.STATUS_META[i["expiry_status"]][0],
    "Match": f"{i['match_confidence']:.0f}%" if i["match_confidence"] else "manual",
    "Status": "Active" if i["status"] == config.STATUS_ACTIVE else "Used up",
} for i in view])
palette = {ui.STATUS_META[k][0]: (v[1], v[2]) for k, v in ui.STATUS_META.items()}


def colour(value: str) -> str:
    fg, bg = palette.get(value, ("inherit", "transparent"))
    return f"color:{fg};background-color:{bg};font-weight:600"


st.dataframe(df.style.map(colour, subset=["Expiry status"]), hide_index=True, width="stretch")

st.subheader("Manage an item")
labels = {f"#{i['id']} - {i['brand_name']} ({format_date(i['expiry_date'])})": i for i in view}
item = labels[st.selectbox("Select item", list(labels))]
b1, b2, b3 = st.columns(3)
if item["status"] == config.STATUS_ACTIVE:
    if b1.button("Mark as used up", width="stretch"):
        db.set_cabinet_status(conn, user["id"], item["id"], config.STATUS_USED_UP)
        st.rerun()
elif b1.button("Mark as active again", width="stretch"):
    db.set_cabinet_status(conn, user["id"], item["id"], config.STATUS_ACTIVE)
    st.rerun()
confirm = b2.checkbox("Confirm delete")
if b3.button("Delete", type="primary", disabled=not confirm, width="stretch"):
    db.delete_cabinet_item(conn, user["id"], item["id"])
    st.rerun()
