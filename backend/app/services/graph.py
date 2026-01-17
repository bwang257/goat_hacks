"""
MBTA Transit Graph - Graph-based pathfinding for transit routing

Stations are nodes, routes/transfers are edges with weights (time/distance).
Uses Dijkstra's algorithm for optimal pathfinding.
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import heapq


@dataclass
class Edge:
    """Edge between two stations with weight (time in seconds)"""
    to_station_id: str
    route: str  # Route name or "walk" for transfers
    weight: float  # Time in seconds
    distance: float  # Distance in meters


@dataclass
class PathSegment:
    """Segment of a path between stations"""
    from_station: str
    to_station: str
    route: str
    time_seconds: float
    distance_meters: float


@dataclass
class Path:
    """Complete path from origin to destination"""
    segments: List[PathSegment]
    total_time: float
    total_distance: float
    transfers: int


class TransitGraph:
    """Graph representing MBTA transit system"""
    
    def __init__(self):
        # Adjacency list: station_id -> [Edge, ...]
        self.graph: Dict[str, List[Edge]] = defaultdict(list)
        self.stations: Dict[str, Dict] = {}  # station_id -> station data
        
    def add_station(self, station_id: str, station_data: Dict):
        """Add a station node to the graph"""
        self.stations[station_id] = station_data
        
    def add_route_edge(self, from_station_id: str, to_station_id: str, route: str, 
                       time_seconds: float, distance_meters: float):
        """Add an edge for a route segment between stations"""
        self.graph[from_station_id].append(
            Edge(to_station_id, route, time_seconds, distance_meters)
        )
    
    def add_transfer_edge(self, from_station_id: str, to_station_id: str, 
                          walk_distance_meters: float, walk_speed_mps: float):
        """Add a transfer edge (walking between platforms)"""
        walk_time = walk_distance_meters / walk_speed_mps
        self.graph[from_station_id].append(
            Edge(to_station_id, "walk", walk_time, walk_distance_meters)
        )
    
    def dijkstra(self, start_id: str, end_id: str) -> Optional[Path]:
        """
        Find shortest path using Dijkstra's algorithm.
        Returns Path or None if no path exists.
        """
        # Priority queue: (total_time, station_id, path_so_far)
        pq = [(0, start_id, [])]
        visited = set()
        distances = {start_id: 0}
        
        while pq:
            current_time, current_id, path = heapq.heappop(pq)
            
            if current_id in visited:
                continue
                
            visited.add(current_id)
            path = path + [current_id]
            
            if current_id == end_id:
                # Reconstruct path segments
                segments = []
                for i in range(len(path) - 1):
                    from_id = path[i]
                    to_id = path[i + 1]
                    
                    # Find edge between these stations
                    edge = None
                    for e in self.graph[from_id]:
                        if e.to_station_id == to_id:
                            edge = e
                            break
                    
                    if edge:
                        segments.append(PathSegment(
                            from_station=from_id,
                            to_station=to_id,
                            route=edge.route,
                            time_seconds=edge.weight,
                            distance_meters=edge.distance
                        ))
                
                transfers = sum(1 for s in segments if s.route == "walk")
                
                return Path(
                    segments=segments,
                    total_time=current_time,
                    total_distance=sum(s.distance_meters for s in segments),
                    transfers=transfers
                )
            
            # Explore neighbors
            for edge in self.graph[current_id]:
                if edge.to_station_id in visited:
                    continue
                
                new_time = current_time + edge.weight
                
                if edge.to_station_id not in distances or new_time < distances[edge.to_station_id]:
                    distances[edge.to_station_id] = new_time
                    heapq.heappush(pq, (new_time, edge.to_station_id, path))
        
        return None  # No path found
    
    def find_all_paths(self, start_id: str, end_id: str, max_paths: int = 3) -> List[Path]:
        """
        Find multiple paths between stations using modified Dijkstra.
        Returns top N shortest paths.
        """
        paths = []
        pq = [(0, start_id, [])]
        visited = set()
        
        while pq and len(paths) < max_paths:
            current_time, current_id, path = heapq.heappop(pq)
            
            if current_id == end_id:
                # Reconstruct path
                segments = []
                for i in range(len(path) - 1):
                    from_id = path[i]
                    to_id = path[i + 1]
                    
                    edge = None
                    for e in self.graph[from_id]:
                        if e.to_station_id == to_id:
                            edge = e
                            break
                    
                    if edge:
                        segments.append(PathSegment(
                            from_station=from_id,
                            to_station=to_id,
                            route=edge.route,
                            time_seconds=edge.weight,
                            distance_meters=edge.distance
                        ))
                
                transfers = sum(1 for s in segments if s.route == "walk")
                paths.append(Path(
                    segments=segments,
                    total_time=current_time,
                    total_distance=sum(s.distance_meters for s in segments),
                    transfers=transfers
                ))
                continue
            
            # Track visited states: (station_id, path_hash) to allow revisiting via different routes
            path_hash = tuple(path[-3:] if len(path) >= 3 else tuple(path))  # Last 3 stations
            state = (current_id, path_hash)
            
            if state in visited:
                continue
            visited.add(state)
            
            for edge in self.graph[current_id]:
                # Avoid cycles (don't revisit same station immediately)
                if edge.to_station_id in path[-2:]:
                    continue
                
                new_path = path + [edge.to_station_id]
                new_time = current_time + edge.weight
                
                # Use path length as tiebreaker for diversity
                tiebreaker = len(new_path) * 0.01
                heapq.heappush(pq, (new_time + tiebreaker, edge.to_station_id, new_path))
        
        return paths
