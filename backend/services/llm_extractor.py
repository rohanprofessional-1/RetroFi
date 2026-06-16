"""LLM-powered extraction of structured IncentiveProgram records from source chunks.

Uses a local qwen2.5:7b model via Ollama to extract structured incentive program
data from raw text chunks parsed from source documents (HTML/PDF).

The extraction pipeline:
1. Groups chunks by detected program context
2. Sends each group to the LLM with a structured JSON extraction prompt
3. Validates responses against the IncentiveProgram Pydantic schema
4. Deduplicates and merges records from multiple chunks for the same program
5. Flags low-confidence extractions for human review
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen

from services.incentive_program_schema import (
    AmountRule,
    ExtractionReviewItem,
    IncentiveProgram,
)
from services.source_parsers import SourceChunk


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "qwen2.5:7b"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT = 120  # 7B model needs more time for structured extraction
DEFAULT_NUM_CTX = 8192

# Fields the LLM should extract (Phase 1 core fields)
EXTRACTION_SCHEMA = {
    "program_id": "Unique slug identifier, e.g., 'ny-empower-plus-heat-pump'",
    "name": "Human-readable program name",
    "source_program_id": "Parent program ID if this is a sub-program, else null",
    "eligible_upgrades": "List from: heat_pump, heat_pump_water_heater, attic_insulation, air_sealing, duct_sealing, electric_cooking, heat_pump_clothes_dryer, smart_thermostat, solar, battery_storage, electrical_panel",
    "amount_rule": {
        "amount_type": "One of: tax_credit, rebate, grant, loan, rate_discount",
        "amount_flat": "Fixed dollar amount or null",
        "amount_percent": "Decimal percentage (0.30 = 30%) or null",
        "annual_cap": "Maximum claimable per year in dollars or null",
        "lifetime_cap": "Maximum per household ever or null",
    },
    "cap_category": "Slug grouping upgrades that share a cap, e.g., 'ny-empower-plus' or null",
    "resets_annually": "Boolean: does the cap reset each year?",
    "expires_year": "Year the program expires (integer) or null",
    "step_down_schedule": "List of {year, rate} objects or null",
    "claim_timing": "One of: tax_filing, point_of_sale, within_90_days, or null",
    "income_tier": "One of: any, below_150_ami, below_80_ami, or null",
    "income_max_absolute": "Dollar ceiling for eligibility or null",
    "tax_liability_required": "Boolean: is this a tax credit requiring tax liability?",
    "stackable": "Boolean: can this be combined with other incentives?",
    "subsidy_basis_reduction": "Boolean: does receiving this reduce cost basis for other credits?",
    "exclusive_with": "List of program_ids this cannot be combined with, or empty list",
    "contractor_required": "Boolean or null",
    "energy_audit_required": "Boolean",
    "program_status": "One of: active, pending, suspended, expired",
    "data_confidence": "Your confidence: high, medium, or low",
}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert at extracting structured incentive program data from government and utility documents.

You will receive a raw text chunk from a source document about energy efficiency incentive programs. Extract ALL distinct incentive programs mentioned in the text.

For each program, output a JSON object with these fields:
{schema}

CRITICAL RULES:
- Output ONLY a JSON array of objects. No markdown, no explanation, no code fences.
- Each object represents ONE program × ONE upgrade category pairing.
- If a program covers multiple upgrade types with DIFFERENT amounts, create SEPARATE objects for each.
- If a program covers multiple upgrade types with the SAME amount, list all upgrades in eligible_upgrades.
- Use decimal percentages (0.30 not 30).
- For dollar amounts, use plain numbers (2000 not "$2,000").
- Set data_confidence to "low" if the text is ambiguous or you're uncertain about key fields.
- If the text doesn't contain enough information to determine a field, use null.
- For tax credits, set tax_liability_required to true and amount_type to "tax_credit".
- For rebates, set subsidy_basis_reduction to true (rebates typically reduce cost basis for federal credits).
- program_id should be a lowercase slug: {{state}}-{{program_short_name}}-{{upgrade}}

If the text does not describe any incentive program, return an empty array: []"""


USER_PROMPT_TEMPLATE = """Extract incentive programs from this {state_upper} source document.

Source: {source_title}
Source type: {source_type}
State: {state_upper}

--- TEXT ---
{text}
--- END TEXT ---

Return a JSON array of IncentiveProgram objects. Remember: output ONLY valid JSON, no markdown."""


# ---------------------------------------------------------------------------
# Extraction pipeline
# ---------------------------------------------------------------------------

def extract_programs_from_chunks(
    chunks: List[SourceChunk],
    state: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
) -> Tuple[List[IncentiveProgram], List[ExtractionReviewItem]]:
    """Extract structured incentive programs from source chunks using LLM.

    Returns:
        programs: Validated IncentiveProgram records
        review_items: Records needing human verification
    """
    if not chunks:
        return [], []

    # Group chunks by source file for context
    chunks_by_source: Dict[str, List[SourceChunk]] = {}
    for chunk in chunks:
        source_key = chunk.source.path.name
        chunks_by_source.setdefault(source_key, []).append(chunk)

    all_raw_programs: List[Dict[str, Any]] = []
    extraction_metadata: List[Tuple[Dict[str, Any], str]] = []  # (raw_dict, chunk_text)

    for source_key, source_chunks in chunks_by_source.items():
        # Combine chunks from the same source for better context
        combined_text = "\n\n---\n\n".join(chunk.text for chunk in source_chunks)
        # Truncate to fit context window
        if len(combined_text) > 6000:
            combined_text = combined_text[:6000]

        source = source_chunks[0].source
        raw_programs = _call_extraction_llm(
            text=combined_text,
            source_title=source.title,
            source_type=source.source_type,
            state=state,
            model=model,
            base_url=base_url,
        )

        for raw in raw_programs:
            all_raw_programs.append(raw)
            extraction_metadata.append((raw, combined_text[:500]))

    # Validate, deduplicate, and separate review items
    programs: List[IncentiveProgram] = []
    review_items: List[ExtractionReviewItem] = []

    seen_ids: set = set()
    for raw, chunk_text in extraction_metadata:
        program, confidence = _validate_and_build(raw, state)
        if program is None:
            continue

        # Deduplicate by program_id
        if program.program_id in seen_ids:
            continue
        seen_ids.add(program.program_id)

        if confidence < 0.6 or program.data_confidence == "low":
            review_items.append(
                ExtractionReviewItem(
                    program=program,
                    source_chunk_text=chunk_text,
                    extraction_confidence=confidence,
                    uncertain_fields=_uncertain_fields(raw),
                    review_notes=f"LLM extraction confidence: {confidence:.0%}",
                )
            )
        else:
            programs.append(program)

    return programs, review_items


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call_extraction_llm(
    text: str,
    source_title: str,
    source_type: str,
    state: str,
    model: str,
    base_url: str,
) -> List[Dict[str, Any]]:
    """Call the local LLM to extract programs from a text chunk."""

    schema_str = json.dumps(EXTRACTION_SCHEMA, indent=2)
    system = SYSTEM_PROMPT.format(schema=schema_str)
    user = USER_PROMPT_TEMPLATE.format(
        state_upper=state.upper(),
        source_title=source_title,
        source_type=source_type,
        text=text,
    )

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0,
        "options": {
            "num_ctx": DEFAULT_NUM_CTX,
        },
        "format": "json",
    }

    endpoint = f"{base_url.rstrip('/')}/v1/chat/completions"
    request = Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"[LLM_EXTRACTOR] LLM call failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return []

    try:
        content = payload["choices"][0]["message"]["content"].strip()
        return _parse_llm_json(content)
    except (KeyError, IndexError) as exc:
        print(f"[LLM_EXTRACTOR] Response parsing failed: {exc}", file=sys.stderr)
        return []


def _parse_llm_json(content: str) -> List[Dict[str, Any]]:
    """Parse LLM response, handling common formatting issues."""
    # Strip markdown code fences if present
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    content = content.strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # Try to find a JSON array in the content
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                print(f"[LLM_EXTRACTOR] Could not parse JSON from response", file=sys.stderr)
                return []
        else:
            print(f"[LLM_EXTRACTOR] No JSON array found in response", file=sys.stderr)
            return []

    if isinstance(parsed, dict):
        # LLM returned a single object instead of an array
        return [parsed]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_and_build(
    raw: Dict[str, Any],
    state: str,
) -> Tuple[Optional[IncentiveProgram], float]:
    """Validate a raw dict and build an IncentiveProgram. Returns (program, confidence)."""

    confidence = 1.0

    # Ensure required fields
    if not raw.get("program_id"):
        return None, 0.0
    if not raw.get("name"):
        return None, 0.0

    # Fix common LLM issues
    raw = _normalize_raw(raw, state)

    # Validate amount_rule
    amount_rule = raw.get("amount_rule", {})
    if not isinstance(amount_rule, dict):
        return None, 0.0

    if "amount_type" not in amount_rule:
        amount_rule["amount_type"] = "rebate"
        confidence -= 0.2

    # Check that at least one amount field is set
    has_amount = any(
        amount_rule.get(f) is not None
        for f in ("amount_flat", "amount_percent", "per_unit_rate")
    )
    if not has_amount:
        confidence -= 0.3

    # Set state and geographic scope
    raw.setdefault("state", state)
    raw.setdefault("geographic_scope", "state")

    try:
        program = IncentiveProgram.model_validate(raw)
        return program, confidence
    except Exception as exc:
        print(f"[LLM_EXTRACTOR] Validation failed for {raw.get('program_id')}: {exc}", file=sys.stderr)
        return None, 0.0


def _normalize_raw(raw: Dict[str, Any], state: str) -> Dict[str, Any]:
    """Fix common LLM response issues."""
    raw = dict(raw)

    # Normalize program_id
    pid = raw.get("program_id", "")
    if not pid.startswith(f"{state}-"):
        raw["program_id"] = f"{state}-{pid}" if pid else f"{state}-unknown"

    # Normalize eligible_upgrades
    upgrades = raw.get("eligible_upgrades")
    if isinstance(upgrades, str):
        raw["eligible_upgrades"] = [u.strip() for u in upgrades.split(",")]
    elif not isinstance(upgrades, list):
        raw["eligible_upgrades"] = []

    # Normalize amount_rule
    ar = raw.get("amount_rule", {})
    if isinstance(ar, dict):
        # Convert percentage if given as whole number (30 → 0.30)
        pct = ar.get("amount_percent")
        if pct is not None and isinstance(pct, (int, float)) and pct > 1:
            ar["amount_percent"] = pct / 100
        raw["amount_rule"] = ar

    # Normalize exclusive_with
    ew = raw.get("exclusive_with")
    if ew is None:
        raw["exclusive_with"] = []
    elif isinstance(ew, str):
        raw["exclusive_with"] = [e.strip() for e in ew.split(",") if e.strip()]

    # Normalize step_down_schedule
    sds = raw.get("step_down_schedule")
    if isinstance(sds, list):
        normalized = []
        for entry in sds:
            if isinstance(entry, dict) and "year" in entry and "rate" in entry:
                rate = entry["rate"]
                if isinstance(rate, (int, float)) and rate > 1:
                    entry["rate"] = rate / 100
                normalized.append(entry)
        raw["step_down_schedule"] = normalized if normalized else None

    return raw


def _uncertain_fields(raw: Dict[str, Any]) -> List[str]:
    """Identify fields that seem uncertain or missing."""
    uncertain = []
    if not raw.get("eligible_upgrades"):
        uncertain.append("eligible_upgrades")

    ar = raw.get("amount_rule", {})
    if isinstance(ar, dict):
        has_amount = any(ar.get(f) for f in ("amount_flat", "amount_percent"))
        if not has_amount:
            uncertain.append("amount_rule")

    if raw.get("income_tier") is None:
        uncertain.append("income_tier")
    if raw.get("cap_category") is None:
        uncertain.append("cap_category")
    if raw.get("resets_annually") is None:
        uncertain.append("resets_annually")

    return uncertain
