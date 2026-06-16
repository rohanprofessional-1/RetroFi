import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env")

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MODEL_ALIASES = {"claude-3-5-haiku-latest": DEFAULT_MODEL}

_AZIMUTH_BINS = [
    (22.5, "north"),
    (67.5, "northeast"),
    (112.5, "east"),
    (157.5, "southeast"),
    (202.5, "south"),
    (247.5, "southwest"),
    (292.5, "west"),
    (337.5, "northwest"),
    (360.0, "north"),
]


def _azimuth_to_direction(azimuth: float) -> str:
    for threshold, direction in _AZIMUTH_BINS:
        if azimuth <= threshold:
            return direction
    return "north"


def _best_roof_segment(roof_segments: list[dict]) -> dict | None:
    if not roof_segments:
        return None
    return max(roof_segments, key=lambda s: s.get("medianSunshineHoursPerYear") or 0)


def _format_installers(installers: list[dict]) -> str:
    if not installers:
        return "none found nearby via Google Places"
    parts = [
        f"{i['name']} ({i['rating']}★, {i['ratings_count']} reviews, {i['vicinity']})"
        for i in installers
    ]
    return "; ".join(parts)


def _format_incentives(matched_incentives: list[dict]) -> str:
    if not matched_incentives:
        return "none matched"
    parts = []
    for inc in matched_incentives[:4]:
        name = inc.get("name", "")
        desc = inc.get("amount_description") or "${:,.0f}".format(inc.get("amount", 0))
        parts.append(f"{name} ({desc})")
    return "; ".join(parts)


def _build_prompt(
    solar_data: dict,
    matched_incentives: list[dict],
    address: str,
    installers: list[dict],
) -> str:
    best = _best_roof_segment(solar_data.get("roofSegments") or [])
    segment_line = ""
    if best:
        direction = _azimuth_to_direction(best.get("azimuthDegrees", 0))
        segment_line = (
            f"- Best roof face: {direction}-facing "
            f"({best.get('azimuthDegrees', 0):.0f}° azimuth, "
            f"{best.get('pitchDegrees', 0):.0f}° pitch, "
            f"{best.get('medianSunshineHoursPerYear', 0):.0f} sunshine hrs/yr)\n"
        )

    net_metering = solar_data.get("netMeteringAllowed")
    net_metering_text = (
        "yes" if net_metering is True else ("no" if net_metering is False else "unknown")
    )

    solar_pct = solar_data.get("solarPercentage")
    solar_pct_text = f"{solar_pct:.0f}%" if solar_pct else "N/A"

    context = (
        "You are a solar installation advisor helping a homeowner take action.\n"
        "Return ONLY a JSON array of exactly 6 objects. Each object must have exactly three keys:\n"
        '  "title": action heading, max 5 words\n'
        '  "summary": one sentence (max 20 words) explaining why this step matters for this homeowner specifically\n'
        '  "bullets": array of 2-4 short action items or data points, max 15 words each — '
        "use real numbers, segment specs, and installer names from the data\n\n"
        "Cover these topics in order: (1) roof placement, (2) getting quotes, "
        "(3) permits and interconnection, (4) incentive paperwork, "
        "(5) net metering enrollment, (6) post-install monitoring.\n"
        "Every bullet must be specific to this homeowner — no generic advice.\n\n"
        "Homeowner data:\n"
        f"- Address: {address}\n"
        f"- System: {solar_data.get('panelCount', 'N/A')} panels, "
        f"{solar_data.get('systemSizeKw', 'N/A')} kW\n"
        f"{segment_line}"
        f"- Annual production: {solar_data.get('annualProductionKwh', 'N/A')} kWh/yr "
        f"({solar_pct_text} of usage)\n"
        f"- Net metering allowed: {net_metering_text}\n"
        f"- Gross install cost: ${solar_data.get('upfrontCost', 0):,.0f}\n"
        f"- Net cost after incentives: ${solar_data.get('netUpfrontCost', 0):,.0f}\n"
        f"- Annual savings: ${solar_data.get('annualSavings', 0):,.0f}/yr\n"
        f"- Payback: {solar_data.get('paybackYears', 'N/A')} years\n"
        f"- Installation notes: {solar_data.get('installationNotes', 'N/A')}\n"
        f"- Nearby rated solar installers: {_format_installers(installers)}\n"
        f"- Incentives available: {_format_incentives(matched_incentives)}\n\n"
        "Return only the JSON array, no other text, no markdown fences."
    )
    return context


def _call_anthropic(prompt: str, api_key: str, model: str) -> list[dict]:
    body = {
        "model": model,
        "max_tokens": 900,
        "temperature": 0.3,
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
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []

    text = "".join(
        block.get("text", "")
        for block in payload.get("content", [])
        if block.get("type") == "text"
    ).strip()

    try:
        steps = json.loads(text)
        if (
            isinstance(steps, list)
            and all(
                isinstance(s, dict)
                and "title" in s
                and "summary" in s
                and "bullets" in s
                and isinstance(s["bullets"], list)
                for s in steps
            )
        ):
            return [
                {"title": s["title"], "summary": s["summary"], "bullets": s["bullets"]}
                for s in steps
            ]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _fallback_steps(
    solar_data: dict,
    matched_incentives: list[dict],
    address: str,
) -> list[dict]:
    panel_count = solar_data.get("panelCount", "N/A")
    system_kw = solar_data.get("systemSizeKw", "N/A")
    annual_savings = solar_data.get("annualSavings") or 0
    net_cost = solar_data.get("netUpfrontCost") or 0
    payback = solar_data.get("paybackYears", "N/A")

    best = _best_roof_segment(solar_data.get("roofSegments") or [])
    roof_direction = _azimuth_to_direction(best.get("azimuthDegrees", 0)) if best else ""
    roof_pitch = best.get("pitchDegrees", 0) if best else 0
    roof_area = best.get("areaMeters2", 0) if best else 0
    roof_sun = best.get("medianSunshineHoursPerYear", 0) if best else 0

    incentive_names = [inc.get("name", "") for inc in matched_incentives[:3] if inc.get("name")]
    net_metering = solar_data.get("netMeteringAllowed")
    solar_pct = solar_data.get("solarPercentage")
    solar_pct_text = f"{solar_pct:.0f}%" if solar_pct else "most"

    roof_bullets = [f"Place all {panel_count} panels on your {roof_direction}-facing section for maximum output"]
    if best:
        roof_bullets.append(f"{roof_direction.capitalize()}-facing: {roof_pitch:.0f}° pitch, {roof_area:.0f} m², {roof_sun:.0f} hrs/yr sunshine")
    roof_bullets.append("Ask each installer to quote specifically for this roof placement")

    steps = [
        {
            "title": "Target Your Best Roof Section",
            "summary": f"Your {roof_direction + '-facing ' if roof_direction else ''}roof section captures the most sun and should host the full array." if roof_direction else "Prioritize the sunniest roof section for your array.",
            "bullets": roof_bullets,
        },
        {
            "title": "Collect at Least 3 Quotes",
            "summary": f"Get competing bids for a {panel_count}-panel, {system_kw} kW system to ensure fair pricing.",
            "bullets": [
                "Compare total installed price per watt",
                "Check panel and inverter brands and models",
                "Confirm 25-year panel warranty and 10-year workmanship warranty",
                "Ask each installer for their interconnection timeline estimate",
            ],
        },
        {
            "title": "Confirm Permits and Interconnection",
            "summary": "Permit and interconnection approvals set your activation date — confirm your installer handles both.",
            "bullets": [
                "Installer pulls local electrical and building permit",
                "Installer submits utility interconnection application",
                "Ask for expected approval timelines before signing",
            ],
        },
        {
            "title": "Lock In Your Incentives",
            "summary": f"Claiming all available incentives reduces your net cost to ${net_cost:,.0f}.",
            "bullets": (
                [f"Apply for: {name}" for name in incentive_names]
                + ["Verify equipment meets IRS Section 48E requirements before signing",
                   "Save all receipts and model numbers for IRS Form 5695"]
            ),
        },
    ]

    if net_metering is True:
        steps.append({
            "title": "Enroll in Net Metering",
            "summary": f"Net metering credits your bill for surplus power and is key to your ${annual_savings:,.0f}/yr savings estimate.",
            "bullets": [
                "Contact your utility to enroll before or at system activation",
                "Confirm your credited export rate per kWh",
                "Track monthly exports vs. imports on your utility bill",
            ],
        })
    else:
        steps.append({
            "title": "Understand Your Export Policy",
            "summary": "Solar buyback rates vary by utility and directly affect your actual annual savings.",
            "bullets": [
                "Ask your utility about their excess-generation credit rate",
                "Compare buyback rate to your import rate",
                "Factor the difference into your payback projection",
            ],
        })

    steps.append({
        "title": "Monitor Output After Activation",
        "summary": f"Your system should cover {solar_pct_text} of usage and pay back in {payback} years — verify it's on track.",
        "bullets": [
            f"Target: ~${annual_savings:,.0f}/yr in savings",
            "Review inverter production reports monthly",
            "Flag any month more than 15% below baseline estimate",
            "Schedule a performance check at 1 year post-activation",
        ],
    })

    return steps


def _resolve_api_key() -> str | None:
    key = os.getenv("ANTHROPIC_API_KEY")
    if key and key != "your_anthropic_api_key_here":
        return key
    env_path = BACKEND_ROOT / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("ANTHROPIC_API_KEY="):
            value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
            if value and value != "your_anthropic_api_key_here":
                return value
    return None


def generate_solar_steps(
    solar_data: dict,
    matched_incentives: list[dict],
    address: str,
    installers: list[dict],
) -> list[dict]:
    api_key = _resolve_api_key()
    if not api_key:
        return _fallback_steps(solar_data, matched_incentives, address)

    model_env = os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL
    model = MODEL_ALIASES.get(model_env, model_env)

    prompt = _build_prompt(solar_data, matched_incentives, address, installers)
    steps = _call_anthropic(prompt, api_key, model)
    if not steps:
        return _fallback_steps(solar_data, matched_incentives, address)
    return steps
