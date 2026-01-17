import httpx
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from functools import lru_cache
import time

class MBTAClient:
    """
    Centralized client for MBTA API v3 interactions.
    Provides methods for fetching schedules, predictions, trips, stops, and alerts.
    Includes caching layer to reduce API calls and respect rate limits.
    """
    
    BASE_URL = "https://api-v3.mbta.com"
    CACHE_TTL = 45  # Cache TTL in seconds (30-60s range)
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.headers = {"x-api-key": api_key} if api_key else {}
        
        # Simple in-memory cache: {cache_key: (data, timestamp)}
        self._cache: Dict[str, Tuple[any, float]] = {}
    
    def _get_cache_key(self, endpoint: str, params: Dict) -> str:
        """Generate cache key from endpoint and params"""
        param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return f"{endpoint}?{param_str}"
    
    def _is_cache_valid(self, cache_entry: Tuple[any, float]) -> bool:
        """Check if cache entry is still valid"""
        _, timestamp = cache_entry
        return (time.time() - timestamp) < self.CACHE_TTL
    
    def _get_from_cache(self, cache_key: str) -> Optional[any]:
        """Get data from cache if valid"""
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if self._is_cache_valid(entry):
                return entry[0]
            else:
                # Remove expired entry
                del self._cache[cache_key]
        return None
    
    def _set_cache(self, cache_key: str, data: any):
        """Store data in cache"""
        self._cache[cache_key] = (data, time.time())
    
    async def _get(self, endpoint: str, params: Optional[Dict] = None, use_cache: bool = True) -> Dict:
        """
        Internal method to make GET requests with caching and error handling.
        """
        if params is None:
            params = {}
        
        cache_key = self._get_cache_key(endpoint, params)
        
        # Check cache first
        if use_cache:
            cached_data = self._get_from_cache(cache_key)
            if cached_data is not None:
                return cached_data
        
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                
                # Store in cache
                if use_cache:
                    self._set_cache(cache_key, data)
                
                return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise Exception(f"MBTA API authentication failed. Check your API key.")
            elif e.response.status_code == 429:
                raise Exception(f"MBTA API rate limit exceeded. Please wait before retrying.")
            else:
                raise Exception(f"MBTA API error: {e.response.status_code} - {e.response.text}")
        except httpx.TimeoutException:
            raise Exception("MBTA API request timed out")
        except Exception as e:
            raise Exception(f"Error calling MBTA API: {str(e)}")
    
    async def get_schedules(
        self,
        route_id: Optional[str] = None,
        stop_id: Optional[str] = None,
        trip_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        direction_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Fetch scheduled trips from MBTA API.
        
        Args:
            route_id: Filter by route (e.g., "Red", "Orange")
            stop_id: Filter by stop/station
            trip_id: Filter by specific trip
            start_time: Minimum departure time (defaults to now)
            end_time: Maximum departure time (defaults to now + 2 hours)
            direction_id: Filter by direction (0 or 1)
            limit: Maximum number of results
        
        Returns:
            List of schedule objects with departure_time, arrival_time, etc.
        """
        params = {}
        
        if route_id:
            params["filter[route]"] = route_id
        if stop_id:
            params["filter[stop]"] = stop_id
        if trip_id:
            params["filter[trip]"] = trip_id
        if direction_id is not None:
            params["filter[direction_id]"] = str(direction_id)
        
        # Set time window
        now = datetime.now(timezone.utc)
        if start_time is None:
            start_time = now
        if end_time is None:
            end_time = now + timedelta(hours=2)
        
        # MBTA API expects ISO format times
        params["filter[min_time]"] = start_time.isoformat()
        params["filter[max_time]"] = end_time.isoformat()
        
        params["page[limit]"] = str(limit)
        params["sort"] = "departure_time"
        
        data = await self._get("/schedules", params)
        return data.get("data", [])
    
    async def get_predictions(
        self,
        stop_id: Optional[str] = None,
        route_id: Optional[str] = None,
        trip_id: Optional[str] = None,
        direction_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get real-time predictions for upcoming departures/arrivals.
        
        Args:
            stop_id: Filter by stop/station
            route_id: Filter by route
            trip_id: Filter by specific trip
            direction_id: Filter by direction (0 or 1)
            limit: Maximum number of predictions
        
        Returns:
            List of prediction objects with departure_time, arrival_time, status, etc.
        """
        params = {}
        
        if stop_id:
            params["filter[stop]"] = stop_id
        if route_id:
            params["filter[route]"] = route_id
        if trip_id:
            params["filter[trip]"] = trip_id
        if direction_id is not None:
            params["filter[direction_id]"] = str(direction_id)
        
        params["page[limit]"] = str(limit)
        params["sort"] = "departure_time"
        params["include"] = "vehicle,trip"
        
        data = await self._get("/predictions", params)
        return data.get("data", [])
    
    async def get_trips_for_route(
        self,
        route_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        direction_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Get trip information for a route within a time window.
        
        Args:
            route_id: Route identifier (e.g., "Red", "Orange")
            start_time: Minimum departure time
            end_time: Maximum departure time
            direction_id: Filter by direction
        
        Returns:
            List of trip objects
        """
        params = {"filter[route]": route_id}
        
        if direction_id is not None:
            params["filter[direction_id]"] = str(direction_id)
        
        if start_time:
            params["filter[min_time]"] = start_time.isoformat()
        if end_time:
            params["filter[max_time]"] = end_time.isoformat()
        
        data = await self._get("/trips", params)
        return data.get("data", [])
    
    async def get_stops_for_route(
        self,
        route_id: str,
        direction_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Get ordered list of stops/stations for a route.
        
        Args:
            route_id: Route identifier
            direction_id: Optional direction filter
        
        Returns:
            List of stop objects in order along the route
        """
        params = {"filter[route]": route_id}
        
        if direction_id is not None:
            params["filter[direction_id]"] = str(direction_id)
        
        params["include"] = "parent_station"
        
        data = await self._get("/stops", params)
        return data.get("data", [])
    
    async def get_alerts(
        self,
        route_id: Optional[str] = None,
        stop_id: Optional[str] = None,
        active_only: bool = True
    ) -> List[Dict]:
        """
        Get service alerts/disruptions.
        
        Args:
            route_id: Filter alerts for specific route
            stop_id: Filter alerts for specific stop
            active_only: Only return active alerts
        
        Returns:
            List of alert objects
        """
        params = {}
        
        if route_id:
            params["filter[route]"] = route_id
        if stop_id:
            params["filter[stop]"] = stop_id
        if active_only:
            params["filter[active]"] = "true"
        
        data = await self._get("/alerts", params)
        return data.get("data", [])
    
    async def get_vehicle_positions(
        self,
        route_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Get live vehicle positions (optional feature).
        
        Args:
            route_id: Filter by route
        
        Returns:
            List of vehicle position objects
        """
        params = {}
        
        if route_id:
            params["filter[route]"] = route_id
        
        data = await self._get("/vehicles", params)
        return data.get("data", [])
    
    async def get_next_departures(
        self,
        stop_id: str,
        route_id: Optional[str] = None,
        direction_id: Optional[int] = None,
        limit: int = 5,
        use_predictions: bool = True
    ) -> List[Dict]:
        """
        Convenience method to get next N departures from a stop.
        Uses predictions if available, falls back to schedules.
        
        Args:
            stop_id: Stop/station identifier
            route_id: Optional route filter
            direction_id: Optional direction filter
            limit: Number of departures to return
            use_predictions: Prefer real-time predictions over schedules
        
        Returns:
            List of departure objects with departure_time, arrival_time, status, etc.
        """
        now = datetime.now(timezone.utc)
        departures = []
        
        # Try predictions first if enabled
        if use_predictions:
            try:
                predictions = await self.get_predictions(
                    stop_id=stop_id,
                    route_id=route_id,
                    direction_id=direction_id,
                    limit=limit
                )
                
                for pred in predictions:
                    attrs = pred.get("attributes", {})
                    departure_time = attrs.get("departure_time")
                    arrival_time = attrs.get("arrival_time")
                    
                    if not departure_time:
                        continue
                    
                    # Parse ISO format time
                    if isinstance(departure_time, str):
                        if departure_time.endswith('Z'):
                            departure_time = departure_time.replace('Z', '+00:00')
                        departure_dt = datetime.fromisoformat(departure_time)
                    else:
                        continue
                    
                    # Skip past departures
                    if departure_dt < now:
                        continue
                    
                    if arrival_time:
                        if isinstance(arrival_time, str):
                            if arrival_time.endswith('Z'):
                                arrival_time = arrival_time.replace('Z', '+00:00')
                            arrival_dt = datetime.fromisoformat(arrival_time)
                        else:
                            arrival_dt = departure_dt
                    else:
                        arrival_dt = departure_dt
                    
                    departures.append({
                        "type": "prediction",
                        "departure_time": departure_dt,
                        "arrival_time": arrival_dt,
                        "status": attrs.get("status", "On time"),
                        "trip_id": pred.get("relationships", {}).get("trip", {}).get("data", {}).get("id"),
                        "vehicle_id": pred.get("relationships", {}).get("vehicle", {}).get("data", {}).get("id"),
                        "stop_id": stop_id,
                        "route_id": route_id
                    })
            except Exception as e:
                # Fall back to schedules if predictions fail
                pass
        
        # If we don't have enough departures, use schedules
        if len(departures) < limit:
            try:
                schedules = await self.get_schedules(
                    stop_id=stop_id,
                    route_id=route_id,
                    direction_id=direction_id,
                    start_time=now,
                    end_time=now + timedelta(hours=2),
                    limit=limit
                )
                
                for sched in schedules:
                    attrs = sched.get("attributes", {})
                    departure_time = attrs.get("departure_time")
                    arrival_time = attrs.get("arrival_time")
                    
                    if not departure_time:
                        continue
                    
                    # Parse ISO format time
                    if isinstance(departure_time, str):
                        if departure_time.endswith('Z'):
                            departure_time = departure_time.replace('Z', '+00:00')
                        departure_dt = datetime.fromisoformat(departure_time)
                    else:
                        continue
                    
                    # Skip past departures
                    if departure_dt < now:
                        continue
                    
                    if arrival_time:
                        if isinstance(arrival_time, str):
                            if arrival_time.endswith('Z'):
                                arrival_time = arrival_time.replace('Z', '+00:00')
                            arrival_dt = datetime.fromisoformat(arrival_time)
                        else:
                            arrival_dt = departure_dt
                    else:
                        arrival_dt = departure_dt
                    
                    # Check if we already have this departure from predictions
                    is_duplicate = any(
                        abs((d["departure_time"] - departure_dt).total_seconds()) < 60
                        for d in departures
                    )
                    
                    if not is_duplicate:
                        departures.append({
                            "type": "schedule",
                            "departure_time": departure_dt,
                            "arrival_time": arrival_dt,
                            "status": "Scheduled",
                            "trip_id": sched.get("relationships", {}).get("trip", {}).get("data", {}).get("id"),
                            "vehicle_id": None,
                            "stop_id": stop_id,
                            "route_id": route_id
                        })
            except Exception as e:
                pass
        
        # Sort by departure time and limit
        departures.sort(key=lambda x: x["departure_time"])
        return departures[:limit]
    
    def clear_cache(self):
        """Clear the API response cache"""
        self._cache.clear()
