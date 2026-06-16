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

# Estimated current attic R-value by construction decade
_ESTIMATED_R_BY_ERA: list[tuple[int, int, str]] = [
    (1950, 0,  "likely R-0 to R-3 — no meaningful insulation in this era"),
    (1970, 5,  "likely R-3 to R-8 — minimal kraft-faced batts if any"),
    (1980, 11, "likely R-8 to R-11 — early codes required minimal ceiling insulation"),
    (1990, 19, "likely R-11 to R-19 — first energy codes introduced R-19 minimums"),
    (2000, 30, "likely R-19 to R-30 — improved codes but below current DOE recommendations"),
    (2012, 38, "likely R-30 to R-38 — near modern code in most zones"),
    (9999, 49, "likely R-38 to R-49 — current code compliance"),
]

# 25C tax credit requires existing insulation below R-19
R19_ELIGIBILITY_THRESHOLD = 19

# Inches of blown insulation needed per R-value
_INCHES_PER_R = {
    "blown_cellulose": 1 / 3.7,   # R-3.7/inch
    "blown_fiberglass": 1 / 2.5,  # R-2.5/inch
}


def _estimate_current_r(year_built: int | None) -> tuple[int, str]:
    if not year_built:
        return 11, "current R-value unknown — measure before getting quotes"
    for cutoff, r_value, note in _ESTIMATED_R_BY_ERA:
        if year_built < cutoff:
            return r_value, note
    return 49, "likely R-38 to R-49 — current code compliance"


def _insulation_type_recommendation(home_type: str | None, year_built: int | None) -> str:
    home = (home_type or "").lower()
    old_home = year_built and year_built < 1980
    if old_home:
        return (
            "blown cellulose recommended — covers irregular joist bays and obstructions in older attics "
            "better than batts; also provides slight air sealing benefit"
        )
    if "condo" in home or "apartment" in home:
        return "confirm attic access — many condos share attic space; get HOA approval before work"
    return (
        "blown fiberglass or cellulose — both effective in newer attics; "
        "cellulose preferred if you plan to DIY-prep areas first"
    )


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
    sq_ft = property_profile.get("square_footage")
    heating_fuel = property_profile.get("heating_fuel") or "unknown"
    era_note = get_construction_era_note(year_built)
    current_r, r_note = _estimate_current_r(year_built)
    target_r = climate_info["target_r_attic"]
    zone = climate_info["zone"]
    insulation_type = _insulation_type_recommendation(home_type, year_built)
    qualifies_25c = current_r < R19_ELIGIBILITY_THRESHOLD
    cellulose_inches = round((int(target_r.split("R-")[1].split(" ")[0]) - current_r) / 3.7, 1) if "R-" in target_r else "N/A"

    return (
        "You are an insulation contractor advising a specific homeowner on attic insulation.\n"
        "Return ONLY a JSON array of exactly 6 objects. Each object must have exactly three keys:\n"
        '  "title": action heading, max 5 words\n'
        '  "summary": one sentence (max 20 words) specific to this homeowner\n'
        '  "bullets": array of 2-4 action items or data points, max 15 words each\n\n'
        "Cover these topics in order: (1) measure current insulation depth and R-value, "
        "(2) confirm 25C tax credit eligibility based on current R-value, "
        "(3) air seal attic bypasses before adding insulation, "
        "(4) choose insulation type and get quotes specifying the target R-value, "
        "(5) incentives and paperwork, "
        "(6) verify the completed work.\n"
        "Every bullet must use real numbers and be specific to this homeowner.\n\n"
        "Homeowner data:\n"
        f"- Address: {address}\n"
        f"- IECC climate zone: {zone} ({climate_info['description']}) — DOE target: {target_r}\n"
        f"- Home: {sq_ft or 'N/A'} sq ft {home_type}, built {era_note}\n"
        f"- Estimated current R-value: {r_note}\n"
        f"- To reach {target_r} using blown cellulose: add ~{cellulose_inches}\" on top of existing insulation\n"
        f"- 25C credit eligibility: {'LIKELY ELIGIBLE — existing insulation appears below R-19' if qualifies_25c else 'MEASURE FIRST — home may be above R-19 threshold for 25C credit'}\n"
        f"- Heating fuel: {heating_fuel} — insulation directly reduces heating load\n"
        f"- Recommended insulation type: {insulation_type}\n"
        f"- Gross install cost: ${gross_cost:,.0f}\n"
        f"- Net cost after incentives: ${net_cost:,.0f}\n"
        f"- Estimated annual savings: ${annual_savings:,.0f}/yr\n"
        f"- Payback: {payback_years if payback_years else 'N/A'} years\n"
        f"- Incentives:\n  {_format_incentives(matched_incentives)}\n"
        f"- Nearby insulation contractors: {_format_contractors(contractors)}\n\n"
        "Return only the JSON array, no markdown fences."
    )


def _call_anthropic(prompt: str) -> list[dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip().strip('"').strip("'")
    if not api_key or api_key == "your_anthropic_api_key_here":
        return []
    body = {
        "model": DEFAULT_MODEL,
        "max_tokens": 900,
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
        block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text"
    ).strip()
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
    home_type = property_profile.get("home_type") or "home"
    sq_ft = property_profile.get("square_footage") or "N/A"
    heating_fuel = property_profile.get("heating_fuel") or "your heating fuel"
    era_note = get_construction_era_note(year_built)
    current_r, r_note = _estimate_current_r(year_built)
    target_r = climate_info["target_r_attic"]
    zone = climate_info["zone"]
    qualifies_25c = current_r < R19_ELIGIBILITY_THRESHOLD
    insulation_type = _insulation_type_recommendation(home_type, year_built)
    contractor_names = [c["name"] for c in contractors]

    incentive_bullets = []
    for inc in matched_incentives[:3]:
        name = inc.get("name", "")
        desc = inc.get("amount_description") or "${:,.0f}".format(inc.get("amount", 0))
        if name:
            incentive_bullets.append(f"{name}: {desc}")
    if not incentive_bullets:
        incentive_bullets = [f"Net cost after incentives: ${net_cost:,.0f}"]
    incentive_bullets.append("Keep contractor invoice showing material costs for IRS Form 5695")

    contractor_bullets = ["Get at least 2 quotes specifying target R-value and product type"]
    if contractor_names:
        contractor_bullets.insert(0, f"Rated local options: {', '.join(contractor_names)}")
    contractor_bullets.append(f"Ask each quote to specify inches of added insulation to reach {target_r}")

    return [
        {
            "title": "Measure Your Current Insulation",
            "summary": f"Your {era_note.split('(')[0].strip()} home is {r_note.split('—')[0].strip()} — measure before ordering materials.",
            "bullets": [
                r_note,
                "Use a ruler in the attic: every inch of blown fiberglass ≈ R-2.5, cellulose ≈ R-3.7",
                "Take photos of the depth stick reading — needed for contractor quotes and incentive paperwork",
                "Check multiple spots; insulation often settles unevenly across the attic floor",
            ],
        },
        {
            "title": "Confirm 25C Credit Eligibility",
            "summary": f"The 25C credit requires existing insulation below R-19 — your home {'likely qualifies' if qualifies_25c else 'needs measurement to confirm'}.",
            "bullets": [
                f"Estimated current R-value: ~R-{current_r} based on {year_built or 'construction era'}",
                f"{'Eligible: existing insulation appears below the R-19 threshold' if qualifies_25c else 'Measure first — if existing insulation is already R-19+, 25C credit may not apply'}",
                "Have contractor document pre-work R-value in writing for IRS Form 5695",
                "25C covers 30% of material + labor costs up to the annual envelope cap",
            ],
        },
        {
            "title": "Air Seal Bypasses First",
            "summary": "Sealing attic air bypasses before insulating locks in long-term energy savings.",
            "bullets": [
                "Add insulation on top of air leaks and you insulate the leak — seal first",
                "Key bypass locations: plumbing and wiring penetrations, attic hatch, recessed lights",
                "Ask your insulation contractor if they include air sealing or if you need a separate crew",
                "Combining air sealing and insulation in one job often saves mobilization cost",
            ],
        },
        {
            "title": f"Specify {target_r} in Every Quote",
            "summary": f"Zone {zone} DOE target is {target_r} — require this in every written quote.",
            "bullets": [
                f"Target R-value for your climate: {target_r}",
                f"Recommended type: {insulation_type}",
                contractor_bullets[0] if contractor_names else "Get at least 2 quotes specifying target R-value",
                "Reject any quote that doesn't state both the R-value target and product type",
            ],
        },
        {
            "title": "Lock In Your Incentives",
            "summary": f"Stacking incentives reduces your cost from ${gross_cost:,.0f} to ${net_cost:,.0f}.",
            "bullets": incentive_bullets,
        },
        {
            "title": "Verify the Completed Work",
            "summary": f"Confirm the installed depth matches the quoted {target_r} before paying the final invoice.",
            "bullets": [
                "Measure installed depth with a ruler in multiple attic locations after work",
                "Blown insulation settles 10–20% over 1–2 years — confirm contractor accounts for this",
                f"Expected annual savings: ${annual_savings:,.0f}/yr on {heating_fuel} heating costs",
                f"Payback at current savings rate: {payback_years if payback_years else 'N/A'} years",
            ],
        },
    ]


def generate_attic_insulation_steps(
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
