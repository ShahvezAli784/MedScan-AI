"""Scan a medicine box/strip: preprocess, OCR, match, confirm, save to the cabinet."""
import hashlib
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import config  # noqa: E402
from src.database import db  # noqa: E402
from src.matching.expiry_parser import parse_expiry  # noqa: E402
from src.matching.fuzzy_match import match_medicine, search_medicines  # noqa: E402
from src.vision import ocr  # noqa: E402
from src.vision.preprocess import ImageQualityError, preprocess_image  # noqa: E402
from streamlit_app import helpers as ui  # noqa: E402

conn = ui.get_db()
user = ui.require_login()
ui.page_header("Scan Medicine", "Upload or capture a photo of a medicine box or strip.", "\U0001F4F7")
medicines = db.list_medicines(conn)
NONE_LABEL = "None of these - search manually"


def run_scan(data: bytes) -> dict[str, Any]:
    """Perceive + reason: preprocess, OCR, parse expiry, fuzzy-match. Never raises."""
    result: dict[str, Any] = {"error": None, "warning": None, "lines": [], "text": "", "matches": [], "expiry": None}
    try:
        prep = preprocess_image(data)
    except ImageQualityError as exc:
        result["error"] = str(exc)
        return result
    result.update(original=prep.original, processed=prep.processed)
    try:
        found = ocr.extract_text(prep.original, prep.processed, ui.get_ocr_reader())
    except ocr.OcrError as exc:
        result["warning"] = f"{exc} You can still search for the medicine manually below."
        return result
    if found.is_empty:
        result["warning"] = ("No text could be read from this image. Try a sharper, well-lit photo of the "
                             "label, or search manually below.")
        return result
    result.update(lines=found.lines, text=found.text, expiry=parse_expiry(found.text))
    result["matches"] = match_medicine([l.text for l in found.lines], medicines)
    return result


tab_upload, tab_camera = st.tabs(["Upload photo", "Use camera"])
with tab_upload:
    uploaded = st.file_uploader("Photo of the medicine box or strip", type=["jpg", "jpeg", "png", "webp"])
with tab_camera:
    captured = st.camera_input("Take a photo of the label")
file = captured or uploaded
if file is None:
    st.info("Add a photo to begin. Make sure the brand name and the EXP date are visible and well lit.")
    st.stop()

data = file.getvalue()
digest = hashlib.sha1(data).hexdigest()
if st.session_state.get("scan_digest") != digest:
    with st.spinner("Reading the packaging..."):
        st.session_state["scan_result"] = run_scan(data)
    st.session_state["scan_digest"] = digest
scan = st.session_state["scan_result"]

if scan["error"]:
    st.error(scan["error"])
    st.stop()

c1, c2 = st.columns(2)
c1.image(scan["original"], caption="Original (resized)", width="stretch")
c2.image(scan["processed"], caption="Preprocessed for OCR", width="stretch")
if scan["warning"]:
    st.warning(scan["warning"])

st.subheader("1. What OCR detected")
if scan["lines"]:
    st.dataframe(pd.DataFrame([{"Text": l.text, "OCR confidence": f"{l.confidence:.0%}", "Image": l.source}
                               for l in scan["lines"]]), hide_index=True, width="stretch")
    with st.expander("Raw OCR text"):
        st.code(scan["text"], language=None)
else:
    st.caption("No text detected.")

st.subheader("2. Confirm the medicine")
matches = scan["matches"]
chosen_id, chosen_score = None, 0.0
if matches:
    if not matches[0].meets_threshold:
        st.warning(f"Match confidence is below {config.MATCH_CONFIDENCE_THRESHOLD:.0f}%. "
                   "Please choose from the top 3 below or search manually.")
    else:
        st.info("Please confirm which medicine this is. Nothing is saved until you do.")
    options = {f"{m.brand_name} ({m.generic_name}) - {m.score:.0f}% match on {m.matched_on}": m for m in matches}
    labels = list(options) + [NONE_LABEL]
    pick = st.radio("Top matches", labels, index=None, key=f"pick_{digest}")
    if pick and pick != NONE_LABEL:
        chosen_id, chosen_score = options[pick].medicine_id, options[pick].score
    manual = pick == NONE_LABEL
else:
    st.warning("No confident match was found. Search the knowledge base manually.")
    manual = True

if manual:
    query = st.text_input("Search by brand or generic name", key=f"q_{digest}")
    hits = search_medicines(query, medicines) if query else []
    if query and not hits:
        st.caption("No medicines found for that search.")
    if hits:
        by_label = {f"{h['brand_name']} ({h['generic_name']})": h for h in hits}
        sel = st.selectbox("Search results", list(by_label), index=None, key=f"sel_{digest}")
        if sel:
            chosen_id, chosen_score = by_label[sel]["id"], 0.0

st.subheader("3. Expiry date")
detected = scan["expiry"]
if detected:
    st.success(f"Detected from text \"{detected.raw}\": **{detected.date.strftime('%d %b %Y')}** (last day of month).")
else:
    st.info("No expiry date detected. Enter it manually if you can see it on the pack.")
modes = (["Use detected date"] if detected else []) + ["Enter manually", "Unknown"]
mode = st.radio("Expiry date", modes, horizontal=True, key=f"exp_mode_{digest}")
expiry_iso = None
if mode == "Use detected date":
    expiry_iso = detected.date.isoformat()
elif mode == "Enter manually":
    expiry_iso = st.date_input("Expiry date", value=date.today() + timedelta(days=365),
                               min_value=date(2000, 1, 1), max_value=date(2099, 12, 31),
                               key=f"exp_{digest}").isoformat()

st.divider()
if chosen_id is None:
    st.caption("Select a medicine above to enable saving.")
if st.button("Save to my cabinet", type="primary", disabled=chosen_id is None):
    try:
        db.add_cabinet_item(conn, user["id"], chosen_id, scan["text"], chosen_score, expiry_iso)
        st.success("Saved to your cabinet. Open **My Cabinet** or **Safety Checks** to review it.")
    except ValueError as exc:
        st.error(str(exc))
