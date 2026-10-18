"""Dashboard: cabinet counts, expiring-soon list, chart and recent scans."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

import config  # noqa: E402
from src.database import db  # noqa: E402
from src.safety import checks  # noqa: E402
from src.utils.common import format_date  # noqa: E402
from streamlit_app import helpers as ui  # noqa: E402

conn = ui.get_db()
user = ui.require_login()
ui.page_header(f"Welcome, {user['name']}", "Your medicine cabinet at a glance.", "\U0001F3E0")

items = checks.annotate_items(db.list_cabinet(conn, user["id"]))
active = [i for i in items if i["status"] == config.STATUS_ACTIVE]
soon = checks.expiring_within(active)
expired = checks.expired_items(active)
dupes = checks.find_duplicate_ingredients(active)

cols = st.columns(4)
with cols[0]: ui.metric_card("Medicines in cabinet", len(active))
with cols[1]: ui.metric_card("Expiring within 60 days", len(soon), config.COLORS["soon"])
with cols[2]: ui.metric_card("Expired", len(expired), config.COLORS["expired"])
with cols[3]: ui.metric_card("Shared-ingredient groups", len(dupes), config.COLORS["primary"])
st.write("")

left, right = st.columns([1, 1])
with left:
    st.subheader("Expiring soon")
    if not soon:
        st.success("Nothing expires in the next 60 days.")
    for item in checks.annotate_items(soon):
        ui.item_card(item)
    if expired:
        st.error(f"{len(expired)} expired item(s). See Safety Checks.")

with right:
    st.subheader("Cabinet breakdown")
    if not active:
        st.info("Your cabinet is empty. Use **Scan Medicine** to add items.")
    else:
        mode = st.radio("Group by", ["Category", "Active ingredient"], horizontal=True)
        if mode == "Category":
            counts = pd.Series([i["category"] or "Other" for i in active]).value_counts()
        else:
            names = [n.title() for i in active for n in set(checks.split_ingredients(i["active_ingredient"]))]
            counts = pd.Series(names).value_counts()
        df = counts.rename_axis("name").reset_index(name="count")
        fig = px.bar(df, x="count", y="name", orientation="h", text="count",
                     color_discrete_sequence=[config.COLORS["primary"]])
        fig.update_layout(height=max(260, 40 * len(df)), margin=dict(l=0, r=10, t=10, b=0),
                          yaxis=dict(autorange="reversed", title=""), xaxis=dict(title="Items", dtick=1),
                          plot_bgcolor="white")
        st.plotly_chart(fig, width="stretch")

st.subheader("Recent scans")
recent = items[:5]
if not recent:
    st.caption("No scans yet.")
else:
    st.dataframe(pd.DataFrame([{
        "Scanned": i["scanned_at"], "Medicine": i["brand_name"],
        "Match confidence": f"{i['match_confidence']:.0f}%" if i["match_confidence"] else "manual",
        "Expiry": format_date(i["expiry_date"]), "Status": ui.STATUS_META[i["expiry_status"]][0],
    } for i in recent]), hide_index=True, width="stretch")
