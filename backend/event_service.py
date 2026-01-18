"""
Event Service for MBTA Route Finder

Detects major Boston events (Red Sox games, Bruins/Celtics games, concerts)
and identifies affected MBTA stations for congestion warnings.
"""

from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass


@dataclass
class EventImpact:
    """Represents an event's impact on transit routes."""
    has_event: bool
    event_type: Optional[str] = None  # "sports" | "concert" | "other"
    event_name: Optional[str] = None
    affected_stations: List[str] = None
    congestion_multiplier: float = 1.0
    event_start_time: Optional[datetime] = None
    
    def __post_init__(self):
        if self.affected_stations is None:
            self.affected_stations = []


# Venue to station mapping
VENUE_STATIONS = {
    "fenway_park": ["place-kencl"],  # Kenmore (Green Line B/D)
    "td_garden": ["place-north"],    # North Station (Orange/Green Lines)
    "mgm_music_hall": ["place-kencl"],  # Near Kenmore (Green Line)
}

# Known major events database (MVP - Phase 1)
# For production, this would be replaced with API calls to Ticketmaster/AllEvents
# Format: (date, venue, event_name, event_type)
KNOWN_EVENTS = [
    # Example format - in production, fetch from APIs
    # (datetime(2026, 3, 28, 19, 0, tzinfo=timezone.utc), "td_garden", "Lady Gaga Concert", "concert"),
    # (datetime(2026, 4, 15, 19, 0, tzinfo=timezone.utc), "fenway_park", "Red Sox vs Yankees", "sports"),
]

# Red Sox 2026 home games (example dates - should be fetched from MLB API in production)
# Format: (month, day, opponent)
RED_SOX_HOME_GAMES_2026 = [
    (3, 28, "Yankees"),
    (3, 29, "Yankees"),
    (3, 30, "Yankees"),
    (4, 1, "Orioles"),
    (4, 2, "Orioles"),
    (4, 15, "Blue Jays"),
    (4, 16, "Blue Jays"),
    (5, 10, "Astros"),
    (5, 11, "Astros"),
    (6, 1, "Rays"),
    (6, 2, "Rays"),
    # Add more as needed
]

# Bruins/Celtics regular season games (example - should be fetched from NHL/NBA APIs)
# Format: (month, day, opponent, team)
TD_GARDEN_GAMES_2026 = [
    (3, 28, "Rangers", "Bruins"),
    (3, 29, "Lakers", "Celtics"),
    (4, 10, "Panthers", "Bruins"),
    # Add more as needed
]


class EventService:
    """Service for detecting events and their impact on transit routes."""
    
    def __init__(self):
        self.venue_stations = VENUE_STATIONS
        self.known_events = KNOWN_EVENTS
        self._cache: Optional[Dict] = None
        self._cache_time: Optional[datetime] = None
    
    def _is_event_time_relevant(self, event_time: datetime, route_time: datetime, hours_before: int = 3, hours_after: int = 3) -> bool:
        """
        Check if event is within the relevant time window for route planning.
        
        Args:
            event_time: When the event starts
            route_time: When the route is planned for
            hours_before: Hours before event to warn
            hours_after: Hours after event to warn
        
        Returns:
            bool: True if event is within the time window
        """
        time_diff = (event_time - route_time).total_seconds()
        hours_diff = time_diff / 3600
        
        # Event is relevant if it's within hours_before to hours_after window
        return -hours_before <= hours_diff <= hours_after
    
    def _get_red_sox_events_today(self, check_date: datetime) -> List[EventImpact]:
        """Check for Red Sox home games on a given date."""
        events = []
        
        for month, day, opponent in RED_SOX_HOME_GAMES_2026:
            event_date = datetime(2026, month, day, 19, 0, tzinfo=timezone.utc)  # Assume 7 PM start
            
            # Check if this date is "today" (within the same day)
            if event_date.date() == check_date.date():
                events.append(EventImpact(
                    has_event=True,
                    event_type="sports",
                    event_name=f"Red Sox vs {opponent}",
                    affected_stations=self.venue_stations["fenway_park"].copy(),
                    congestion_multiplier=1.3,  # +30% congestion at Kenmore
                    event_start_time=event_date
                ))
        
        return events
    
    def _get_td_garden_events_today(self, check_date: datetime) -> List[EventImpact]:
        """Check for TD Garden events (Bruins, Celtics, concerts) on a given date."""
        events = []
        
        for month, day, opponent, team in TD_GARDEN_GAMES_2026:
            event_date = datetime(2026, month, day, 19, 30, tzinfo=timezone.utc)  # Assume 7:30 PM start
            
            if event_date.date() == check_date.date():
                events.append(EventImpact(
                    has_event=True,
                    event_type="sports",
                    event_name=f"{team} vs {opponent}",
                    affected_stations=self.venue_stations["td_garden"].copy(),
                    congestion_multiplier=1.3,  # +30% congestion at North Station
                    event_start_time=event_date
                ))
        
        return events
    
    def check_events_for_route(self, route_stations: List[str], route_time: Optional[datetime] = None) -> EventImpact:
        """
        Check if any events affect the given route.
        
        Args:
            route_stations: List of station IDs in the route
            route_time: When the route is planned (defaults to now)
        
        Returns:
            EventImpact: Event impact information
        """
        if route_time is None:
            route_time = datetime.now(timezone.utc)
        
        # Get all events for today
        all_events = []
        all_events.extend(self._get_red_sox_events_today(route_time))
        all_events.extend(self._get_td_garden_events_today(route_time))
        
        # Check if any events affect stations in the route
        affected_events = []
        affected_stations_set = set()
        
        for event in all_events:
            if not event.has_event:
                continue
            
            # Check if event time is relevant (within 3 hours before/after)
            if event.event_start_time and self._is_event_time_relevant(event.event_start_time, route_time):
                # Check if any route stations are affected
                route_stations_set = set(route_stations)
                affected_stations_in_route = route_stations_set.intersection(set(event.affected_stations))
                
                if affected_stations_in_route:
                    affected_events.append(event)
                    affected_stations_set.update(affected_stations_in_route)
        
        if not affected_events:
            return EventImpact(has_event=False)
        
        # If multiple events, combine them
        # Use the highest congestion multiplier
        max_multiplier = max(event.congestion_multiplier for event in affected_events)
        event_names = [event.event_name for event in affected_events]
        
        return EventImpact(
            has_event=True,
            event_type=affected_events[0].event_type,  # Use first event type
            event_name=" & ".join(event_names),  # Combine event names
            affected_stations=list(affected_stations_set),
            congestion_multiplier=max_multiplier,
            event_start_time=affected_events[0].event_start_time
        )


# Singleton instance
_event_service: Optional[EventService] = None

def get_event_service() -> EventService:
    """Get or create event service singleton."""
    global _event_service
    if _event_service is None:
        _event_service = EventService()
    return _event_service
