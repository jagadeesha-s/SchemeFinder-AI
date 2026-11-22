"""Chat box shown directly under the profile section.

Scholarship questions are answered from your scheme database by backend/scholarship_chat.py (no AI guessing).
Any other question goes to the existing Gemini pipeline (orchestrator.handle), exactly like the old chat."""
import streamlit as st

from backend.scholarship_chat import respond
from ui.components import render_card, render_result

STATE_KEY = "profile_chat"
MAX_SHOWN = 12                      # newest messages drawn on the page
SUGGESTIONS = ["List all scholarships", "Which scholarships can I get?", "What documents do I need for NSP?"]


def _ask_gemini(orch, message: str, profile: dict) -> dict:
    try:
        with st.spinner("Searching the scheme database..."):
            return orch.handle(message, profile, "auto", None, None, False, True)
    except Exception as exc:
        return {"error": f"Something went wrong: {exc}"}


def _draw(msg: dict, index: int) -> None:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        elif msg["kind"] == "scholarship":
            reply = msg["reply"]
            st.markdown(reply["text"])
            if reply["show_cards"]:                  # full detail cards when only a few scholarships match
                for j, card in enumerate(reply["cards"]):
                    render_card(card, f"pc{index}_{j}")
        else:
            render_result(msg["result"], f"pcai{index}")


def render_profile_chat(user: dict, profile: dict, orch) -> None:
    ss = st.session_state
    history = ss.setdefault(STATE_KEY, [])

    st.markdown('<div class="section-title">Ask SchemeFinder AI about scholarships and schemes</div>',
                unsafe_allow_html=True)
    with st.container(border=True):
        if profile:
            st.caption("I use your saved profile. You can also type details, e.g. "
                       "'I am a 20 year old SC student from Karnataka, family income 1.5 lakh'.")
        else:
            st.caption("Save your profile above for an exact eligibility check, or type your details in the message.")

        cols = st.columns(len(SUGGESTIONS))
        for col, text in zip(cols, SUGGESTIONS):
            if col.button(text, key=f"pc_chip_{text}"):
                ss["pc_pending"] = text

        history_box = st.container()                 # messages appear above the input box
        prompt = st.chat_input("Ask in simple English, e.g. 'list all scholarships' or 'which scholarship can I get?'",
                               key="pc_input")
        message = prompt or ss.pop("pc_pending", None)
        if message:
            history.append({"role": "user", "content": message})
            reply = respond(message, profile)
            if reply is not None:
                history.append({"role": "assistant", "kind": "scholarship", "reply": reply})
            else:
                history.append({"role": "assistant", "kind": "ai", "result": _ask_gemini(orch, message, profile)})

        with history_box:
            start = max(len(history) - MAX_SHOWN, 0)
            for i, msg in enumerate(history[start:], start=start):
                _draw(msg, i)
        if history and st.button("🧹 Clear chat", key="pc_clear"):
            ss[STATE_KEY] = []
            st.rerun()