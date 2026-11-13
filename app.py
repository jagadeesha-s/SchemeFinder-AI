"""Streamlit frontend for SchemeFinder AI.  Run:  streamlit run app.py"""
import streamlit as st

import config
from backend.ingestion import ingest_directory
from backend.orchestrator import SchemeFinderOrchestrator

st.set_page_config( page_icon="🏛️", 
    page_title="SchemeFinder AI | Government Scheme Finder India",layout="wide")
st.title("SchemeFinder AI")
st.header("Find Government Schemes Across India")

st.write(
    "Discover Central and State Government schemes, "
    "check eligibility, find scholarships and get "
    "guidance on how to apply."
)
st.markdown(
    """
<style>
.hero {background: linear-gradient(135deg,#FF9933 0%,#ffffff 50%,#138808 100%);
       padding: 1.6rem 2rem; border-radius: 16px; margin-bottom: 1rem;}
.hero h1 {color:#0b2a6f; margin:0; font-size:2.2rem;}
.hero p {color:#1f2937; margin:.4rem 0 0 0; font-size:1.05rem;}
.badge {display:inline-block; padding:.2rem .7rem; border-radius:999px; color:#fff;
        font-weight:600; font-size:.85rem;}
</style>
""",
    unsafe_allow_html=True,
)

INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
    "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan",
    "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]
STATUS_STYLE = {
    "eligible": ("✅ Eligible", "#16a34a"),
    "potentially_eligible": ("🟡 Potentially eligible", "#d97706"),
    "ineligible": ("❌ Not eligible", "#dc2626"),
}


@st.cache_resource(show_spinner="Loading embedding model and document index...")
def get_orchestrator() -> SchemeFinderOrchestrator:
    return SchemeFinderOrchestrator()


# ------------------------------------------------------------------ helpers
def source_line(src: dict) -> str:
    label = src["file"] + (f", page {src['page']}" if src.get("page") else "")
    if src.get("official_url"):
        return f"[{label}]({src['official_url']})"
    return label


def render_card(card: dict) -> None:
    label, color = STATUS_STYLE[card["status"]]
    with st.container(border=True):
        st.markdown(f"### {card['scheme_name']}")
        st.markdown(f'<span class="badge" style="background:{color}">{label}</span>', unsafe_allow_html=True)
        st.caption("🏢 " + (card.get("department") or "Department not stated in the source documents"))
        if card.get("description"):
            st.write(card["description"])
        if card.get("explanation"):
            st.info(card["explanation"])

        if card["eligibility_criteria"]:
            st.markdown("**Eligibility criteria**")
            st.markdown("\n".join(f"- {c}" for c in card["eligibility_criteria"]))
        if card["reasons"]:
            st.markdown("**Why this status**")
            st.markdown("\n".join(f"- {r}" for r in card["reasons"]))
        if card["missing_information"]:
            st.warning("Information needed: " + "; ".join(card["missing_information"]))

        app = card.get("application")
        if app:
            st.markdown("**Required documents**")
            docs = app["required_documents"]
            st.markdown("\n".join(f"- {d}" for d in docs) if docs else "_Not stated in the indexed documents._")
            st.markdown("**Application steps**")
            steps = app["application_steps"]
            st.markdown("\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)) if steps
                        else "_Not stated in the indexed documents._")
            st.markdown("**Deadline:** " + (app["deadline"] or "Not verified in the indexed documents"))
            if app.get("official_link"):
                st.markdown(f"**Official application portal:** {app['official_link']}")
            else:
                st.markdown("**Official application portal:** _not found in the indexed documents_")
            if app.get("notes"):
                st.caption(app["notes"])
        else:
            st.caption("Click **Application Guidance** for documents, steps and the application portal.")

        st.markdown("**Sources:** " + " · ".join(source_line(s) for s in card["sources"]))


def render_result(result: dict) -> None:
    if result.get("error"):
        st.error(result["error"])
        return
    if result["message"]:
        st.markdown(result["message"])
    for card in result["cards"]:
        render_card(card)
    if not result["cards"] and result["sources"]:
        st.markdown("**Sources:** " + " · ".join(source_line(s) for s in result["sources"]))
    if result["follow_up_questions"]:
        st.markdown("**To give you a more accurate answer, please tell me:**")
        st.markdown("\n".join(f"- {q}" for q in result["follow_up_questions"]))
    st.caption(result["disclaimer"])


def run_query(orch: SchemeFinderOrchestrator, query: str, profile: dict, mode: str) -> dict:
    try:
        with st.spinner("Agents are reading the official documents..."):
            return orch.handle(query, profile, mode)
    except Exception as exc:
        return {"error": f"Something went wrong: {exc}"}


# ------------------------------------------------------------------ header
st.markdown(
    """
<div class="hero"><h1>🏛️ SchemeFinder AI</h1>
<p>Describe your situation in plain English. Five AI agents search official government documents to
find schemes, check your eligibility and explain how to apply - always with sources.</p></div>
""",
    unsafe_allow_html=True,
)

if not config.GEMINI_API_KEY:
   st.error("GEMINI_API_KEY is missing. Please check your .env file.")
   st.stop()

orch = get_orchestrator()

# ----------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("👤 Your Profile")
    age = st.number_input("Age", min_value=0, max_value=120, value=None, step=1, placeholder="e.g. 28")
    state = st.selectbox("State / UT", ["Select..."] + INDIAN_STATES)
    income = st.number_input("Annual family income (₹)", min_value=0, value=None, step=10000,
                             placeholder="e.g. 250000")
    category = st.selectbox("Category", ["Select...", "General", "OBC", "SC", "ST", "EWS", "Other"])
    gender = st.selectbox("Gender (optional)", ["Select...", "Female", "Male", "Other"])
    education = st.selectbox(
        "Highest education",
        ["Select...", "Below 10th", "10th pass", "12th pass", "Diploma / ITI", "Graduate",
         "Post-graduate", "Doctorate"],
    )
    occupation = st.text_input("Occupation", placeholder="e.g. Farmer, Student, Weaver")

    st.divider()
    st.caption(f"📚 Indexed chunks: **{orch.store.count()}**")
    if st.button("🔄 Re-index documents"):
        with st.spinner("Reading PDFs and building the ChromaDB index..."):
            stats = ingest_directory(orch.store, reset=True)
        st.success(f"Indexed {stats['files']} file(s), {stats['chunks']} chunks.")
        for skipped in stats["skipped"]:
            st.warning("Skipped: " + skipped)

profile = {
    "age": age, "state": state, "annual_income": income, "category": category,
    "gender": gender, "education": education, "occupation": occupation,
}

# -------------------------------------------------------------------- main
st.subheader("📝 Describe your situation")
situation = st.text_area(
    "situation", label_visibility="collapsed", height=110,
    placeholder="e.g. I am a 45-year-old farmer from Bihar with 1.5 acres of land and a family income of "
                "₹1.8 lakh. Which schemes can I get?",
)

c1, c2, c3 = st.columns(3)
mode = None
if c1.button("🔍 Discover Schemes"):
    mode = "discover"
if c2.button("✅ Check Eligibility"):
    mode = "eligibility"
if c3.button("📋 Apply Application"):
    mode = "application"

if mode:
    st.session_state["last_result"] = run_query(orch, situation, profile, mode)
if "last_result" in st.session_state:
    render_result(st.session_state["last_result"])

# -------------------------------------------------------------------- chat
st.divider()
st.subheader("💬 Chat with SchemeFinder AI")
st.session_state.setdefault("chat", [])

prompt = st.chat_input("Ask anything, e.g. 'Am I eligible for PM-KISAN? I am a 40 year old farmer.'")
if prompt:
    st.session_state["chat"].append({"role": "user", "content": prompt})
    result = run_query(orch, prompt, profile, "auto")
    st.session_state["chat"].append({"role": "assistant", "result": result})

for msg in st.session_state["chat"]:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            render_result(msg["result"])
