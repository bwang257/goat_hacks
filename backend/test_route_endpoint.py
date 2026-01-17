"""
Quick diagnostic script to verify the /api/route endpoint is working
"""
import asyncio
import json

async def test_route_endpoint():
    """Test if the route endpoint can be called"""
    try:
        # Import after path setup
        from main import app

        # List all routes
        print("=" * 60)
        print("Registered Routes:")
        print("=" * 60)
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                methods = getattr(route, 'methods', set())
                print(f"{', '.join(methods):8} {route.path}")

        print("\n" + "=" * 60)
        print("Looking for /api/route endpoint...")
        print("=" * 60)

        route_endpoint = None
        for route in app.routes:
            if hasattr(route, 'path') and route.path == '/api/route':
                route_endpoint = route
                print(f"✓ Found: {route.path}")
                print(f"  Methods: {getattr(route, 'methods', 'N/A')}")
                print(f"  Name: {getattr(route, 'name', 'N/A')}")
                break

        if not route_endpoint:
            print("✗ /api/route endpoint NOT FOUND")
            print("\nEndpoints containing 'route':")
            for route in app.routes:
                if hasattr(route, 'path') and 'route' in route.path.lower():
                    print(f"  - {route.path}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_route_endpoint())
