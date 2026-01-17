# 2026 GoatHacks - MBTA Transfer Helper

Team: `Brian Wang`, `Aman Siddiqi`

## MBTA Map Frontend + Backend

A React + Leaflet frontend with FastAPI backend for displaying MBTA stops on an interactive map with walking time calculation.

### Setup Instructions

#### Backend Setup

**Note:** Python 3.11 or 3.12 is recommended for best compatibility. Python 3.13 may require Rust to build some dependencies.

1. **Navigate to backend directory:**
   ```bash
   cd backend
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Upgrade pip and install dependencies:**
   ```bash
   pip install --upgrade pip wheel
   pip install -r requirements.txt
   ```

   If you encounter build errors related to `pydantic-core` requiring Rust, either:
   - Use Python 3.11 or 3.12 instead (recommended)
   - Or install Rust: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`

4. **Run the FastAPI server:**
   ```bash
   python main.py
   ```
   
   Or using uvicorn directly:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

   The backend will be available at `http://localhost:8000`

#### Frontend Setup

1. **Install dependencies (from project root):**
   ```bash
   npm install
   ```

2. **Create `.env` file:**
   Create a `.env` file in the project root with your MBTA API key:
   ```
   VITE_MBTA_API_KEY=your_mbta_api_key_here
   ```

3. **Run development server:**
   ```bash
   npm run dev
   ```

   Open the URL printed by Vite (usually `http://localhost:5173` or `http://localhost:5174`) in your browser.

**Note:** Both the backend (port 8000) and frontend (port 5173/5174) must be running simultaneously.

### Features

- Interactive Leaflet map centered on Boston
- Loads MBTA stops from MBTA v3 API (requires API key)
- Only fetches/renders stops within current viewport (debounced, cached)
- Click two points on map OR click two stop markers to calculate walking time
- FastAPI backend calculates walking time using OSRM public routing API
- Marker clustering for efficient rendering of many stops

### Project Structure

```
goat_hacks/
├── backend/
│   ├── main.py          # FastAPI server with walking time endpoint
│   └── requirements.txt # Python dependencies
├── src/
│   ├── App.tsx          # Main map component
│   ├── App.css          # Styles for info panel
│   ├── main.tsx         # React entry point
│   ├── index.css        # Global styles
│   └── vite-env.d.ts    # TypeScript env types
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
└── tsconfig.node.json
```
