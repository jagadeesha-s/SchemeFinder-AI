"""Agent 4 - Application guidance."""
import json

from backend.llm import invoke_json
from backend.utils import find_urls, norm
from prompts.prompts import APPLICATION_FORMAT, APPLICATION_HUMAN, APPLICATION_SYSTEM


class ApplicationAgent:
    def run(self, scheme_names: list[str], profile: dict, context: str, sources: dict) -> dict:
        """Return {normalised scheme name: application details}."""
        if not scheme_names:
            return {}
        raw = invoke_json(
            APPLICATION_SYSTEM,
            APPLICATION_HUMAN,
            output_format=APPLICATION_FORMAT,
            schemes=json.dumps(scheme_names, ensure_ascii=False),
            profile=json.dumps(profile, ensure_ascii=False),
            context=context,
        )
        # A link is only kept if it literally appears in the retrieved documents/metadata.
        allowed = find_urls(context) | {s["official_url"] for s in sources.values() if s.get("official_url")}
        allowed = {u.rstrip("/").lower() for u in allowed}

        out = {}
        for item in raw.get("applications") or []:
            link = item.get("official_link")
            if not link or link.rstrip("/").lower() not in allowed:
                link = None
            out[norm(item.get("scheme_name", ""))] = {
                "required_documents": item.get("required_documents") or [],
                "application_steps": item.get("application_steps") or [],
                "deadline": item.get("deadline"),
                "official_link": link,
                "notes": item.get("notes"),
            }
        return out
