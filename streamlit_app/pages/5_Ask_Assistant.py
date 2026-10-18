"""Chat with the grounded, tool-calling cabinet assistant."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from src.ai import coach  # noqa: E402
from streamlit_app import helpers as ui  # noqa: E402

conn = ui.get_db()
user = ui.require_login()
ui.page_header("Ask Assistant", "Ask about your cabinet. Answers come only from the database and your cabinet data.", "\U0001F4AC")

enabled = coach.ai_enabled()
if not enabled:
    ui.ai_disabled_notice()
language = ui.language_select("Reply language", key="assistant_lang")
history: list[dict] = st.session_state.setdefault("chat", [])

QUICK = ["What is in my cabinet?", "What is expiring soon?", "Do I have duplicate ingredients?",
         "Explain my medicines in simple words"]
cols = st.columns(len(QUICK))
quick = next((q for col, q in zip(cols, QUICK) if col.button(q, disabled=not enabled, width="stretch")), None)
if history and st.button("Clear conversation"):
    history.clear()
    st.rerun()

for msg in history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("tools"):
            st.caption("Tools used: " + ", ".join(msg["tools"]))

question = st.chat_input("Ask about your cabinet...", disabled=not enabled) or quick
if question:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            result = coach.ask_assistant(conn, user["id"], history, question, language)
        (st.markdown if result.ok else st.error)(result.text)
        if result.tools_used:
            st.caption("Tools used: " + ", ".join(dict.fromkeys(result.tools_used)))
        if result.used_fallback:
            st.caption("Tool calling was unavailable; answered from a plain prompt.")
    history.append({"role": "user", "content": question})
    if result.ok:
        history.append({"role": "assistant", "content": result.text, "tools": list(dict.fromkeys(result.tools_used))})
