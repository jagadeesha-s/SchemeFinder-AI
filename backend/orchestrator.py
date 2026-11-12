"""Coordinates the five agents."""
import config
from agents.application_agent import ApplicationAgent
from agents.eligibility_agent import EligibilityAgent
from agents.explainer_agent import ExplainerAgent
from agents.retrieval_agent import RetrievalAgent
from agents.router_agent import IntentRouterAgent
from backend.utils import clean_profile, missing_fields, norm
from backend.vector_store import SchemeVectorStore

STATUS_ORDER = {"eligible": 0, "potentially_eligible": 1, "ineligible": 2}
DEFAULT_QUERIES = {
    "discover": "Find government schemes that match my profile",
    "eligibility": "Check which government schemes I am eligible for",
    "application": "How do I apply for the government schemes that match my profile",
}


def _result(intent="discover", message="", cards=None, questions=None, sources=None, profile=None) -> dict:
    return {
        "intent": intent,
        "message": message,
        "cards": cards or [],
        "follow_up_questions": questions or [],
        "sources": sources or [],
        "profile_used": profile or {},
        "disclaimer": config.DISCLAIMER,
    }


class SchemeFinderOrchestrator:
    def __init__(self) -> None:
        self.store = SchemeVectorStore()
        self.router = IntentRouterAgent()
        self.retriever = RetrievalAgent(self.store)
        self.eligibility = EligibilityAgent()
        self.application = ApplicationAgent()
        self.explainer = ExplainerAgent()

    def handle(self, query: str, ui_profile: dict | None, mode: str = "auto") -> dict:
        query = (query or "").strip()
        profile = clean_profile(ui_profile)

        if self.store.count() == 0:
            return _result(
                message="No scheme documents are indexed yet. Add PDFs to data/schemes/ and click "
                "'Re-index documents' (or run `python -m scripts.ingest`).",
                profile=profile,
            )

        # ---- Agent 1: route + extract details from the text ----
        intent, scheme_name, search_query = mode, None, query
        if query:
            routed = self.router.run(query)
            profile.update(routed["profile"])  # details typed in the message are the most recent
            scheme_name, search_query = routed["scheme_name"], routed["search_query"]
            if mode == "auto":
                intent = routed["intent"]
        elif mode == "auto" or not profile:
            return _result(
                message="Please describe your situation or fill in the profile in the sidebar first.",
                questions=[config.FIELD_QUESTIONS[f] for f in missing_fields(profile)],
                profile=profile,
            )
        if not query:
            query = search_query = DEFAULT_QUERIES.get(intent, DEFAULT_QUERIES["discover"])

        missing = missing_fields(profile)

        # ---- Agent 2: retrieve ----
        retrieved = self.retriever.run(search_query, profile, scheme_name if intent == "application" else None)
        if not retrieved["found"]:
            return _result(
                intent=intent,
                message="I could not find any scheme in the indexed official documents that matches your "
                "request. Try describing your situation differently, or add more official scheme PDFs.",
                questions=[config.FIELD_QUESTIONS[f] for f in missing],
                profile=profile,
            )
        context, sources = retrieved["context"], retrieved["sources"]

        # ---- General questions: Explainer answers directly ----
        if intent == "general":
            ans = self.explainer.answer_general(query, context, sources)
            return _result(intent, ans["answer"], sources=ans["sources"], profile=profile)

        # ---- Agent 3: eligibility ----
        elig = self.eligibility.run(query, profile, missing, context, sources)
        cards = sorted(elig["schemes"], key=lambda c: STATUS_ORDER[c["status"]])
        questions = list(elig["follow_up_questions"])
        questions += [config.FIELD_QUESTIONS[f] for f in missing]
        for c in cards:
            questions += c["questions_for_user"]
        questions = list(dict.fromkeys(q for q in questions if q))

        if not cards:
            return _result(
                intent=intent,
                message="No matching scheme was found in the indexed official documents for your request.",
                questions=questions,
                profile=profile,
            )

        # ---- Agent 4: application guidance (only for non-ineligible schemes) ----
        if intent == "application":
            names = [c["scheme_name"] for c in cards if c["status"] != "ineligible"]
            apps = self.application.run(names, profile, context, sources)
            for c in cards:
                details = apps.get(norm(c["scheme_name"]))
                c["application"] = details
        for c in cards:
            c.setdefault("application", None)

        # ---- Agent 5: explain in simple English ----
        exp = self.explainer.explain_results(query, cards)
        for c in cards:
            c["explanation"] = exp["explanations"].get(norm(c["scheme_name"]), "")

        all_sources = {s["id"]: s for c in cards for s in c["sources"]}
        return _result(
            intent=intent,
            message=exp["summary"],
            cards=cards,
            questions=questions,
            sources=list(all_sources.values()),
            profile=profile,
        )
