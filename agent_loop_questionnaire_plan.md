# Agent Loop Questionnaire Plan

## Model and Agent to Use
- Claude Sonnet 4.6
- Create a Claude agent that will run the loop described below.

## What The Loop Should Do
- The loop should determine what additional data is needed to help the customer.
- The loop will send data to the Google Solar API and a RAG index that analyzes finanacial incentives and rebates for a specific address and based on that it should identify what other data is needed.
- There will be a profile that contains that the loop is told that is needed. It should go until that profile is completed.
- A maximum of 10 questions should be asked to the user.

## Step 0 — Pre-fill from RentCast (Before Any Questions)

Before the LLM loop starts, call `get_pre_filled_answers(address)` in `backend/services/rentcast_api.py`.
RentCast returns public property record data that can automatically answer several questionnaire fields:

| Questionnaire Field | RentCast Source Field |
|---|---|
| Home ownership status | `ownerOccupied` (bool) |
| Home type | `propertyType` |
| Year built | `yearBuilt` |
| Primary heating fuel | inferred from `features.heatingType` |
| Roof type | `features.roofType` |
| Square footage | `squareFootage` |
| Number of occupants | estimated from `bedrooms` |

Any field that is `None` after this step must be asked in the LLM loop.
Fields **not** available from RentCast (always ask): monthly electricity bill, monthly gas bill, appliance fuel (water heating + cooking), EV ownership/plans, primary goal, roof replacement plans, planned electric additions.

---

## Questionnaire Priority

Questions are prioritized by their direct impact on Solar API accuracy and AI recommendation quality.
Only ask questions for fields that RentCast could not pre-fill.

### Priority 1 — Essential (directly feed into API calls)
These must be asked first. They are required for `financialAnalyses` in the Solar API and for correctly sizing the system.

1. **Monthly electricity bill (or annual kWh)** — required for `financialAnalyses` in the Solar API and for sizing the system correctly
2. **Monthly gas bill** — needed to calculate heat pump savings vs. current heating cost
3. **Do you own this home, or are you renting/leasing?** — incentives are only available to owners; renters get a different set of options *(skip if `ownerOccupied` was returned by RentCast)*
4. **Is your heating, water heating, and cooking primarily electric or gas?** — determines the full electrification load and which upgrade path makes financial sense *(heating fuel may be partially inferred from RentCast `heatingType`; water heating and cooking must always be asked)*
5. **Roof type** (asphalt shingle, metal, tile, flat, etc.) — affects solar panel mounting, suitability, and install cost *(skip if returned by RentCast `features.roofType`)*

### Priority 2 — High-Value (dramatically improves AI recommendations)
Ask these next if question budget allows.

5. **Home type** (single family, condo, townhouse) — affects what upgrades are even possible *(skip if returned by RentCast `propertyType`)*
6. **Year built** — homes before ~1980 often need insulation/air sealing before other upgrades, or savings projections will be wrong *(skip if returned by RentCast `yearBuilt`)*
7. **Primary heating fuel** (gas, electric, oil, propane) — determines which upgrade path makes financial sense *(skip if inferred from RentCast `heatingType`)*
8. **Do you currently own an EV, or plan to buy one in the next 3 years?** — significantly affects panel sizing and total system load
9. **Are you planning a roof replacement in the next 5 years?** — affects whether solar is recommended now or deferred
10. **What is your primary goal?** (lower bills / backup power during outages / reduce carbon / increase home value) — shapes which upgrades are surfaced first

### Priority 3 — Nice to Have (can be skipped or made optional)
Ask only if questions remain within the 10-question budget.

- **Approximate square footage** — improves heat pump sizing estimates *(skip if returned by RentCast `squareFootage`)*
- **Number of occupants** — affects hot water heater sizing *(skip if estimated from RentCast `bedrooms`)*
- **Any existing upgrades** (already have solar, new HVAC, etc.) — avoids redundant recommendations
- **Are you planning other major electric additions?** (pool, hot tub, ADU, workshop, battery backup) — affects panel and system sizing
