from __future__ import annotations

from typing import Any


def month_distance(start_month: str, end_month: str) -> int:
    """Return inclusive month count, with acquisition month as month one."""
    start_year, start_number = (int(part) for part in start_month.split("-", 1))
    end_year, end_number = (int(part) for part in end_month.split("-", 1))
    return max(0, (end_year - start_year) * 12 + end_number - start_number + 1)


def depreciation_progress(
    cost_minor: int, useful_life_months: int, elapsed_months: int
) -> tuple[int, int]:
    """Return accumulated and remaining minor units using exact integer arithmetic."""
    cost = max(0, int(cost_minor))
    life = max(1, int(useful_life_months))
    elapsed = min(life, max(0, int(elapsed_months)))
    # Round cumulative depreciation so indivisible minor currency units are
    # spread across the useful life rather than all being front-loaded.
    accumulated = (2 * cost * elapsed + life) // (2 * life)
    return accumulated, cost - accumulated


def monthly_depreciation_minor(
    cost_minor: int, useful_life_months: int, month_index: int
) -> int:
    """Return this month's straight-line depreciation in the currency's minor unit."""
    cost = max(0, int(cost_minor))
    life = max(1, int(useful_life_months))
    month = int(month_index)
    if month < 1 or month > life:
        return 0
    current, _ = depreciation_progress(cost, life, month)
    previous, _ = depreciation_progress(cost, life, month - 1)
    return current - previous


def fixed_asset_values(asset: Any, as_of_month: str) -> tuple[int, int, int]:
    """Return effective elapsed months, accumulated depreciation, and book value."""
    effective_month = as_of_month
    disposal_month = asset["disposal_month"]
    if disposal_month and disposal_month < as_of_month:
        effective_month = str(disposal_month)
    elapsed = month_distance(str(asset["acquisition_month"]), effective_month)
    accumulated, remaining = depreciation_progress(
        int(asset["cost_minor"]), int(asset["useful_life_months"]), elapsed
    )
    return elapsed, accumulated, remaining
