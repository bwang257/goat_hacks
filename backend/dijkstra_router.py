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
from transfer_analyzer import calculate_transfer_time, rate_transfer

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

            # Get the current line we're on (from the last edge in path)
            current_line = None
            if current.path:
                last_edge = current.path[-1]
                current_line = last_edge.get("line") or last_edge.get("route_id")

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

                # Add a small penalty for unnecessary line changes
                # This ensures we prefer staying on the same line when costs are equal
                edge_line = edge.get("line") or edge.get("route_id")
                if current_line and edge_line and current_line != edge_line:
                    # Check if both are train edges (not walk)
                    edge_type = edge.get("type", "train")
                    last_edge_type = current.path[-1].get("type", "train") if current.path else "train"
                    if edge_type == "train" and last_edge_type == "train":
                        # Add 1 second penalty for line change - just enough to break ties
                        # This won't affect routes where changing lines is actually faster
                        new_time += 1

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
        walking_speed_kmh: float = 5.0,
        request_time: Optional[datetime] = None,
        debug: bool = False
    ) -> Route:
        """
        Phase 2: Enrich static path with real-time train departure data.

        Args:
            path: List of edges from Dijkstra
            departure_time: When to start searching for departures (may be later than "now" for alternatives)
            mbta_client: MBTA API client for real-time data
            walking_speed_kmh: User's walking speed preference
            request_time: Original "now" time when user requested route (for total_time calculation)
            debug: Print debug information

        Returns:
            Route object with real-time departure/arrival times
        """

        if debug:
            print(f"\n{'='*60}")
            print(f"REAL-TIME ENRICHMENT")
            print(f"{'='*60}")
            print(f"Departure time: {departure_time.strftime('%I:%M %p')}")
            if request_time:
                print(f"Request time (now): {request_time.strftime('%I:%M %p')}")
            print()

        # Store request time separately - this is when user clicked, used for total_time calculation
        # If not provided, use departure_time as request_time (for primary routes)
        if request_time is None:
            request_time = departure_time
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
                # Walking: recalculate time based on user's walking speed
                walk_distance = edge.get("distance_meters", 0)
                
                # Calculate walking time based on user's speed preference
                # Speed conversion: km/h to m/s
                speed_ms = walking_speed_kmh * 1000 / 3600
                walk_time = walk_distance / speed_ms if speed_ms > 0 else edge.get("time_seconds", 0)

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
                # Note: Green Line branches (B, C, D, E) are NOT considered transfers
                def is_same_line_family(line1, line2):
                    """Check if two lines are in the same family (e.g., Green Line branches)"""
                    if line1 is None or line2 is None:
                        return False
                    # Green Line branches
                    green_branches = {'B', 'C', 'D', 'E', 'Green-B', 'Green-C', 'Green-D', 'Green-E'}
                    if line1 in green_branches and line2 in green_branches:
                        return True
                    # Otherwise, must match exactly
                    return line1 == line2

                is_transfer = (current_line is not None and not is_same_line_family(line_name, current_line))
                transfer_buffer_seconds = 0
                if is_transfer:
                    num_transfers += 1
                    # Calculate dynamic transfer buffer based on station, lines, and walking speed
                    transfer_buffer_seconds = calculate_transfer_time(
                        station_id=from_station,
                        from_line=current_line,
                        to_line=line_name,
                        walking_speed_kmh=walking_speed_kmh
                    )
                    current_time += timedelta(seconds=transfer_buffer_seconds)
                    if debug:
                        print(f"  Transfer from {current_line} to {line_name} (+{transfer_buffer_seconds/60:.1f} min)")

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

                            # Get actual arrival time at destination stop if available
                            # The arrival_time in next_train is for the from_station, not to_station
                            # So we need to get the arrival time at the destination stop
                            arr_time = None
                            actual_travel_time = static_travel_time
                            
                            # Try to get arrival time at destination stop using trip_id
                            if mbta_client and next_train.get("trip_id") and to_station:
                                try:
                                    # Get predictions for the destination stop with the same trip
                                    dest_predictions = await mbta_client.get_predictions(
                                        stop_id=to_station,
                                        trip_id=next_train["trip_id"],
                                        limit=1
                                    )
                                    
                                    if dest_predictions:
                                        dest_pred = dest_predictions[0]
                                        dest_attrs = dest_pred.get("attributes", {})
                                        dest_arrival = dest_attrs.get("arrival_time")
                                        
                                        if dest_arrival:
                                            if isinstance(dest_arrival, str):
                                                if dest_arrival.endswith('Z'):
                                                    dest_arrival = dest_arrival.replace('Z', '+00:00')
                                                arr_time = datetime.fromisoformat(dest_arrival)
                                            elif isinstance(dest_arrival, datetime):
                                                arr_time = dest_arrival
                                            
                                            # Ensure arrival time is after departure time
                                            if arr_time and arr_time > dep_time:
                                                actual_travel_time = (arr_time - dep_time).total_seconds()
                                            else:
                                                arr_time = None
                                except Exception as e:
                                    if debug:
                                        print(f"  Could not get arrival time at destination: {e}")
                            
                            # Fallback to static estimate if we couldn't get actual arrival time
                            if arr_time is None:
                                arr_time = dep_time + timedelta(seconds=static_travel_time)
                                actual_travel_time = static_travel_time

                            # Calculate transfer rating if this is a transfer
                            transfer_rating = None
                            slack_time = None
                            if is_transfer and transfer_buffer_seconds > 0:
                                # Slack time = available time - required buffer
                                # Available time is the wait_time we calculated
                                # But we need to account for the buffer we already added
                                slack_time = wait_time - transfer_buffer_seconds
                                transfer_rating = rate_transfer(slack_time).value

                            if debug:
                                print(f"  Next train: {dep_time.strftime('%I:%M %p')} (wait {wait_time/60:.1f} min)")
                                print(f"  Travel time: {static_travel_time/60:.1f} min")
                                print(f"  Status: {next_train.get('status', 'Scheduled')}")
                                if is_transfer:
                                    print(f"  Transfer rating: {transfer_rating} (slack: {slack_time/60:.1f} min)")

                            segment = RouteSegment(
                                from_station=from_station,
                                to_station=to_station,
                                type="train",
                                line=line_name,
                                route_id=route_id,
                                time_seconds=actual_travel_time,
                                distance_meters=edge.get("distance_meters", 0),
                                departure_time=dep_time,
                                arrival_time=arr_time,
                                status=next_train.get("status", "Scheduled"),
                                transfer_rating=transfer_rating,
                                slack_time_seconds=slack_time,
                                buffer_seconds=transfer_buffer_seconds if is_transfer else None
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
        # Calculate total_time from request_time (when user clicked) to arrival
        # This includes wait time for first train, not just travel time
        total_time = (current_time - request_time).total_seconds()

        if debug:
            print()
            print(f"Total journey time (from now): {total_time/60:.1f} minutes")
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
        walking_speed_kmh: float = 5.0,
        request_time: Optional[datetime] = None,
        debug: bool = False
    ) -> Optional[Route]:
        """
        Complete two-phase routing: Dijkstra + Real-time enrichment

        Args:
            start_station_id: Starting station ID
            end_station_id: Destination station ID
            departure_time: When to start searching for departures (defaults to now, may be later for alternatives)
            mbta_client: MBTA API client for real-time data (optional)
            walking_speed_kmh: User's walking speed preference
            request_time: Original "now" time when user requested route (for total_time calculation)
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
        
        # If request_time not provided, use departure_time (for primary routes where they're the same)
        if request_time is None:
            request_time = departure_time

        # Phase 2: Enrich with real-time data (minimal API calls)
        route = await self.enrich_with_realtime(
            path, 
            departure_time, 
            mbta_client, 
            walking_speed_kmh=walking_speed_kmh,
            request_time=request_time,
            debug=debug
        )

        return route

    async def suggest_alternatives(
        self,
        primary_route: Route,
        start_station_id: str,
        end_station_id: str,
        mbta_client,
        request_time: Optional[datetime] = None,
        walking_speed_kmh: float = 5.0,
        max_alternatives: int = 3,
        debug: bool = False
    ) -> List[Route]:
        """
        Suggest alternative routes when the primary route has risky/unlikely transfers.

        Finds alternatives by trying later departures, aiming for routes where
        all transfers are rated as "likely".

        Args:
            primary_route: The original route to improve upon
            start_station_id: Starting station ID
            end_station_id: Destination station ID
            mbta_client: MBTA API client for real-time data
            max_alternatives: Maximum number of alternatives to return (default: 3)
            debug: Print debug information

        Returns:
            List of alternative Route objects, sorted by total journey time
        """

        if debug:
            print(f"\n{'='*60}")
            print(f"SEARCHING FOR ALTERNATIVE ROUTES")
            print(f"{'='*60}")

        # Check if primary route has risky/unlikely transfers
        has_risky_transfers = any(
            seg.transfer_rating in ["risky", "unlikely"]
            for seg in primary_route.segments
            if seg.transfer_rating is not None
        )

        # Even if primary route has no risky transfers, we can still find later departure times
        # This allows us to show alternative routes for later times
        if not has_risky_transfers:
            if debug:
                print("Primary route has no risky transfers - finding later departure alternatives")

        # Use request_time if provided, otherwise fall back to primary_route.departure_time
        # request_time represents "now" when the user first requested the route
        if request_time is None:
            request_time = primary_route.departure_time

        if debug:
            print(f"Found risky transfers in primary route")
            for seg in primary_route.segments:
                if seg.transfer_rating in ["risky", "unlikely"]:
                    print(f"  {self.get_station_name(seg.from_station)}: {seg.transfer_rating}")

        alternatives = []

        # Try departures at 5, 10, and 15 minutes later
        base_departure = primary_route.departure_time
        delay_increments = [300, 600, 900]  # 5, 10, 15 minutes in seconds

        for delay_seconds in delay_increments:
            if len(alternatives) >= max_alternatives:
                break

            adjusted_departure = base_departure + timedelta(seconds=delay_seconds)

            if debug:
                print(f"\nTrying departure at {adjusted_departure.strftime('%I:%M %p')} (+{delay_seconds/60:.0f} min)")

            try:
                # Find route with adjusted departure time, but pass original request_time for total_time calculation
                alt_route = await self.find_route(
                    start_station_id=start_station_id,
                    end_station_id=end_station_id,
                    departure_time=adjusted_departure,
                    mbta_client=mbta_client,
                    walking_speed_kmh=walking_speed_kmh,
                    request_time=request_time,  # Pass original "now" time
                    debug=False  # Don't spam debug output
                )

                if not alt_route:
                    if debug:
                        print("  No route found")
                    continue

                # total_time_seconds should already be calculated from request_time to arrival_time
                # But ensure it's correct by recalculating
                if alt_route.arrival_time and request_time:
                    calculated_total_seconds = (alt_route.arrival_time - request_time).total_seconds()
                    alt_route.total_time_seconds = calculated_total_seconds
                    alt_route.total_time_minutes = round(calculated_total_seconds / 60, 1)

                # If primary route has risky transfers, only accept alternatives with all "likely" transfers
                # Otherwise, accept any alternative route (for showing later departure times)
                if has_risky_transfers:
                    # Check if all transfers are "likely"
                    all_transfers_likely = all(
                        seg.transfer_rating == "likely" or seg.transfer_rating is None
                        for seg in alt_route.segments
                    )

                    if all_transfers_likely:
                        alternatives.append(alt_route)
                        if debug:
                            print(f"  ✓ Alternative found - all transfers LIKELY")
                            print(f"    Total time: {alt_route.total_time_seconds/60:.1f} min")
                            print(f"    Arrival: {alt_route.arrival_time.strftime('%I:%M %p')}")
                    else:
                        if debug:
                            risky_count = sum(
                                1 for seg in alt_route.segments
                                if seg.transfer_rating in ["risky", "unlikely"]
                            )
                            print(f"  ✗ Still has {risky_count} risky transfer(s)")
                else:
                    # For non-risky primary routes, accept any alternative (later departure time)
                    alternatives.append(alt_route)
                    if debug:
                        print(f"  ✓ Alternative found - later departure")
                        print(f"    Total time: {alt_route.total_time_seconds/60:.1f} min")
                        print(f"    Arrival: {alt_route.arrival_time.strftime('%I:%M %p')}")

            except Exception as e:
                if debug:
                    print(f"  Error finding alternative: {e}")
                continue

        # Filter alternatives to only include those with later arrival times than primary route
        if primary_route.arrival_time:
            alternatives = [
                alt for alt in alternatives 
                if alt.arrival_time and alt.arrival_time > primary_route.arrival_time
            ]
        
        # Sort alternatives by arrival time (earliest later arrival first)
        alternatives.sort(key=lambda r: r.arrival_time if r.arrival_time else datetime.max.replace(tzinfo=timezone.utc))

        if debug:
            print(f"\nFound {len(alternatives)} alternative route(s)")

        return alternatives[:max_alternatives]
