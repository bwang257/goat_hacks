from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TransferRequest(BaseModel):
    origin_stop: str
    origin_route: str
    transfer_stop: str
    transfer_route: str
    destination_stop: str
    user_speed_mps: float


class ConfidenceScore(BaseModel):
    score: str  # "LIKELY" | "RISKY" | "UNLIKELY"
    color: str  # "green" | "yellow" | "red"
    cushion_seconds: int
    message: str


class Prediction(BaseModel):
    route: str
    direction: str
    arrival_time: str  # ISO 8601
    vehicle_id: Optional[str] = None


class TransferOption(BaseModel):
    incoming_prediction: Prediction
    outgoing_prediction: Prediction
    walk_time_seconds: int
    confidence: ConfidenceScore


class TransferResponse(BaseModel):
    options: list[TransferOption]


class GeminiRequest(BaseModel):
    station_name: str
    math_confidence: str
    current_time: str


class GeminiInsight(BaseModel):
    adjusted_confidence: str  # "LIKELY" | "RISKY" | "UNLIKELY"
    reason: str
    pro_tip: str
