import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from schemas import (
    IncentiveAnalysisRequest,
    IncentiveAnalysisResponse,
    RetrofitCalculationRequest,
    RetrofitCalculationResponse,
    RetrofitSummaryResponse,
    SequenceRetrofitRequest,
    SequenceRetrofitResponse,
    SolarActionStepsRequest,
    SolarActionStepsResponse,
    SolarStep,
)
from services.llm_summary import summarize_retrofit_calculation
from services.nearby_contractors import find_solar_installers
from services.property_data import get_property_and_solar_data
from services.questionnaire import get_next_question
from services.rentcast_api import get_pre_filled_answers
from services.retrofit_analyzer import analyze_retrofit_incentives
from services.retrofit_calculator import calculate_retrofit_options, compute_efficiency_lookup
from services.retrofit_request_builder import build_retrofit_calculation_request
from services.sequencing import sequence_options
from services.solar_action_steps import generate_solar_steps


BACKEND_ROOT = Path(__file__).resolve().parent
load_dotenv(BACKEND_ROOT.parent / ".env")
load_dotenv(BACKEND_ROOT / ".env")

try:
    from sqlmodel import SQLModel, create_engine
    import models  # Registers SQLModel tables for metadata creation.
except ModuleNotFoundError:
    SQLModel = None
    create_engine = None

app = FastAPI(title="RetroFi ATL API", description="AI-powered retrofit planner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PropertyLookupRequest(BaseModel):
    address: str


class QuestionnaireNextRequest(BaseModel):
    answers: dict


class GeneratePlanRequest(BaseModel):
    address: str
    answers: dict

# Connect to a local SQLite database for boilerplate/development for now,
# but can easily be swapped for Postgres later as per the stack requirements.
sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

engine = create_engine(sqlite_url, echo=True) if create_engine else None

@app.on_event("startup")
def on_startup():
    if SQLModel and engine:
        SQLModel.metadata.create_all(engine)

@app.get("/")
def read_root():
    return {"message": "Welcome to the RetroFi ATL API"}


@app.get("/config/google-maps")
def google_maps_config():
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("VITE_GOOGLE_API_KEY") or ""
    if not api_key:
        raise HTTPException(status_code=404, detail="Google Maps API key is not configured")
    return {"api_key": api_key}

@app.post("/analyze-incentives/", response_model=IncentiveAnalysisResponse)
def analyze_incentives(request: IncentiveAnalysisRequest):
    return analyze_retrofit_incentives(request)

@app.post("/calculate-retrofit/", response_model=RetrofitCalculationResponse)
def calculate_retrofit(request: RetrofitCalculationRequest):
    return calculate_retrofit_options(request)

@app.post("/summarize-retrofit/", response_model=RetrofitSummaryResponse)
def summarize_retrofit(request: RetrofitCalculationRequest):
    calculation = calculate_retrofit_options(request)
    return summarize_retrofit_calculation(calculation)


@app.post("/sequence-retrofit/", response_model=SequenceRetrofitResponse)
def sequence_retrofit(request: SequenceRetrofitRequest):
    efficiency_lookup = compute_efficiency_lookup(request.ranked_options)
    sequenced = sequence_options(
        request.ranked_options, focus=request.focus, efficiency_lookup=efficiency_lookup
    )
    return SequenceRetrofitResponse(ranked_options=sequenced, sequencing_focus=request.focus)


@app.post("/property-lookup")
def property_lookup(request: PropertyLookupRequest):
    try:
        pre_filled = get_pre_filled_answers(request.address)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"RentCast API error: {exc}") from exc

    meta = pre_filled.pop("_property_meta", {})
    return {"pre_filled": pre_filled, "meta": meta}


@app.post("/questionnaire/next")
def questionnaire_next(request: QuestionnaireNextRequest):
    return get_next_question(request.answers)


@app.post("/generate-plan", response_model=RetrofitSummaryResponse)
async def generate_plan(request: GeneratePlanRequest):
    monthly_bill = _money_to_float(request.answers.get("monthly_electricity_bill"))
    try:
        combined = await get_property_and_solar_data(request.address, monthly_bill)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Property or solar API error: {exc}") from exc

    solar_data = combined.get("_solar_data")
    answers = {**combined, **request.answers}
    if "_property_meta" not in answers and combined.get("_property_meta"):
        answers["_property_meta"] = combined["_property_meta"]

    calculation_request = build_retrofit_calculation_request(
        address=request.address,
        answers=answers,
        solar_data=solar_data,
    )
    calculation = calculate_retrofit_options(calculation_request)
    summary = summarize_retrofit_calculation(calculation)
    return summary.model_copy(update={"solar_data": solar_data})


@app.post("/generate-plan/", response_model=RetrofitSummaryResponse)
async def generate_plan_slash(request: GeneratePlanRequest):
    return await generate_plan(request)


@app.post("/solar-action-steps", response_model=SolarActionStepsResponse)
async def solar_action_steps(request: SolarActionStepsRequest):
    coords = request.solar_data.get("coordinates") or {}
    lat = coords.get("lat")
    lng = coords.get("lng")

    installers = []
    if lat is not None and lng is not None:
        installers = await find_solar_installers(lat, lng)

    steps = generate_solar_steps(
        solar_data=request.solar_data,
        matched_incentives=request.matched_incentives,
        address=request.address,
        installers=installers,
    )
    return SolarActionStepsResponse(
        steps=[SolarStep(**s) for s in steps],
        nearby_installers=installers,
        source="ai" if steps else "fallback",
    )


def _money_to_float(value) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = "".join(char for char in str(value) if char.isdigit() or char == ".")
    return float(cleaned) if cleaned else 0.0
