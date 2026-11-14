"""Sign In / Sign Up screens (email + OTP)."""
import streamlit as st

import config
from backend import auth


def _otp_flow(purpose: str) -> None:
    """purpose: 'signup' or 'signin'. Keeps its own step state per purpose."""
    k = purpose
    state = st.session_state.setdefault(f"otp_{k}", {"sent_to": None, "dev_otp": None})

    name = ""
    if purpose == "signup":
        name = st.text_input("Full name", key=f"{k}_name", placeholder="e.g. Ananya Sharma")
    email = st.text_input("Gmail / email address", key=f"{k}_email", placeholder="yourname@gmail.com")

    label = "Send OTP" if not state["sent_to"] else "Resend OTP"
    if st.button(label, key=f"{k}_send", type="primary"):
        ok, msg, dev = auth.request_otp(email, purpose, name)
        if ok:
            state["sent_to"], state["dev_otp"] = email.strip().lower(), dev
            st.success(msg)
        else:
            st.error(msg)

    if state["sent_to"]:
        if state["dev_otp"]:
            st.warning(f"DEMO MODE - your OTP is **{state['dev_otp']}** (set SMTP in .env to send real emails).")
        code = st.text_input("Enter the 6-digit OTP", key=f"{k}_code", max_chars=config.OTP_LENGTH)
        verify_label = "Verify & Sign Up" if purpose == "signup" else "Verify & Sign In"
        if st.button(verify_label, key=f"{k}_verify", type="primary"):
            ok, msg, user = auth.verify_otp(state["sent_to"], code, purpose)
            if ok:
                st.session_state["user"] = user
                st.session_state.pop(f"otp_{k}", None)
                st.rerun()
            else:
                st.error(msg)


def render_auth_page() -> None:
    left, mid, right = st.columns([1, 2, 1])
    with mid:
        st.markdown('<div class="section-title">Welcome - please sign in to continue</div>', unsafe_allow_html=True)
        tab_in, tab_up = st.tabs(["🔐 Sign In", "📝 Sign Up"])
        with tab_in:
            _otp_flow("signin")
        with tab_up:
            _otp_flow("signup")
        st.caption("We use your email only to verify your identity and save your applications.")
