# Quick Start Guide

## 🚀 Starting the Application

Simply run:
```bash
./start.sh
```

This will:
1. ✅ Set the MBTA API key
2. ✅ Activate the Python virtual environment
3. ✅ Start the backend server (FastAPI with uvicorn)
4. ✅ Start the frontend development server (Vite)

## 📍 Access Points

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## 🎯 Features Available

### Transfer Rating System
- **Smart Buffers**: Station-specific transfer times (Park St: 3.5min, DTX: 2.5min, etc.)
- **Transfer Ratings**: Text indicators showing LIKELY/RISKY/UNLIKELY
- **Alternative Routes**: Automatic suggestions when transfers are risky

### Transfer Ratings
- **LIKELY** = Safe transfer (> 5 min slack)
- **RISKY** = Tight transfer (2-5 min slack)
- **UNLIKELY** = Very difficult transfer (< 2 min slack)

### User Interface
- **Apple Maps Style**: Grouped route segments showing consecutive stops on same line
- **Two Route Options**: See earliest route and safer alternative side-by-side
- **Smart Map View**: Route stations visible, non-route stations hidden
- **Clean Navigation**: Back button returns to search when viewing routes
- **MBTA T Logo**: Official branding throughout
- **Accessibility**: Full keyboard navigation and screen reader support

## 🛑 Stopping the Application

Press `Ctrl+C` in the terminal where start.sh is running.

This will cleanly stop both the backend and frontend servers.

## 🧪 Testing Routes

Try these routes to see transfer ratings:

1. **Harvard → Copley** (Red→Green transfer at Park St)
2. **Downtown Crossing → Back Bay** (Red→Commuter Rail at South Station)
3. **Park Street → Kenmore** (Multiple Green Line branch transfers)

## ⚙️ Troubleshooting

### Backend won't start
```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

### Frontend won't start
```bash
npm install
```

### Check if ports are in use
```bash
lsof -i :8000  # Backend port
lsof -i :5173  # Frontend port
```

## 📚 More Information

- Full documentation: `TRANSFER_RATING_COMPLETE.md`
- Backend tests: `backend/test_backend_summary.py`
- Frontend build: `npm run build`
