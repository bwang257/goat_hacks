# 2026 GoatHacks - MBTA Transfer Helper

Team: `Brian Wang`, `Aman Siddiqi`

## Overview

Real-time MBTA transfer prediction tool with confidence scoring and AI-enhanced insights. Calculate whether you'll make your connection based on live train predictions, walking speed, and contextual analysis.

## Quick Start

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Environment Variables

**Frontend** (`frontend/.env`):
```
VITE_MAPBOX_TOKEN=your_token_here
```

**Backend** (`backend/.env`):
```
MBTA_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
PORT=8000
```

## Tech Stack

- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + Mapbox GL
- **Backend**: FastAPI + Python 3.11+ + Google Gemini 1.5 Flash
- **APIs**: MBTA V3 API for real-time predictions