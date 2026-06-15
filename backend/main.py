import os
from pathlib import Path
from typing import Optional

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
)
from services.building_classifier import HOMEOWNER_MODE, classify_retrofit_mode
from services.building_retrofit_model import (
    analyze_building_retrofit,
    build_building_retrofit_request,
    building_summary,
)
from services.llm_summary import summarize_retrofit_calculation
from services.property_data import get_property_and_solar_data
from services.questionnaire import get_next_question
from services.rentcast_api import get_pre_filled_answers
from services.retrofit_analyzer import analyze_retrofit_incentives
from services.retrofit_calculator import calculate_retrofit_options
from services.retrofit_request_builder import build_retrofit_calculation_request


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
    mode: Optional[str] = None
    role: Optional[str] = None
    scope: Optional[str] = None


class QuestionnaireNextRequest(BaseModel):
    answers: dict


class GeneratePlanRequest(BaseModel):
    address: str
    answers: dict
    mode: Optional[str] = None
    role: Optional[str] = None
    scope: Optional[str] = None

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


@app.post("/property-lookup")
def property_lookup(request: PropertyLookupRequest):
    try:
        pre_filled = get_pre_filled_answers(request.address)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"RentCast API error: {exc}") from exc

    meta = pre_filled.pop("_property_meta", {})
    mode = classify_retrofit_mode(
        {**pre_filled, "_property_meta": meta, "role": request.role, "scope": request.scope},
        requested_mode=request.mode,
    )
    return {"pre_filled": pre_filled, "meta": meta, "mode": mode, "role": request.role, "scope": request.scope}


@app.post("/questionnaire/next")
def questionnaire_next(request: QuestionnaireNextRequest):
    return get_next_question(request.answers)


@app.post("/generate-plan", response_model=RetrofitSummaryResponse)
async def generate_plan(request: GeneratePlanRequest):
    request_context = _request_context(request)
    monthly_bill = _money_to_float(request.answers.get("monthly_electricity_bill"))
    try:
        combined = await get_property_and_solar_data(request.address, monthly_bill)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Property or solar API error: {exc}") from exc

    solar_data = combined.get("_solar_data")
    answers = {**combined, **request.answers, **request_context}
    if "_property_meta" not in answers and combined.get("_property_meta"):
        answers["_property_meta"] = combined["_property_meta"]

    mode = classify_retrofit_mode(answers, requested_mode=request.mode)
    if mode != HOMEOWNER_MODE:
        building_request = build_building_retrofit_request(
            address=request.address,
            answers=answers,
            mode=mode,
        )
        building_analysis = analyze_building_retrofit(building_request)
        return RetrofitSummaryResponse(
            mode=mode,
            building_analysis=building_analysis,
            llm_summary=building_summary(building_analysis),
            summary_source="building_mode",
            model=None,
        )

    calculation_request = build_retrofit_calculation_request(
        address=request.address,
        answers=answers,
        solar_data=solar_data,
    )
    calculation = calculate_retrofit_options(calculation_request)
    summary = summarize_retrofit_calculation(calculation)
    return _copy_summary_with_mode(summary, HOMEOWNER_MODE)


@app.post("/generate-plan/", response_model=RetrofitSummaryResponse)
async def generate_plan_slash(request: GeneratePlanRequest):
    return await generate_plan(request)


def _money_to_float(value) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = "".join(char for char in str(value) if char.isdigit() or char == ".")
    return float(cleaned) if cleaned else 0.0


def _request_context(request: GeneratePlanRequest) -> dict:
    context = {}
    if request.mode:
        context["mode"] = request.mode
    if request.role:
        context["role"] = request.role
    if request.scope:
        context["scope"] = request.scope
    return context


def _copy_summary_with_mode(summary: RetrofitSummaryResponse, mode: str) -> RetrofitSummaryResponse:
    if hasattr(summary, "model_copy"):
        return summary.model_copy(update={"mode": mode})
    return summary.copy(update={"mode": mode})
