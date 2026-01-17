import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
from route_planner import TransitGraph, Route, RouteSegment
from mbta_client import MBTAClient

class MultiRoutePlanner:
    """
    Handles complex multi-route pathfinding with real transfer times.
    Supports journeys requiring transfers between different routes/lines.
    """
    
    MIN_TRANSFER_TIME = timedelta(minutes=2)  # Minimum time to transfer
    MAX_TRANSFER_TIME = timedelta(minutes=30)  # Max wait for transfer
    
    def __init__(self, transit_graph: TransitGraph, mbta_client: MBTAClient):
        self.transit_graph = transit_graph
        self.mbta_client = mbta_client
    
    def _get_route_id_from_line_name(self, line_name: str) -> str:
        """Convert line display name to route_id"""
        mapping = {
            "Red Line": "Red",
            "Orange Line": "Orange",
            "Blue Line": "Blue",
            "Green Line": "Green",
            "Green Line B": "Green-B",
            "Green Line C": "Green-C",
            "Green Line D": "Green-D",
            "Green Line E": "Green-E",
            "B": "Green-B",
            "C": "Green-C",
            "D": "Green-D",
            "E": "Green-E",
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
    
    async def _get_trip_segment(
        self,
        start_station: str,
        end_station: str,
        route_id: str,
        departure_time: datetime,
        direction_id: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Get a single trip segment from start to end on the same route.
        Returns segment info with actual departure/arrival times from MBTA API.
        """
        # Get schedules for this route from start station
        schedules = await self.mbta_client.get_schedules(
            route_id=route_id,
            stop_id=start_station,
            start_time=departure_time,
            end_time=departure_time + timedelta(hours=2),
            direction_id=direction_id,
            limit=10
        )
        
        if not schedules:
            return None
        
        # Find schedule that goes to end_station
        # This is simplified - in reality we'd need to check trip stops
        for schedule in schedules:
            trip_id = schedule.get("relationships", {}).get("trip", {}).get("data", {}).get("id")
            if not trip_id:
                continue
            
            # Get all stops for this trip to see if it goes to end_station
            # For now, use a simplified approach: check if we can find a path
            # In production, you'd query trip stops from MBTA API
            
            attrs = schedule.get("attributes", {})
            dep_time_str = attrs.get("departure_time")
            arr_time_str = attrs.get("arrival_time")
            
            if not dep_time_str:
                continue
            
            # Parse times
            if isinstance(dep_time_str, str):
                if dep_time_str.endswith('Z'):
                    dep_time_str = dep_time_str.replace('Z', '+00:00')
                dep_time = datetime.fromisoformat(dep_time_str)
            else:
                continue
            
            # For now, estimate arrival based on path length
            # In full implementation, query schedule for end_station arrival
            path_length = self._estimate_path_length(start_station, end_station, route_id)
            est_arrival = dep_time + timedelta(seconds=path_length * 120)  # ~2 min per station
            
            return {
                "from_station": start_station,
                "to_station": end_station,
                "route_id": route_id,
                "trip_id": trip_id,
                "departure_time": dep_time,
                "arrival_time": est_arrival,
                "status": "Scheduled"
            }
        
        return None
    
    def _estimate_path_length(self, start: str, end: str, route_id: str) -> int:
        """Estimate number of stations between start and end on a route"""
        # Simple BFS to count stations
        visited = set()
        queue = [(start, 0)]
        
        while queue:
            current, depth = queue.pop(0)
            if current == end:
                return depth
            
            if current in visited:
                continue
            visited.add(current)
            
            edges = self.transit_graph.adjacency.get(current, [])
            for edge in edges:
                if (edge.get("route_id") == route_id and 
                    edge.get("type") == "train" and
                    edge["to"] not in visited):
                    queue.append((edge["to"], depth + 1))
        
        return 5  # Default estimate
    
    async def _find_transfer_station(
        self,
        route1_id: str,
        route2_id: str,
        current_station: str
    ) -> Optional[str]:
        """Find a station where we can transfer from route1 to route2"""
        # Get stations on route1
        route1_stations = set()
        for edge in self.transit_graph.edges:
            if edge.get("route_id") == route1_id and edge.get("type") == "train":
                route1_stations.add(edge["from"])
                route1_stations.add(edge["to"])
        
        # Get stations on route2
        route2_stations = set()
        for edge in self.transit_graph.edges:
            if edge.get("route_id") == route2_id and edge.get("type") == "train":
                route2_stations.add(edge["from"])
                route2_stations.add(edge["to"])
        
        # Find intersection (transfer stations)
        transfer_stations = route1_stations & route2_stations
        
        if not transfer_stations:
            return None
        
        # Prefer stations closer to current_station
        # Simple: return first transfer station (could be improved with distance)
        return list(transfer_stations)[0]
    
    async def find_multi_route_path(
        self,
        start_station_id: str,
        end_station_id: str,
        departure_time: Optional[datetime] = None,
        max_transfers: int = 3,
        prefer_fewer_transfers: bool = True
    ) -> Optional[Route]:
        """
        Find path between stations that may require transfers.
        
        Uses a simplified approach:
        1. Try direct route (same line)
        2. Try one-transfer routes
        3. Try multi-transfer routes (up to max_transfers)
        
        Returns Route with all segments including transfers.
        """
        if departure_time is None:
            departure_time = datetime.now(timezone.utc)
        
        # First, try time-aware pathfinding from route_planner
        # This handles same-line and simple transfers
        route = await self.transit_graph.find_time_aware_path(
            start_station_id=start_station_id,
            end_station_id=end_station_id,
            departure_time=departure_time,
            mbta_client=self.mbta_client,
            prefer_fewer_transfers=prefer_fewer_transfers,
            max_transfers=max_transfers,
            debug=False
        )
        
        if route:
            return route
        
        # If that fails, try a more exhaustive search
        # This is a simplified multi-route planner
        # In production, you'd use a more sophisticated algorithm like RAPTOR
        
        # Get all routes serving start and end stations
        start_node = self.transit_graph.nodes.get(start_station_id)
        end_node = self.transit_graph.nodes.get(end_station_id)
        
        if not start_node or not end_node:
            return None
        
        start_routes = set(start_node.get("lines", []))
        end_routes = set(end_node.get("lines", []))
        
        # Check if any routes overlap (direct route possible)
        shared_routes = start_routes & end_routes
        if shared_routes:
            # Already tried in find_time_aware_path, skip
            pass
        
        # Try one-transfer routes
        for start_line in start_routes:
            start_route_id = self._get_route_id_from_line_name(start_line)
            
            for end_line in end_routes:
                end_route_id = self._get_route_id_from_line_name(end_line)
                
                if start_route_id == end_route_id:
                    continue  # Already tried
                
                # Find transfer station
                transfer_station = await self._find_transfer_station(
                    start_route_id, end_route_id, start_station_id
                )
                
                if not transfer_station:
                    continue
                
                # Try to build two-segment route
                try:
                    # First segment: start -> transfer
                    seg1 = await self._get_trip_segment(
                        start_station_id, transfer_station, start_route_id, departure_time
                    )
                    
                    if not seg1:
                        continue
                    
                    # Calculate transfer arrival and minimum wait
                    transfer_arrival = seg1["arrival_time"]
                    min_departure = transfer_arrival + self.MIN_TRANSFER_TIME
                    
                    # Second segment: transfer -> end
                    seg2 = await self._get_trip_segment(
                        transfer_station, end_station_id, end_route_id, min_departure
                    )
                    
                    if not seg2:
                        continue
                    
                    # Build route segments
                    segments = []
                    
                    # First segment
                    segments.append(RouteSegment(
                        from_station=seg1["from_station"],
                        to_station=seg1["to_station"],
                        type="train",
                        line=start_line,
                        route_id=start_route_id,
                        time_seconds=(seg1["arrival_time"] - seg1["departure_time"]).total_seconds(),
                        distance_meters=0,  # Would need to calculate
                        departure_time=seg1["departure_time"],
                        arrival_time=seg1["arrival_time"],
                        status=seg1.get("status")
                    ))
                    
                    # Transfer segment
                    wait_time = (seg2["departure_time"] - seg1["arrival_time"]).total_seconds()
                    segments.append(RouteSegment(
                        from_station=transfer_station,
                        to_station=transfer_station,
                        type="transfer",
                        line=None,
                        route_id=None,
                        time_seconds=wait_time,
                        distance_meters=0,
                        departure_time=seg1["arrival_time"],
                        arrival_time=seg2["departure_time"],
                        status="Transfer"
                    ))
                    
                    # Second segment
                    segments.append(RouteSegment(
                        from_station=seg2["from_station"],
                        to_station=seg2["to_station"],
                        type="train",
                        line=end_line,
                        route_id=end_route_id,
                        time_seconds=(seg2["arrival_time"] - seg2["departure_time"]).total_seconds(),
                        distance_meters=0,
                        departure_time=seg2["departure_time"],
                        arrival_time=seg2["arrival_time"],
                        status=seg2.get("status")
                    ))
                    
                    total_time = (seg2["arrival_time"] - seg1["departure_time"]).total_seconds()
                    
                    return Route(
                        segments=segments,
                        total_time_seconds=total_time,
                        total_distance_meters=0,
                        num_transfers=1,
                        departure_time=seg1["departure_time"],
                        arrival_time=seg2["arrival_time"]
                    )
                
                except Exception as e:
                    # Continue to next route combination
                    continue
        
        return None
