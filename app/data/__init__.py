"""Packaged reference data."""

from app.data.base_foods import BASE_FOODS as FOUNDATION_FOODS
from app.data.fndds_foods import FNDDS_FOODS

BASE_FOODS = FOUNDATION_FOODS + FNDDS_FOODS

__all__ = ["BASE_FOODS", "FNDDS_FOODS", "FOUNDATION_FOODS"]
