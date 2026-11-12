"""Agent 1 - Intent Router."""
from backend.llm import invoke_json
from backend.utils import clean_profile
from prompts.prompts import ROUTER_FORMAT, ROUTER_HUMAN, ROUTER_SYSTEM

VALID_INTENTS = {"discover", "eligibility", "application", "general"}


class IntentRouterAgent:
    def run(self, query: str) -> dict:
        raw = invoke_json(ROUTER_SYSTEM, ROUTER_HUMAN, output_format=ROUTER_FORMAT, query=query)
        intent = str(raw.get("intent", "discover")).lower().strip()
        if intent not in VALID_INTENTS:
            intent = "discover"
        scheme = raw.get("scheme_name")
        return {
            "intent": intent,
            "scheme_name": scheme if scheme and str(scheme).lower() != "null" else None,
            "search_query": raw.get("search_query") or query,
            "profile": clean_profile(raw.get("profile")),
        }
