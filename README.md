# MBTA Route Finder

An intelligent real-time transit routing application for the MBTA system that helps you find the fastest routes between stations with live predictions, weather-aware walking times, event alerts, and voice input.

## Features

### Core Routing
- **Multi-Modal Route Planning** - Finds optimal routes using trains, walking, and transfers
- **Real-Time Predictions** - Uses live MBTA API data for accurate departure/arrival times
- **Multiple Route Alternatives** - Shows 3 route options with different departure times
- **Transfer Ratings** - Color-coded badges (Likely/Risky/Unlikely) based on transfer timing
- **Walking Time Calculations** - OSRM-based walking routes with customizable speed

### Smart Features
- **Weather-Aware Routing** - Adjusts walking times based on current weather conditions (rain, snow, temperature)
- **Event Alerts** - Warns about Red Sox games, Bruins/Celtics games, and concerts that may cause congestion
- **Voice Input** - Speak your route: "From Harvard to Park Street" (Web Speech API)
- **Natural Language Queries** - Parse route queries like "Get me to Fenway from Downtown Crossing"

### User Experience
- **Interactive Map** - Full-screen Leaflet map with zoom-based station filtering
- **Compact Search Overlay** - Lightweight search interface overlaid on map
- **Timeline Route Display** - Detailed timeline view showing each segment with times
- **Expandable Segments** - Click to see intermediate stops on each line
- **Dark Theme** - Optional dark mode for low-light viewing
- **Settings Panel** - Adjust walking speed (1-5 mph), theme preferences

### Visual Features
- **Color-Coded Lines** - Routes colored by MBTA line (Red, Orange, Blue, Green, Purple for Commuter Rail)
- **Transfer Information** - Shows platform positions, congestion levels, and accessibility tips
- **Walking Distance Display** - Shows walking distance in miles for walk segments
- **Route Geometry** - Paths follow actual MBTA route shapes, not straight lines

## Quick Start

### Prerequisites

- **Python 3.11 or 3.12** (recommended)
- **Node.js 16+** and npm
- **MBTA API Key** - Get one free at https://api-v3.mbta.com/

### Setup Instructions

#### 1. Get Your MBTA API Key

1. Visit https://api-v3.mbta.com/
2. Click "Register for an API Key"
3. Fill out the form (it's free!)
4. Check your email for the API key

#### 2. Download MBTA Station Data

This step downloads all MBTA station data and creates the transit graph. **You only need to do this once.**

```bash
# Export your API key
export MBTA_API_KEY='your_api_key_here'

# Download station data
python3 download_mbta_data.py
```

This creates `backend/data/mbta_stations.json` with all station information.

#### 3. Build Transit Graph

This creates walking connections between nearby stations:

```bash
cd backend
python3 build_transit_graph.py
```

This creates `backend/data/mbta_transit_graph.json`. **This step can take 5-10 minutes** as it calculates walking routes between all nearby station pairs.

#### 4. Set Up Backend

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip wheel

# Install dependencies
pip install -r requirements.txt
```

#### 5. Set Up Frontend

```bash
# From project root
npm install
```

#### 6. Start the Application

**Option A: Use the startup script (recommended)**

```bash
# From project root
./start.sh
```

This starts both backend and frontend automatically with your API key.

**Option B: Manual start (two terminals)**

Terminal 1 - Backend:
```bash
cd backend
source venv/bin/activate
export MBTA_API_KEY='your_api_key_here'
python3 main.py
```

Terminal 2 - Frontend:
```bash
# From project root
npm run dev
```

#### 7. Open the Application

Visit **http://localhost:5173** (or the URL shown by Vite) in your browser.

## How to Use

### Selecting Stations

**Method 1: Click on Map**
- Click any T marker on the map
- First click = start station (green marker)
- Second click = end station (red marker)

**Method 2: Search by Name**
- Type station names in the search boxes
- Select from the dropdown

**Method 3: Voice Input** (Chrome/Edge)
- Click the microphone button in the search overlay
- Speak: "From Harvard to Park Street" or "Get me to Fenway from Downtown Crossing"
- The app will automatically parse and select stations

### Understanding Results

**Route Cards** show:
- **Rating Badge** - Likely (green), Risky (orange), or Unlikely (red) based on transfer timing
- **Total Time** - Time from now to arrival
- **Departure/Arrival Times** - When to leave and when you'll arrive
- **Transfer Count** - Number of transfers required

**Timeline Display** (click to expand):
- Time-anchored segments showing each part of the journey
- Train segments show line, number of stops, and duration
- Walk segments show distance in miles
- Transfer segments show platform info and tips

**Warning Banners** appear at the top for:
- **Event Alerts** - Major events (games, concerts) affecting stations
- **Weather Advisories** - Weather conditions affecting walking times

### Settings

Click the settings icon to adjust:
- **Walking Speed** - 1-5 mph (affects walking time calculations)
- **Theme** - Light or Dark mode

## Project Structure

```
goat_hacks/
├── backend/
│   ├── data/
│   │   ├── mbta_stations.json          # Station data (generated)
│   │   ├── mbta_transit_graph.json     # Transit graph (generated)
│   │   └── transfer_station_data.json  # Transfer station metadata
│   ├── main.py                          # FastAPI server
│   ├── dijkstra_router.py               # Main routing algorithm
│   ├── route_planner.py                 # Time-aware pathfinding
│   ├── mbta_client.py                   # MBTA API client with caching
│   ├── weather_service.py               # Weather API integration
│   ├── event_service.py                 # Event detection (games, concerts)
│   ├── requirements.txt                 # Python dependencies
│   └── venv/                            # Virtual environment
├── src/
│   ├── App.tsx                          # Main React component
│   ├── App.css                          # Styles
│   ├── main.tsx                         # React entry point
│   └── index.css                        # Global styles
├── download_mbta_data.py                # Data downloader
├── start.sh                             # Startup script
├── package.json                         # Node dependencies
└── README.md
```

## API Endpoints

### Core Routing
- `POST /api/route` - Find optimal route between two stations
- `POST /api/route/alternatives` - Get additional route alternatives
- `POST /api/parse-route-query` - Parse natural language route queries

### Data
- `GET /api/stations` - Get all MBTA stations
- `GET /api/stations/search?query=...` - Search stations by name
- `GET /api/routes` - Get all MBTA routes/lines
- `GET /api/transfer-station-data` - Get transfer station metadata

### Utilities
- `POST /api/walking-time` - Calculate walking time between stations

## Technologies Used

### Frontend
- **React** + **TypeScript** - UI framework
- **Leaflet** + **React-Leaflet** - Interactive maps
- **Vite** - Build tool and dev server
- **Web Speech API** - Voice input support

### Backend
- **FastAPI** - Modern Python web framework
- **uvicorn** - ASGI server
- **httpx** - Async HTTP client for MBTA API
- **pydantic** - Data validation

### External APIs
- **MBTA V3 API** - Real-time train predictions, schedules, and station data
- **Weather.gov API** - Weather conditions (no key required)
- **OSRM** - Walking route calculations
- **OpenStreetMap** - Map tiles

## Advanced Features

### Weather-Aware Routing
The app automatically adjusts walking times based on current weather:
- Heavy rain/snow: +20% walking time
- Light rain/snow: +10% walking time
- Extreme cold (<20°F) or heat (>90°F): +5% walking time

### Event Awareness
Detects major Boston events that may cause congestion:
- **Fenway Park** - Red Sox games → affects Kenmore station
- **TD Garden** - Bruins, Celtics games, concerts → affects North Station
- Shows warnings within 3 hours before/after event time

### Routing Algorithm
Uses a two-phase approach:
1. **Dijkstra's Algorithm** - Fast pathfinding on static graph
2. **Real-Time Enrichment** - Fills in actual departure/arrival times from MBTA API

This ensures fast response times while maintaining accuracy with live data.

## Troubleshooting

**"Port 8000 already in use"**
```bash
lsof -ti:8000 | xargs kill -9
```

**"No module named 'fastapi'"**
- Make sure virtual environment is activated: `source venv/bin/activate`
- Reinstall dependencies: `pip install -r requirements.txt`

**"File not found: data/mbta_stations.json"**
- Run the data downloader: `python3 download_mbta_data.py`

**No routes showing up**
- Check that your MBTA API key is set: `echo $MBTA_API_KEY`
- Some routes may not have real-time data (especially weekends)
- Make sure you've built the transit graph: `cd backend && python3 build_transit_graph.py`

**Voice input not working**
- Voice input requires Chrome, Edge, or Safari
- Check browser permissions for microphone access
- HTTPS may be required (use `npm run dev -- --https` for local testing)

**Weather/Event data not showing**
- Weather service uses Weather.gov (no key required, but may fail if offline)
- Event detection uses hardcoded game dates (will be expanded with API integration)

## Development

### Running Tests

```bash
cd backend
source venv/bin/activate

# Test weather adjustments
python3 test_weather_adjustment.py

# Test event detection
python3 test_event_service.py
```

### Updating Data

To refresh MBTA station data:

```bash
export MBTA_API_KEY='your_key'
python3 download_mbta_data.py
cd backend
python3 build_transit_graph.py
```

## Credits

Built for GoatHacks 2026

### Acknowledgments
- MBTA for their excellent V3 API
- OpenStreetMap and OSRM for walking route data
- Weather.gov for free weather API
- Leaflet for the mapping library

## License

MIT License - feel free to use and modify!
