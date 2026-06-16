import json
import os
import re
from pathlib import Path
from typing import Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from schemas import RetrofitCalculationResponse, RetrofitSummaryResponse


BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Default Local LLM settings
DEFAULT_LLM_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_LOCAL_MODEL = "qwen2.5:0.5b"


def summarize_retrofit_calculation(
    calculation: RetrofitCalculationResponse,
) -> RetrofitSummaryResponse:
    provider, _ = _config_value("LLM_PROVIDER")
    base_url, _ = _config_value("LOCAL_LLM_BASE_URL")
    base_url = base_url or DEFAULT_LLM_BASE_URL
    model_value, _ = _config_value("LOCAL_LLM_MODEL")
    model = model_value or DEFAULT_LOCAL_MODEL

    prompt = build_summary_prompt(calculation)

    summary, source = _call_local_llm(prompt=prompt, base_url=base_url, model=model)
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
    # Build a highly concise payload so smaller local models are not overwhelmed
    ranked_options_summary = []
    for opt in calculation.ranked_options:
        ranked_options_summary.append({
            "rank": opt.rank,
            "name": opt.name,
            "net_cost": opt.net_cost,
            "annual_savings": opt.annual_savings,
            "payback_years": opt.payback_years,
        })

    payload = {
        "address": calculation.address,
        "totals": {
            "net_cost": calculation.totals.net_cost,
            "annual_savings": calculation.totals.annual_savings,
            "carbon_avoided_tons": calculation.totals.carbon_avoided_tons,
        },
        "ranked_options": ranked_options_summary,
    }
    return (
        "You are RetroFi ATL's homeowner-facing retrofit advisor.\n"
        "The deterministic engine is the source of truth. Do not recalculate, alter, "
        "or invent dollar amounts, carbon values, payback periods, incentives, rankings, "
        "or eligibility facts.\n"
        "Write a concise plain-English recommendation for an Atlanta homeowner.\n"
        "Format rules:\n"
        "- Write exactly one short paragraph. Keep it to 60 words maximum.\n"
        "- Do not use any markdown, bold formatting, bullet points, headers, or lists. Write only plain text.\n"
        "- Start with the single best first action and why.\n"
        "- Mention only the most important cost, savings, incentive, and payback facts.\n"
        "- End with one practical next step.\n"
        "Use only the provided facts.\n\n"
        f"DETERMINISTIC_CONTEXT_JSON:\n{json.dumps(payload, indent=2)}"
    )


def _call_local_llm(prompt: str, base_url: str, model: str) -> Tuple[str, str]:
    timeout_str, _ = _config_value("LOCAL_LLM_TIMEOUT_SECONDS")
    timeout = int(timeout_str) if timeout_str else 30
    
    num_ctx_str, _ = _config_value("LOCAL_LLM_NUM_CTX")
    num_ctx = int(num_ctx_str) if num_ctx_str else 8192

    temperature_str, _ = _config_value("LOCAL_LLM_TEMPERATURE")
    temperature = float(temperature_str) if temperature_str else 0.0

    system_instruction = (
        "You are RetroFi ATL's homeowner-facing retrofit advisor.\n"
        "The deterministic engine is the source of truth. Do not recalculate, alter, "
        "or invent dollar amounts, carbon values, payback periods, incentives, rankings, "
        "or eligibility facts.\n"
        "Format rules:\n"
        "- Write exactly one short paragraph. Keep it to 60 words maximum.\n"
        "- Do not use any markdown, bold formatting, bullet points, headers, or lists. Write only plain text.\n"
        "- Start with the single best first action and why.\n"
        "- Mention only the most important cost, savings, incentive, and payback facts.\n"
        "- End with one practical next step.\n"
        "Use only the provided facts."
    )

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "options": {
            "num_ctx": num_ctx,
        }
    }
    
    headers = {
        "Content-Type": "application/json",
    }
    
    api_key, _ = _config_value("LLM_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # We use OpenAI compatible endpoint for Ollama or external providers
    endpoint = f"{base_url.rstrip('/')}/v1/chat/completions"
    
    request = Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        import sys
        print(f"[LLM_SUMMARY] Local LLM call failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return "", "fallback"

    try:
        summary = payload["choices"][0]["message"]["content"].strip()
        return (summary, "local_llm") if summary else ("", "fallback")
    except (KeyError, IndexError) as exc:
        import sys
        print(f"[LLM_SUMMARY] Local LLM payload parsing failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return "", "fallback"


def _clean_summary_text(summary: str) -> str:
    lines = []
    for line in summary.splitlines():
        cleaned = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        cleaned = re.sub(r"^\s*[-*•]\s+", "", cleaned)
        cleaned = re.sub(r"^\s*\d+\.\s+", "", cleaned)
        lines.append(cleaned.strip())

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)

    # Collapse all newlines (single or double) into spaces to form one clean prose block
    cleaned = re.sub(r"\s*\n\s*", " ", cleaned)
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
        "This fallback summary was generated without an API key or local model; the numeric "
        "results still come from the deterministic engine."
    )


def _config_value(key: str) -> Tuple[Optional[str], str]:
    value = os.getenv(key)
    if value:
        return value, "process_env"

    env_path = BACKEND_ROOT / ".env"
    if not env_path.exists():
        return None, "missing"

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        env_key, env_value = stripped.split("=", 1)
        normalized_key = env_key.strip()
        if normalized_key == key:
            resolved = env_value.strip().strip('"').strip("'")
            return resolved, "dotenv"
    return None, "missing"


def _model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
