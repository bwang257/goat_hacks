import httpx
import json
import asyncio
import os

async def download_shapes(api_key: str):
    """Download route shapes from MBTA API and add to existing station data"""

    print("=" * 60)
    print("Downloading MBTA Route Shapes")
    print("=" * 60)
    print()

    # Load existing station data
    data_file = "./data/mbta_stations.json"
    if not os.path.exists(data_file):
        print(f"ERROR: {data_file} not found!")
        print("Please run download_mbta_data.py first")
        return

    with open(data_file, "r") as f:
        mbta_data = json.load(f)

    print(f"Loaded existing data with {len(mbta_data['stations'])} stations")

    base_url = "https://api-v3.mbta.com"
    headers = {"x-api-key": api_key} if api_key else {}

    # Get all route IDs from existing data
    route_ids = list(mbta_data["routes"].keys())
    print(f"Found {len(route_ids)} routes to fetch shapes for")
    print()

    all_shapes = {}

    async with httpx.AsyncClient(timeout=60.0) as client:
        for idx, route_id in enumerate(route_ids):
            route_name = mbta_data["routes"][route_id]["display_name"]
            print(f"[{idx+1}/{len(route_ids)}] Fetching shapes for {route_name} ({route_id})...")

            try:
                # Fetch shapes for this route
                shapes_url = f"{base_url}/shapes"
                params = {"filter[route]": route_id}

                response = await client.get(shapes_url, params=params, headers=headers)
                response.raise_for_status()
                shapes_data = response.json()

                route_shapes = []
                for shape in shapes_data.get("data", []):
                    attrs = shape["attributes"]

                    # Extract polyline and metadata
                    shape_info = {
                        "id": shape["id"],
                        "polyline": attrs.get("polyline", ""),
                        "name": attrs.get("name"),
                        "direction_id": attrs.get("direction_id"),
                        "priority": attrs.get("priority", 0)
                    }

                    if shape_info["polyline"]:
                        route_shapes.append(shape_info)

                if route_shapes:
                    all_shapes[route_id] = route_shapes
                    print(f"  ✓ Found {len(route_shapes)} shapes")
                else:
                    print(f"  ⚠ No shapes found")

                # Rate limiting
                await asyncio.sleep(0.1)

            except httpx.HTTPStatusError as e:
                print(f"  ⚠ HTTP error {e.response.status_code}: {e}")
            except Exception as e:
                print(f"  ⚠ Error: {e}")

    # Add shapes to existing data
    mbta_data["shapes"] = all_shapes

    # Save updated data
    print()
    print("=" * 60)
    print("Saving updated data with shapes...")

    with open(data_file, "w") as f:
        json.dump(mbta_data, f, indent=2)

    print(f"✓ Data saved to: {data_file}")
    print("=" * 60)
    print()
    print(f"Summary:")
    print(f"  Total routes: {len(route_ids)}")
    print(f"  Routes with shapes: {len(all_shapes)}")
    print(f"  Total shapes: {sum(len(shapes) for shapes in all_shapes.values())}")
    print()
    print("You can now restart your backend server to use the shape data!")

async def main():
    # Get API key
    api_key = os.environ.get("MBTA_API_KEY")

    if not api_key:
        print("MBTA API key required!")
        print()
        print("Get a free key at: https://api-v3.mbta.com/")
        print()
        api_key = input("Enter your MBTA API key: ").strip()

        if not api_key:
            print("Error: API key is required")
            return

    await download_shapes(api_key)

if __name__ == "__main__":
    asyncio.run(main())
