"""Tests for the scholarship chat. Run from the project root:   python -m tests.test_scholarship_chat
No API key and no ChromaDB needed."""
from backend.scholarship_chat import extract_details, respond, scholarship_records

STUDENT = {"age": 20, "state": "Karnataka", "category": "SC", "annual_income": 150000,
           "occupation": "Student", "gender": "Male", "education": "12th pass"}


def names(reply):
    return reply["text"]


# 1. scholarships are detected by NAME (a skills scheme with a 'stipend' is not a scholarship)
recs = scholarship_records()
ids = {r["id"] for r in recs}
assert "pm-vishwakarma" not in ids and "pm-kisan" not in ids
assert {"nsp", "csss"} <= ids, ids
print("1. scholarship records:", sorted(ids))

# 2. 'list all' lists every scholarship, with or without a profile
for saved in ({}, STUDENT):
    reply = respond("list all scholarship", saved)
    assert reply["kind"] == "list" and f"all {len(recs)} scholarships" in reply["text"], reply["text"][:120]
    assert all(r["scheme_name"] in reply["text"] for r in recs)
print("2. 'list all' ok")

# 3. personal answers use the profile: state-specific scholarships of another state are hidden
reply = respond("Which scholarships can I get?", {**STUDENT, "state": "Bihar"})
assert "State Scholarship Portal (SSP), Karnataka" not in reply["text"].split("hidden")[0]
assert "hidden" in reply["text"]
reply = respond("Which scholarships can I get?", STUDENT)
assert "State Scholarship Portal (SSP), Karnataka" in reply["text"]
assert "Special Scholarship Scheme (PM-USP)" not in reply["text"].split("hidden")[0]       # J&K only
reply = respond("show all scholarships including not eligible", {**STUDENT, "state": "Bihar"})
assert "Not eligible" in reply["text"]
print("3. profile-based filtering ok")

# 4. not a student -> not eligible for student scholarships; working student still counts
farmer = {"age": 45, "state": "Bihar", "category": "General", "occupation": "Farmer", "annual_income": 180000}
reply = respond("any scholarship for me?", farmer)
assert "may suit you" not in reply["text"] or "none of them" in reply["text"] or reply["cards"] == [] or \
    all(c["status"] != "eligible" for c in reply["cards"])
worker = {"age": 24, "state": "Bihar", "occupation": "Private employee", "studying": "Yes", "education": "Graduate"}
reply = respond("scholarships for me", worker)
assert any(c["status"] != "ineligible" for c in reply["cards"]), "a working student must not be rejected as non-student"
print("4. occupation / studying rules ok")

# 5. details typed in simple English are understood (and typos tolerated)
d = extract_details("I am a 20 year old SC girl from Karnataka, family income 1.5 lakh, student")
assert d["age"] == 20 and d["state"] == "Karnataka" and d["category"] == "SC" and d["gender"] == "Female"
assert d["annual_income"] == 150000 and d["occupation"] == "Student"
assert extract_details("my income is Rs 1,80,000")["annual_income"] == 180000
reply = respond("any scolarship for a 20 year old SC student from Karnataka?", {})
assert reply and "Details taken from your message" in reply["text"]
print("5. simple English + typo ok")

# 6. one named scholarship
reply = respond("what documents do I need for NSP", {})
assert reply["kind"] == "named" and reply["show_cards"] and "Required documents" in reply["text"]
reply = respond("how to apply for CSSS?", {})
assert "How to apply" in reply["text"] and "scholarships.gov.in" in reply["text"]
print("6. named scholarship ok")

# 7. community warning is shown instead of guessing
reply = respond("Am I eligible for PM YASASVI?", {"category": "SC", "state": "Karnataka"})
assert "may not be meant for you" in reply["text"]
print("7. community warning ok")

# 8. other questions are NOT answered here (they go to the Gemini assistant); greetings get help
assert respond("Am I eligible for PM-KISAN?", {"state": "Bihar"}) is None
assert respond("tell me about health insurance", {}) is None
assert respond("hi", {})["kind"] == "help"
print("8. fallback / greeting ok")
print("ALL SCHOLARSHIP CHAT TESTS PASSED")