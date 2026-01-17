import httpx
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class RealtimeTrain:
    """Represents a single train with real-time prediction"""
    route_id: str
    line_name: str
    direction_id: int
    departure_time: datetime
    arrival_time: datetime
    status: str  # "On time", "Delayed", etc.
    prediction_id: str
    vehicle_id: Optional[str]

@dataclass
class SameLineRoute:
    """A route on a single line with multiple train options"""
    line_name: str
    line_color: str
    from_station_name: str
    to_station_name: str
    direction_name: str
    scheduled_time_minutes: float
    distance_meters: float
    next_trains: List[Dict]  # List of next N trains with timing info
    path_coordinates: List[Dict] = None  # Station-by-station path coordinates

class RealtimeSameLineRouter:
    def __init__(self, mbta_api_key: str, transit_graph):
        self.mbta_api_key = mbta_api_key
        self.transit_graph = transit_graph
    
    def is_same_line_route(self, start_station_id: str, end_station_id: str) -> Optional[str]:
        """
        Check if two stations are on the same line.
        Returns the shared line name if they are, None otherwise.
        """
        start_station = self.transit_graph.nodes.get(start_station_id)
        end_station = self.transit_graph.nodes.get(end_station_id)
        
        if not start_station or not end_station:
            return None

        # Find shared lines
        start_lines = set(start_station.get("lines", []))
        end_lines = set(end_station.get("lines", []))
        shared_lines = start_lines & end_lines

        if not shared_lines:
            return None

        # If multiple shared lines, prefer the one that has an actual path
        if len(shared_lines) > 1:
            for line in shared_lines:
                route_id = self.get_route_id_from_line_name(line)
                # Check if there's a connection on this route
                edges = self.transit_graph.adjacency.get(start_station_id, [])
                for edge in edges:
                    if edge.get("route_id") == route_id:
                        return line

        # Return the first shared line
        return list(shared_lines)[0]
    
    def get_line_color(self, line_name: str) -> str:
        """Get hex color for a line (without # prefix)"""
        colors = {
            # Heavy Rail
            "Red Line": "DA291C",
            "Orange Line": "ED8B00",
            "Blue Line": "003DA5",
            # Green Line
            "Green Line": "00843D",
            "Green Line B": "00843D",
            "Green Line C": "00843D",
            "Green Line D": "00843D",
            "Green Line E": "00843D",
            "B": "00843D",
            "C": "00843D",
            "D": "00843D",
            "E": "00843D",
            # Commuter Rail (purple)
            "Providence/Stoughton Line": "80276C",
            "Framingham/Worcester Line": "80276C",
            "Franklin/Foxboro Line": "80276C",
            "Needham Line": "80276C",
            "Fairmount Line": "80276C",
            "Lowell Line": "80276C",
            "Haverhill Line": "80276C",
            "Newburyport/Rockport Line": "80276C",
            "Fitchburg Line": "80276C",
            "Kingston Line": "80276C",
            "Greenbush Line": "80276C",
            "Fall River/New Bedford Line": "80276C",
            "Foxboro Event Service": "80276C",
        }
        return colors.get(line_name, "000000")
    
    def get_route_id_from_line_name(self, line_name: str) -> str:
        """Convert line display name to route_id"""
        # Map display names to route IDs
        mapping = {
            # Heavy Rail
            "Red Line": "Red",
            "Orange Line": "Orange",
            "Blue Line": "Blue",
            # Green Line
            "Green Line": "Green",
            "Green Line B": "Green-B",
            "Green Line C": "Green-C",
            "Green Line D": "Green-D",
            "Green Line E": "Green-E",
            "B": "Green-B",
            "C": "Green-C",
            "D": "Green-D",
            "E": "Green-E",
            # Commuter Rail
            "Providence/Stoughton Line": "CR-Providence",
            "Framingham/Worcester Line": "CR-Worcester",
            "Franklin/Foxboro Line": "CR-Franklin",
            "Needham Line": "CR-Needham",
            "Fairmount Line": "CR-Fairmount",
            "Lowell Line": "CR-Lowell",
            "Haverhill Line": "CR-Haverhill",
            "Newburyport/Rockport Line": "CR-Newburyport",
            "Fitchburg Line": "CR-Fitchburg",
            "Kingston Line": "CR-Kingston",
            "Greenbush Line": "CR-Greenbush",
            "Fall River/New Bedford Line": "CR-NewBedford",
            "Foxboro Event Service": "CR-Foxboro",
        }
        return mapping.get(line_name, line_name)
    
    def calculate_direction(
        self,
        start_station_id: str,
        end_station_id: str,
        route_id: str
    ) -> tuple[int, str]:
        """
        Determine which direction (0 or 1) goes from start to end.
        Returns (direction_id, direction_name)
        """
        # Get all edges on this route from start station
        edges = self.transit_graph.adjacency.get(start_station_id, [])
        route_edges = [e for e in edges if e.get("route_id") == route_id]
        
        if not route_edges:
            return (0, "Unknown")
        
        # Follow the path to see which direction leads to end station
        # Simple approach: check if end station is reachable in forward direction
        visited = set()
        current = start_station_id
        direction_id = 0  # Assume direction 0 first
        
        # BFS to find if end is reachable
        queue = [(current, [])]
        while queue:
            curr_id, path = queue.pop(0)
            
            if curr_id == end_station_id:
                # Found it! Check the direction from first hop
                if len(path) > 0:
                    # Direction is consistent along the path
                    break
                return (direction_id, "Outbound")  # Default
            
            if curr_id in visited:
                continue
            visited.add(curr_id)
            
            # Get next stations on this route
            next_edges = self.transit_graph.adjacency.get(curr_id, [])
            for edge in next_edges:
                if edge.get("route_id") == route_id and edge["to"] not in visited:
                    queue.append((edge["to"], path + [edge["to"]]))
        
        # Direction names (simplified - real MBTA has specific names)
        direction_names = {
            "Red": ["Ashmont/Braintree", "Alewife"],
            "Orange": ["Forest Hills", "Oak Grove"],
            "Blue": ["Bowdoin", "Wonderland"],
            "Green-B": ["Boston College", "Park Street"],
            "Green-C": ["Cleveland Circle", "North Station"],
            "Green-D": ["Riverside", "Union Square"],
            "Green-E": ["Heath Street", "Medford/Tufts"],
        }
        
        direction_name = direction_names.get(route_id, ["Outbound", "Inbound"])[direction_id]
        return (direction_id, direction_name)
    
    async def get_next_trains_for_route(
        self,
        station_id: str,
        route_id: str,
        direction_id: int,
        limit: int = 3
    ) -> List[RealtimeTrain]:
        """Fetch next N trains from MBTA Predictions API"""
        
        url = "https://api-v3.mbta.com/predictions"
        params = {
            "filter[stop]": station_id,
            "filter[route]": route_id,
            "filter[direction_id]": direction_id,
            "sort": "departure_time",
            "include": "vehicle"
        }
        headers = {"x-api-key": self.mbta_api_key}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
            
            trains = []
            from datetime import timezone
            now = datetime.now(timezone.utc)

            for prediction in data.get("data", [])[:limit]:
                attrs = prediction["attributes"]

                # Get departure time
                departure = attrs.get("departure_time")
                arrival = attrs.get("arrival_time")
                status = attrs.get("status", "On time")

                if not departure:
                    continue

                # Parse times - ensure timezone aware
                if departure.endswith('Z'):
                    departure = departure.replace('Z', '+00:00')
                departure_dt = datetime.fromisoformat(departure)

                # Skip trains that already left
                if departure_dt < now:
                    continue

                if arrival:
                    if arrival.endswith('Z'):
                        arrival = arrival.replace('Z', '+00:00')
                    arrival_dt = datetime.fromisoformat(arrival)
                else:
                    arrival_dt = departure_dt
                
                # Get vehicle ID if available
                vehicle_rel = prediction["relationships"].get("vehicle", {}).get("data")
                vehicle_id = vehicle_rel["id"] if vehicle_rel else None
                
                # Get line name from route
                line_name = self._get_line_display_name(route_id)
                
                trains.append(RealtimeTrain(
                    route_id=route_id,
                    line_name=line_name,
                    direction_id=direction_id,
                    departure_time=departure_dt,
                    arrival_time=arrival_dt,
                    status=status,
                    prediction_id=prediction["id"],
                    vehicle_id=vehicle_id
                ))
            
            return trains
            
        except Exception as e:
            print(f"Error fetching predictions: {e}")
            return []
    
    def _get_line_display_name(self, route_id: str) -> str:
        """Convert route_id back to display name"""
        mapping = {
            "Red": "Red Line",
            "Orange": "Orange Line",
            "Blue": "Blue Line",
            "Green-B": "B",
            "Green-C": "C",
            "Green-D": "D",
            "Green-E": "E",
        }
        return mapping.get(route_id, route_id)
    
    def calculate_scheduled_time(
        self,
        start_station_id: str,
        end_station_id: str,
        route_id: str
    ) -> tuple[float, float]:
        """
        Calculate scheduled travel time and distance from graph.
        Returns (time_seconds, distance_meters)
        """
        # BFS to find path along this route
        visited = set()
        queue = [(start_station_id, 0, 0)]  # (station_id, time, distance)
        
        while queue:
            curr_id, time, dist = queue.pop(0)
            
            if curr_id == end_station_id:
                return (time, dist)
            
            if curr_id in visited:
                continue
            visited.add(curr_id)
            
            edges = self.transit_graph.adjacency.get(curr_id, [])
            for edge in edges:
                if edge.get("route_id") == route_id and edge["to"] not in visited:
                    new_time = time + edge["time_seconds"]
                    new_dist = dist + edge.get("distance_meters", 0)
                    queue.append((edge["to"], new_time, new_dist))
        
        return (0, 0)  # No path found
    
    async def get_same_line_route(
        self,
        start_station_id: str,
        end_station_id: str,
        num_trains: int = 3
    ) -> Optional[SameLineRoute]:
        """
        Get real-time route information for same-line journey.
        Returns None if stations are not on the same line.
        """
        
        # Check if same line
        shared_line = self.is_same_line_route(start_station_id, end_station_id)
        if not shared_line:
            return None
        
        # Get station info
        start_station = self.transit_graph.nodes[start_station_id]
        end_station = self.transit_graph.nodes[end_station_id]
        
        # Get route ID and direction
        route_id = self.get_route_id_from_line_name(shared_line)
        direction_id, direction_name = self.calculate_direction(
            start_station_id,
            end_station_id,
            route_id
        )
        
        # Get scheduled time and distance
        scheduled_time, distance = self.calculate_scheduled_time(
            start_station_id,
            end_station_id,
            route_id
        )
        
        # Get next trains with real-time predictions
        next_trains_data = await self.get_next_trains_for_route(
            start_station_id,
            route_id,
            direction_id,
            limit=num_trains
        )

        # Format train information
        from datetime import timezone
        now = datetime.now(timezone.utc)
        next_trains = []

        if next_trains_data:
            # Use real-time predictions
            for train in next_trains_data:
                minutes_until = (train.departure_time - now).total_seconds() / 60

                # Estimate arrival at destination
                est_arrival = train.departure_time + timedelta(seconds=scheduled_time)
                total_time = (est_arrival - now).total_seconds() / 60

                next_trains.append({
                    "departure_time": train.departure_time.isoformat(),
                    "arrival_time": est_arrival.isoformat(),
                    "minutes_until_departure": round(minutes_until, 1),
                    "total_trip_minutes": round(total_time, 1),
                    "status": train.status or "Scheduled",
                    "vehicle_id": train.vehicle_id,
                    "countdown_text": self._format_countdown(minutes_until)
                })
        else:
            # Fallback to estimated schedule
            # Determine realistic interval based on route type
            if route_id.startswith('CR-'):
                # Commuter rail: typically 30-60 min intervals
                base_wait = 15  # Assume next train in 15-45 min
                interval = 30   # Trains every 30 min
            else:
                # Subway: 5-10 min intervals
                base_wait = 3
                interval = 6

            for i in range(num_trains):
                departure = now + timedelta(minutes=base_wait + i*interval)
                arrival = departure + timedelta(seconds=scheduled_time)
                minutes_until = base_wait + (i*interval)

                next_trains.append({
                    "departure_time": departure.isoformat(),
                    "arrival_time": arrival.isoformat(),
                    "minutes_until_departure": float(minutes_until),
                    "total_trip_minutes": round(scheduled_time / 60, 1),
                    "status": "Estimated - No real-time data",
                    "vehicle_id": None,
                    "countdown_text": self._format_countdown(minutes_until)
                })
        
        # Get the actual path of stations
        path_coordinates = self.get_station_path(
            start_station_id,
            end_station_id,
            route_id
        )

        return SameLineRoute(
            line_name=shared_line,
            line_color=self.get_line_color(shared_line),
            from_station_name=start_station["name"],
            to_station_name=end_station["name"],
            direction_name=direction_name,
            scheduled_time_minutes=round(scheduled_time / 60, 1),
            distance_meters=round(distance, 0),
            next_trains=next_trains,
            path_coordinates=path_coordinates
        )
    
    def _format_countdown(self, minutes: float) -> str:
        """Format countdown text like 'Arriving', '2 min', '15 min'"""
        if minutes < 1:
            return "Arriving"
        elif minutes < 2:
            return "1 min"
        else:
            return f"{int(minutes)} min"

    def get_station_path(
        self,
        start_station_id: str,
        end_station_id: str,
        route_id: str
    ) -> List[Dict]:
        """
        Get the ordered list of stations along the route from start to end.
        Returns list of dicts with station_id, station_name, latitude, longitude.
        """
        # BFS to find path along this route
        visited = set()
        queue = [(start_station_id, [start_station_id])]

        while queue:
            curr_id, path = queue.pop(0)

            if curr_id == end_station_id:
                # Found the path! Convert to coordinates
                coordinates = []
                for station_id in path:
                    station = self.transit_graph.nodes.get(station_id)
                    if station:
                        coordinates.append({
                            "station_id": station_id,
                            "station_name": station["name"],
                            "latitude": station["latitude"],
                            "longitude": station["longitude"]
                        })
                return coordinates

            if curr_id in visited:
                continue
            visited.add(curr_id)

            # Get next stations on this route
            edges = self.transit_graph.adjacency.get(curr_id, [])

            for edge in edges:
                if edge.get("route_id") == route_id and edge["to"] not in visited:
                    queue.append((edge["to"], path + [edge["to"]]))

        return []  # No path found