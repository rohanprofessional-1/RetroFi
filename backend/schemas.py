from typing import List, Optional

from pydantic import BaseModel, Field


class IncentiveAnalysisRequest(BaseModel):
    address: str
    zip_code: Optional[str] = None
    home_type: Optional[str] = None
    year_built: Optional[int] = None
    square_footage: Optional[int] = None
    household_income: Optional[float] = None
    utility: Optional[str] = None
    upgrade_interests: List[str] = Field(default_factory=list)


class SourceCitation(BaseModel):
    id: str
    title: str
    source: str
    source_url: Optional[str] = None
    snippet: str


class IncentiveMatch(BaseModel):
    id: str
    name: str
    source: str
    incentive_type: str
    amount: float
    amount_description: str
    eligible_upgrades: List[str]
    eligibility_notes: str
    stackable: bool
    citation_id: str


class UpgradeAnalysis(BaseModel):
    upgrade_key: str
    name: str
    description: str
    rank: int
    gross_cost: float
    net_cost: float
    annual_savings: float
    carbon_avoided_tons: float
    payback_years: Optional[float]
    confidence: str
    matched_incentives: List[IncentiveMatch]
    citations: List[str]


class AnalysisAssumptions(BaseModel):
    location: str
    square_footage: int
    home_type: str
    utility: str
    notes: List[str]


class IncentiveAnalysisResponse(BaseModel):
    address: str
    summary: str
    ranked_upgrades: List[UpgradeAnalysis]
    eligible_incentives: List[IncentiveMatch]
    assumptions: AnalysisAssumptions
    citations: List[SourceCitation]
