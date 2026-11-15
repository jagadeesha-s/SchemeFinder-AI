"""Streamlit frontend for SchemeFinder AI.  Run:  streamlit run app.py"""
import streamlit as st

import config
import db_config
from backend import auth
from backend.ingestion import index_summary, ingest_directory
from backend.orchestrator import SchemeFinderOrchestrator
from backend.profile import profile_completion
from ui.auth_page import render_auth_page
from ui.components import render_result
from ui.profile_form import ensure_loaded, render_profile_section
from ui.styles import CSS, HEADER_HTML, NOTICE_HTML

st.set_page_config(page_title="SchemeFinder AI", page_icon="🏛️", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
st.markdown("<style>.stButton > button {width: 100%;}</style>", unsafe_allow_html=True)
st.markdown(HEADER_HTML, unsafe_allow_html=True)

CATEGORY_ICONS = {
    "Education": "🎓", "Agriculture": "🌾", "Healthcare": "🏥", "Housing": "🏠",
    "Women & Child": "👩‍👧", "Employment": "🛠️", "SC/ST/OBC Welfare": "🤝", "Business": "💼",
}
LEVEL_OPTIONS = {"All schemes": None, "Central schemes": "Central", "State / UT schemes": "State/UT"}


@st.cache_resource(show_spinner="Loading models and preparing the scheme index (first run only)...")
def get_orchestrator() -> SchemeFinderOrchestrator:
    orch = SchemeFinderOrchestrator()
    if orch.store.count() == 0:          # e.g. first start on Streamlit Community Cloud
        ingest_directory(orch.store)
    return orch


def run_query(orch, query, profile, mode, category, level, hide_ineligible, relevant_only) -> dict:
    try:
        with st.spinner("Checking schemes..."):
            return orch.handle(query, profile, mode, category, level, hide_ineligible, relevant_only)
    except Exception as exc:
        return {"error": f"Something went wrong: {exc}"}


def run_ingestion(orch, rebuild: bool) -> None:
    bar = st.progress(0.0, text="Starting...")

    def update(done, total, message):
        bar.progress(min(done / max(total, 1), 1.0), text=message[:80])

    stats = ingest_directory(orch.store, reset=rebuild, progress=update)
    bar.empty()
    st.success(f"{stats['unique_schemes']} unique schemes · {stats['chunks']} chunks "
               f"(added {stats['added']}, updated {stats['updated']}, unchanged {stats['unchanged']}, "
               f"removed {stats['removed']})")
    for msg in stats["errors"]:
        st.error(msg)
    if stats["warnings"]:
        with st.expander(f"{len(stats['warnings'])} warning(s)"):
            for msg in stats["warnings"]:
                st.write("• " + msg)


# ------------------------------------------------------------ login gate
if "user" not in st.session_state:
    st.markdown(NOTICE_HTML, unsafe_allow_html=True)
    render_auth_page()
    st.stop()

user = st.session_state["user"]
orch = get_orchestrator()
ensure_loaded(user)

# ----------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown(f"**👋 Welcome, {user['name']}**")
    st.caption(user["email"])
    if st.button("Sign out"):
        for key in [k for k in st.session_state if k.startswith("pf_")] + [
                "user", "last_result", "chat", "saved_profile", "profile_mode"]:
            st.session_state.pop(key, None)
        st.rerun()
    st.caption(f"Profile completion: **{profile_completion(st.session_state['saved_profile'])['percent']}%**")

    st.divider()
    st.markdown("#### 📂 My Applications")
    apps = auth.list_applications(user["email"])
    if not apps:
        st.caption("Nothing saved yet. Open a scheme and press **Save to My Applications**.")
    for i, a in enumerate(apps):
        st.markdown(f"**{a['scheme_name']}**")
        st.caption(a["status"])
        c1, c2 = st.columns(2)
        if a["official_url"]:
            c1.link_button("Portal", a["official_url"])
        if "Applied" not in a["status"] and c2.button("I applied", key=f"applied_{i}"):
            auth.save_application(user["email"], a["scheme_name"], a["official_url"], "Applied (self-reported)")
            st.rerun()
    if apps:
        st.caption("Status is self-reported. Check the official portal for the real status.")

    st.divider()
    summary = index_summary()
    st.caption(f"📚 Unique schemes: **{summary['schemes']}** · Indexed chunks: **{orch.store.count()}**")
    if st.button("🔄 Update index (fast)"):
        run_ingestion(orch, rebuild=False)
    with st.expander("Advanced"):
        if st.button("Full rebuild"):
            run_ingestion(orch, rebuild=True)

# -------------------------------------------------------------------- main
st.markdown(NOTICE_HTML, unsafe_allow_html=True)

# ---- My Profile (saved in session state + the user's account; never erased by the filters below)
profile, find_clicked = render_profile_section(user)

st.markdown('<div class="section-title">Browse by category</div>', unsafe_allow_html=True)
cat_options = ["All categories"] + db_config.CATEGORIES
chosen = st.radio(
    "category", cat_options, horizontal=True, label_visibility="collapsed",
    format_func=lambda c: c if c == "All categories" else f"{CATEGORY_ICONS.get(c, '')} {c}",
)
category_filter = None if chosen == "All categories" else chosen

f1, f2, f3 = st.columns(3)
level_label = f1.selectbox("Central or State scheme", list(LEVEL_OPTIONS))
level_filter = LEVEL_OPTIONS[level_label]
relevant_only = f2.checkbox("Show only schemes relevant to my profile", value=True)
hide_ineligible = f3.checkbox("Hide schemes I am not eligible for", value=False)
if not profile:
    st.info("Save your profile above to get personalised results. Until then, every scheme is listed without an eligibility check.")

st.markdown('<div class="section-title">Describe your situation (optional)</div>', unsafe_allow_html=True)
situation = st.text_area(
    "situation", label_visibility="collapsed", height=100,
    placeholder="Leave this empty and press a button to list schemes instantly using your saved profile and the "
                "filters above, or type e.g. 'Am I eligible for a scholarship? I am in my 3rd year of engineering.'",
)

c1, c2, c3 = st.columns(3)
mode = None
if c1.button("🔍 Discover Schemes"):
    mode = "discover"
if c2.button("✅ Check Eligibility"):
    mode = "eligibility"
if c3.button("📝 Apply Application", type="primary"):
    mode = "application"
if find_clicked:                      # "Find My Schemes" in the profile section
    mode = "discover"
    st.toast("Results are shown below the filters.", icon="🔎")

if mode:
    st.session_state["show_n"] = db_config.CARDS_PER_PAGE
    st.session_state["last_result"] = run_query(orch, situation, profile, mode, category_filter,
                                                 level_filter, hide_ineligible, relevant_only)
if "last_result" in st.session_state:
    render_result(st.session_state["last_result"], "main",
                  st.session_state.get("show_n", db_config.CARDS_PER_PAGE), filters=True)

# -------------------------------------------------------------------- chat
st.divider()
st.markdown('<div class="section-title">Chat with SchemeFinder AI</div>', unsafe_allow_html=True)
st.session_state.setdefault("chat", [])

prompt = st.chat_input("Ask anything, e.g. 'Am I eligible for PM-KISAN?'")
if prompt:
    st.session_state["chat"].append({"role": "user", "content": prompt})
    result = run_query(orch, prompt, profile, "auto", category_filter, level_filter, hide_ineligible, relevant_only)
    st.session_state["chat"].append({"role": "assistant", "result": result})

for i, msg in enumerate(st.session_state["chat"]):
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            render_result(msg["result"], f"chat{i}")

st.markdown('<div class="footer-note">SchemeFinder AI is an independent information tool. '
            'Official information is available only on government portals.</div>', unsafe_allow_html=True)