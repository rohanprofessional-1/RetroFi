PRIORITY_FIELDS = [
    (
        "monthly_electricity_bill",
        "What is your average monthly electricity bill?",
        "number",
        None,
    ),
    ("monthly_gas_bill", "What is your average monthly gas bill?", "number", None),
    (
        "home_ownership_status",
        "Do you own this home, or are you renting?",
        "choice",
        ["Own", "Rent / Lease"],
    ),
    (
        "appliances_fuel",
        "Is your water heating and cooking primarily electric or gas?",
        "choice",
        ["Electric", "Gas", "Mixed (both)"],
    ),
    (
        "roof_type",
        "What type of roof does your home have?",
        "choice",
        ["Asphalt Shingle", "Metal", "Tile", "Flat / TPO", "Other"],
    ),
    (
        "home_type",
        "What type of home do you live in?",
        "choice",
        ["Single Family", "Townhouse", "Condo / Apartment", "Other"],
    ),
    (
        "year_built",
        "Approximately when was your home built?",
        "choice",
        ["Before 1980", "1980 - 2000", "2001 - 2015", "After 2015"],
    ),
    (
        "primary_heating_fuel",
        "What is your primary heating fuel?",
        "choice",
        ["Gas", "Electric", "Oil", "Propane"],
    ),
    (
        "ev_owner_or_planning",
        "Do you own an EV, or plan to buy one in the next 3 years?",
        "choice",
        ["Yes, I own one", "Planning within 3 years", "No"],
    ),
    (
        "planning_roof_replacement",
        "Are you planning a roof replacement in the next 5 years?",
        "choice",
        ["Yes", "No", "Not sure"],
    ),
    (
        "square_footage",
        "What is the approximate square footage of your home?",
        "choice",
        ["Under 1,000 sq ft", "1,000 - 1,500 sq ft", "1,500 - 2,500 sq ft", "Over 2,500 sq ft"],
    ),
    (
        "num_occupants",
        "How many people live in your home?",
        "choice",
        ["1", "2", "3", "4", "5 or more"],
    ),
    (
        "planned_electric_additions",
        "Are you planning major electric additions?",
        "choice",
        ["Yes", "No"],
    ),
]
MAX_QUESTIONS = 10


def get_next_question(answers: dict) -> dict:
    if answers.get("_questions_asked", 0) >= MAX_QUESTIONS:
        return {"complete": True}

    for field_key, question, input_type, options in PRIORITY_FIELDS:
        if answers.get(field_key) is None:
            result = {
                "question": question,
                "field_key": field_key,
                "input_type": input_type,
            }
            if options is not None:
                result["options"] = options
            return result
    return {"complete": True}
