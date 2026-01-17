import { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMapEvents } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import './App.css';

// Fix for default marker icons in React-Leaflet
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

let DefaultIcon = L.icon({
  iconUrl: icon,
  shadowUrl: iconShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41]
});

L.Marker.prototype.options.icon = DefaultIcon;

interface Station {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  lines: string[];
  municipality: string;
  wheelchair_boarding: number;
}

interface WalkingTimeResult {
  duration_minutes: number;
  duration_seconds: number;
  distance_meters: number;
  distance_km: number;
  walking_speed_kmh: number;
  station_1: Station;
  station_2: Station;
}

// Custom marker icons for selected stations
const startIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});

const endIcon = new L.Icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});

const API_BASE = 'http://localhost:8000';

function StationSearch({ 
  label, 
  onSelect, 
  selectedStation 
}: { 
  label: string;
  onSelect: (station: Station) => void;
  selectedStation: Station | null;
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Station[]>([]);
  const [showResults, setShowResults] = useState(false);

  useEffect(() => {
    if (query.length > 1) {
      fetch(`${API_BASE}/api/stations/search?query=${query}`)
        .then(res => res.json())
        .then(data => {
          setResults(data);
          setShowResults(true);
        })
        .catch(err => console.error('Error searching stations:', err));
    } else {
      setResults([]);
      setShowResults(false);
    }
  }, [query]);

  const selectStation = (station: Station) => {
    onSelect(station);
    setQuery(station.name);
    setShowResults(false);
  };

  return (
    <div style={{ position: 'relative', marginBottom: '1rem' }}>
      <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold' }}>
        {label}
      </label>
      <input
        type="text"
        value={selectedStation ? selectedStation.name : query}
        onChange={(e) => {
          setQuery(e.target.value);
          if (selectedStation) onSelect(null as any);
        }}
        placeholder="Search for a station..."
        style={{
          width: '100%',
          padding: '0.5rem',
          fontSize: '1rem',
          border: '1px solid #ccc',
          borderRadius: '4px'
        }}
      />
      
      {showResults && results.length > 0 && (
        <ul style={{
          position: 'absolute',
          background: 'white',
          border: '1px solid #ccc',
          borderRadius: '4px',
          listStyle: 'none',
          padding: 0,
          margin: '4px 0 0 0',
          maxHeight: '200px',
          overflow: 'auto',
          zIndex: 1000,
          width: '100%',
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
        }}>
          {results.map(station => (
            <li
              key={station.id}
              onClick={() => selectStation(station)}
              style={{
                padding: '0.75rem',
                cursor: 'pointer',
                borderBottom: '1px solid #eee'
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#f0f0f0'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}
            >
              <div style={{ fontWeight: 'bold' }}>{station.name}</div>
              <div style={{ fontSize: '0.85rem', color: '#666' }}>
                {station.lines.join(', ')} • {station.municipality}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MapClickHandler({ 
  onMapClick,
  selectingStation 
}: { 
  onMapClick: (lat: number, lng: number) => void;
  selectingStation: 'start' | 'end' | null;
}) {
  useMapEvents({
    click(e) {
      if (selectingStation) {
        onMapClick(e.latlng.lat, e.latlng.lng);
      }
    },
  });
  return null;
}

function App() {
  const [stations, setStations] = useState<Station[]>([]);
  const [startStation, setStartStation] = useState<Station | null>(null);
  const [endStation, setEndStation] = useState<Station | null>(null);
  const [result, setResult] = useState<WalkingTimeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectingStation, setSelectingStation] = useState<'start' | 'end' | null>(null);

  // Load all stations on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/stations`)
      .then(res => res.json())
      .then(data => setStations(data))
      .catch(err => console.error('Error loading stations:', err));
  }, []);

  // Handle map click to find nearest station
  const handleMapClick = async (lat: number, lng: number) => {
    try {
      const response = await fetch(`${API_BASE}/api/stations/nearest?lat=${lat}&lng=${lng}&limit=1`);
      const nearestStations = await response.json();
      
      if (nearestStations.length > 0) {
        const nearest = nearestStations[0];
        if (selectingStation === 'start') {
          setStartStation(nearest);
        } else if (selectingStation === 'end') {
          setEndStation(nearest);
        }
      }
      
      setSelectingStation(null);
    } catch (err) {
      console.error('Error finding nearest station:', err);
      setSelectingStation(null);
    }
  };

  const calculateWalkingTime = async () => {
    if (!startStation || !endStation) {
      alert('Please select both start and end stations');
      return;
    }

    setLoading(true);
    setResult(null);

    try {
      const response = await fetch(`${API_BASE}/api/walking-time`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          station_id_1: startStation.id,
          station_id_2: endStation.id,
          walking_speed_kmh: 5.0
        })
      });

      if (!response.ok) {
        throw new Error('Failed to calculate walking time');
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      console.error('Error calculating walking time:', err);
      alert('Error calculating walking time. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const clearSelection = () => {
    setStartStation(null);
    setEndStation(null);
    setResult(null);
  };

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      {/* Sidebar */}
      <div style={{
        width: '400px',
        padding: '1.5rem',
        backgroundColor: '#f8f9fa',
        overflowY: 'auto',
        borderRight: '1px solid #ddd'
      }}>
        <h1 style={{ marginTop: 0 }}>MBTA Walking Time Calculator</h1>
        
        <p style={{ color: '#666', fontSize: '0.9rem' }}>
          Search for stations or click on the map to select them.
        </p>

        {/* Start Station */}
        <StationSearch
          label="From Station"
          onSelect={setStartStation}
          selectedStation={startStation}
        />
        
        <button
          onClick={() => setSelectingStation('start')}
          disabled={selectingStation === 'start'}
          style={{
            width: '100%',
            padding: '0.5rem',
            marginBottom: '1rem',
            backgroundColor: selectingStation === 'start' ? '#28a745' : '#007bff',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '0.9rem'
          }}
        >
          {selectingStation === 'start' ? 'Click on map to select...' : 'Select on Map'}
        </button>

        {/* End Station */}
        <StationSearch
          label="To Station"
          onSelect={setEndStation}
          selectedStation={endStation}
        />
        
        <button
          onClick={() => setSelectingStation('end')}
          disabled={selectingStation === 'end'}
          style={{
            width: '100%',
            padding: '0.5rem',
            marginBottom: '1rem',
            backgroundColor: selectingStation === 'end' ? '#dc3545' : '#007bff',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '0.9rem'
          }}
        >
          {selectingStation === 'end' ? 'Click on map to select...' : 'Select on Map'}
        </button>

        {/* Calculate Button */}
        <button
          onClick={calculateWalkingTime}
          disabled={!startStation || !endStation || loading}
          style={{
            width: '100%',
            padding: '0.75rem',
            marginBottom: '0.5rem',
            backgroundColor: startStation && endStation ? '#28a745' : '#6c757d',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: startStation && endStation ? 'pointer' : 'not-allowed',
            fontSize: '1rem',
            fontWeight: 'bold'
          }}
        >
          {loading ? 'Calculating...' : 'Calculate Walking Time'}
        </button>

        <button
          onClick={clearSelection}
          style={{
            width: '100%',
            padding: '0.5rem',
            marginBottom: '1.5rem',
            backgroundColor: '#6c757d',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '0.9rem'
          }}
        >
          Clear Selection
        </button>

        {/* Results */}
        {result && (
          <div style={{
            backgroundColor: 'white',
            padding: '1rem',
            borderRadius: '8px',
            border: '1px solid #ddd'
          }}>
            <h2 style={{ marginTop: 0, fontSize: '1.25rem' }}>Result</h2>
            
            <div style={{ marginBottom: '1rem' }}>
              <strong>From:</strong> {result.station_1.name}
              <div style={{ fontSize: '0.85rem', color: '#666' }}>
                {result.station_1.lines.join(', ')}
              </div>
            </div>
            
            <div style={{ marginBottom: '1rem' }}>
              <strong>To:</strong> {result.station_2.name}
              <div style={{ fontSize: '0.85rem', color: '#666' }}>
                {result.station_2.lines.join(', ')}
              </div>
            </div>
            
            <div style={{
              backgroundColor: '#e7f3ff',
              padding: '1rem',
              borderRadius: '4px',
              marginTop: '1rem'
            }}>
              <div style={{ fontSize: '2rem', fontWeight: 'bold', color: '#0066cc' }}>
                {result.duration_minutes} min
              </div>
              <div style={{ fontSize: '0.9rem', color: '#666' }}>
                {result.distance_km} km ({result.distance_meters.toFixed(0)} meters)
              </div>
              <div style={{ fontSize: '0.85rem', color: '#666', marginTop: '0.5rem' }}>
                Walking at {result.walking_speed_kmh} km/h
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Map */}
      <div style={{ flex: 1, position: 'relative' }}>
        <MapContainer
          center={[42.3601, -71.0589]} // Boston
          zoom={13}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          />
          
          <MapClickHandler
            onMapClick={handleMapClick}
            selectingStation={selectingStation}
          />

          {/* Show all stations */}
          {stations.map(station => (
            <Marker
              key={station.id}
              position={[station.latitude, station.longitude]}
            >
              <Popup>
                <strong>{station.name}</strong><br />
                {station.lines.join(', ')}<br />
                <button
                  onClick={() => setStartStation(station)}
                  style={{ marginRight: '5px', marginTop: '5px' }}
                >
                  Set as Start
                </button>
                <button
                  onClick={() => setEndStation(station)}
                  style={{ marginTop: '5px' }}
                >
                  Set as End
                </button>
              </Popup>
            </Marker>
          ))}

          {/* Highlight selected start station */}
          {startStation && (
            <Marker
              position={[startStation.latitude, startStation.longitude]}
              icon={startIcon}
            >
              <Popup>
                <strong>START: {startStation.name}</strong><br />
                {startStation.lines.join(', ')}
              </Popup>
            </Marker>
          )}

          {/* Highlight selected end station */}
          {endStation && (
            <Marker
              position={[endStation.latitude, endStation.longitude]}
              icon={endIcon}
            >
              <Popup>
                <strong>END: {endStation.name}</strong><br />
                {endStation.lines.join(', ')}
              </Popup>
            </Marker>
          )}
        </MapContainer>

        {selectingStation && (
          <div style={{
            position: 'absolute',
            top: '20px',
            left: '50%',
            transform: 'translateX(-50%)',
            backgroundColor: selectingStation === 'start' ? '#28a745' : '#dc3545',
            color: 'white',
            padding: '1rem 2rem',
            borderRadius: '8px',
            zIndex: 1000,
            boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
            fontWeight: 'bold'
          }}>
            Click on the map to select {selectingStation === 'start' ? 'START' : 'END'} station
            <button
              onClick={() => setSelectingStation(null)}
              style={{
                marginLeft: '1rem',
                padding: '0.25rem 0.5rem',
                backgroundColor: 'white',
                color: '#333',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;