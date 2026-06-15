import os
import json
import anthropic

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

# Ordered list of questionnaire fields with their priority tier.
# The loop works through these in order, skipping any that are already
# filled by RentCast, and stops after 10 questions are asked.
PRIORITY_FIELDS = [
    # Priority 1 — Essential (always asked; RentCast cannot source these)
    ("monthly_electricity_bill", "P1", "What is your average monthly electricity bill?"),
    ("monthly_gas_bill", "P1", "What is your average monthly gas bill?"),
    ("home_ownership_status", "P1", "Do you own this home, or are you renting?"),
    ("appliances_fuel", "P1", "Is your water heating and cooking primarily electric or gas?"),
    ("roof_type", "P1", "What type of roof does your home have (e.g. asphalt shingle, metal, tile, flat)?"),
    # Priority 2 — High-Value (skip if RentCast pre-filled)
    ("home_type", "P2", "What type of home do you live in (single family, condo, townhouse)?"),
    ("year_built", "P2", "Approximately what year was your home built?"),
    ("primary_heating_fuel", "P2", "What is your primary heating fuel (gas, electric, oil, propane)?"),
    ("ev_owner_or_planning", "P2", "Do you currently own an EV, or plan to buy one in the next 3 years?"),
    ("planning_roof_replacement", "P2", "Are you planning a roof replacement in the next 5 years?"),
    ("primary_goal", "P2", "What is your primary goal — lower bills, backup power, reduce carbon, or increase home value?"),
    # Priority 3 — Nice to Have (skip if RentCast pre-filled)
    ("square_footage", "P3", "What is the approximate square footage of your home?"),
    ("num_occupants", "P3", "How many people live in your home?"),
    ("planned_electric_additions", "P3", "Are you planning any major electric additions such as a pool, hot tub, ADU, or battery backup?"),
]

MAX_QUESTIONS = 10


def get_next_question(answers: dict) -> dict:
    """
    Determines the next question to present to the user.

    Accepts the current answers dict (which starts as the RentCast pre-fill
    and grows with each user response).  Returns either:
      {"question": "...", "field_key": "..."}
    or:
      {"complete": True}

    The decision of *which* question to ask is delegated to Claude so that
    the phrasing can be contextualised by what the user has already told us.
    """
    questions_asked = answers.get("_questions_asked", 0)
    if questions_asked >= MAX_QUESTIONS:
        return {"complete": True}

    # Find the next unfilled field in priority order
    missing = [
        (field, priority, hint)
        for field, priority, hint in PRIORITY_FIELDS
        if answers.get(field) is None
    ]

    if not missing:
        return {"complete": True}

    next_field, next_priority, hint = missing[0]

    # Build a compact profile of what we know (exclude private meta keys)
    known = {
        k: v for k, v in answers.items()
        if not k.startswith("_") and v is not None
    }

    prompt = f"""You are a friendly home energy advisor helping a homeowner in Atlanta, GA get a personalised retrofit plan.

Homeowner profile so far:
{json.dumps(known, indent=2) if known else "(No information yet)"}

The next field we need to ask about is: "{next_field}" (hint: {hint})

Write a single, warm, conversational question to collect this information.
- 1–2 sentences max.
- Do not number the question or include any preamble.
- Return ONLY valid JSON in this exact shape, with no markdown fences:
{{"question": "<your question here>", "field_key": "{next_field}"}}"""

    try:
        response = _client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        result = json.loads(raw)
        # Guard: ensure field_key is present and correct
        result["field_key"] = next_field
        return result
    except Exception:
        # Fallback to the static hint if Claude is unavailable
        return {"question": hint, "field_key": next_field}


def generate_retrofit_plan(address: str, answers: dict) -> dict:
    """
    Uses Claude to synthesise the completed questionnaire profile into a
    structured retrofit plan that matches the Dashboard data shape.
    """
    meta = answers.get("_property_meta", {})
    profile = {k: v for k, v in answers.items() if not k.startswith("_") and v is not None}

    prompt = f"""You are a home energy retrofit advisor specialising in Atlanta, GA homes.

Property address: {address}
Public records data: {json.dumps(meta, indent=2)}

Homeowner answers:
{json.dumps(profile, indent=2)}

Generate a personalised retrofit plan. Return ONLY a valid JSON object (no markdown fences) with this exact shape:

{{
  "summary": "<2–3 sentence personalised summary referencing the homeowner's goals and home characteristics>",
  "metrics": {{
    "upfrontCost": <total estimated cost after incentives, integer dollars>,
    "annualSavings": <estimated annual dollar savings, integer>,
    "carbonAvoided": "<X.X tons>",
    "paybackYears": <estimated payback period, one decimal>
  }},
  "upgrades": [
    {{"id": 1, "name": "<upgrade name>", "cost": <integer dollars>, "savings": <integer dollars per year>}},
    ...
  ],
  "incentives": [
    {{"id": 1, "name": "<incentive name>", "amount": <integer dollars>, "type": "Tax Credit" | "Rebate" | "Grant"}},
    ...
  ]
}}

Rules:
- Include 2–4 of the most impactful upgrades given the profile.
- Include 2–4 relevant IRA tax credits and Georgia/Atlanta-specific rebates.
- Base numbers on realistic 2024–2025 estimates for Atlanta, GA.
- If primary_goal is null, default to "lower bills".
- Tailor the summary to reference the homeowner's primary_goal if provided."""

    try:
        response = _client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        plan = json.loads(raw.strip())
        plan["address"] = address
        return plan
    except Exception:
        # Graceful fallback so the UI never crashes
        return {
            "address": address,
            "summary": (
                "Based on your home profile, we recommend starting with a heat pump and "
                "improved attic insulation. Atlanta's climate and available IRA incentives "
                "make these upgrades particularly cost-effective."
            ),
            "metrics": {
                "upfrontCost": 14000,
                "annualSavings": 1100,
                "carbonAvoided": "3.8 tons",
                "paybackYears": 12.7,
            },
            "upgrades": [
                {"id": 1, "name": "Air Source Heat Pump", "cost": 10500, "savings": 750},
                {"id": 2, "name": "Attic Insulation (R-49)", "cost": 3500, "savings": 350},
            ],
            "incentives": [
                {"id": 1, "name": "Energy Efficient Home Improvement Credit (25C)", "amount": 2000, "type": "Tax Credit"},
                {"id": 2, "name": "Local Utility Rebate", "amount": 500, "type": "Rebate"},
            ],
        }
