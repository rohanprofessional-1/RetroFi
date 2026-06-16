from datetime import datetime
from typing import List, Literal, Optional

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
    # New structured fields (Phase 1)
    cap_category: Optional[str] = None
    resets_annually: Optional[bool] = None
    tax_liability_required: Optional[bool] = None
    amount_type: Optional[str] = None
    subsidy_basis_reduction: Optional[bool] = None
    cap_pool_note: Optional[str] = None
    tax_liability_note: Optional[str] = None
    exclusive_with: List[str] = Field(default_factory=list)


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


class PropertyProfile(BaseModel):
    address: str
    zip_code: Optional[str] = None
    home_type: Optional[str] = None
    year_built: Optional[int] = None
    square_footage: Optional[int] = None
    bedrooms: Optional[int] = None
    stories: Optional[float] = None
    heating_fuel: Optional[str] = None
    cooling_type: Optional[str] = None
    water_heater_fuel: Optional[str] = None


class HouseholdProfile(BaseModel):
    household_income: Optional[float] = None
    household_size: Optional[int] = None
    owner_occupied: Optional[bool] = None
    tax_liability_estimate: Optional[float] = None
    utility: Optional[str] = None
    electric_rate_per_kwh: Optional[float] = None
    gas_rate_per_therm: Optional[float] = None


class SolarPotentialInput(BaseModel):
    solar_viable: bool = False
    max_array_panels: Optional[int] = None
    yearly_energy_dc_kwh: Optional[float] = None
    installed_system_kw: Optional[float] = None
    estimated_install_cost: Optional[float] = None
    annual_sunshine_hours: Optional[float] = None
    roof_segment_count: Optional[int] = None


class RetcastInput(BaseModel):
    baseline_annual_kwh: Optional[float] = None
    baseline_annual_therms: Optional[float] = None
    projected_annual_kwh: Optional[float] = None
    projected_annual_therms: Optional[float] = None
    grid_carbon_kg_per_kwh: Optional[float] = None
    gas_carbon_kg_per_therm: Optional[float] = None
    confidence: Optional[str] = None


class RetrofitCalculationRequest(BaseModel):
    property: PropertyProfile
    household: HouseholdProfile = Field(default_factory=HouseholdProfile)
    solar: Optional[SolarPotentialInput] = None
    retcast: Optional[RetcastInput] = None
    upgrade_interests: List[str] = Field(default_factory=list)
    focus: Literal["cost", "carbon", "balanced"] = "balanced"
    budget_per_year: Optional[float] = None       # per-year spend ceiling; triggers the timeline pass
    planning_horizon_years: int = 5               # T in the math, default 5
    discount_rate: float = 0.05                   # r for NPV, default 5%
    current_year: int = Field(default_factory=lambda: datetime.now().year)


class RetrofitOptionCalculation(BaseModel):
    upgrade_key: str
    name: str
    description: str
    rank: int
    gross_cost: float
    incentive_total: float
    net_cost: float
    annual_savings: float
    carbon_avoided_tons: float
    payback_years: Optional[float]
    score: float
    confidence: str
    matched_incentives: List[IncentiveMatch]
    citations: List[str]
    calculation_notes: List[str]
    recommended_sequence: int = 0
    sequence_notes: List[str] = Field(default_factory=list)


class RetrofitCalculationTotals(BaseModel):
    gross_cost: float
    incentive_total: float
    net_cost: float
    annual_savings: float
    carbon_avoided_tons: float


class LlmContext(BaseModel):
    homeowner_summary_facts: List[str]
    ranked_option_facts: List[str]
    assumptions: List[str]
    missing_inputs: List[str]
    citation_snippets: List[str]


class TimelineYear(BaseModel):
    year: int                                  # calendar year
    upgrades: List[str]                        # upgrade_keys scheduled this year
    outlay: float                              # cash out of pocket this year
    incentives_captured: float                 # incentives received (with timing lag)
    annual_savings_added: float                # new savings unlocked this year
    cumulative_savings_pv: float               # PV of savings from this cohort through the horizon
    cap_sharing_notes: List[str] = Field(default_factory=list)  # e.g. "HP+HPWH split $2000 25C cap"


class TimelineUpgradeDetail(BaseModel):
    upgrade_key: str
    scheduled_year: Optional[int] = None       # calendar year, or None if skipped
    skipped_reason: Optional[str] = None       # "over_budget", "dependency_unmet", "dominated"
    incentive_value: float                     # total incentive captured in the scheduled year
    incentive_confidence: float                # 0-1, drives UI caveat display
    npv: float                                 # NPV over the horizon
    carbon_value: float                        # cumulative carbon avoided (tons) over the horizon
    score: float                               # focus-weighted normalized score
    data_gaps: List[str] = Field(default_factory=list)  # fields that were None, for UI transparency


class RetrofitTimeline(BaseModel):
    years: List[TimelineYear]                  # indexed by calendar year
    upgrade_details: List[TimelineUpgradeDetail]
    total_npv: float
    total_carbon_avoided_tons: float
    focus: str                                 # "cost" / "carbon" / "balanced"
    planning_horizon_years: int
    key_insight: Optional[str] = None          # e.g. staggering captures extra federal credits


class RetrofitCalculationResponse(BaseModel):
    address: str
    ranked_options: List[RetrofitOptionCalculation]
    totals: RetrofitCalculationTotals
    assumptions: AnalysisAssumptions
    citations: List[SourceCitation]
    llm_context: LlmContext
    sequencing_focus: str = "balanced"
    timeline: Optional[RetrofitTimeline] = None


class RetrofitSummaryResponse(BaseModel):
    calculation: RetrofitCalculationResponse
    llm_summary: str
    summary_source: str
    model: Optional[str] = None
    solar_data: Optional[dict] = None
    property_profile: Optional[dict] = None


class SequenceRetrofitRequest(BaseModel):
    ranked_options: List[RetrofitOptionCalculation]
    focus: Literal["cost", "carbon", "balanced"] = "balanced"


class SequenceRetrofitResponse(BaseModel):
    ranked_options: List[RetrofitOptionCalculation]
    sequencing_focus: str


class ActionStepsRequest(BaseModel):
    address: str
    upgrade_key: str
    gross_cost: float = 0
    net_cost: float = 0
    annual_savings: float = 0
    payback_years: Optional[float] = None
    matched_incentives: List[dict] = Field(default_factory=list)
    property_profile: Optional[dict] = None
    coordinates: Optional[dict] = None


class ActionStepsResponse(BaseModel):
    steps: List["SolarStep"]
    nearby_contractors: List["NearbyInstaller"]
    source: str


class SolarActionStepsRequest(BaseModel):
    address: str
    solar_data: dict
    matched_incentives: List[dict] = Field(default_factory=list)


class NearbyInstaller(BaseModel):
    name: str
    rating: float
    ratings_count: int
    vicinity: str
    place_id: str
    lat: Optional[float] = None
    lng: Optional[float] = None


class SolarStep(BaseModel):
    title: str
    summary: str
    bullets: List[str]


class SolarActionStepsResponse(BaseModel):
    steps: List[SolarStep]
    nearby_installers: List[NearbyInstaller]
    source: str
