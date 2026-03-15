from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class RoomEstimateRequest(BaseModel):
    width_cm: int = Field(..., ge=180, le=1200)
    length_cm: int = Field(..., ge=180, le=1200)
    height_cm: int = Field(240, ge=180, le=400)
    mood: str = "minimal"
    purpose: str = "work_sleep"
    budget_krw: int = Field(..., ge=100000)


class RecommendationRequest(BaseModel):
    room_id: str
    required_categories: List[str] = Field(default_factory=lambda: ["bed", "desk", "chair", "storage"])
