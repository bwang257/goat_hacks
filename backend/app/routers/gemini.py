from fastapi import APIRouter
from ..models import GeminiRequest, GeminiInsight
from ..services import gemini

router = APIRouter(prefix="/api", tags=["gemini"])


@router.post("/enhanced-confidence", response_model=GeminiInsight)
async def get_enhanced_confidence(req: GeminiRequest):
    result = await gemini.analyze_transfer_risk(
        req.station_name,
        req.math_confidence,
        req.current_time
    )
    return GeminiInsight(**result)
