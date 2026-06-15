import re
from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Optional

from services.source_parsers import SourceChunk


MEASURE_ALIASES = {
    "heat_pump": ["heat pump", "air source heat pump", "mini-split", "minisplit"],
    "attic_insulation": ["attic insulation", "insulation", "building envelope"],
    "air_sealing": ["air sealing", "air seal"],
    "duct_sealing": ["duct sealing", "duct"],
    "heat_pump_water_heater": ["heat pump water heater", "water heater"],
    "electric_cooking": ["cooktop", "electric stove", "range", "oven", "induction"],
    "heat_pump_clothes_dryer": ["heat pump clothes dryer", "clothes dryer"],
    "smart_thermostat": ["smart thermostat", "thermostat"],
    "solar": ["solar", "solar electric", "photovoltaic"],
    "battery_storage": ["battery storage", "battery"],
    "electrical_panel": ["electric panel", "panelboard", "branch circuits"],
}

MEASURE_LABELS = {
    "heat_pump": "Air Source Heat Pump",
    "attic_insulation": "Attic Insulation",
    "air_sealing": "Air Sealing",
    "duct_sealing": "Duct Sealing",
    "heat_pump_water_heater": "Heat Pump Water Heater",
    "electric_cooking": "Electric Cooking Appliance",
    "heat_pump_clothes_dryer": "Heat Pump Clothes Dryer",
    "smart_thermostat": "Smart Thermostat",
    "solar": "Residential Solar",
    "battery_storage": "Battery Storage",
    "electrical_panel": "Electrical Panel Upgrade",
}


@dataclass
class IncentiveIndexRecord:
    id: str
    program_id: str
    program_name: str
    admin: str
    source_url: str
    source_type: str
    document_date: str
    jurisdiction: str
    utility_territory: str
    building_type: str
    fuel_type: str
    measure: str
    equipment_requirements: str
    rebate_amount: float
    rebate_percent: float
    max_cap: float
    eligibility_rules: str
    income_rules: str
    contractor_rules: str
    application_deadline: str
    stacking_notes: str
    raw_text_chunk: str
    parse_confidence: str = "medium"

    def to_metadata(self) -> Dict:
        metadata = asdict(self)
        metadata.pop("raw_text_chunk")
        return metadata


def extract_records(chunks: Iterable[SourceChunk]) -> List[IncentiveIndexRecord]:
    records: List[IncentiveIndexRecord] = []
    for chunk in chunks:
        if chunk.source.path.name.lower() == "heip-sf-preconditions.pdf":
            continue
        records.extend(_records_for_chunk(chunk))

    records.extend(_manual_georgia_power_heip_records(chunks))
    return _dedupe_records(records)


def _records_for_chunk(chunk: SourceChunk) -> List[IncentiveIndexRecord]:
    text = chunk.text
    source = chunk.source
    context = _program_context(source.title, source.source_type, source.source_url)
    measures = _detect_measures(text, context["program_id"])
    if not measures:
        return []

    records: List[IncentiveIndexRecord] = []
    for measure in measures:
        rebate_amount, rebate_percent, max_cap = _amount_fields(text, measure, context["program_id"])
        records.append(
            IncentiveIndexRecord(
                id=f"{context['program_id']}-{measure}-{chunk.chunk_id}",
                program_id=context["program_id"],
                program_name=context["program_name"],
                admin=context["admin"],
                source_url=source.source_url or context["source_url"],
                source_type=source.source_type,
                document_date=source.document_date or "",
                jurisdiction=context["jurisdiction"],
                utility_territory=context["utility_territory"],
                building_type=_building_type(text, context["program_id"]),
                fuel_type=_fuel_type(text, measure),
                measure=measure,
                equipment_requirements=_equipment_requirements(text),
                rebate_amount=rebate_amount,
                rebate_percent=rebate_percent,
                max_cap=max_cap,
                eligibility_rules=_eligibility_rules(text),
                income_rules=_income_rules(text),
                contractor_rules=_contractor_rules(text),
                application_deadline=_application_deadline(text),
                stacking_notes=_stacking_notes(text, context["program_id"]),
                raw_text_chunk=text,
                parse_confidence="high" if source.parser == "html" else "medium",
            )
        )
    return records


def _program_context(title: str, source_type: str, source_url: Optional[str]) -> Dict[str, str]:
    lower_title = title.lower()
    if "residential clean energy" in lower_title:
        return {
            "program_id": "irs-25d",
            "program_name": "Residential Clean Energy Credit",
            "admin": "Internal Revenue Service",
            "source_url": source_url or "https://www.irs.gov/credits-deductions/residential-clean-energy-credit",
            "jurisdiction": "US",
            "utility_territory": "",
        }
    if "home improvement" in lower_title or "5967" in lower_title or "5886" in lower_title:
        return {
            "program_id": "irs-25c",
            "program_name": "Energy Efficient Home Improvement Credit",
            "admin": "Internal Revenue Service",
            "source_url": source_url or "https://www.irs.gov/credits-deductions/energy-efficient-home-improvement-credit",
            "jurisdiction": "US",
            "utility_territory": "",
        }
    if "hear" in lower_title or "diy" in lower_title:
        return {
            "program_id": "ga-hear-diy",
            "program_name": "Georgia Home Energy Rebates HEAR DIY Pathway",
            "admin": "Georgia Home Energy Rebates",
            "source_url": source_url or "https://energyrebates.georgia.gov",
            "jurisdiction": "Georgia",
            "utility_territory": "",
        }
    if "heip" in lower_title:
        return {
            "program_id": "ga-power-heip",
            "program_name": "Georgia Power Home Energy Improvement Program",
            "admin": "Georgia Power",
            "source_url": source_url or "",
            "jurisdiction": "Georgia",
            "utility_territory": "Georgia Power",
        }
    return {
        "program_id": _slug(title),
        "program_name": title,
        "admin": "Unknown",
        "source_url": source_url or "",
        "jurisdiction": "Unknown",
        "utility_territory": "",
    }


def _detect_measures(text: str, program_id: str) -> List[str]:
    lower_text = text.lower()
    measures = [
        measure
        for measure, aliases in MEASURE_ALIASES.items()
        if any(alias in lower_text for alias in aliases)
    ]
    if program_id == "irs-25d" and not measures:
        if "clean energy" in lower_text or "qualified expenses" in lower_text:
            measures.extend(["solar", "battery_storage"])
    return list(dict.fromkeys(measures))


def _amount_fields(text: str, measure: str, program_id: str) -> tuple[float, float, float]:
    lower_text = text.lower()
    dollars = [_money_to_float(match) for match in re.findall(r"\$[\d,]+", text)]
    percentages = [float(match) / 100 for match in re.findall(r"(\d{1,3})\s*%", text)]

    if program_id == "irs-25c":
        if measure in {"heat_pump", "heat_pump_water_heater"}:
            return 0, 0.30, 2000
        if measure in {"attic_insulation", "air_sealing", "electrical_panel"}:
            return 0, 0.30, 1200
    if program_id == "irs-25d":
        return 0, 0.30, 0
    if program_id == "ga-hear-diy":
        return 0, 1.0 if "below 80%" in lower_text else 0.5, 840

    percent = percentages[0] if percentages else 0
    max_cap = max(dollars) if dollars else 0
    return 0, percent, max_cap


def _equipment_requirements(text: str) -> str:
    sentences = _sentences_with(text, ["energy star", "qualified", "manufacturer", "seer", "hspf", "cop", "test-in", "test-out"])
    return " ".join(sentences[:3])


def _eligibility_rules(text: str) -> str:
    sentences = _sentences_with(text, ["eligible", "qualify", "qualified", "homeowners", "tenants", "existing home"])
    return " ".join(sentences[:4])


def _income_rules(text: str) -> str:
    sentences = _sentences_with(text, ["income", "ami", "80%", "150%", "low-income"])
    return " ".join(sentences[:4])


def _contractor_rules(text: str) -> str:
    sentences = _sentences_with(text, ["contractor", "licensed", "installation", "install", "self-install"])
    return " ".join(sentences[:4])


def _application_deadline(text: str) -> str:
    sentences = _sentences_with(text, ["deadline", "90 days", "application", "apply"])
    return " ".join(sentences[:3])


def _stacking_notes(text: str, program_id: str) -> str:
    sentences = _sentences_with(text, ["stack", "subsidy", "rebate", "credit", "combined"])
    if sentences:
        return " ".join(sentences[:3])
    if program_id.startswith("irs"):
        return "Federal tax credits may interact with rebates and subsidies; verify current tax guidance."
    return ""


def _building_type(text: str, program_id: str) -> str:
    lower_text = text.lower()
    if "tenant" in lower_text:
        return "tenant"
    if "multifamily" in lower_text:
        return "multifamily"
    if "single" in lower_text or program_id == "ga-power-heip":
        return "single_family"
    return "unknown"


def _fuel_type(text: str, measure: str) -> str:
    lower_text = text.lower()
    if "electric" in lower_text or measure in {"electric_cooking", "heat_pump_clothes_dryer"}:
        return "electric"
    if "natural gas" in lower_text or "gas" in lower_text:
        return "gas"
    return "unknown"


def _manual_georgia_power_heip_records(chunks: Iterable[SourceChunk]) -> List[IncentiveIndexRecord]:
    source_chunk = next(
        (chunk for chunk in chunks if chunk.source.path.name.lower() == "heip-sf-preconditions.pdf"),
        None,
    )
    if source_chunk is None:
        return []

    source = source_chunk.source
    raw_text = source.text[:1400]
    rows = [
        ("attic_insulation", 0.50, 250, "Existing attic insulation must be less than R-19. Installation across attic spaces is required."),
        ("air_sealing", 0.50, 300, "A home energy assessment with test-in and test-out is required."),
        ("duct_sealing", 0.50, 300, "Duct testing and leakage reduction are required for qualifying duct systems."),
        ("smart_thermostat", 0.50, 75, "ENERGY STAR certified smart thermostat for ducted central HVAC systems."),
        ("heat_pump_water_heater", 0.50, 500, "ENERGY STAR certified heat pump water heater installed by a licensed plumber, program contractor, or self-installed where allowed."),
    ]
    return [
        IncentiveIndexRecord(
            id=f"ga-power-heip-{measure}",
            program_id="ga-power-heip",
            program_name="Georgia Power Home Energy Improvement Program",
            admin="Georgia Power",
            source_url=source.source_url or "",
            source_type=source.source_type,
            document_date=source.document_date or "",
            jurisdiction="Georgia",
            utility_territory="Georgia Power",
            building_type="single_family",
            fuel_type=_fuel_type(requirements, measure),
            measure=measure,
            equipment_requirements=requirements,
            rebate_amount=0,
            rebate_percent=percent,
            max_cap=cap,
            eligibility_rules="Modeled from Georgia Power HEIP preconditions. Plain PDF extraction is garbled, so these rows require source review before production use.",
            income_rules="",
            contractor_rules=requirements if "contractor" in requirements.lower() or "licensed" in requirements.lower() else "",
            application_deadline="",
            stacking_notes="Utility rebate; verify current stacking rules with federal tax credits.",
            raw_text_chunk=raw_text,
            parse_confidence="manual_review",
        )
        for measure, percent, cap, requirements in rows
    ]


def _dedupe_records(records: List[IncentiveIndexRecord]) -> List[IncentiveIndexRecord]:
    deduped: Dict[str, IncentiveIndexRecord] = {}
    for record in records:
        deduped[record.id] = record
    return list(deduped.values())


def _sentences_with(text: str, needles: List[str]) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [
        sentence.strip()
        for sentence in sentences
        if sentence.strip() and any(needle in sentence.lower() for needle in needles)
    ]


def _money_to_float(value: str) -> float:
    return float(value.replace("$", "").replace(",", ""))


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
