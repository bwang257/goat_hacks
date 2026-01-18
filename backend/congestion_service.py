"""
Congestion Service for MBTA Route Finder

Calculates congestion levels for stations based on:
- Time of day (rush hour patterns)
- Day of week (weekday vs weekend)
- Special events (sports games, concerts)
"""

from typing import Dict, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum


class CongestionLevel(str, Enum):
    """Congestion levels for stations/segments"""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass
class StationCongestion:
    """Congestion info for a specific station"""
    station_id: str
    level: CongestionLevel
    reason: str  # "rush_hour", "event", "normal"
    multiplier: float  # Time multiplier (1.0 = normal, 1.3 = 30% longer)


# Major hub stations that get congested during rush hour
RUSH_HOUR_STATIONS = {
    # Red Line hubs
    "place-pktrm": 1.3,      # Park Street
    "place-dwnxg": 1.3,      # Downtown Crossing
    "place-sstat": 1.4,      # South Station - major commuter hub
    "place-hrsq": 1.2,       # Harvard Square
    "place-knncl": 1.2,      # Kendall/MIT
    "place-cntsq": 1.2,      # Central Square

    # Orange Line hubs
    "place-north": 1.4,      # North Station - major commuter hub
    "place-haecl": 1.2,      # Haymarket
    "place-state": 1.3,      # State Street
    "place-bbsta": 1.3,      # Back Bay - commuter rail
    "place-rugg": 1.2,       # Ruggles

    # Green Line hubs
    "place-gover": 1.2,      # Government Center
    "place-coecl": 1.2,      # Copley
    "place-hymnl": 1.2,      # Hynes Convention Center
    "place-kencl": 1.2,      # Kenmore

    # Blue Line
    "place-aport": 1.2,      # Airport
    "place-mvbcl": 1.2,      # Maverick
}

# Stations affected by specific events (in addition to venue stations)
EVENT_OVERFLOW_STATIONS = {
    "fenway_park": ["place-kencl", "place-coecl", "place-hymnl"],  # Kenmore + nearby
    "td_garden": ["place-north", "place-haecl", "place-state"],    # North Station + nearby
}


def get_rush_hour_multiplier(hour: int, is_weekday: bool) -> float:
    """
    Get congestion multiplier based on time of day.

    Rush hours:
    - Morning: 7-9 AM (peak at 8 AM)
    - Evening: 5-7 PM (peak at 5:30-6 PM)

    Args:
        hour: Hour of day (0-23)
        is_weekday: True if Monday-Friday

    Returns:
        Multiplier (1.0 = normal, higher = more congested)
    """
    if not is_weekday:
        # Weekends are generally less congested
        # Slight bump around noon for shopping/events
        if 11 <= hour <= 14:
            return 1.1
        return 1.0

    # Weekday rush hour patterns
    if 7 <= hour <= 9:
        # Morning rush
        if hour == 8:
            return 1.0  # Peak morning rush
        return 0.8  # Shoulder hours
    elif 17 <= hour <= 19:
        # Evening rush
        if hour == 17 or hour == 18:
            return 1.0  # Peak evening rush
        return 0.8  # Shoulder
    elif 9 < hour < 17:
        # Midday - moderate
        return 0.5
    else:
        # Off-peak (early morning, late night)
        return 0.3


def calculate_station_congestion(
    station_id: str,
    check_time: Optional[datetime] = None,
    event_affected_stations: Optional[List[str]] = None,
    event_multiplier: float = 1.0
) -> StationCongestion:
    """
    Calculate congestion level for a specific station.

    Args:
        station_id: MBTA station ID
        check_time: Time to check congestion for (defaults to now)
        event_affected_stations: List of stations affected by current events
        event_multiplier: Multiplier from event service

    Returns:
        StationCongestion with level and details
    """
    if check_time is None:
        check_time = datetime.now(timezone.utc)

    # Convert to local time for hour/day checks
    # Boston is UTC-5 (EST) or UTC-4 (EDT)
    local_hour = (check_time.hour - 5) % 24  # Approximate EST
    is_weekday = check_time.weekday() < 5

    # Check if station is affected by events
    if event_affected_stations and station_id in event_affected_stations:
        level = _multiplier_to_level(event_multiplier)
        return StationCongestion(
            station_id=station_id,
            level=level,
            reason="event",
            multiplier=event_multiplier
        )

    # Check if station is a rush hour hub
    if station_id in RUSH_HOUR_STATIONS:
        base_multiplier = RUSH_HOUR_STATIONS[station_id]
        time_factor = get_rush_hour_multiplier(local_hour, is_weekday)

        # Combine base station congestion with time factor
        # Rush hour stations at peak time get full multiplier
        # Off-peak they get reduced multiplier
        effective_multiplier = 1.0 + (base_multiplier - 1.0) * time_factor

        if time_factor >= 0.8:  # Rush hour
            level = _multiplier_to_level(effective_multiplier)
            return StationCongestion(
                station_id=station_id,
                level=level,
                reason="rush_hour",
                multiplier=effective_multiplier
            )

    # Default: normal congestion
    return StationCongestion(
        station_id=station_id,
        level=CongestionLevel.LOW,
        reason="normal",
        multiplier=1.0
    )


def _multiplier_to_level(multiplier: float) -> CongestionLevel:
    """Convert multiplier to congestion level"""
    if multiplier >= 1.4:
        return CongestionLevel.VERY_HIGH
    elif multiplier >= 1.25:
        return CongestionLevel.HIGH
    elif multiplier >= 1.1:
        return CongestionLevel.MODERATE
    else:
        return CongestionLevel.LOW


def get_route_congestion(
    station_ids: List[str],
    check_time: Optional[datetime] = None,
    event_affected_stations: Optional[List[str]] = None,
    event_multiplier: float = 1.0
) -> Dict[str, StationCongestion]:
    """
    Get congestion levels for all stations in a route.

    Args:
        station_ids: List of station IDs in the route
        check_time: Time to check congestion for
        event_affected_stations: Stations affected by events
        event_multiplier: Event congestion multiplier

    Returns:
        Dict mapping station_id to StationCongestion
    """
    congestion_map = {}

    for station_id in station_ids:
        congestion = calculate_station_congestion(
            station_id,
            check_time,
            event_affected_stations,
            event_multiplier
        )
        # Only include if not low congestion
        if congestion.level != CongestionLevel.LOW:
            congestion_map[station_id] = congestion

    return congestion_map


def should_avoid_station(
    station_id: str,
    check_time: Optional[datetime] = None,
    event_affected_stations: Optional[List[str]] = None,
    event_multiplier: float = 1.0,
    avoid_threshold: CongestionLevel = CongestionLevel.HIGH
) -> bool:
    """
    Check if a station should be avoided due to congestion.

    Args:
        station_id: Station to check
        check_time: Time to check
        event_affected_stations: Event-affected stations
        event_multiplier: Event congestion multiplier
        avoid_threshold: Minimum congestion level to avoid

    Returns:
        True if station should be avoided
    """
    congestion = calculate_station_congestion(
        station_id,
        check_time,
        event_affected_stations,
        event_multiplier
    )

    # Compare enum values
    level_order = [CongestionLevel.LOW, CongestionLevel.MODERATE,
                   CongestionLevel.HIGH, CongestionLevel.VERY_HIGH]

    return level_order.index(congestion.level) >= level_order.index(avoid_threshold)


# Singleton instance
_congestion_service_cache: Dict[str, StationCongestion] = {}

def get_congestion_for_station(station_id: str, check_time: Optional[datetime] = None) -> Optional[str]:
    """
    Simple helper to get congestion level string for a station.
    Returns None if congestion is low.
    """
    congestion = calculate_station_congestion(station_id, check_time)
    if congestion.level == CongestionLevel.LOW:
        return None
    return congestion.level.value
