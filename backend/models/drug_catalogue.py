"""Pydantic model for the drug_catalogue MongoDB collection."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DrugCatalogueEntry(BaseModel):
    """MongoDB model for the drug_catalogue collection."""
    id: Optional[str] = Field(default=None, alias="_id")
    inn: str  # International Non-proprietary Name
    display_names: dict[str, str] = {}  # keyed by locale: {"fr": "Amoxicilline", "en": "Amoxicillin"}
    trade_names: dict[str, str] = {}    # keyed by region: {"TG": "Amoxil-TG", "BJ": "Clamoxyl"}
    available_regions: list[str] = []   # e.g. ["TG", "BJ"]
    atc_class: str = ""                 # e.g. "J01CA04"

    class Config:
        populate_by_name = True
