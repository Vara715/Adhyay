"""Seed helpers for the deterministic in-memory company environment."""

from backend.data.scenarios import SCENARIOS, copy_scenario_data

DEFAULT_SCENARIO = "inventory_supplier_failure"


def load_seed_data(scenario_key: str = DEFAULT_SCENARIO) -> dict:
    return copy_scenario_data(scenario_key)


def available_scenarios() -> list[dict[str, str]]:
    return [
        {"key": scenario.key, "name": scenario.name, "description": scenario.description}
        for scenario in SCENARIOS.values()
    ]
