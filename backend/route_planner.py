import json
import heapq
import asyncio
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

@dataclass
class RouteSegment:
    """Represents one segment of a journey"""
    from_station: str
    to_station: str
    type: str  # "train", "walk", or "transfer"
    line: Optional[str]  # Line name if train, None if walk/transfer
    route_id: Optional[str]  # Route ID if train
    time_seconds: float  # Duration of this segment
    distance_meters: float
    departure_time: Optional[datetime] = None  # When this segment starts
    arrival_time: Optional[datetime] = None  # When this segment ends
    status: Optional[str] = None  # "On time", "Delayed", etc. for train segments

@dataclass
class Route:
    """Complete route from start to end"""
    segments: List[RouteSegment]
    total_time_seconds: float
    total_distance_meters: float
    num_transfers: int
    departure_time: Optional[datetime] = None  # When journey starts
    arrival_time: Optional[datetime] = None  # When journey ends

class TransitGraph:
    def __init__(self, graph_file: str = "data/mbta_transit_graph.json"):
        with open(graph_file, "r") as f:
            data = json.load(f)
        
        self.metadata = data.get("metadata", {})
        self.nodes = data["graph"]["nodes"]
        self.edges = data["graph"]["edges"]
        self.transfer_stations = data.get("transfer_stations", [])
        
        # Build adjacency list for faster lookups
        self.adjacency = {}
        for edge in self.edges:
            from_id = edge["from"]
            if from_id not in self.adjacency:
                self.adjacency[from_id] = []
            self.adjacency[from_id].append(edge)
    
    def _build_route(self, path: List[Dict]) -> Route:
        """Convert a list of edges into a Route object"""
        segments = []
        total_time = 0
        total_distance = 0
        num_transfers = 0
        current_line = None
        departure_time = None
        arrival_time = None
        
        for edge in path:
            # Get time_seconds - for train edges it may not exist (use from API)
            # For walking edges, it should exist
            edge_time = edge.get("time_seconds", 0)
            
            # Get departure/arrival times if available
            seg_departure = edge.get("departure_time")
            seg_arrival = edge.get("arrival_time")
            
            if seg_departure and isinstance(seg_departure, str):
                seg_departure = datetime.fromisoformat(seg_departure.replace('Z', '+00:00'))
            if seg_arrival and isinstance(seg_arrival, str):
                seg_arrival = datetime.fromisoformat(seg_arrival.replace('Z', '+00:00'))
            
            if seg_departure and not departure_time:
                departure_time = seg_departure
            if seg_arrival:
                arrival_time = seg_arrival
            
            segment = RouteSegment(
                from_station=edge["from"],
                to_station=edge["to"],
                type=edge["type"],
                line=edge.get("line"),
                route_id=edge.get("route_id"),
                time_seconds=edge_time,
                distance_meters=edge.get("distance_meters", 0),
                departure_time=seg_departure,
                arrival_time=seg_arrival,
                status=edge.get("status")
            )
            segments.append(segment)
            
            total_time += edge_time
            total_distance += edge.get("distance_meters", 0)
            
            # Count transfers
            if edge.get("type") == "train":
                if current_line and edge.get("line") != current_line:
                    num_transfers += 1
                current_line = edge.get("line")
        
        return Route(
            segments=segments,
            total_time_seconds=total_time,
            total_distance_meters=total_distance,
            num_transfers=num_transfers,
            departure_time=departure_time,
            arrival_time=arrival_time
        )
    
    def get_station_name(self, station_id: str) -> str:
        """Get station name from ID"""
        return self.nodes.get(station_id, {}).get("name", station_id)
    
    def find_shortest_path(
        self,
        start_station_id: str,
        end_station_id: str,
        prefer_fewer_transfers: bool = True,
        debug: bool = False
    ) -> Optional[Route]:
        """
        Find shortest path using static graph (for walking-only or backward compatibility).
        For time-aware routing with MBTA schedules, use find_time_aware_path instead.
        """
        
        if start_station_id not in self.nodes or end_station_id not in self.nodes:
            return None
        
        pq = [(0, start_station_id, [], None)]
        best_times = {start_station_id: 0}
        
        TRANSFER_PENALTY = 180 if prefer_fewer_transfers else 0
        
        paths_explored = 0
        
        while pq:
            current_time, current_station, path, current_line = heapq.heappop(pq)
            paths_explored += 1
            
            # Found destination
            if current_station == end_station_id:
                if debug:
                    print(f"\n✓ Found optimal path after exploring {paths_explored} possibilities")
                    print(f"  Total time: {current_time/60:.1f} minutes")
                    print(f"  Path length: {len(path)} segments")
                return self._build_route(path)
            
            # Skip if we've found a better path to this station
            if current_time > best_times.get(current_station, float('inf')):
                continue
            
            # Explore neighbors
            for edge in self.adjacency.get(current_station, []):
                next_station = edge["to"]
                
                # For train edges without time_seconds, skip (need API lookup)
                # For walking edges, use the time_seconds
                if edge.get("type") == "train" and "time_seconds" not in edge:
                    continue  # Skip train edges without time - need API
                
                edge_time = edge.get("time_seconds", 0)
                
                # Add transfer penalty if changing lines
                transfer_penalty = 0
                if current_line and edge.get("type") == "train":
                    if edge.get("line") != current_line:
                        transfer_penalty = TRANSFER_PENALTY
                        if debug and transfer_penalty > 0:
                            print(f"  Transfer penalty: {current_line} → {edge.get('line')}")
                
                total_time = current_time + edge_time + transfer_penalty
                
                # Only continue if this is a better path
                if total_time < best_times.get(next_station, float('inf')):
                    best_times[next_station] = total_time
                    new_path = path + [edge]
                    new_line = edge.get("line") if edge.get("type") == "train" else current_line
                    heapq.heappush(pq, (total_time, next_station, new_path, new_line))
        
        if debug:
            print(f"\n✗ No path found after exploring {paths_explored} possibilities")
        
        return None
    
    async def find_time_aware_path(
        self,
        start_station_id: str,
        end_station_id: str,
        departure_time: Optional[datetime] = None,
        mbta_client = None,
        prefer_fewer_transfers: bool = True,
        max_transfers: int = 3,
        debug: bool = False
    ) -> Optional[Route]:
        """
        Find path using time-aware routing with MBTA API schedules/predictions.
        
        Args:
            start_station_id: Starting station
            end_station_id: Ending station
            departure_time: When to start journey (defaults to now)
            mbta_client: MBTAClient instance for API calls
            prefer_fewer_transfers: Prefer routes with fewer transfers
            max_transfers: Maximum number of transfers allowed
            debug: Print debug information
        
        Returns:
            Route object with actual departure/arrival times, or None if no path
        """
        if not mbta_client:
            raise ValueError("mbta_client is required for time-aware routing")
        
        if start_station_id not in self.nodes or end_station_id not in self.nodes:
            return None
        
        if departure_time is None:
            departure_time = datetime.now(timezone.utc)
        
        # Time-expanded graph approach: nodes are (station_id, arrival_time)
        # Priority queue: (arrival_time, station_id, path, num_transfers)
        pq = [(departure_time, start_station_id, [], 0, None)]
        
        # Best arrival time at each station
        best_arrivals: Dict[str, datetime] = {start_station_id: departure_time}
        
        paths_explored = 0
        MAX_EXPLORATIONS = 1000  # Limit to prevent infinite loops
        
        while pq and paths_explored < MAX_EXPLORATIONS:
            current_arrival, current_station, path, num_transfers, current_line = heapq.heappop(pq)
            paths_explored += 1
            
            # Found destination
            if current_station == end_station_id:
                if debug:
                    print(f"\n✓ Found optimal path after exploring {paths_explored} possibilities")
                    total_time = (current_arrival - departure_time).total_seconds()
                    print(f"  Total time: {total_time/60:.1f} minutes")
                    print(f"  Transfers: {num_transfers}")
                return self._build_route(path)
            
            # Skip if we've found a better path to this station
            if current_station in best_arrivals and current_arrival > best_arrivals[current_station]:
                continue
            
            # Check transfer limit
            if num_transfers > max_transfers:
                continue
            
            # Explore neighbors
            for edge in self.adjacency.get(current_station, []):
                next_station = edge["to"]
                edge_type = edge.get("type", "train")
                
                if edge_type == "walk":
                    # Walking edges have static time_seconds
                    walk_time = edge.get("time_seconds", 0)
                    if walk_time == 0:
                        continue
                    
                    next_arrival = current_arrival + timedelta(seconds=walk_time)
                    
                    # Only continue if this is better
                    if next_station not in best_arrivals or next_arrival < best_arrivals[next_station]:
                        best_arrivals[next_station] = next_arrival
                        walk_edge = edge.copy()
                        walk_edge["departure_time"] = current_arrival.isoformat()
                        walk_edge["arrival_time"] = next_arrival.isoformat()
                        new_path = path + [walk_edge]
                        heapq.heappush(pq, (next_arrival, next_station, new_path, num_transfers, current_line))
                
                elif edge_type == "train":
                    # Train edges need MBTA API lookup
                    route_id = edge.get("route_id")
                    if not route_id:
                        continue
                    
                    # Get next departures from current station on this route
                    try:
                        # Determine direction - simple heuristic: check if end station is reachable
                        # For now, try both directions and pick the one that gets us closer
                        direction_id = None  # Will try both if None
                        
                        departures = await mbta_client.get_next_departures(
                            stop_id=current_station,
                            route_id=route_id,
                            direction_id=direction_id,
                            limit=3,
                            use_predictions=True
                        )
                        
                        # Filter departures that are after current arrival time
                        valid_departures = [
                            d for d in departures
                            if d["departure_time"] >= current_arrival
                        ]
                        
                        if not valid_departures:
                            continue
                        
                        # Use the first valid departure
                        departure = valid_departures[0]
                        dep_time = departure["departure_time"]
                        
                        # For now, estimate travel time to next station
                        # In a full implementation, we'd query the schedule for arrival at next_station
                        # For simplicity, use a conservative estimate based on route type
                        route_type = edge.get("route_type", 1)
                        if route_type == 1:  # Heavy Rail
                            segment_time = 120  # 2 min per segment estimate
                        elif route_type == 0:  # Light Rail
                            segment_time = 150  # 2.5 min per segment
                        else:  # Commuter Rail
                            segment_time = 180  # 3 min per segment
                        
                        # Calculate arrival at next station
                        next_arrival = dep_time + timedelta(seconds=segment_time)
                        
                        # Check if this is a transfer
                        is_transfer = (current_line is not None and 
                                     edge.get("line") != current_line)
                        
                        # Add transfer wait time if needed
                        if is_transfer:
                            # Minimum transfer time: 2 minutes
                            min_transfer_time = timedelta(minutes=2)
                            if dep_time < current_arrival + min_transfer_time:
                                # Need to wait for next departure
                                if len(valid_departures) > 1:
                                    departure = valid_departures[1]
                                    dep_time = departure["departure_time"]
                                    next_arrival = dep_time + timedelta(seconds=segment_time)
                                else:
                                    continue  # No valid transfer possible
                        
                        # Only continue if this is better
                        if next_station not in best_arrivals or next_arrival < best_arrivals[next_station]:
                            best_arrivals[next_station] = next_arrival
                            
                            train_edge = edge.copy()
                            train_edge["departure_time"] = dep_time.isoformat()
                            train_edge["arrival_time"] = next_arrival.isoformat()
                            train_edge["time_seconds"] = segment_time
                            train_edge["status"] = departure.get("status", "Scheduled")
                            
                            new_transfers = num_transfers + (1 if is_transfer else 0)
                            new_line = edge.get("line")
                            new_path = path + [train_edge]
                            
                            heapq.heappush(pq, (next_arrival, next_station, new_path, new_transfers, new_line))
                    
                    except Exception as e:
                        if debug:
                            print(f"Error getting departures for {current_station} on {route_id}: {e}")
                        continue
        
        if debug:
            print(f"\n✗ No path found after exploring {paths_explored} possibilities")
        
        return None
