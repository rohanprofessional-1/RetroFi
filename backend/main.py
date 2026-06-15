from fastapi import FastAPI, HTTPException
from sqlmodel import SQLModel, Session, create_engine
from models import Property, RetrofitPlan, Upgrade, Incentive

app = FastAPI(title="RetroFi ATL API", description="AI-powered retrofit planner API")

# Connect to a local SQLite database for boilerplate/development for now,
# but can easily be swapped for Postgres later as per the stack requirements.
sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

engine = create_engine(sqlite_url, echo=True)

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)

@app.get("/")
def read_root():
    return {"message": "Welcome to the RetroFi ATL API"}

@app.post("/generate-plan/")
def generate_plan(address: str):
    # Placeholder for the main generation logic:
    # 1. Fetch Property Data (Zillow/ATTOM)
    # 2. Fetch Solar Potential (Google Solar API)
    # 3. Fetch Incentives (Rewiring America)
    # 4. Generate AI Plan (OpenAI/Gemini)
    
    return {
        "status": "success",
        "message": f"Plan generated for {address}",
        "plan": {
            "address": address,
            "estimated_savings": 1200,
            "upgrades": ["Heat Pump", "Insulation"]
        }
    }
