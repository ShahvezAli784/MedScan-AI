"""Search the knowledge base and show a grounded AI explanation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

import config  # noqa: E402
from src.ai import coach  # noqa: E402
from src.database import db  # noqa: E402
from src.matching.fuzzy_match import search_medicines  # noqa: E402
from streamlit_app import helpers as ui  # noqa: E402

conn = ui.get_db()
ui.require_login()
ui.page_header("Medicine Info", "Search the knowledge base for general information.", "\U0001F50E")
medicines = db.list_medicines(conn)

query = st.text_input("Search by brand, generic name or active ingredient", placeholder="e.g. Panadol, ibuprofen")
results = search_medicines(query, medicines, limit=15) if query else medicines
if not results:
    st.warning("No medicines found. Try another spelling or a generic name.")
    st.stop()

by_label = {f"{m['brand_name']} ({m['generic_name']})": m for m in results}
label = st.selectbox("Medicine", list(by_label))
med = by_label[label]

st.markdown(
    f'<div class="ms-card"><h4>{med["brand_name"]}</h4>'
    f'<div class="ms-muted">{med["category"]} &middot; {med["strength"]}</div><br>'
    f'<b>Generic name:</b> {med["generic_name"]}<br><b>Active ingredient:</b> {med["active_ingredient"]}<br><br>'
    f'<b>Uses:</b> {med["uses"]}<br><br><b>Warnings:</b> {med["warnings"]}<br><br>'
    f'<span class="ms-muted">Source: {med["source"]}</span></div>', unsafe_allow_html=True)

st.subheader("AI explanation")
if not coach.ai_enabled():
    ui.ai_disabled_notice()
    st.stop()
language = ui.language_select()
cache = st.session_state.setdefault("explanations", {})
key = (med["id"], language)
if st.button("Explain this medicine", type="primary"):
    with st.spinner("Asking the assistant..."):
        cache[key] = coach.explain_medicine(med, language)
if key in cache:
    result = cache[key]
    (st.markdown if result.ok else st.error)(result.text)
    if result.ok:
        st.caption("Generated only from the database record shown above. Verify against the official leaflet.")
