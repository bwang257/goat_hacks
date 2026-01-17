from datetime import datetime, timedelta
from ..models import ConfidenceScore


def calculate_confidence(
    incoming_arrival: datetime,
    outgoing_departure: datetime,
    walk_distance_meters: float,
    user_speed_mps: float
) -> ConfidenceScore:
    """
    Calculate transfer confidence based on timing and walking speed.
    
    Buffers:
    - 15s: Platform crowding
    - 20s: Doors, escalators, confusion
    - 30s: Safety margin
    Total: 65 seconds
    """
    # Calculate walk time
    base_walk_time = walk_distance_meters / user_speed_mps
    
    # Add buffers (crowd + doors, but safety margin applied separately)
    CROWD_BUFFER = 15
    DOOR_BUFFER = 20
    SAFETY_MARGIN = 30
    total_walk_time = base_walk_time + CROWD_BUFFER + DOOR_BUFFER
    
    # Calculate arrival at outgoing platform
    arrival_at_transfer = incoming_arrival + timedelta(seconds=total_walk_time)
    
    # Calculate cushion time (time until departure minus safety margin)
    time_until_departure = (outgoing_departure - arrival_at_transfer).total_seconds()
    cushion_seconds = int(time_until_departure - SAFETY_MARGIN)
    
    # Determine confidence level
    if cushion_seconds >= 120:
        return ConfidenceScore(
            score="LIKELY",
            color="green",
            cushion_seconds=cushion_seconds,
            message=f"You'll have {cushion_seconds // 60} minutes to spare"
        )
    elif cushion_seconds >= 0:
        return ConfidenceScore(
            score="RISKY",
            color="yellow",
            cushion_seconds=cushion_seconds,
            message=f"Only {cushion_seconds}s buffer - walk briskly!"
        )
    else:
        return ConfidenceScore(
            score="UNLIKELY",
            color="red",
            cushion_seconds=cushion_seconds,
            message=f"You'll miss by {abs(cushion_seconds)}s"
        )
