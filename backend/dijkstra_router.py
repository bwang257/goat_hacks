"""
Clean Dijkstra-based routing with real-time enrichment.
Two-phase approach:
  1. Fast static pathfinding using pre-computed times
  2. Real-time enrichment for train departures
"""
import heapq
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from route_planner import Route, RouteSegment

@dataclass
class DijkstraNode:
    """Node in Dijkstra's priority queue"""
    total_time: float  # Total time from start (in seconds)
    station_id: str
    path: List[Dict]  # List of edges taken to reach this node

    def __lt__(self, other):
        """For heap comparison"""
        return self.total_time < other.total_time


class DijkstraRouter:
    """
    Clean Dijkstra-based router that separates pathfinding from real-time data.
    Phase 1: Find optimal path using static graph (fast, no API calls)
    Phase 2: Enrich with real-time train times (minimal API calls)
    """

    def __init__(self, graph_data: Dict):
        """
        Initialize with transit graph data

        Args:
            graph_data: Dict with 'nodes' and 'edges' from transit graph
        """
        self.nodes = graph_data["nodes"]
        self.edges = graph_data["edges"]

        # Build adjacency list for fast lookups
        self.adjacency: Dict[str, List[Dict]] = {}
        for edge in self.edges:
            from_id = edge["from"]
            if from_id not in self.adjacency:
                self.adjacency[from_id] = []
            self.adjacency[from_id].append(edge)

    def get_station_name(self, station_id: str) -> str:
        """Get human-readable station name"""
        return self.nodes.get(station_id, {}).get("name", station_id)

    def find_shortest_path(
        self,
        start_station_id: str,
        end_station_id: str,
        debug: bool = False
    ) -> Optional[List[Dict]]:
        """
        Phase 1: Find shortest path using Dijkstra's algorithm.
        Uses pre-computed travel times from graph (no API calls).

        Args:
            start_station_id: Starting station ID
            end_station_id: Destination station ID
            debug: Print debug information

        Returns:
            List of edges representing the path, or None if no path exists
        """

        # Validate inputs
        if start_station_id not in self.nodes or end_station_id not in self.nodes:
            if debug:
                print(f"Invalid stations: {start_station_id} or {end_station_id}")
            return None

        if debug:
            print(f"\n{'='*60}")
            print(f"DIJKSTRA PATHFINDING")
            print(f"{'='*60}")
            print(f"Start: {self.get_station_name(start_station_id)}")
            print(f"End: {self.get_station_name(end_station_id)}")
            print()

        # Initialize Dijkstra's algorithm
        pq = [DijkstraNode(0.0, start_station_id, [])]
        visited = set()
        nodes_explored = 0

        while pq:
            current = heapq.heappop(pq)
            nodes_explored += 1

            # Found destination
            if current.station_id == end_station_id:
                if debug:
                    print(f"✓ Path found!")
                    print(f"  Nodes explored: {nodes_explored}")
                    print(f"  Total time: {current.total_time/60:.1f} minutes")
                    print(f"  Segments: {len(current.path)}")
                return current.path

            # Skip if already visited
            if current.station_id in visited:
                continue
            visited.add(current.station_id)

            # Explore all neighboring edges
            for edge in self.adjacency.get(current.station_id, []):
                next_station = edge["to"]

                # Skip if already visited
                if next_station in visited:
                    continue

                # Get edge travel time
                edge_time = edge.get("time_seconds", 0)

                # Skip edges without time data
                if edge_time <= 0:
                    continue

                # Calculate new total time
                new_time = current.total_time + edge_time

                # Create new path
                new_path = current.path + [edge]

                # Add to priority queue
                heapq.heappush(pq, DijkstraNode(new_time, next_station, new_path))

        # No path found
        if debug:
            print(f"✗ No path found after exploring {nodes_explored} nodes")
        return None

    async def enrich_with_realtime(
        self,
        path: List[Dict],
        departure_time: datetime,
        mbta_client,
        debug: bool = False
    ) -> Route:
        """
        Phase 2: Enrich static path with real-time train departure data.

        Args:
            path: List of edges from Dijkstra
            departure_time: When to start the journey
            mbta_client: MBTA API client for real-time data
            debug: Print debug information

        Returns:
            Route object with real-time departure/arrival times
        """

        if debug:
            print(f"\n{'='*60}")
            print(f"REAL-TIME ENRICHMENT")
            print(f"{'='*60}")
            print(f"Departure time: {departure_time.strftime('%I:%M %p')}")
            print()

        current_time = departure_time
        enriched_segments = []
        total_distance = 0
        num_transfers = 0
        current_line = None

        for i, edge in enumerate(path):
            edge_type = edge.get("type", "train")
            from_station = edge["from"]
            to_station = edge["to"]

            if debug:
                from_name = self.get_station_name(from_station)
                to_name = self.get_station_name(to_station)
                print(f"Segment {i+1}: {edge_type.upper()} - {from_name} → {to_name}")

            if edge_type == "walk":
                # Walking: time is fixed
                walk_time = edge.get("time_seconds", 0)
                walk_distance = edge.get("distance_meters", 0)

                arrival_time = current_time + timedelta(seconds=walk_time)

                segment = RouteSegment(
                    from_station=from_station,
                    to_station=to_station,
                    type="walk",
                    line=None,
                    route_id=None,
                    time_seconds=walk_time,
                    distance_meters=walk_distance,
                    departure_time=current_time,
                    arrival_time=arrival_time,
                    status="Walking"
                )

                if debug:
                    print(f"  Walk time: {walk_time/60:.1f} min ({walk_distance:.0f}m)")

                current_time = arrival_time
                current_line = None  # Walking resets line
                total_distance += walk_distance

            elif edge_type == "train":
                # Train: get real-time departure
                route_id = edge.get("route_id")
                line_name = edge.get("line")
                static_travel_time = edge.get("time_seconds", 120)  # Default 2 min

                # Check if this is a transfer
                is_transfer = (current_line is not None and line_name != current_line)
                if is_transfer:
                    num_transfers += 1
                    # Add minimum transfer time (2 minutes)
                    current_time += timedelta(minutes=2)
                    if debug:
                        print(f"  Transfer from {current_line} to {line_name} (+2 min)")

                # Get next train departure
                try:
                    if mbta_client:
                        departures = await mbta_client.get_next_departures(
                            stop_id=from_station,
                            route_id=route_id,
                            limit=3,
                            use_predictions=True
                        )

                        # Find next available departure after current time
                        valid_departures = [d for d in departures if d["departure_time"] >= current_time]

                        if valid_departures:
                            next_train = valid_departures[0]
                            dep_time = next_train["departure_time"]
                            wait_time = (dep_time - current_time).total_seconds()

                            # Use static travel time for arrival estimate
                            arr_time = dep_time + timedelta(seconds=static_travel_time)

                            if debug:
                                print(f"  Next train: {dep_time.strftime('%I:%M %p')} (wait {wait_time/60:.1f} min)")
                                print(f"  Travel time: {static_travel_time/60:.1f} min")
                                print(f"  Status: {next_train.get('status', 'Scheduled')}")

                            segment = RouteSegment(
                                from_station=from_station,
                                to_station=to_station,
                                type="train",
                                line=line_name,
                                route_id=route_id,
                                time_seconds=(arr_time - dep_time).total_seconds(),
                                distance_meters=edge.get("distance_meters", 0),
                                departure_time=dep_time,
                                arrival_time=arr_time,
                                status=next_train.get("status", "Scheduled")
                            )

                            current_time = arr_time
                        else:
                            # No upcoming trains - use estimated times
                            if debug:
                                print(f"  No upcoming trains - using estimates")

                            dep_time = current_time
                            arr_time = dep_time + timedelta(seconds=static_travel_time)

                            segment = RouteSegment(
                                from_station=from_station,
                                to_station=to_station,
                                type="train",
                                line=line_name,
                                route_id=route_id,
                                time_seconds=static_travel_time,
                                distance_meters=edge.get("distance_meters", 0),
                                departure_time=dep_time,
                                arrival_time=arr_time,
                                status="Estimated"
                            )

                            current_time = arr_time
                    else:
                        # No MBTA client - use static times
                        dep_time = current_time
                        arr_time = dep_time + timedelta(seconds=static_travel_time)

                        segment = RouteSegment(
                            from_station=from_station,
                            to_station=to_station,
                            type="train",
                            line=line_name,
                            route_id=route_id,
                            time_seconds=static_travel_time,
                            distance_meters=edge.get("distance_meters", 0),
                            departure_time=dep_time,
                            arrival_time=arr_time,
                            status="Scheduled"
                        )

                        current_time = arr_time

                except Exception as e:
                    if debug:
                        print(f"  Error getting real-time data: {e}")

                    # Fallback to static times
                    dep_time = current_time
                    arr_time = dep_time + timedelta(seconds=static_travel_time)

                    segment = RouteSegment(
                        from_station=from_station,
                        to_station=to_station,
                        type="train",
                        line=line_name,
                        route_id=route_id,
                        time_seconds=static_travel_time,
                        distance_meters=edge.get("distance_meters", 0),
                        departure_time=dep_time,
                        arrival_time=arr_time,
                        status="Estimated"
                    )

                    current_time = arr_time

                current_line = line_name
                total_distance += edge.get("distance_meters", 0)

            else:
                # Unknown edge type - skip
                continue

            enriched_segments.append(segment)

        # Build final route
        total_time = (current_time - departure_time).total_seconds()

        if debug:
            print()
            print(f"Total journey time: {total_time/60:.1f} minutes")
            print(f"Total transfers: {num_transfers}")
            print(f"Arrival time: {current_time.strftime('%I:%M %p')}")

        return Route(
            segments=enriched_segments,
            total_time_seconds=total_time,
            total_distance_meters=total_distance,
            num_transfers=num_transfers,
            departure_time=departure_time,
            arrival_time=current_time
        )

    async def find_route(
        self,
        start_station_id: str,
        end_station_id: str,
        departure_time: Optional[datetime] = None,
        mbta_client = None,
        debug: bool = False
    ) -> Optional[Route]:
        """
        Complete two-phase routing: Dijkstra + Real-time enrichment

        Args:
            start_station_id: Starting station ID
            end_station_id: Destination station ID
            departure_time: When to depart (defaults to now)
            mbta_client: MBTA API client for real-time data (optional)
            debug: Print debug information

        Returns:
            Route object with complete journey details, or None if no route
        """

        # Phase 1: Find optimal path (fast, no API calls)
        path = self.find_shortest_path(start_station_id, end_station_id, debug=debug)

        if not path:
            return None

        # Set default departure time
        if departure_time is None:
            departure_time = datetime.now(timezone.utc)

        # Phase 2: Enrich with real-time data (minimal API calls)
        route = await self.enrich_with_realtime(path, departure_time, mbta_client, debug=debug)

        return route
