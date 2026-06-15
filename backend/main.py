from dotenv import load_dotenv
load_dotenv()  # loads backend/.env before any service module reads os.getenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import SQLModel, create_engine
from models import Property, RetrofitPlan, Upgrade, Incentive
from services.rentcast_api import get_pre_filled_answers
from services.ai_planner import get_next_question, generate_retrofit_plan

app = FastAPI(title="RetroFi ATL API", description="AI-powered retrofit planner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url, echo=True)


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)


# ── Request body models ────────────────────────────────────────────────────────

class PropertyLookupRequest(BaseModel):
    address: str

class QuestionnaireNextRequest(BaseModel):
    answers: dict

class GeneratePlanRequest(BaseModel):
    address: str
    answers: dict


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/")
def read_root():
    return {"message": "Welcome to the RetroFi ATL API"}


@app.post("/property-lookup")
def property_lookup(req: PropertyLookupRequest):
    """
    Step 1 of the workflow: look up the property via RentCast and return
    all fields that can be pre-filled so the questionnaire only asks for
    data we don't already have.
    """
    try:
        pre_filled = get_pre_filled_answers(req.address)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"RentCast API error: {e}")

    meta = pre_filled.pop("_property_meta", {})
    return {"pre_filled": pre_filled, "meta": meta}


@app.post("/questionnaire/next")
def questionnaire_next(req: QuestionnaireNextRequest):
    """
    Step 2 of the workflow: stateless questionnaire driver.
    Accepts the current answers profile and returns either the next
    question to ask the user, or {complete: true} when all required
    fields are filled or the 10-question budget is exhausted.
    """
    try:
        result = get_next_question(req.answers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Questionnaire error: {e}")
    return result


@app.post("/generate-plan")
def generate_plan(req: GeneratePlanRequest):
    """
    Step 3 of the workflow: synthesise the completed answers profile into a
    full retrofit plan via the Claude LLM.
    """
    try:
        plan = generate_retrofit_plan(req.address, req.answers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plan generation error: {e}")
    return {"status": "success", "plan": plan}
