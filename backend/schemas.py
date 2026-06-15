from typing import List, Optional

from pydantic import BaseModel, Field


class IncentiveAnalysisRequest(BaseModel):
    address: str
    zip_code: Optional[str] = None
    home_type: Optional[str] = None
    year_built: Optional[int] = None
    square_footage: Optional[int] = None
    household_income: Optional[float] = None
    owner_occupied: Optional[bool] = None
    utility: Optional[str] = None
    market_segment: str = "homeowner"
    role: Optional[str] = None
    building_type: Optional[str] = None
    units: Optional[int] = None
    utility_structure: Optional[str] = None
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


class RetrofitPreferences(BaseModel):
    primary_goal: Optional[str] = None
    roof_type: Optional[str] = None
    roof_replacement_status: Optional[str] = None
    ev_owner_or_planning: Optional[str] = None
    planned_electric_additions: Optional[bool] = None


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
    preferences: RetrofitPreferences = Field(default_factory=RetrofitPreferences)
    solar: Optional[SolarPotentialInput] = None
    retcast: Optional[RetcastInput] = None
    upgrade_interests: List[str] = Field(default_factory=list)


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


class RetrofitCalculationResponse(BaseModel):
    address: str
    ranked_options: List[RetrofitOptionCalculation]
    totals: RetrofitCalculationTotals
    assumptions: AnalysisAssumptions
    citations: List[SourceCitation]
    llm_context: LlmContext


class BuildingUtilityHistoryInput(BaseModel):
    fuel_type: str
    months: int
    total_usage: Optional[float] = None
    total_cost: Optional[float] = None
    usage_unit: Optional[str] = None
    meter_scope: Optional[str] = None
    utility: Optional[str] = None


class BuildingRetrofitRequest(BaseModel):
    address: str
    mode: str = "building"
    role: Optional[str] = None
    scope: Optional[str] = None
    building_type: Optional[str] = None
    gross_floor_area: Optional[int] = None
    units: Optional[int] = None
    occupancy: Optional[int] = None
    year_built: Optional[int] = None
    owner_occupied: Optional[bool] = None
    utility: Optional[str] = None
    electric_utility: Optional[str] = None
    gas_utility: Optional[str] = None
    utility_structure: Optional[str] = None
    electric_metering: Optional[str] = None
    gas_metering: Optional[str] = None
    electric_bill_responsibility: Optional[str] = None
    gas_bill_responsibility: Optional[str] = None
    portfolio_manager_property_id: Optional[str] = None
    utility_history: List[BuildingUtilityHistoryInput] = Field(default_factory=list)
    existing_systems: List[str] = Field(default_factory=list)
    hvac_system_type: Optional[str] = None
    domestic_hot_water_type: Optional[str] = None
    roof_control: Optional[str] = None
    primary_goal: Optional[str] = None
    planning_horizon: Optional[str] = None
    capex_budget_range: Optional[str] = None


class BuildingRecommendation(BaseModel):
    package_key: str
    name: str
    description: str
    priority: int
    data_required: List[str] = Field(default_factory=list)
    confidence: str = "low"
    estimated_cost_range: Optional[str] = None
    estimated_annual_savings_range: Optional[str] = None
    owner_tenant_split_note: Optional[str] = None


class BuildingBenchmark(BaseModel):
    annual_electric_kwh: Optional[float] = None
    annual_gas_therms: Optional[float] = None
    annual_utility_cost: Optional[float] = None
    site_eui_kbtu_per_sq_ft: Optional[float] = None
    utility_cost_per_sq_ft: Optional[float] = None
    confidence: str = "low"
    notes: List[str] = Field(default_factory=list)


class BuildingRetrofitResponse(BaseModel):
    mode: str
    address: str
    building_type: Optional[str] = None
    gross_floor_area: Optional[int] = None
    units: Optional[int] = None
    missing_inputs: List[str]
    benchmarking_ready: bool
    data_completeness_score: int = 0
    benchmark: Optional[BuildingBenchmark] = None
    recommendations: List[BuildingRecommendation]
    eligible_incentives: List[IncentiveMatch] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    assumptions: AnalysisAssumptions


class RetrofitSummaryResponse(BaseModel):
    mode: str = "homeowner"
    calculation: Optional[RetrofitCalculationResponse] = None
    building_analysis: Optional[BuildingRetrofitResponse] = None
    llm_summary: str
    summary_source: str
    model: Optional[str] = None
