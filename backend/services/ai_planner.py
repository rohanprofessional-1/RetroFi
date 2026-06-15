import os
import json
import anthropic

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

# Each entry: (field_key, priority, question_text, input_type, options_or_None)
# input_type: "number" — free numeric entry; "choice" — tap-to-select buttons
PRIORITY_FIELDS = [
    # Priority 1 — Essential (always asked; RentCast cannot source these)
    ("monthly_electricity_bill", "P1", "What is your average monthly electricity bill?",
     "number", None),
    ("monthly_gas_bill", "P1", "What is your average monthly gas bill?",
     "number", None),
    ("home_ownership_status", "P1", "Do you own this home, or are you renting?",
     "choice", ["Own", "Rent / Lease"]),
    ("appliances_fuel", "P1", "Is your water heating and cooking primarily electric or gas?",
     "choice", ["Electric", "Gas", "Mixed (both)"]),
    ("roof_type", "P1", "What type of roof does your home have?",
     "choice", ["Asphalt Shingle", "Metal", "Tile", "Flat / TPO", "Other"]),
    # Priority 2 — High-Value (skip if RentCast pre-filled)
    ("home_type", "P2", "What type of home do you live in?",
     "choice", ["Single Family", "Townhouse", "Condo / Apartment", "Other"]),
    ("year_built", "P2", "Approximately when was your home built?",
     "choice", ["Before 1980", "1980 – 2000", "2001 – 2015", "After 2015"]),
    ("primary_heating_fuel", "P2", "What is your primary heating fuel?",
     "choice", ["Gas", "Electric", "Oil", "Propane"]),
    ("ev_owner_or_planning", "P2", "Do you own an EV, or plan to buy one in the next 3 years?",
     "choice", ["Yes, I own one", "Planning within 3 years", "No"]),
    ("planning_roof_replacement", "P2", "Are you planning a roof replacement in the next 5 years?",
     "choice", ["Yes", "No", "Not sure"]),
    ("primary_goal", "P2", "What is your primary goal?",
     "choice", ["Lower bills", "Backup power during outages", "Reduce carbon footprint", "Increase home value"]),
    # Priority 3 — Nice to Have (skip if RentCast pre-filled)
    ("square_footage", "P3", "What is the approximate square footage of your home?",
     "choice", ["Under 1,000 sq ft", "1,000 – 1,500 sq ft", "1,500 – 2,500 sq ft", "Over 2,500 sq ft"]),
    ("num_occupants", "P3", "How many people live in your home?",
     "choice", ["1", "2", "3", "4", "5 or more"]),
    ("planned_electric_additions", "P3", "Are you planning major electric additions (pool, hot tub, ADU, battery backup)?",
     "choice", ["Yes", "No"]),
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

    Questions are returned deterministically from the static PRIORITY_FIELDS list.
    """
    questions_asked = answers.get("_questions_asked", 0)
    if questions_asked >= MAX_QUESTIONS:
        return {"complete": True}

    # Find the next unfilled field in priority order
    missing = [
        (field, priority, hint, input_type, options)
        for field, priority, hint, input_type, options in PRIORITY_FIELDS
        if answers.get(field) is None
    ]

    if not missing:
        return {"complete": True}

    next_field, next_priority, hint, input_type, options = missing[0]
    result = {"question": hint, "field_key": next_field, "input_type": input_type}
    if options is not None:
        result["options"] = options
    return result


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
