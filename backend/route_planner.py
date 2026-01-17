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
        Find path using time-aware routing, optionally prioritizing fewer transfers via multi-objective optimization.
        """
        if not mbta_client:
            raise ValueError("mbta_client is required for time-aware routing")
        
        if start_station_id not in self.nodes or end_station_id not in self.nodes:
            return None
        
        if departure_time is None:
            departure_time = datetime.now(timezone.utc)
        
        # Priority Queue Item: (sort_key, current_arrival, current_station, path, num_transfers, current_line)
        # Sort Key: (num_transfers, current_arrival) if prefer_fewer_transfers else (current_arrival, num_transfers)
        initial_sort = (0, departure_time) if prefer_fewer_transfers else (departure_time, 0)
        pq = [(initial_sort, departure_time, start_station_id, [], 0, None)]
        
        # Pareto Optimal Labels: station_id -> List[Tuple[transfers, arrival_time]]
        # We only keep labels that are non-dominated.
        best_labels: Dict[str, List[Tuple[int, datetime]]] = {}
        best_labels[start_station_id] = [(0, departure_time)]
        
        paths_explored = 0
        MAX_EXPLORATIONS = 2000  # Increased limit for multi-objective search
        
        while pq and paths_explored < MAX_EXPLORATIONS:
            _, current_arrival, current_station, path, num_transfers, current_line = heapq.heappop(pq)
            paths_explored += 1
            
            # Found destination
            if current_station == end_station_id:
                if debug:
                    print(f"\n✓ Found optimal path after exploring {paths_explored} possibilities")
                    total_time = (current_arrival - departure_time).total_seconds()
                    print(f"  Total time: {total_time/60:.1f} minutes")
                    print(f"  Transfers: {num_transfers}")
                return self._build_route(path)
            
            # Dominance Check (Pruning)
            # Check if this path is dominated by an existing label for this station
            labels = best_labels.get(current_station, [])
            # A path (t1, time1) is dominated if there exists (t2, time2) such that t2 <= t1 AND time2 <= time1
            # (and strictly better in at least one)
            # Note: Since we popped from PQ, we might have popped a dominated path if it was inserted before the improved path found.
            is_dominated = False
            for (l_transfers, l_time) in labels:
                if l_transfers <= num_transfers and l_time <= current_arrival:
                    if l_transfers < num_transfers or l_time < current_arrival:
                        is_dominated = True
                        break
                    # If equal, we continue (it's the same state) - logic below handles updating labels
            
            # Note: For Pareto BFS, strict dominance check on POP is good, but managing the list on PUSH is cleaner.
            # Here we assume if it was in PQ, it was valid at push time.
            # But we can skip if we found something strictly better since then.
            # Actually, standard Dijkstra logic is: if current_dist > best_dist[u], continue.
            # Here: if strictly dominated, continue.
             
            # Explore neighbors
            edges = self.adjacency.get(current_station, [])
            
            # Heuristic: If current station serves trains, don't walk long distances
            serves_trains = any(e.get("type") == "train" for e in edges)
            
            # Optimization: If we are on a line, and can stay on it, prefer that.
            stations_reachable_by_current_line = set()
            if current_line:
                for edge in edges:
                    if edge.get("type") == "train" and edge.get("line") == current_line:
                        stations_reachable_by_current_line.add(edge["to"])
            
            for edge in edges:
                next_station = edge["to"]
                edge_type = edge.get("type", "train")
                
                # Logic to prevent hopping off train to walk to the next station
                if current_line and edge_type == "walk":
                    if next_station in stations_reachable_by_current_line:
                        continue
                
                # Logic: Don't walk long distances (>5 mins) if we can take a train from here
                if serves_trains and edge_type == "walk":
                    walk_time = edge.get("time_seconds", 0)
                    if walk_time > 300: 
                        continue
                
                next_arrival = current_arrival
                new_transfers = num_transfers
                new_line = current_line
                edge_metadata = {}
                
                # --- EDGE COST CALCULATION ---
                if edge_type == "walk":
                    walk_time = edge.get("time_seconds", 0)
                    if walk_time == 0: continue
                    next_arrival = current_arrival + timedelta(seconds=walk_time)
                    # Use a heuristic "virtual transfer" cost for long walks? No, keep pure.
                    new_line = None # Walking breaks the line? Or keeps it? Usually breaks.
                    if current_line is not None:
                        # User said: "don't have any transfers that go from a train/subway to walking"
                        # This implies walking counts as a transfer or break.
                        # We resets line.
                        pass
                
                elif edge_type == "train":
                    route_id = edge.get("route_id")
                    if not route_id: continue
                    edge_line = edge.get("line")
                    
                    # Check transfer
                    is_transfer = (current_line is not None and edge_line != current_line)
                    if is_transfer:
                        new_transfers += 1
                        if new_transfers > max_transfers: continue

                    # SAME-LINE ZERO WAIT OPTIMIZATION
                    if current_line and edge_line == current_line:
                        segment_time = edge.get("time_seconds")
                        if not segment_time:
                            rt = edge.get("route_type", 1)
                            segment_time = 180 if rt == 2 else (120 if rt == 1 else 150)
                        next_arrival = current_arrival + timedelta(seconds=segment_time)
                        edge_metadata["status"] = "On Train"
                        new_line = edge_line
                    
                    else:
                        # API Lookup
                        try:
                            # CR Support: Verify route_id
                            # get_next_departures handles it.
                            deps = await mbta_client.get_next_departures(
                                stop_id=current_station,
                                route_id=route_id,
                                limit=3,
                                use_predictions=True
                            )
                            valid_deps = [d for d in deps if d["departure_time"] >= current_arrival]
                            
                            # Transfer slack
                            if is_transfer:
                                min_transfer = timedelta(minutes=2)
                                valid_deps = [d for d in valid_deps if d["departure_time"] >= current_arrival + min_transfer]
                            
                            if not valid_deps: continue
                            
                            departure = valid_deps[0]
                            dep_time = departure["departure_time"]
                            
                            # Travel time
                            segment_time = edge.get("time_seconds")
                            if not segment_time:
                                rt = edge.get("route_type", 1)
                                segment_time = 180 if rt == 2 else (120 if rt == 1 else 150)
                            
                            next_arrival = dep_time + timedelta(seconds=segment_time)
                            new_line = edge_line
                            
                            edge_metadata["departure_time"] = dep_time.isoformat()
                            edge_metadata["status"] = departure.get("status", "Scheduled")
                            
                        except Exception as e:
                            # if debug: print(f"API Error: {e}")
                            continue

                # --- UPDATE PARETO SET & PQ ---
                # Check if (new_transfers, next_arrival) is dominated by any existing label at next_station
                labels = best_labels.get(next_station, [])
                is_this_dominated = False
                for (l_transfers, l_time) in labels:
                     if l_transfers <= new_transfers and l_time <= next_arrival:
                          is_this_dominated = True
                          break
                
                if not is_this_dominated:
                    # Remove dominated labels
                    new_labels = [l for l in labels if not (new_transfers <= l[0] and next_arrival <= l[1])]
                    new_labels.append((new_transfers, next_arrival))
                    best_labels[next_station] = new_labels
                    
                    # Build path
                    new_edge = edge.copy()
                    new_edge["arrival_time"] = next_arrival.isoformat()
                    if "departure_time" in edge_metadata:
                        new_edge["departure_time"] = edge_metadata["departure_time"]
                    else:
                        new_edge["departure_time"] = current_arrival.isoformat()
                    if "status" in edge_metadata:
                        new_edge["status"] = edge_metadata["status"]
                        
                    new_path = path + [new_edge]
                    
                    # Sort Key
                    sort_key = (new_transfers, next_arrival) if prefer_fewer_transfers else (next_arrival, new_transfers)
                    
                    heapq.heappush(pq, (sort_key, next_arrival, next_station, new_path, new_transfers, new_line))

        if debug:
            print(f"\n✗ No path found after exploring {paths_explored} possibilities")
        return None
