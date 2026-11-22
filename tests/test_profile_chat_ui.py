"""Screen test for the chat box (no API key / ChromaDB needed; the Gemini call is replaced by a stub).
Run from the project root:   python -m tests.test_profile_chat_ui        (needs: pip install streamlit)
Uses a temporary database - your real data/users.db is never touched."""
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

tmp = Path(tempfile.mkdtemp())
config.USERS_DB = tmp / "users.db"
config.CHROMA_DIR = tmp / "chroma"

import db_config  # noqa: E402

db_config.MANIFEST_FILE = tmp / "chroma" / "ingest_manifest.json"


class FakeStore:                                   # stands in for ChromaDB
    def __init__(self):
        self.docs, self.version = {}, 0

    def add_documents(self, docs, ids):
        self.docs.update(dict(zip(ids, docs)))

    def delete(self, ids):
        [self.docs.pop(i, None) for i in ids]

    def reset(self):
        self.docs = {}

    def count(self):
        return len(self.docs)

    @staticmethod
    def make_filter(**kwargs):
        return None

    def search(self, *args, **kwargs):
        return []


def _no_gemini(*args, **kwargs):
    raise RuntimeError("Gemini is switched off in this test")


sys.modules["backend.vector_store"] = types.SimpleNamespace(SchemeVectorStore=FakeStore)
sys.modules["backend.llm"] = types.SimpleNamespace(invoke_json=_no_gemini)

from streamlit.testing.v1 import AppTest  # noqa: E402

PROFILE = {"age": 20, "state": "Karnataka", "category": "SC", "annual_income": 150000, "occupation": "Student",
           "gender": "Male", "education": "12th pass", "studying": "Yes"}


def new_app():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    at.session_state["user"] = {"email": "t@example.com", "name": "Test User"}
    at.session_state["saved_profile"] = dict(PROFILE)
    at.session_state["profile_mode"] = "view"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def chat_text(at):
    return " ".join(m.value for chat in at.chat_message for m in chat.markdown)


at = new_app()
assert len(at.chat_input) == 1, "exactly one chat box"
assert any("Ask SchemeFinder AI" in m.value for m in at.markdown)
print("1. chat box is on the page (one input)")

at.chat_input(key="pc_input").set_value("list all scholarships").run()
assert not at.exception, [e.value for e in at.exception]
text = chat_text(at)
assert "all 5 scholarships" in text and "National Scholarship Portal" in text
print("2. 'list all scholarships' lists them")

at.chat_input(key="pc_input").set_value("Which scholarships can I get?").run()
assert not at.exception, [e.value for e in at.exception]
assert "may suit you" in chat_text(at) and "Karnataka" in chat_text(at)
print("3. personalised answer uses the saved profile")

at.chat_input(key="pc_input").set_value("what documents are needed for NSP").run()
assert [b for b in at.button if b.label.startswith("💾")] or "Required documents" in chat_text(at)
print("4. named scholarship answer + detail card ok")

at.chat_input(key="pc_input").set_value("Am I eligible for PM-KISAN?").run()
assert not at.exception, [e.value for e in at.exception]
assert any("Gemini is switched off" in e.value for e in at.error)          # went to the Gemini pipeline
print("5. other questions go to the Gemini assistant")

[b for b in at.button if b.label == "🧹 Clear chat"][0].click().run()
assert at.session_state["profile_chat"] == []
[b for b in at.button if b.label == "List all scholarships"][0].click().run()
assert "all 5 scholarships" in chat_text(at)
assert at.session_state["saved_profile"]["state"] == "Karnataka"            # the profile is untouched
print("6. suggestion buttons + clear chat ok")
print("ALL CHAT SCREEN TESTS PASSED")