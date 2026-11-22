
"""Left sidebar navigation for SchemeFinder AI."""

import streamlit as st


NAV_ITEMS = {
    "Home": "🏠",
    "All Schemes": "🏛️",
    "Application Status": "📋",
    "Profile": "👤",
    "Sign Out": "🚪",
}


def _sign_out():
    """Clear login-related session data without deleting saved database records."""

    keys_to_clear = [
        "user",
        "last_result",
        "chat",
        "saved_profile",
        "profile_mode",
        "selected_page",
        "show_n",
    ]

    for key in keys_to_clear:
        st.session_state.pop(key, None)

    # Clear profile form widget values.
    for key in list(st.session_state.keys()):
        if key.startswith("pf_"):
            st.session_state.pop(key, None)

    st.rerun()


def render_sidebar(user=None):
    """
    Render the left navigation menu.

    Signed-in users:
        Home, All Schemes, Application Status, Profile, Sign Out

    Guests:
        Home, All Schemes
    """

    signed_in = bool(user)

    with st.sidebar:
        st.markdown(
            """
            <div class="sf-sidebar-brand">
                <div class="sf-sidebar-logo">🏛️</div>
                <div class="sf-sidebar-title">SchemeFinder AI</div>
                <div class="sf-sidebar-subtitle">
                    Government Scheme Navigator
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.divider()

        if signed_in:
            st.markdown(
                f"**Welcome, {user.get('name', 'User')}**"
            )
            st.caption(user.get("email", ""))

        st.markdown("#### Navigation")

        if signed_in:
            available_items = list(NAV_ITEMS.keys())
        else:
            available_items = ["Home", "All Schemes"]

        previous_page = st.session_state.get(
            "selected_page", "Home"
        )

        if previous_page not in available_items:
            previous_page = "Home"

        selected_page = st.radio(
            "Main navigation",
            options=available_items,
            index=available_items.index(previous_page),
            format_func=lambda item: (
                f"{NAV_ITEMS[item]}  {item}"
            ),
            label_visibility="collapsed",
            key="sf_navigation",
        )

        st.session_state["selected_page"] = selected_page

        if selected_page == "Sign Out":
            _sign_out()

        st.divider()

        if signed_in:
            st.caption("Your account and saved information are protected.")

        st.caption(
            "SchemeFinder AI provides information about "
            "government schemes. Verify details on official portals."
        )

    return selected_page
