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

# HPWH uses ~3.5× less electricity than electric resistance
HPWH_COP = 3.5
# kWh to heat one gallon of water by 90°F (typical tank delta)
KWH_PER_GALLON = 0.111

# Tank size recommendation by household size
_TANK_SIZE: list[tuple[int, int]] = [
    (1, 40),
    (2, 50),
    (3, 50),
    (4, 65),
    (5, 65),
    (99, 80),
]


def _tank_size_for_household(household_size: int | None) -> int:
    size = household_size or 2
    for threshold, gallons in _TANK_SIZE:
        if size <= threshold:
            return gallons
    return 80


def _switching_economics(
    water_heater_fuel: str | None,
    electricity_per_kwh: float | None,
    gas_per_therm: float | None,
) -> str:
    fuel = (water_heater_fuel or "").lower()
    if "gas" in fuel and gas_per_therm and electricity_per_kwh:
        # 1 therm heats ~29 gallons at 90°F delta; HPWH at 3.5 COP uses 0.111/3.5 kWh/gal
        gas_cost_per_gal = gas_per_therm / 29
        hp_cost_per_gal = (KWH_PER_GALLON / HPWH_COP) * electricity_per_kwh
        if hp_cost_per_gal < gas_cost_per_gal:
            savings_pct = round((gas_cost_per_gal - hp_cost_per_gal) / gas_cost_per_gal * 100)
            return (
                f"At ${electricity_per_kwh:.3f}/kWh and ${gas_per_therm:.3f}/therm: "
                f"HPWH costs ${hp_cost_per_gal:.4f}/gal to heat vs gas at ${gas_cost_per_gal:.4f}/gal — "
                f"{savings_pct}% cheaper per gallon"
            )
        else:
            return (
                f"At ${electricity_per_kwh:.3f}/kWh and ${gas_per_therm:.3f}/therm: "
                f"gas water heating is currently cheaper per gallon in this market — "
                f"verify rates before committing"
            )
    if "electric" in fuel and electricity_per_kwh:
        annual_kwh_resistance = 4500  # typical 50-gal electric resistance
        annual_kwh_hpwh = annual_kwh_resistance / HPWH_COP
        annual_savings = (annual_kwh_resistance - annual_kwh_hpwh) * electricity_per_kwh
        return (
            f"At ${electricity_per_kwh:.3f}/kWh: HPWH uses ~{int(annual_kwh_hpwh):,} kWh/yr vs "
            f"~{int(annual_kwh_resistance):,} kWh/yr for electric resistance — "
            f"~${annual_savings:.0f}/yr savings"
        )
    return "switching economics depend on local electricity vs fuel rates — request a cost comparison from your contractor"


def _space_requirement_note(home_type: str | None, sq_ft: int | None) -> str:
    home = (home_type or "").lower()
    if "condo" in home or "apartment" in home:
        return "condos often lack the 700+ cubic feet of ambient air HPWHs require — confirm space before purchasing"
    if "townhouse" in home:
        return "townhouses with a basement or utility room typically have adequate space; confirm before purchasing"
    return "install in unconditioned basement, garage, or utility room with 700+ cubic feet of ambient air"


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
    rates: dict,
    contractors: list[dict],
) -> str:
    water_heater_fuel = property_profile.get("water_heater_fuel") or "unknown"
    household_size = property_profile.get("household_size") or property_profile.get("household_size")
    home_type = property_profile.get("home_type") or "home"
    sq_ft = property_profile.get("square_footage")
    tank_size = _tank_size_for_household(household_size)
    economics = _switching_economics(water_heater_fuel, rates.get("electricity_per_kwh"), rates.get("gas_per_therm"))
    space_note = _space_requirement_note(home_type, sq_ft)
    switching_from_gas = "gas" in (water_heater_fuel or "").lower()

    return (
        "You are a plumbing contractor advising a specific homeowner on installing a heat pump water heater.\n"
        "Return ONLY a JSON array of exactly 6 objects. Each object must have exactly three keys:\n"
        '  "title": action heading, max 5 words\n'
        '  "summary": one sentence (max 20 words) specific to this homeowner\n'
        '  "bullets": array of 2-4 action items or data points, max 15 words each\n\n'
        "Cover these topics in order: (1) confirm installation space requirements, "
        "(2) electrical work needed (especially if switching from gas), "
        "(3) right tank size for this household, "
        "(4) switching economics at actual local rates, "
        "(5) incentives and paperwork, "
        "(6) operating mode setup and first-year tips.\n"
        "Every bullet must use real numbers and be specific to this homeowner.\n\n"
        "Homeowner data:\n"
        f"- Address: {address}\n"
        f"- Current water heater fuel: {water_heater_fuel}\n"
        f"- Home type: {home_type}, {sq_ft or 'N/A'} sq ft\n"
        f"- Household size: {household_size or 'unknown'} people → recommended tank: {tank_size} gallons\n"
        f"- Space note: {space_note}\n"
        f"- {'Switching from gas requires: new 240V/30A circuit + capping gas line (electrician needed first)' if switching_from_gas else 'Switching from electric resistance: direct 240V swap, simpler installation'}\n"
        f"- Economics: {economics}\n"
        f"- Gross install cost: ${gross_cost:,.0f}\n"
        f"- Net cost after incentives: ${net_cost:,.0f}\n"
        f"- Estimated annual savings: ${annual_savings:,.0f}/yr\n"
        f"- Payback: {payback_years if payback_years else 'N/A'} years\n"
        f"- Incentives:\n  {_format_incentives(matched_incentives)}\n"
        f"- Nearby contractors: {_format_contractors(contractors)}\n\n"
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
        block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text"
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
    rates: dict,
    contractors: list[dict],
) -> list[dict]:
    water_heater_fuel = property_profile.get("water_heater_fuel") or "unknown"
    household_size = property_profile.get("household_size")
    home_type = property_profile.get("home_type") or "home"
    sq_ft = property_profile.get("square_footage")
    tank_size = _tank_size_for_household(household_size)
    economics = _switching_economics(water_heater_fuel, rates.get("electricity_per_kwh"), rates.get("gas_per_therm"))
    space_note = _space_requirement_note(home_type, sq_ft)
    switching_from_gas = "gas" in (water_heater_fuel or "").lower()
    contractor_names = [c["name"] for c in contractors]

    incentive_bullets = []
    for inc in matched_incentives[:3]:
        name = inc.get("name", "")
        desc = inc.get("amount_description") or "${:,.0f}".format(inc.get("amount", 0))
        if name:
            incentive_bullets.append(f"{name}: {desc}")
    if not incentive_bullets:
        incentive_bullets = [f"Net cost after incentives: ${net_cost:,.0f}"]
    incentive_bullets.append("Unit must be ENERGY STAR certified for 25C credit — verify before purchase")

    electrical_bullets = (
        [
            "Run new 240V/30A dedicated circuit to water heater location (electrician required)",
            "Cap existing gas line at the appliance — licensed plumber or gas fitter required",
            "Electrical work must complete before plumber arrives to install unit",
        ]
        if switching_from_gas else
        [
            "Verify existing 240V/30A circuit is present — most electric tank heaters have this",
            "Switching from electric resistance is a near-direct swap on the same circuit",
            "Confirm circuit breaker amperage matches new unit requirements",
        ]
    )

    contractor_bullets = ["Get quotes from both a licensed plumber and electrician" if switching_from_gas else "Get quotes from a licensed plumber"]
    if contractor_names:
        contractor_bullets.insert(0, f"Rated local options: {', '.join(contractor_names)}")
    contractor_bullets.append("Ask each contractor for their ENERGY STAR product recommendation")

    return [
        {
            "title": "Confirm Installation Space",
            "summary": f"HPWHs need 700+ cubic feet of ambient air — your {home_type} location matters.",
            "bullets": [
                space_note,
                "Avoid tight closets — the unit pulls heat from surrounding air and needs room",
                "Unconditioned spaces (basement, garage) work best and improve efficiency",
                "Measure doorway clearances — most units are 20–24\" diameter and 60–70\" tall",
            ],
        },
        {
            "title": "Handle the Electrical Work First",
            "summary": f"{'Switching from gas requires electrical upgrades before the plumber arrives.' if switching_from_gas else 'Switching from electric resistance simplifies the install significantly.'}",
            "bullets": electrical_bullets,
        },
        {
            "title": f"Right-Size Your Tank",
            "summary": f"A {tank_size}-gallon HPWH is the right size for your household.",
            "bullets": [
                f"Household of {household_size or '2'}: {tank_size}-gallon tank recommended",
                "HPWH recovery is slower than resistance — size up if you have high peak demand",
                "First-hour rating (FHR) matters more than tank size — check the EnergyGuide label",
                "Ask contractor for models with UEF (Uniform Energy Factor) ≥ 3.5",
            ],
        },
        {
            "title": "Review the Switching Economics",
            "summary": f"Switching from {water_heater_fuel} changes your water heating operating cost.",
            "bullets": [
                economics,
                f"Annual savings estimate: ${annual_savings:,.0f}/yr",
                "Ask for a 10-year operating cost comparison from your contractor",
            ],
        },
        {
            "title": "Claim Your Incentives",
            "summary": f"Incentives reduce your cost from ${gross_cost:,.0f} to ${net_cost:,.0f}.",
            "bullets": incentive_bullets,
        },
        {
            "title": "Set Operating Mode Correctly",
            "summary": f"Mode selection determines efficiency — heat pump mode is the default target.",
            "bullets": [
                "Set to 'Heat Pump' or 'Efficiency' mode — not 'Hybrid' or 'Electric' — for max savings",
                "Resistance backup mode costs 3.5× more per gallon — only use for high-demand periods",
                f"Expected payback: {payback_years if payback_years else 'N/A'} years at ${annual_savings:,.0f}/yr savings",
                "Schedule a check-in at 3 months to confirm mode settings and savings",
            ],
        },
    ]


def generate_heat_pump_water_heater_steps(
    address: str,
    gross_cost: float,
    net_cost: float,
    annual_savings: float,
    payback_years: float | None,
    matched_incentives: list[dict],
    property_profile: dict,
    rates: dict,
    contractors: list[dict],
) -> list[dict]:
    prompt = _build_prompt(
        address, gross_cost, net_cost, annual_savings, payback_years,
        matched_incentives, property_profile, rates, contractors,
    )
    steps = _call_anthropic(prompt)
    if not steps:
        steps = _fallback_steps(
            gross_cost, net_cost, annual_savings, payback_years,
            matched_incentives, property_profile, rates, contractors,
        )
    return steps
