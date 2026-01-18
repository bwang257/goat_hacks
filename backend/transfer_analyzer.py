"""
Transfer Analyzer Module

Calculates transfer likelihood ratings based on:
- Slack time (time available minus time required for transfer)
- Station-specific buffer times (major hubs require more time)
- Line-specific factors (some transfers are more complex)
"""

from enum import Enum
from typing import Optional


class TransferRating(str, Enum):
    """Transfer likelihood rating"""
    LIKELY = "likely"      # > 5 minutes slack time - comfortable transfer
    RISKY = "risky"        # 2-5 minutes slack time - tight but possible
    UNLIKELY = "unlikely"  # < 2 minutes slack time - very difficult


# Station-specific buffer times in seconds
# Major transfer hubs need more time due to platform distance, crowds, and complexity
STATION_BUFFERS = {
    # Red Line transfers
    "place-pktrm": 180,     # Park Street (Red/Green hub - very complex)
    "place-dwnxg": 150,     # Downtown Crossing (Orange/Red - busy)
    "place-sstat": 180,     # South Station (Red/Commuter Rail - large station)
    "place-jfk": 120,       # JFK/UMass (Red Line branches)

    # Orange Line transfers
    "place-north": 180,     # North Station (Orange/Commuter Rail - large)
    "place-bbsta": 120,     # Back Bay (Orange/Commuter Rail)
    "place-rugg": 90,       # Ruggles (Orange/Commuter Rail)
    "place-haecl": 120,     # Haymarket (Orange/Green)
    "place-state": 120,     # State (Orange/Blue)

    # Green Line transfers
    "place-gover": 120,     # Government Center (Green/Blue)
    "place-coecl": 90,      # Copley (Green Line branches)
    "place-kencl": 120,     # Kenmore (Green Line branches)
    "place-lech": 120,      # Lechmere (Green Line)

    # Blue Line transfers
    "place-aport": 90,      # Airport (Blue Line)

    # Green Line - specific branches have platform complexity
    "place-north": 180,     # North Station (also Green)

    # Default for all other stations
    "default": 60
}


# Line-specific adjustments (added to station buffer)
# Some line combinations require extra time due to platform layout or accessibility
LINE_TRANSFER_ADJUSTMENTS = {
    # Green Line is complex with multiple branches and platforms
    ("Red Line", "Green Line"): 30,
    ("Green Line", "Red Line"): 30,
    ("Orange Line", "Green Line"): 20,
    ("Green Line", "Orange Line"): 20,

    # Commuter Rail requires extra time (longer platforms, fare gates)
    ("Red Line", "Commuter Rail"): 60,
    ("Commuter Rail", "Red Line"): 60,
    ("Orange Line", "Commuter Rail"): 60,
    ("Commuter Rail", "Orange Line"): 60,

    # Blue Line transfers
    ("Blue Line", "Green Line"): 20,
    ("Green Line", "Blue Line"): 20,
    ("Blue Line", "Orange Line"): 20,
    ("Orange Line", "Blue Line"): 20,
}


def calculate_transfer_time(
    station_id: str,
    from_line: Optional[str] = None,
    to_line: Optional[str] = None,
    walking_speed_kmh: float = 5.0
) -> int:
    """
    Calculate the required buffer time for a transfer at a specific station,
    adjusted for walking speed.

    Base buffers assume 5.0 km/h walking speed. Slower speeds increase buffer,
    faster speeds decrease it (with a minimum floor).

    Args:
        station_id: MBTA station ID (e.g., "place-pktrm")
        from_line: Line transferring from (e.g., "Red Line")
        to_line: Line transferring to (e.g., "Green Line")
        walking_speed_kmh: User's walking speed in km/h (default 5.0)

    Returns:
        Required buffer time in seconds
    """
    # Get base station buffer (calibrated for 5.0 km/h)
    base_buffer = STATION_BUFFERS.get(station_id, STATION_BUFFERS["default"])

    # Add line-specific adjustment if applicable
    line_adjustment = 0
    if from_line and to_line:
        line_pair = (from_line, to_line)
        line_adjustment = LINE_TRANSFER_ADJUSTMENTS.get(line_pair, 0)

    base_total = base_buffer + line_adjustment

    # Calculate walking-speed adjustment
    # Base speed is 5.0 km/h - scale buffer proportionally
    BASE_WALKING_SPEED = 5.0
    if walking_speed_kmh > 0:
        speed_factor = BASE_WALKING_SPEED / walking_speed_kmh
    else:
        speed_factor = 1.0

    # Apply speed factor to the "walking portion" of buffer
    # Assume ~60% of buffer is walking time, 40% is fixed (waiting, orientation)
    WALKING_PORTION = 0.6
    walking_time = base_total * WALKING_PORTION
    fixed_time = base_total * (1 - WALKING_PORTION)

    adjusted_walking_time = walking_time * speed_factor
    total_buffer = int(fixed_time + adjusted_walking_time)

    # Minimum buffer floor (never less than 30 seconds)
    return max(total_buffer, 30)


def rate_transfer(slack_time_seconds: float) -> TransferRating:
    """
    Rate the likelihood of successfully making a transfer based on slack time.

    Slack time = (next train departure - current train arrival - walking time - buffer)

    Args:
        slack_time_seconds: Available slack time in seconds

    Returns:
        TransferRating (LIKELY, RISKY, or UNLIKELY)
    """
    # Conservative thresholds for user safety
    if slack_time_seconds > 300:  # > 5 minutes
        return TransferRating.LIKELY
    elif slack_time_seconds > 120:  # 2-5 minutes
        return TransferRating.RISKY
    else:  # < 2 minutes
        return TransferRating.UNLIKELY


def get_transfer_details(
    station_id: str,
    from_line: Optional[str],
    to_line: Optional[str],
    arrival_time_seconds: float,
    departure_time_seconds: float,
    walking_time_seconds: float = 0,
    walking_speed_kmh: float = 5.0
) -> dict:
    """
    Get comprehensive transfer analysis including rating and timing breakdown.

    Args:
        station_id: MBTA station ID
        from_line: Line transferring from
        to_line: Line transferring to
        arrival_time_seconds: When arriving at transfer station (epoch seconds)
        departure_time_seconds: When next train departs (epoch seconds)
        walking_time_seconds: Time to walk between platforms
        walking_speed_kmh: User's walking speed in km/h (default 5.0)

    Returns:
        Dictionary with transfer analysis:
        {
            "buffer_seconds": 180,
            "walking_time_seconds": 90,
            "total_required_seconds": 270,
            "available_seconds": 420,
            "slack_time_seconds": 150,
            "rating": "risky"
        }
    """
    buffer_seconds = calculate_transfer_time(station_id, from_line, to_line, walking_speed_kmh)
    total_required = buffer_seconds + walking_time_seconds
    available_time = departure_time_seconds - arrival_time_seconds
    slack_time = available_time - total_required

    rating = rate_transfer(slack_time)

    return {
        "buffer_seconds": buffer_seconds,
        "walking_time_seconds": walking_time_seconds,
        "total_required_seconds": total_required,
        "available_seconds": available_time,
        "slack_time_seconds": slack_time,
        "rating": rating.value
    }
