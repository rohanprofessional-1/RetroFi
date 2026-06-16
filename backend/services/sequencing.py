import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from schemas import RetrofitOptionCalculation


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEQUENCING_SEED_PATH = DATA_DIR / "sequencing_dependencies_seed.json"


@lru_cache(maxsize=1)
def _load_dependency_map() -> Dict[str, Dict]:
    with SEQUENCING_SEED_PATH.open("r", encoding="utf-8") as file:
        entries = json.load(file)
    return {entry["upgrade_key"]: entry for entry in entries}


def sequence_options(
    options: List[RetrofitOptionCalculation],
    focus: str = "balanced",
    dependency_map: Optional[Dict[str, Dict]] = None,
    efficiency_lookup: Optional[Dict[str, Dict[str, float]]] = None,
) -> List[RetrofitOptionCalculation]:
    if not options:
        return []

    dependency_map = dependency_map if dependency_map is not None else _load_dependency_map()
    efficiency_lookup = efficiency_lookup or {}
    options_by_key = {option.upgrade_key: option for option in options}
    present_keys = set(options_by_key.keys())

    depends_on: Dict[str, List[str]] = {}
    for key in present_keys:
        entry = dependency_map.get(key, {})
        depends_on[key] = sorted(dep for dep in entry.get("depends_on", []) if dep in present_keys)

    dependents: Dict[str, List[str]] = {key: [] for key in present_keys}
    in_degree: Dict[str, int] = {}
    for key, deps in depends_on.items():
        in_degree[key] = len(deps)
        for dep in deps:
            dependents[dep].append(key)

    ready = sorted(key for key, degree in in_degree.items() if degree == 0)
    assigned: Dict[str, int] = {}
    notes: Dict[str, List[str]] = {key: [] for key in present_keys}
    sequence_number = 1

    while ready:
        selected = _select_by_focus(ready, focus, efficiency_lookup, options_by_key)
        deps = depends_on[selected]
        if deps:
            notes[selected].append(
                f"Comes after {', '.join(deps)} based on hand-curated install dependencies."
            )
        if len(ready) > 1:
            notes[selected].append(_focus_note(focus))
        elif not deps:
            notes[selected].append("No install dependencies; can be scheduled independently.")

        ready.remove(selected)
        assigned[selected] = sequence_number
        sequence_number += 1

        for dependent in sorted(dependents[selected]):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                ready.append(dependent)
        ready.sort()

    unassigned = sorted(
        (key for key in present_keys if key not in assigned),
        key=lambda key: options_by_key[key].score,
        reverse=True,
    )
    for key in unassigned:
        notes[key].append(
            "Dependency cycle detected among remaining upgrades; placed by balanced score as a fallback."
        )
        assigned[key] = sequence_number
        sequence_number += 1

    return [
        _copy_model(
            option,
            {
                "recommended_sequence": assigned[option.upgrade_key],
                "sequence_notes": notes[option.upgrade_key],
            },
        )
        for option in options
    ]


def _select_by_focus(
    candidates: List[str],
    focus: str,
    efficiency_lookup: Dict[str, Dict[str, float]],
    options_by_key: Dict[str, RetrofitOptionCalculation],
) -> str:
    if focus == "cost":
        metric = lambda key: efficiency_lookup.get(key, {}).get("cost_efficiency", 0)
    elif focus == "carbon":
        metric = lambda key: efficiency_lookup.get(key, {}).get("carbon_efficiency", 0)
    else:
        metric = lambda key: options_by_key[key].score
    return max(sorted(candidates), key=metric)


def _focus_note(focus: str) -> str:
    if focus == "cost":
        return "Prioritized ahead of other ready upgrades for higher cost savings per dollar invested."
    if focus == "carbon":
        return "Prioritized ahead of other ready upgrades for higher carbon reduction per dollar invested."
    return "Prioritized ahead of other ready upgrades for the best balanced cost/carbon score."


def _copy_model(model, update: Dict):
    if hasattr(model, "model_copy"):
        return model.model_copy(update=update)
    return model.copy(update=update)
