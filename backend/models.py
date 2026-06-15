from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship

class PropertyBase(SQLModel):
    address: str
    square_footage: Optional[int] = None
    year_built: Optional[int] = None
    home_type: Optional[str] = None

class Property(PropertyBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Relationships
    plans: List["RetrofitPlan"] = Relationship(back_populates="property_")


class RetrofitPlanBase(SQLModel):
    property_id: int = Field(foreign_key="property.id")
    total_upfront_cost: Optional[float] = 0.0
    total_annual_savings: Optional[float] = 0.0
    total_carbon_avoided: Optional[float] = 0.0
    estimated_payback_years: Optional[float] = 0.0
    ai_summary_text: Optional[str] = None

class RetrofitPlan(RetrofitPlanBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Relationships
    property_: Property = Relationship(back_populates="plans")
    upgrades: List["Upgrade"] = Relationship(back_populates="plan")
    incentives: List["Incentive"] = Relationship(back_populates="plan")


class UpgradeBase(SQLModel):
    plan_id: int = Field(foreign_key="retrofitplan.id")
    name: str
    description: Optional[str] = None
    rank_order: int = 1
    estimated_cost: Optional[float] = 0.0
    annual_savings: Optional[float] = 0.0
    carbon_avoided: Optional[float] = 0.0

class Upgrade(UpgradeBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Relationships
    plan: RetrofitPlan = Relationship(back_populates="upgrades")


class IncentiveBase(SQLModel):
    plan_id: int = Field(foreign_key="retrofitplan.id")
    name: str
    source: str # e.g. "Rewiring America", "Local Utility"
    amount: float = 0.0
    incentive_type: str # e.g. "Tax Credit", "Rebate"

class Incentive(IncentiveBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Relationships
    plan: RetrofitPlan = Relationship(back_populates="incentives")
