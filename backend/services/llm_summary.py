import json
import os
import re
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from schemas import RetrofitCalculationResponse, RetrofitSummaryResponse


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MODEL_ALIASES = {
    "claude-3-5-haiku-latest": DEFAULT_MODEL,
}
DEBUG_LOG_PATH = Path("/Users/rohannair/Desktop/Shenanigans/retrofi-atl/.cursor/debug-05fe41.log")
DEBUG_SESSION_ID = "05fe41"
DEBUG_LOG_ENDPOINT = "http://127.0.0.1:7596/ingest/3f6d0d4e-1307-4f80-a381-cf3930c45abc"


# region agent log
def _debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict):
    payload = {
        "sessionId": DEBUG_SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload) + "\n")
    except OSError:
        try:
            request = Request(
                DEBUG_LOG_ENDPOINT,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Debug-Session-Id": DEBUG_SESSION_ID,
                },
                method="POST",
            )
            urlopen(request, timeout=2).close()
        except OSError:
            pass
# endregion


def summarize_retrofit_calculation(
    calculation: RetrofitCalculationResponse,
) -> RetrofitSummaryResponse:
    api_key, api_key_source = _config_value("ANTHROPIC_API_KEY")
    model_value, model_source = _config_value("ANTHROPIC_MODEL")
    model = MODEL_ALIASES.get(model_value or DEFAULT_MODEL, model_value or DEFAULT_MODEL)
    # region agent log
    _debug_log(
        "initial",
        "H1,H2,H3,H5",
        "backend/services/llm_summary.py:31",
        "LLM config resolved",
        {
            "api_key_present": bool(api_key),
            "api_key_is_placeholder": api_key == "your_anthropic_api_key_here",
            "api_key_source": api_key_source,
            "model": model,
            "model_source": model_source,
            "env_key_present": bool(os.getenv("ANTHROPIC_API_KEY")),
            "env_model_present": bool(os.getenv("ANTHROPIC_MODEL")),
            "dotenv_exists": (BACKEND_ROOT / ".env").exists(),
        },
    )
    # endregion

    if not api_key or api_key == "your_anthropic_api_key_here":
        # region agent log
        _debug_log(
            "initial",
            "H2,H5",
            "backend/services/llm_summary.py:50",
            "Fallback before Anthropic call",
            {"reason": "missing_or_placeholder_key", "model": model},
        )
        # endregion
        return RetrofitSummaryResponse(
            calculation=calculation,
            llm_summary=_fallback_summary(calculation),
            summary_source="fallback",
            model=model,
        )

    prompt = build_summary_prompt(calculation)
    # region agent log
    _debug_log(
        "initial",
        "H1,H3,H4",
        "backend/services/llm_summary.py:65",
        "Calling Anthropic",
        {
            "model": model,
            "prompt_chars": len(prompt),
            "ranked_options": len(calculation.ranked_options),
            "citations": len(calculation.citations),
        },
    )
    # endregion
    summary, source = _call_anthropic(prompt=prompt, api_key=api_key, model=model)
    if source == "fallback":
        summary = _fallback_summary(calculation)
    else:
        summary = _clean_summary_text(summary)

    return RetrofitSummaryResponse(
        calculation=calculation,
        llm_summary=summary,
        summary_source=source,
        model=model,
    )


def build_summary_prompt(calculation: RetrofitCalculationResponse) -> str:
    payload = {
        "address": calculation.address,
        "totals": _model_to_dict(calculation.totals),
        "ranked_options": [_model_to_dict(option) for option in calculation.ranked_options],
        "assumptions": _model_to_dict(calculation.assumptions),
        "llm_context": _model_to_dict(calculation.llm_context),
        "citations": [_model_to_dict(citation) for citation in calculation.citations],
    }
    return (
        "You are RetroFi ATL's homeowner-facing retrofit advisor.\n"
        "The deterministic engine is the source of truth. Do not recalculate, alter, "
        "or invent dollar amounts, carbon values, payback periods, incentives, rankings, "
        "or eligibility facts.\n"
        "Write a concise plain-English recommendation for an Atlanta homeowner.\n"
        "Format rules:\n"
        "- No Markdown, headings, bullets, numbered lists, hashtags, or bold markers.\n"
        "- Keep it to 2 short paragraphs, 120 words maximum.\n"
        "- Start with the single best first action and why.\n"
        "- Mention only the most important cost, savings, incentive, and payback facts.\n"
        "- End with one practical next step.\n"
        "Use only the provided citations and facts.\n\n"
        f"DETERMINISTIC_CONTEXT_JSON:\n{json.dumps(payload, indent=2)}"
    )


def _call_anthropic(prompt: str, api_key: str, model: str) -> Tuple[str, str]:
    body = {
        "model": model,
        "max_tokens": 240,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    request = Request(
        ANTHROPIC_MESSAGES_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")[:800]
        # region agent log
        _debug_log(
            "initial",
            "H1",
            "backend/services/llm_summary.py:119",
            "Anthropic HTTPError",
            {"status": exc.code, "reason": exc.reason, "body": error_body},
        )
        # endregion
        return "", "fallback"
    except URLError as exc:
        # region agent log
        _debug_log(
            "initial",
            "H3",
            "backend/services/llm_summary.py:132",
            "Anthropic URLError",
            {"reason": str(exc.reason)},
        )
        # endregion
        return "", "fallback"
    except TimeoutError as exc:
        # region agent log
        _debug_log(
            "initial",
            "H3",
            "backend/services/llm_summary.py:144",
            "Anthropic timeout",
            {"error": str(exc)},
        )
        # endregion
        return "", "fallback"
    except json.JSONDecodeError as exc:
        # region agent log
        _debug_log(
            "initial",
            "H4",
            "backend/services/llm_summary.py:156",
            "Anthropic JSON decode error",
            {"error": str(exc)},
        )
        # endregion
        return "", "fallback"

    text_parts = [
        block.get("text", "")
        for block in payload.get("content", [])
        if block.get("type") == "text"
    ]
    summary = "\n".join(part for part in text_parts if part).strip()
    # region agent log
    _debug_log(
        "initial",
        "H4",
        "backend/services/llm_summary.py:172",
        "Anthropic response parsed",
        {
            "content_blocks": len(payload.get("content", [])),
            "text_blocks": len(text_parts),
            "summary_chars": len(summary),
            "stop_reason": payload.get("stop_reason"),
        },
    )
    # endregion
    return (summary, "anthropic") if summary else ("", "fallback")


def _clean_summary_text(summary: str) -> str:
    lines = []
    for line in summary.splitlines():
        cleaned = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        cleaned = re.sub(r"^\s*[-*]\s+", "", cleaned)
        cleaned = re.sub(r"^\s*\d+\.\s+", "", cleaned)
        lines.append(cleaned.strip())

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _fallback_summary(calculation: RetrofitCalculationResponse) -> str:
    if not calculation.ranked_options:
        return "No retrofit options were returned by the deterministic engine."

    top = calculation.ranked_options[0]
    return (
        f"RetroFi ATL ranked {top.name} as the first move for {calculation.address}. "
        f"It has an estimated net cost of ${top.net_cost:,.0f}, annual savings of "
        f"${top.annual_savings:,.0f}, carbon avoidance of {top.carbon_avoided_tons:.1f} "
        f"tons per year, and a payback of {top.payback_years} years. Across all modeled "
        f"options, the plan totals ${calculation.totals.net_cost:,.0f} in net cost, "
        f"${calculation.totals.annual_savings:,.0f} in annual savings, and "
        f"{calculation.totals.carbon_avoided_tons:.1f} tons of annual carbon avoidance. "
        "This fallback summary was generated without an Anthropic API key; the numeric "
        "results still come from the deterministic engine."
    )


def _config_value(key: str) -> Tuple[Optional[str], str]:
    value = os.getenv(key)
    if value:
        return value, "process_env"

    env_path = BACKEND_ROOT / ".env"
    if not env_path.exists():
        # region agent log
        _debug_log(
            "initial",
            "H1,H2",
            "backend/services/llm_summary.py:252",
            "Config lookup skipped dotenv",
            {"key": key, "reason": "dotenv_missing"},
        )
        # endregion
        return None, "missing"

    seen_keys = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        env_key, env_value = stripped.split("=", 1)
        normalized_key = env_key.strip()
        seen_keys.append(normalized_key)
        if normalized_key == key:
            resolved = env_value.strip().strip('"').strip("'")
            # region agent log
            _debug_log(
                "initial",
                "H2,H3",
                "backend/services/llm_summary.py:260",
                "Config lookup resolved from dotenv",
                {
                    "key": key,
                    "value_present": bool(resolved),
                    "value_is_placeholder": resolved == "your_anthropic_api_key_here",
                    "raw_key_had_export_prefix": env_key.strip().startswith("export "),
                    "raw_key_had_whitespace": env_key != env_key.strip(),
                },
            )
            # endregion
            return resolved, "dotenv"
    # region agent log
    _debug_log(
        "initial",
        "H2",
        "backend/services/llm_summary.py:262",
        "Config lookup missed key in dotenv",
        {
            "key": key,
            "seen_key_count": len(seen_keys),
            "saw_export_prefixed_target": f"export {key}" in seen_keys,
        },
    )
    # endregion
    return None, "missing"


def _model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
