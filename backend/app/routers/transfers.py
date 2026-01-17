from fastapi import APIRouter, HTTPException
from datetime import datetime
from ..models import TransferRequest, TransferOption, TransferResponse
from ..services import mbta, confidence
import json
import os

router = APIRouter(prefix="/api", tags=["transfers"])


@router.post("/calculate-transfer", response_model=TransferResponse)
async def calculate_transfer(req: TransferRequest):
    try:
        # Get predictions for both legs
        incoming_trains = await mbta.get_predictions(req.origin_stop, req.origin_route)
        outgoing_trains = await mbta.get_predictions(req.transfer_stop, req.transfer_route)
        
        if not incoming_trains or not outgoing_trains:
            raise HTTPException(
                status_code=404,
                detail="No predictions available for selected routes"
            )
        
        # Load transfer distances
        transfers_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "transfers.json"
        )
        
        with open(transfers_path) as f:
            transfers = json.load(f)
        
        transfer_key = f"{req.origin_route}-to-{req.transfer_route}"
        walk_distance = transfers.get(req.transfer_stop, {}).get(transfer_key, 100)
        
        # Calculate confidence for each combination
        options = []
        for incoming in incoming_trains:
            for outgoing in outgoing_trains:
                try:
                    arrival = datetime.fromisoformat(
                        incoming["arrival_time"].replace("Z", "+00:00")
                    )
                    departure = datetime.fromisoformat(
                        outgoing["arrival_time"].replace("Z", "+00:00")
                    )
                    
                    # Skip if departure is before arrival
                    if departure <= arrival:
                        continue
                    
                    conf = confidence.calculate_confidence(
                        arrival,
                        departure,
                        walk_distance,
                        req.user_speed_mps
                    )
                    
                    from ..models import Prediction
                    
                    options.append(
                        TransferOption(
                            incoming_prediction=Prediction(**incoming),
                            outgoing_prediction=Prediction(**outgoing),
                            walk_time_seconds=int(walk_distance / req.user_speed_mps),
                            confidence=conf
                        )
                    )
                except Exception as e:
                    print(f"Error processing prediction pair: {e}")
                    continue
        
        if not options:
            raise HTTPException(
                status_code=404,
                detail="No valid transfer options found"
            )
        
        # Return top 3 sorted by confidence (highest cushion first)
        options.sort(key=lambda x: x.confidence.cushion_seconds, reverse=True)
        
        return TransferResponse(options=options[:3])
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
