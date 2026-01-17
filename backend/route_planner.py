import json
import heapq
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

@dataclass
class RouteSegment:
    """Represents one segment of a journey"""
    from_station: str
    to_station: str
    type: str  # "train" or "walk"
    line: Optional[str]  # Line name if train, None if walk
    time_seconds: float
    distance_meters: float

@dataclass
class Route:
    """Complete route from start to end"""
    segments: List[RouteSegment]
    total_time_seconds: float
    total_distance_meters: float
    num_transfers: int

class TransitGraph:
    def __init__(self, graph_file: str = "data/mbta_transit_graph.json"):
        with open(graph_file, "r") as f:
            data = json.load(f)
        
        self.metadata = data["metadata"]
        self.nodes = data["graph"]["nodes"]
        self.edges = data["graph"]["edges"]
        
        # Build adjacency list for faster lookups
        self.adjacency = {}
        for edge in self.edges:
            from_id = edge["from"]
            if from_id not in self.adjacency:
                self.adjacency[from_id] = []
            self.adjacency[from_id].append(edge)
    
    # def find_shortest_path(
    #     self,
    #     start_station_id: str,
    #     end_station_id: str,
    #     prefer_fewer_transfers: bool = True
    # ) -> Optional[Route]:
    #     """
    #     Find the shortest path between two stations using Dijkstra's algorithm.
        
    #     Args:
    #         start_station_id: Starting station ID
    #         end_station_id: Ending station ID
    #         prefer_fewer_transfers: If True, add penalty for transfers
        
    #     Returns:
    #         Route object with complete journey details, or None if no path exists
    #     """
        
    #     if start_station_id not in self.nodes or end_station_id not in self.nodes:
    #         return None
        
    #     # Priority queue: (total_time, station_id, path, current_line)
    #     # path is a list of edges taken
    #     pq = [(0, start_station_id, [], None)]
        
    #     # Best time to reach each station
    #     best_times = {start_station_id: 0}
        
    #     TRANSFER_PENALTY = 180 if prefer_fewer_transfers else 0  # 3 min penalty
        
    #     while pq:
    #         current_time, current_station, path, current_line = heapq.heappop(pq)
            
    #         # Found destination
    #         if current_station == end_station_id:
    #             return self._build_route(path)
            
    #         # Skip if we've found a better path to this station
    #         if current_time > best_times.get(current_station, float('inf')):
    #             continue
            
    #         # Explore neighbors
    #         for edge in self.adjacency.get(current_station, []):
    #             next_station = edge["to"]
    #             edge_time = edge["time_seconds"]
                
    #             # Add transfer penalty if changing lines
    #             transfer_penalty = 0
    #             if current_line and edge.get("type") == "train":
    #                 if edge.get("line") != current_line:
    #                     transfer_penalty = TRANSFER_PENALTY
                
    #             total_time = current_time + edge_time + transfer_penalty
                
    #             # Only continue if this is a better path
    #             if total_time < best_times.get(next_station, float('inf')):
    #                 best_times[next_station] = total_time
    #                 new_path = path + [edge]
    #                 new_line = edge.get("line") if edge.get("type") == "train" else current_line
    #                 heapq.heappush(pq, (total_time, next_station, new_path, new_line))
        
    #     # No path found
    #     return None
    
    def _build_route(self, path: List[Dict]) -> Route:
        """Convert a list of edges into a Route object"""
        segments = []
        total_time = 0
        total_distance = 0
        num_transfers = 0
        current_line = None
        
        for edge in path:
            segment = RouteSegment(
                from_station=edge["from"],
                to_station=edge["to"],
                type=edge["type"],
                line=edge.get("line"),
                time_seconds=edge["time_seconds"],
                distance_meters=edge.get("distance_meters", 0)
            )
            segments.append(segment)
            
            total_time += edge["time_seconds"]
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
            num_transfers=num_transfers
        )
    
    def get_station_name(self, station_id: str) -> str:
        """Get station name from ID"""
        return self.nodes.get(station_id, {}).get("name", station_id)
    
    def find_shortest_path(
        self,
        start_station_id: str,
        end_station_id: str,
        prefer_fewer_transfers: bool = True,
        debug: bool = False  # Add debug flag
    ) -> Optional[Route]:
        """Find shortest path with optional debugging"""
        
        if start_station_id not in self.nodes or end_station_id not in self.nodes:
            return None
        
        pq = [(0, start_station_id, [], None)]
        best_times = {start_station_id: 0}
        
        TRANSFER_PENALTY = 180 if prefer_fewer_transfers else 0
        
        paths_explored = 0  # Count how many paths we explore
        
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
                edge_time = edge["time_seconds"]
                
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


# if __name__ == "__main__":
#     graph = TransitGraph("./data/mbta_transit_graph.json")
    
#     print("=" * 60)
#     print("TEST 1: Same line (Red Line)")
#     print("=" * 60)
#     # Harvard (Red) to South Station (Red)
#     route1 = graph.find_shortest_path("place-harsq", "place-sstat", debug=True)
    
#     if route1:
#         print(f"\nRoute: {route1.num_transfers} transfers")
#         for seg in route1.segments:
#             if seg.type == "train":
#                 print(f"  - {seg.line}: {graph.get_station_name(seg.from_station)} → {graph.get_station_name(seg.to_station)}")
    
#     print("\n" + "=" * 60)
#     print("TEST 2: Cross-line (Red to Orange)")
#     print("=" * 60)
#     # Harvard (Red) to Forest Hills (Orange)
#     route2 = graph.find_shortest_path("place-harsq", "place-forhl", debug=True)
    
#     if route2:
#         print(f"\nRoute: {route2.num_transfers} transfers")
#         for seg in route2.segments:
#             if seg.type == "train":
#                 print(f"  - {seg.line}: {graph.get_station_name(seg.from_station)} → {graph.get_station_name(seg.to_station)}")
#             elif seg.type == "walk":
#                 print(f"  - WALK: {graph.get_station_name(seg.from_station)} → {graph.get_station_name(seg.to_station)}")

# Add this to route_planner.py
if __name__ == "__main__":
    graph = TransitGraph("./data/mbta_transit_graph.json")
    
    print("=" * 60)
    print("Comparing Route Options: Harvard → Forest Hills")
    print("=" * 60)
    
    # Option 1: With transfer penalty (should prefer fewer transfers)
    print("\nOption 1: Prefer fewer transfers (180s penalty)")
    route1 = graph.find_shortest_path("place-harsq", "place-forhl", prefer_fewer_transfers=True)
    
    if route1:
        print(f"Total time: {route1.total_time_seconds/60:.1f} minutes")
        print(f"Transfers: {route1.num_transfers}")
        print("Path:")
        current_line = None
        for i, seg in enumerate(route1.segments):
            from_name = graph.get_station_name(seg.from_station)
            to_name = graph.get_station_name(seg.to_station)
            if seg.type == "train":
                if current_line != seg.line:
                    print(f"  [{seg.line}]")
                    current_line = seg.line
                print(f"    {from_name} → {to_name} ({seg.time_seconds:.0f}s)")
            else:
                print(f"  [WALK] {from_name} → {to_name} ({seg.time_seconds:.0f}s)")
    
    # Option 2: Without transfer penalty (fastest absolute time)
    print("\n" + "=" * 60)
    print("Option 2: No transfer penalty (fastest absolute)")
    route2 = graph.find_shortest_path("place-harsq", "place-forhl", prefer_fewer_transfers=False)
    
    if route2:
        print(f"Total time: {route2.total_time_seconds/60:.1f} minutes")
        print(f"Transfers: {route2.num_transfers}")
        print("Path:")
        current_line = None
        for i, seg in enumerate(route2.segments):
            from_name = graph.get_station_name(seg.from_station)
            to_name = graph.get_station_name(seg.to_station)
            if seg.type == "train":
                if current_line != seg.line:
                    print(f"  [{seg.line}]")
                    current_line = seg.line
                print(f"    {from_name} → {to_name} ({seg.time_seconds:.0f}s)")
            else:
                print(f"  [WALK] {from_name} → {to_name} ({seg.time_seconds:.0f}s)")
    
    # Option 3: Manually calculate what SHOULD be the best route
    print("\n" + "=" * 60)
    print("Manual calculation: Red → Orange route")
    print("=" * 60)
    
    # Red Line: Harvard → DTX
    red_stations = ["place-harsq", "place-cntsq", "place-knncl", "place-chmnl", 
                    "place-pktrm", "place-dwnxg"]
    red_time = 0
    for i in range(len(red_stations) - 1):
        edges = graph.adjacency.get(red_stations[i], [])
        red_edges = [e for e in edges if e.get("line") == "Red Line" and e["to"] == red_stations[i+1]]
        if red_edges:
            red_time += red_edges[0]["time_seconds"]
    
    print(f"Red Line (Harvard → DTX): {red_time:.0f}s ({red_time/60:.1f} min)")
    
    # Transfer penalty
    print(f"Transfer penalty: 180s (3 min)")
    
    # Orange Line: DTX → Forest Hills
    orange_stations = ["place-dwnxg", "place-chncl", "place-tumnl", "place-bbsta",
                      "place-masta", "place-rugg", "place-rcmnl", "place-jaksn",
                      "place-sbmnl", "place-grnst", "place-forhl"]
    orange_time = 0
    for i in range(len(orange_stations) - 1):
        edges = graph.adjacency.get(orange_stations[i], [])
        orange_edges = [e for e in edges if e.get("line") == "Orange Line" and e["to"] == orange_stations[i+1]]
        if orange_edges:
            orange_time += orange_edges[0]["time_seconds"]
    
    print(f"Orange Line (DTX → Forest Hills): {orange_time:.0f}s ({orange_time/60:.1f} min)")
    
    total_red_orange = red_time + 180 + orange_time
    print(f"\nTotal Red→Orange route: {total_red_orange:.0f}s ({total_red_orange/60:.1f} min)")
    
    # Now check the commuter rail route that was chosen
    print("\n" + "=" * 60)
    print("Commuter Rail Route Analysis")
    print("=" * 60)
    
    # The route went: Red → South Station → Back Bay → Ruggles → Forest Hills
    # Let's see the times for commuter rail segments
    
    # Check South Station → Back Bay on Worcester Line
    ss_edges = graph.adjacency.get("place-sstat", [])
    worcester_edges = [e for e in ss_edges if e.get("line") == "Framingham/Worcester Line"]
    print("\nSouth Station Framingham/Worcester connections:")
    for e in worcester_edges[:3]:
        print(f"  → {graph.get_station_name(e['to'])}: {e['time_seconds']:.0f}s")