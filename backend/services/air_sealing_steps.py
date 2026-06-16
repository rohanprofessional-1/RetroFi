import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from services.climate_zone import get_climate_zone, get_construction_era_note


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env")

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def _format_incentives(matched_incentives: list[dict]) -> str:
    if not matched_incentives:
        return "none matched"
    parts = []
    for inc in matched_incentives[:4]:
        name = inc.get("name", "")
        desc = inc.get("amount_description") or "${:,.0f}".format(inc.get("amount", 0))
        notes = inc.get("eligibility_notes", "")
        parts.append(f"{name} ({desc}){': ' + notes if notes else ''}")
    return "\n  ".join(parts)


def _format_contractors(contractors: list[dict]) -> str:
    if not contractors:
        return "none found nearby"
    return "; ".join(
        f"{c['name']} ({c['rating']}★, {c['ratings_count']} reviews, {c['vicinity']})"
        for c in contractors
    )


def _build_prompt(
    address: str,
    gross_cost: float,
    net_cost: float,
    annual_savings: float,
    payback_years: float | None,
    matched_incentives: list[dict],
    property_profile: dict,
    climate_info: dict,
    contractors: list[dict],
) -> str:
    year_built = property_profile.get("year_built")
    home_type = property_profile.get("home_type") or "home"
    sq_ft = property_profile.get("square_footage") or "unknown"
    heating_fuel = property_profile.get("heating_fuel") or "unknown"
    era_note = get_construction_era_note(year_built)

    fuel_impact = {
        "natural_gas": "natural gas heat — air sealing directly reduces therms burned each winter",
        "oil": "oil heat — reducing infiltration meaningfully cuts expensive heating oil consumption",
        "propane": "propane heat — air sealing reduces one of the highest-cost heating fuels",
        "electric": "electric heat — air sealing reduces the heating load on electric resistance or heat pump systems",
    }.get(heating_fuel, f"{heating_fuel} heat")

    return (
        "You are a home performance contractor advising a specific homeowner on air sealing.\n"
        "Return ONLY a JSON array of exactly 6 objects. Each object must have exactly three keys:\n"
        '  "title": action heading, max 5 words\n'
        '  "summary": one sentence (max 20 words) specific to this homeowner\n'
        '  "bullets": array of 2-4 action items or data points, max 15 words each\n\n'
        "Cover these topics in order: (1) home energy audit, (2) target leakage points for this home's "
        "age and type, (3) contractor selection, (4) incentive requirements and paperwork, "
        "(5) what happens during the work, (6) verifying results.\n"
        "Every bullet must reference real numbers, the home's construction era, or local contractor names.\n\n"
        "Homeowner data:\n"
        f"- Address: {address}\n"
        f"- IECC climate zone: {climate_info['zone']} ({climate_info['description']}) — "
        f"air sealing priority is {climate_info['air_sealing_priority']} in this climate\n"
        f"- Home: {sq_ft} sq ft {home_type}, built {era_note}\n"
        f"- Heating fuel: {fuel_impact}\n"
        f"- Gross install cost: ${gross_cost:,.0f}\n"
        f"- Net cost after incentives: ${net_cost:,.0f}\n"
        f"- Estimated annual savings: ${annual_savings:,.0f}/yr\n"
        f"- Payback: {payback_years if payback_years else 'N/A'} years\n"
        f"- Incentives available:\n  {_format_incentives(matched_incentives)}\n"
        f"- Nearby certified contractors: {_format_contractors(contractors)}\n\n"
        "Return only the JSON array, no markdown fences."
    )


def _call_anthropic(prompt: str) -> list[dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip().strip('"').strip("'")
    if not api_key or api_key == "your_anthropic_api_key_here":
        return []

    body = {
        "model": DEFAULT_MODEL,
        "max_tokens": 1600,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = Request(
        ANTHROPIC_MESSAGES_URL,
        data=json.dumps(body).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []

    text = "".join(
        block.get("text", "")
        for block in payload.get("content", [])
        if block.get("type") == "text"
    ).strip()
    if text.startswith("```"):
        text = text.lstrip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    if text.endswith("```"):
        text = text[:-3].strip()

    try:
        steps = json.loads(text)
        if isinstance(steps, list) and all(
            isinstance(s, dict) and "title" in s and "summary" in s and "bullets" in s
            for s in steps
        ):
            return [{"title": s["title"], "summary": s["summary"], "bullets": s["bullets"]} for s in steps]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def _fallback_steps(
    gross_cost: float,
    net_cost: float,
    annual_savings: float,
    payback_years: float | None,
    matched_incentives: list[dict],
    property_profile: dict,
    climate_info: dict,
    contractors: list[dict],
) -> list[dict]:
    year_built = property_profile.get("year_built")
    sq_ft = property_profile.get("square_footage") or "N/A"
    heating_fuel = property_profile.get("heating_fuel") or "your heating fuel"
    era_note = get_construction_era_note(year_built)
    zone = climate_info["zone"]
    priority = climate_info["air_sealing_priority"]
    incentive_names = [inc.get("name", "") for inc in matched_incentives[:3] if inc.get("name")]
    contractor_names = [c["name"] for c in contractors]

    leakage_bullets = [
        f"Priority: attic bypasses around plumbing, wiring, and HVAC chases in your {era_note.split('(')[0].strip()} home",
        "Also check rim joists at basement/crawl space perimeter and recessed light fixtures",
    ]
    if year_built and year_built < 1980:
        leakage_bullets.insert(0, "Pre-1980 construction: expect unsealed wall top plates connecting floors to attic — a major infiltration path")

    audit_bullets = [
        "Request a blower door test to quantify current air leakage (in ACH50)",
        "Audit is often required to claim the 25C tax credit",
        f"Zone {zone} ({priority} priority) means sealing delivers above-average payback for your climate",
    ]
    if incentive_names:
        audit_bullets.append("Ask auditor to document pre-work conditions — needed for incentive paperwork")

    contractor_bullets = [
        "Look for BPI Building Analyst or RESNET HERS Rater certification",
    ]
    if contractor_names:
        contractor_bullets.append(f"Rated local options: {', '.join(contractor_names)}")
    contractor_bullets.append("Get at least 2 quotes specifying blower door test-in and test-out")

    incentive_bullets = []
    for inc in matched_incentives[:3]:
        name = inc.get("name", "")
        desc = inc.get("amount_description") or "${:,.0f}".format(inc.get("amount", 0))
        if name:
            incentive_bullets.append(f"{name}: {desc}")
    if not incentive_bullets:
        incentive_bullets = [f"Net cost after incentives: ${net_cost:,.0f}"]
    incentive_bullets.append("Keep contractor invoices and material receipts for IRS Form 5695")

    return [
        {
            "title": "Schedule a Home Energy Audit",
            "summary": f"A professional audit establishes your air leakage baseline and is often required for incentives.",
            "bullets": audit_bullets,
        },
        {
            "title": "Identify Your Leakage Points",
            "summary": f"Your {sq_ft} sq ft home built {era_note.split('(')[0].strip()} has construction-era-specific infiltration paths.",
            "bullets": leakage_bullets + ["Ask the auditor to rank leakage paths by impact before work begins"],
        },
        {
            "title": "Choose a Certified Contractor",
            "summary": "BPI or RESNET certification ensures blower door testing and quality air sealing technique.",
            "bullets": contractor_bullets,
        },
        {
            "title": "Lock In Your Incentives",
            "summary": f"Incentives reduce your gross cost from ${gross_cost:,.0f} to ${net_cost:,.0f}.",
            "bullets": incentive_bullets,
        },
        {
            "title": "Understand the Work Scope",
            "summary": "Air sealing uses foam, mastic, and caulk — it's disruptive in the attic but minimal elsewhere.",
            "bullets": [
                "Attic work typically takes 1–2 days depending on home size and leakage severity",
                "Contractor will use caulk, spray foam, and rigid board to seal penetrations",
                "Some disruption to attic storage; HVAC system may need to be off during work",
                "Ask for a written scope listing each leakage area and the sealing method",
            ],
        },
        {
            "title": "Verify Results With Blower Door",
            "summary": f"A post-work blower door test confirms the work delivered the ${annual_savings:,.0f}/yr savings estimate.",
            "bullets": [
                "Request a test-out blower door reading — compare ACH50 before vs. after",
                "Typical well-sealed homes achieve 20–40% reduction in air leakage",
                f"Expected payback at current savings rate: {payback_years if payback_years else 'N/A'} years",
                "Test results document is required for the 25C federal tax credit",
            ],
        },
    ]


def generate_air_sealing_steps(
    address: str,
    gross_cost: float,
    net_cost: float,
    annual_savings: float,
    payback_years: float | None,
    matched_incentives: list[dict],
    property_profile: dict,
    contractors: list[dict],
) -> list[dict]:
    climate_info = get_climate_zone(address, property_profile.get("zip_code"))
    prompt = _build_prompt(
        address, gross_cost, net_cost, annual_savings, payback_years,
        matched_incentives, property_profile, climate_info, contractors,
    )
    steps = _call_anthropic(prompt)
    if not steps:
        steps = _fallback_steps(
            gross_cost, net_cost, annual_savings, payback_years,
            matched_incentives, property_profile, climate_info, contractors,
        )
    return steps
