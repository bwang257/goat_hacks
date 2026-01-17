# MBTA Real-Time Transfer Helper

**Team:** Brian Wang & Aman Siddiqi
**Event:** GoatHacks 2026

An intelligent real-time transit helper for the MBTA system that helps you find the fastest way to get from station A to station B, with live train predictions and walking time calculations.

## Features

✨ **Interactive Map** - Click on any MBTA station to select start/end points
🚇 **Real-Time Train Predictions** - See the next 3 trains with live departure/arrival times
🚶 **Smart Route Planning** - Automatically calculates same-line routes or walking paths
🎨 **Color-Coded Routes** - Visual paths colored by line (Red, Orange, Blue, Green, Purple for Commuter Rail)
⚡ **Customizable Walking Speed** - Adjust walking speed (2-8 km/h) for personalized estimates
📍 **Station-by-Station Paths** - Routes follow actual MBTA line paths, not straight lines

## Quick Start

### Prerequisites

- **Python 3.11 or 3.12** (recommended for best compatibility)
- **Node.js 16+** and npm
- **MBTA API Key** - Get one free at https://api-v3.mbta.com/

### Setup Instructions

#### 1. Get Your MBTA API Key

1. Visit https://api-v3.mbta.com/
2. Click "Register for an API Key"
3. Fill out the form (it's free!)
4. Check your email for the API key
5. Save it - you'll need it in the next steps

#### 2. Clone and Navigate to Project

```bash
cd goat_hacks
```

#### 3. Download MBTA Station Data

This step downloads all MBTA station data and creates the transit graph. **You only need to do this once.**

```bash
# Export your API key
export MBTA_API_KEY='your_api_key_here'

# Download station data
python3 download_mbta_data.py
```

This will create `data/mbta_stations.json` with all station information.

#### 4. Build Transit Graph (Optional but Recommended)

This creates walking connections between nearby stations:

```bash
cd backend
python3 build_transit_graph.py
```

This will create `data/mbta_transit_graph.json`. **This step can take 5-10 minutes** as it calculates walking routes between all nearby station pairs.

#### 5. Set Up Backend

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

**Troubleshooting:** If you get build errors with `pydantic-core`:
- Use Python 3.11 or 3.12 (recommended), OR
- Install Rust: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`

#### 6. Set Up Frontend

```bash
# From project root
npm install
```

#### 7. Start the Application

**Option A: Use the startup script (easiest)**

```bash
# From project root
./start.sh
```

This will start both backend and frontend automatically with your API key.

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

#### 8. Open the Application

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

### Understanding Results

**Same-Line Routes** (e.g., Harvard → Park Street on Red Line):
- Shows colored line following actual MBTA route
- Displays next 3 trains with:
  - Departure countdown ("Arriving", "5 min", etc.)
  - Destination arrival time
  - Total trip time
- Route path shows all intermediate stations

**Different-Line Routes** (e.g., Harvard → Lechmere):
- Shows walking path with blue dashed line
- Displays walking time based on your selected speed
- Adjust walking speed with slider (2-8 km/h)

### Walking Speed Adjustment

Use the slider in the sidebar to set your walking pace:
- **2 km/h** - Slow/leisurely walk
- **5 km/h** - Average walking speed (default)
- **8 km/h** - Fast walk/light jog

Routes automatically recalculate when you change the speed.

## Project Structure

```
goat_hacks/
├── backend/
│   ├── data/
│   │   ├── mbta_stations.json       # Station data (generated)
│   │   └── mbta_transit_graph.json  # Transit graph (generated)
│   ├── main.py                       # FastAPI server
│   ├── realtime_same_line.py         # Real-time predictions
│   ├── build_transit_graph.py        # Graph builder
│   ├── route_planner.py              # Route planning algorithms
│   ├── requirements.txt              # Python dependencies
│   └── venv/                         # Virtual environment
├── src/
│   ├── App.tsx                       # Main React component
│   ├── App.css                       # Styles
│   ├── main.tsx                      # React entry point
│   └── index.css                     # Global styles
├── download_mbta_data.py             # Data downloader
├── start.sh                          # Startup script
├── package.json                      # Node dependencies
└── README.md
```

## API Endpoints

The backend provides the following endpoints:

- `GET /` - API info and status
- `GET /api/stations` - Get all MBTA stations
- `GET /api/stations/search?query=...` - Search stations by name
- `GET /api/realtime/same-line?station_id_1=...&station_id_2=...` - Get real-time route between two stations
- `POST /api/walking-time` - Calculate walking time between stations

## Technologies Used

### Frontend
- **React** + **TypeScript** - UI framework
- **Leaflet** - Interactive maps
- **React-Leaflet** - React bindings for Leaflet
- **Vite** - Build tool and dev server

### Backend
- **FastAPI** - Modern Python web framework
- **uvicorn** - ASGI server
- **httpx** - Async HTTP client for MBTA API
- **pydantic** - Data validation

### APIs
- **MBTA V3 API** - Real-time train predictions and station data
- **OSRM** - Walking route calculations

## Features in Detail

### Real-Time Predictions
- Fetches live train data from MBTA API
- Shows next 3 upcoming trains for same-line routes
- Displays departure and arrival times
- Falls back to estimated schedules when real-time data unavailable
- Smart intervals: 6 min for subway, 30 min for commuter rail

### Smart Route Selection
- Prefers main-line routes over event service routes
- Uses A* pathfinding to avoid unnecessary branches
- Follows actual station-by-station paths
- Supports all MBTA lines:
  - Heavy Rail: Red, Orange, Blue
  - Light Rail: Green (B, C, D, E branches)
  - Commuter Rail: 13 lines (Providence, Worcester, Franklin, etc.)

### Visual Map Display
- Custom T logo markers color-coded by line
- Polylines follow actual route paths
- Line colors match official MBTA colors
- Smooth station-to-station rendering

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

**No trains showing up**
- Check that your MBTA API key is set: `echo $MBTA_API_KEY`
- Some routes may not have real-time data (especially weekends)
- Look for "Estimated" status in train listings

**Walking routes not showing**
- Make sure you've run `build_transit_graph.py`
- Check that backend is running on port 8000

## Development Notes

### Adding New Features

The codebase is structured for easy extension:

- **Add new API endpoints**: Edit `backend/main.py`
- **Modify route calculation**: Edit `backend/realtime_same_line.py`
- **Update UI components**: Edit `src/App.tsx`
- **Adjust map styling**: Edit `src/App.css`

### Data Updates

To refresh MBTA station data (e.g., when new stations open):

```bash
export MBTA_API_KEY='your_key'
python3 download_mbta_data.py
cd backend
python3 build_transit_graph.py
```

## Credits

Built with ❤️ by Brian Wang and Aman Siddiqi for GoatHacks 2026

### Acknowledgments
- MBTA for their excellent V3 API
- OpenStreetMap and OSRM for walking route data
- Leaflet for the mapping library

## License

MIT License - feel free to use and modify!

---

**Need help?** Open an issue or reach out to the team!
