"""Structured incentive program schema for the calculation layer.

This module defines the canonical Pydantic models that the optimizer reads.
The schema is designed to support timeline optimization, cap pool resolution,
subsidy basis reduction, and stacking rules.

Phase 1 fields (15 core optimizer fields):
    cap_category, resets_annually, step_down_schedule, expires_year,
    subsidy_basis_reduction, amount_type, amount_flat, amount_percent,
    annual_cap, lifetime_cap, income_tier, tax_liability_required,
    stackable, exclusive_with, claim_timing

Phase 2/3 fields are present but optional for forward compatibility.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Amount rule
# ---------------------------------------------------------------------------

class AmountRule(BaseModel):
    """How much the incentive is worth."""

    amount_type: Literal[
        "tax_credit", "rebate", "grant", "loan", "rate_discount"
    ]
    amount_flat: Optional[float] = None
    amount_percent: Optional[float] = None
    annual_cap: Optional[float] = None
    lifetime_cap: Optional[float] = None
    per_unit_rate: Optional[float] = None
    per_unit_basis: Optional[str] = None  # "sq_ft", "kw", "btu_hr"
    min_project_cost: Optional[float] = None

    def calculate(self, gross_cost: float, prior_rebates: float = 0) -> float:
        """Return the dollar value of this incentive for a given project cost.

        ``prior_rebates`` is used when subsidy basis reduction applies —
        the cost basis is reduced by previously received rebates before
        calculating the credit.
        """
        effective_cost = max(gross_cost - prior_rebates, 0)

        if self.amount_flat is not None:
            amount = self.amount_flat
        elif self.amount_percent is not None:
            amount = effective_cost * self.amount_percent
        elif self.per_unit_rate is not None:
            # Caller must pass gross_cost as quantity * unit_cost for this case.
            amount = effective_cost * self.per_unit_rate
        else:
            return 0.0

        if self.annual_cap is not None:
            amount = min(amount, self.annual_cap)
        if self.lifetime_cap is not None:
            amount = min(amount, self.lifetime_cap)
        if self.min_project_cost is not None and gross_cost < self.min_project_cost:
            return 0.0
        return round(amount, 2)


# ---------------------------------------------------------------------------
# Step-down schedule
# ---------------------------------------------------------------------------

class StepDownEntry(BaseModel):
    """A single year in a declining incentive schedule."""

    year: int
    rate: float  # e.g., 0.30 for 30%


# ---------------------------------------------------------------------------
# Incentive program (the core model)
# ---------------------------------------------------------------------------

class IncentiveProgram(BaseModel):
    """Structured representation of a single incentive program.

    This is the canonical record the calculation layer reads.
    Each record represents one program × one upgrade category pairing
    (e.g., 25C for heat pumps is separate from 25C for insulation).
    """

    # Identity
    program_id: str
    name: str
    source_program_id: Optional[str] = None  # parent program (e.g., "irs-25c")

    # What upgrades it covers
    eligible_upgrades: List[str] = Field(default_factory=list)

    # ---------- Phase 1: Core optimizer fields (15) ----------

    # Amount
    amount_rule: AmountRule

    # Cap pooling — which upgrades share a cap
    cap_category: Optional[str] = None  # e.g., "25c-heat-pump-equipment"

    # Temporal
    resets_annually: bool = False
    available_from_year: Optional[int] = None
    expires_year: Optional[int] = None
    step_down_schedule: Optional[List[StepDownEntry]] = None
    claim_timing: Optional[str] = None  # "tax_filing", "point_of_sale", "within_90_days"

    # Eligibility
    income_tier: Optional[str] = None  # "any", "below_150_ami", "below_80_ami"
    income_max_absolute: Optional[float] = None
    income_max_ami_percent: Optional[int] = None
    tax_liability_required: bool = False

    # Stacking
    stackable: bool = True
    subsidy_basis_reduction: bool = False  # IRS rule: rebate reduces 25C cost basis
    exclusive_with: List[str] = Field(default_factory=list)  # program_ids this conflicts with

    # ---------- Phase 2: Eligibility detail fields ----------

    ownership_required: bool = True
    primary_residence_required: bool = True
    home_type_eligible: List[str] = Field(default_factory=lambda: ["single_family"])
    equipment_certification: Optional[str] = None
    contractor_required: Optional[bool] = None
    energy_audit_required: bool = False

    # ---------- Phase 3: Availability signals ----------

    program_status: str = "active"  # active / pending / suspended / expired
    availability_type: Optional[str] = None  # "always", "pool_limited", "income_waitlisted"
    data_confidence: str = "medium"  # high / medium / low
    last_verified_date: Optional[str] = None

    # ---------- Geographic ----------

    geographic_scope: str = "federal"  # "federal", "state", "utility", "local"
    state: Optional[str] = None  # two-letter code, e.g., "ga"
    utility_territory: Optional[str] = None

    # ---------- Source linkage ----------

    source_url: Optional[str] = None
    citation_chunk_ids: List[str] = Field(default_factory=list)

    # ---------- Computed helpers ----------

    def effective_rate(self, tax_year: int) -> Optional[float]:
        """Return the effective percentage rate for a given tax year.

        Accounts for step-down schedules. Returns None if the program
        has expired or is not yet available.
        """
        if self.expires_year is not None and tax_year > self.expires_year:
            return None
        if self.available_from_year is not None and tax_year < self.available_from_year:
            return None

        if self.step_down_schedule:
            # Find the applicable rate for the given year
            applicable = [
                entry for entry in self.step_down_schedule if entry.year <= tax_year
            ]
            if applicable:
                return max(applicable, key=lambda e: e.year).rate
            # Before the first step-down year — use the base rate
            return self.amount_rule.amount_percent

        return self.amount_rule.amount_percent

    def calculate_amount(
        self,
        gross_cost: float,
        prior_rebates: float = 0,
        tax_year: int = 2026,
    ) -> float:
        """Calculate the dollar amount of this incentive.

        Handles step-down schedules and subsidy basis reduction.
        """
        effective_basis = prior_rebates if self.subsidy_basis_reduction else 0

        # If there's a step-down schedule, override the rate for this year
        if self.step_down_schedule:
            rate = self.effective_rate(tax_year)
            if rate is None:
                return 0.0
            # Create a temporary amount rule with the adjusted rate
            adjusted = self.amount_rule.model_copy(update={"amount_percent": rate})
            return adjusted.calculate(gross_cost, effective_basis)

        return self.amount_rule.calculate(gross_cost, effective_basis)


# ---------------------------------------------------------------------------
# Extraction review item (for human review of LLM-extracted records)
# ---------------------------------------------------------------------------

class ExtractionReviewItem(BaseModel):
    """A low-confidence extraction needing human verification."""

    program: IncentiveProgram
    source_chunk_text: str = ""
    extraction_confidence: float = 0.0  # 0.0 to 1.0
    uncertain_fields: List[str] = Field(default_factory=list)
    review_notes: str = ""


# ---------------------------------------------------------------------------
# Cap pool resolution
# ---------------------------------------------------------------------------

class CapPool(BaseModel):
    """A group of programs sharing a single cap."""

    cap_category: str
    annual_cap: Optional[float] = None
    lifetime_cap: Optional[float] = None
    resets_annually: bool = False
    program_ids: List[str] = Field(default_factory=list)


def build_cap_pools(programs: List[IncentiveProgram]) -> Dict[str, CapPool]:
    """Group programs by cap_category to resolve shared caps.

    Example: heat pump + HPWH both have cap_category "25c-heat-pump-equipment"
    → they share a single $2,000 annual cap, not $2,000 each.
    """
    pools: Dict[str, CapPool] = {}
    for program in programs:
        category = program.cap_category
        if not category:
            continue
        if category not in pools:
            pools[category] = CapPool(
                cap_category=category,
                annual_cap=program.amount_rule.annual_cap,
                lifetime_cap=program.amount_rule.lifetime_cap,
                resets_annually=program.resets_annually,
            )
        pools[category].program_ids.append(program.program_id)
    return pools


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------

def load_programs(path: Path) -> List[IncentiveProgram]:
    """Load and validate incentive programs from a JSON file."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return [IncentiveProgram.model_validate(record) for record in raw]


def load_all_programs(
    data_dir: Path,
    state_code: Optional[str] = None,
) -> List[IncentiveProgram]:
    """Load federal programs plus optional state-specific programs.

    Always loads incentive_programs_federal.json.
    If state_code is provided, also loads incentive_programs_{state_code}.json.
    """
    federal = load_programs(data_dir / "incentive_programs_federal.json")
    if state_code:
        state = load_programs(data_dir / f"incentive_programs_{state_code}.json")
        return federal + state
    return federal
