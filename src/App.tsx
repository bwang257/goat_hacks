import { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMapEvents, useMap } from 'react-leaflet';
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

interface NextTrainInfo {
  departure_time: string;
  arrival_time: string;
  minutes_until_departure: number;
  total_trip_minutes: number;
  status: string;
  vehicle_id?: string;
  countdown_text: string;
}

interface StationCoordinate {
  station_id: string;
  station_name: string;
  latitude: number;
  longitude: number;
}

interface SameLineRouteResult {
  is_same_line: boolean;
  line_name?: string;
  line_color?: string;
  from_station_name?: string;
  to_station_name?: string;
  direction_name?: string;
  scheduled_time_minutes?: number;
  distance_meters?: number;
  next_trains?: NextTrainInfo[];
  message?: string;
  path_coordinates?: StationCoordinate[];
  geometry_coordinates?: [number, number][];
}

interface RouteSegment {
  from_station_id: string;
  from_station_name: string;
  to_station_id: string;
  to_station_name: string;
  type: string;
  line?: string;
  route_id?: string;
  time_seconds: number;
  time_minutes: number;
  distance_meters: number;
  departure_time?: string;
  arrival_time?: string;
  status?: string;
  geometry_coordinates?: [number, number][];
}

interface RouteResult {
  segments: RouteSegment[];
  total_time_seconds: number;
  total_time_minutes: number;
  total_distance_meters: number;
  total_distance_km: number;
  num_transfers: number;
  departure_time?: string;
  arrival_time?: string;
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

// Create custom T logo markers for each line
function createTMarker(lines: string[]): L.DivIcon {
  // Determine the color based on the primary line
  const lineColors: { [key: string]: string } = {
    'Red': '#DA291C',
    'Orange': '#ED8B00',
    'Blue': '#003DA5',
    'Green': '#00843D',
    'Green-B': '#00843D',
    'Green-C': '#00843D',
    'Green-D': '#00843D',
    'Green-E': '#00843D',
    'Silver': '#7C878E',
    'Mattapan': '#DA291C'
  };

  // Get the primary line color
  let primaryColor = '#000000';
  for (const line of lines) {
    const cleanLine = line.replace(' Line', '').trim();
    if (lineColors[cleanLine]) {
      primaryColor = lineColors[cleanLine];
      break;
    }
  }

  // Create multi-line display if station has multiple lines
  const lineIndicators = lines.map(line => {
    const cleanLine = line.replace(' Line', '').trim();
    const color = lineColors[cleanLine] || '#000000';
    return `<div style="background-color: ${color}; width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin: 0 1px;"></div>`;
  }).join('');

  return L.divIcon({
    className: 't-marker',
    html: `
      <div style="
        background-color: white;
        border: 2px solid ${primaryColor};
        border-radius: 50%;
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        font-size: 14px;
        color: ${primaryColor};
        box-shadow: 0 2px 5px rgba(0,0,0,0.3);
        cursor: pointer;
      ">
        T
      </div>
      <div style="
        position: absolute;
        top: 26px;
        left: 50%;
        transform: translateX(-50%);
        background-color: white;
        border: 1px solid #ccc;
        border-radius: 3px;
        padding: 2px 4px;
        white-space: nowrap;
        display: flex;
        gap: 2px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.2);
      ">
        ${lineIndicators}
      </div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -12]
  });
}

const API_BASE = 'http://localhost:8000';

// Helper functions for time formatting
function formatTime(isoString: string): string {
  const date = new Date(isoString);
  const hours = date.getHours();
  const minutes = date.getMinutes();
  const ampm = hours >= 12 ? 'PM' : 'AM';
  const displayHours = hours % 12 || 12;
  const displayMinutes = minutes.toString().padStart(2, '0');
  return `${displayHours}:${displayMinutes} ${ampm}`;
}

function formatDuration(minutes: number): string {
  if (minutes < 1) {
    return 'Now';
  } else if (minutes < 2) {
    return '1 min';
  } else {
    return `${Math.round(minutes)} min`;
  }
}



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

// Component to fit map bounds to show both stations
function MapBoundsUpdater({
  startStation,
  endStation
}: {
  startStation: Station | null;
  endStation: Station | null;
}) {
  const map = useMap();

  useEffect(() => {
    if (startStation && endStation) {
      const bounds = L.latLngBounds(
        [startStation.latitude, startStation.longitude],
        [endStation.latitude, endStation.longitude]
      );
      map.fitBounds(bounds, { padding: [50, 50] });
    }
  }, [startStation, endStation, map]);

  return null;
}

function App() {
  const [stations, setStations] = useState<Station[]>([]);
  const [startStation, setStartStation] = useState<Station | null>(null);
  const [endStation, setEndStation] = useState<Station | null>(null);
  const [result, setResult] = useState<WalkingTimeResult | null>(null);
  const [sameLineRoute, setSameLineRoute] = useState<SameLineRouteResult | null>(null);
  const [routeResult, setRouteResult] = useState<RouteResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectingStation, setSelectingStation] = useState<'start' | 'end' | null>(null);
  const [routeGeometry, setRouteGeometry] = useState<[number, number][]>([]);
  const [routeSegments, setRouteSegments] = useState<{ coordinates: [number, number][], color: string, opacity: number, dashArray: string | null }[]>([]);
  const [routeShapes, setRouteShapes] = useState<{ [key: string]: { id: string; coordinates: [number, number][]; }[] }>({});
  const [walkingSpeed, setWalkingSpeed] = useState<number>(5.0); // km/h

  // Helper function to get line color
  const getLineColor = (lineName: string) => {
    if (!lineName) return '#999999';
    if (lineName.includes('Red')) return '#DA291C';
    if (lineName.includes('Orange')) return '#ED8B00';
    if (lineName.includes('Blue')) return '#003DA5';
    // Ensure "Greenbush" does not trigger "Green" line color
    if (lineName.includes('Green') && !lineName.includes('Greenbush')) return '#00843D';
    if (lineName.includes('Mattapan')) return '#DA291C';
    // Commuter Rail purple
    return '#80276C';
  };

  // Auto-calculate when both stations are selected or walking speed changes
  useEffect(() => {
    if (startStation && endStation && !loading) {
      calculateRoute();
    }
  }, [startStation, endStation, walkingSpeed]);

  // Load all stations on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/stations`)
      .then(res => res.json())
      .then(data => setStations(data))
      .catch(err => console.error('Error loading stations:', err));
  }, []);

  // Load route shapes on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/shapes`)
      .then(res => res.json())
      .then(data => setRouteShapes(data))
      .catch(err => console.error('Error loading shapes:', err));
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

  const calculateRoute = async () => {
    if (!startStation || !endStation) {
      return;
    }

    setLoading(true);
    setResult(null);
    setSameLineRoute(null);
    setRouteResult(null);
    setRouteGeometry([]);

    try {
      // First, try to get a comprehensive route using the new API
      try {
        const routeResponse = await fetch(`${API_BASE}/api/route`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            station_id_1: startStation.id,
            station_id_2: endStation.id,
            prefer_fewer_transfers: true,
            use_realtime: true
          })
        });

        if (routeResponse.ok) {
          const routeData = await routeResponse.json();

          // Check if this is a same-line route (all train segments are on the same line)
          const trainSegments = routeData.segments.filter((s: any) => s.type === 'train');
          const distinctLines = new Set(trainSegments.map((s: any) => s.line));
          const hasTransfers = routeData.segments.some((s: any) => s.type === 'transfer');

          if (trainSegments.length > 0 && distinctLines.size === 1 && !hasTransfers) {
            // Try to get same-line route details for better display
            try {
              const sameLineResponse = await fetch(
                `${API_BASE}/api/realtime/same-line?station_id_1=${startStation.id}&station_id_2=${endStation.id}&num_trains=3`
              );

              if (sameLineResponse.ok) {
                const sameLineData = await sameLineResponse.json();
                if (sameLineData.is_same_line) {
                  setSameLineRoute(sameLineData);
                  setLoading(false);
                  return;
                }
              }
            } catch (err) {
              // Continue with route result
            }
          }

          // Use the comprehensive route result
          setRouteResult(routeData);
          setRouteGeometry([]);

          // Build route segments for display
          const displaySegments: {
            coordinates: [number, number][],
            color: string,
            opacity: number,
            dashArray: string | null
          }[] = [];

          for (const seg of routeData.segments) {
            const fromStation = stations.find(s => s.id === seg.from_station_id);
            const toStation = stations.find(s => s.id === seg.to_station_id);

            if (fromStation && toStation) {
              const coords: [number, number][] = seg.geometry_coordinates && seg.geometry_coordinates.length > 0
                ? seg.geometry_coordinates as [number, number][]
                : [
                  [fromStation.latitude, fromStation.longitude],
                  [toStation.latitude, toStation.longitude]
                ];

              if (seg.type === 'train' && seg.line) {
                // Train segment - uses line color
                displaySegments.push({
                  coordinates: coords,
                  color: getLineColor(seg.line),
                  opacity: 0.8,
                  dashArray: null
                });
              } else {
                // Walk or transfer - dashed blue
                displaySegments.push({
                  coordinates: coords,
                  color: '#0066cc',
                  opacity: 0.6,
                  dashArray: '10, 10'
                });
              }
            }
          }

          setRouteSegments(displaySegments);

          setLoading(false);
          return;
        }
      } catch (err) {
        console.log('Route API not available, trying same-line check');
      }

      // Fallback: Check if stations are on the same line
      try {
        const sameLineResponse = await fetch(
          `${API_BASE}/api/realtime/same-line?station_id_1=${startStation.id}&station_id_2=${endStation.id}&num_trains=3`
        );

        if (sameLineResponse.ok) {
          const sameLineData = await sameLineResponse.json();

          if (sameLineData.is_same_line) {
            setSameLineRoute(sameLineData);
            setLoading(false);
            return;
          }
        }
      } catch (err) {
        console.log('Same-line check not available');
      }

      // Final fallback: calculate walking time
      const response = await fetch(`${API_BASE}/api/walking-time`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          station_id_1: startStation.id,
          station_id_2: endStation.id,
          walking_speed_kmh: walkingSpeed
        })
      });

      if (!response.ok) {
        throw new Error('Failed to calculate route');
      }

      const data = await response.json();
      setResult(data);

      // Fetch the actual route geometry from OSRM
      const routeResponse = await fetch(
        `https://routing.openstreetmap.de/routed-foot/route/v1/foot/${startStation.longitude},${startStation.latitude};${endStation.longitude},${endStation.latitude}?overview=full&geometries=geojson`
      );

      if (routeResponse.ok) {
        const routeData = await routeResponse.json();
        if (routeData.routes && routeData.routes[0]) {
          // Convert GeoJSON coordinates [lng, lat] to Leaflet format [lat, lng]
          const coords = routeData.routes[0].geometry.coordinates.map(
            (coord: [number, number]) => [coord[1], coord[0]] as [number, number]
          );
          setRouteGeometry(coords);
        }
      }
    } catch (err) {
      console.error('Error calculating route:', err);
    } finally {
      setLoading(false);
    }
  };



  const clearSelection = () => {
    setStartStation(null);
    setEndStation(null);
    setResult(null);
    setSameLineRoute(null);
    setRouteResult(null);
    setRouteGeometry([]);
    setRouteSegments([]);
  };

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      {/* Sidebar */}
      <div style={{
        width: '380px',
        padding: '1.5rem',
        backgroundColor: '#f8f9fa',
        overflowY: 'auto',
        borderRight: '1px solid #ddd'
      }}>
        <h1 style={{ marginTop: 0, fontSize: '1.5rem' }}>MBTA Route Finder</h1>

        <p style={{ color: '#999', fontSize: '0.85rem', marginBottom: '1.5rem' }}>
          Select two stations to find the best route between them
        </p>

        {/* Start Station */}
        <StationSearch
          label="From Station"
          onSelect={setStartStation}
          selectedStation={startStation}
        />

        {/* End Station */}
        <StationSearch
          label="To Station"
          onSelect={setEndStation}
          selectedStation={endStation}
        />

        {/* Walking Speed Control */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold' }}>
            Walking Speed: {walkingSpeed} km/h
          </label>
          <input
            type="range"
            min="2"
            max="8"
            step="0.5"
            value={walkingSpeed}
            onChange={(e) => setWalkingSpeed(parseFloat(e.target.value))}
            style={{ width: '100%' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#666' }}>
            <span>Slow (2 km/h)</span>
            <span>Fast (8 km/h)</span>
          </div>
        </div>

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
        {sameLineRoute && sameLineRoute.is_same_line && (
          <div style={{
            backgroundColor: 'white',
            padding: '1rem',
            borderRadius: '8px',
            border: `3px solid #${sameLineRoute.line_color}`
          }}>
            <h2 style={{ marginTop: 0, fontSize: '1.25rem', color: `#${sameLineRoute.line_color}` }}>
              {sameLineRoute.line_name}
            </h2>

            <div style={{ marginBottom: '0.75rem' }}>
              <strong>{sameLineRoute.from_station_name}</strong> → <strong>{sameLineRoute.to_station_name}</strong>
            </div>

            <div style={{
              backgroundColor: '#f0f8ff',
              padding: '0.75rem',
              borderRadius: '4px',
              marginBottom: '1rem'
            }}>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: `#${sameLineRoute.line_color}` }}>
                {formatDuration(sameLineRoute.scheduled_time_minutes)}
              </div>
            </div>

            <h3 style={{ marginTop: '1rem', marginBottom: '0.75rem', fontSize: '0.95rem' }}>Next Trains</h3>
            <div style={{ maxHeight: '280px', overflowY: 'auto' }}>
              {sameLineRoute.next_trains && sameLineRoute.next_trains.length > 0 ? (
                sameLineRoute.next_trains.map((train, idx) => (
                  <div
                    key={idx}
                    style={{
                      backgroundColor: '#f8f9fa',
                      padding: '0.5rem',
                      marginBottom: '0.4rem',
                      borderRadius: '3px',
                      borderLeft: `3px solid #${sameLineRoute.line_color}`
                    }}
                  >
                    <div style={{ fontWeight: 'bold', color: `#${sameLineRoute.line_color}`, fontSize: '0.95rem' }}>
                      Departs in {train.countdown_text}
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#666', marginTop: '0.25rem' }}>
                      📍 Arrive at destination: {formatTime(train.arrival_time)}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: '#888', marginTop: '0.15rem' }}>
                      Total trip time: {formatDuration(train.total_trip_minutes)}
                    </div>
                  </div>
                ))
              ) : (
                <div style={{ color: '#999', fontSize: '0.85rem' }}>No upcoming trains</div>
              )}
            </div>
          </div>
        )}

        {/* Comprehensive Route Result */}
        {routeResult && !sameLineRoute?.is_same_line && (
          <div style={{
            backgroundColor: 'white',
            padding: '1rem',
            borderRadius: '8px',
            border: '1px solid #ddd',
            marginBottom: '1rem'
          }}>
            <h2 style={{ marginTop: 0, fontSize: '1.25rem', color: '#0066cc' }}>
              Trip Plan
            </h2>

            <div style={{ marginBottom: '0.75rem' }}>
              <strong>{startStation?.name}</strong> → <strong>{endStation?.name}</strong>
            </div>

            <div style={{
              backgroundColor: '#e7f3ff',
              padding: '0.75rem',
              borderRadius: '4px',
              marginBottom: '1rem'
            }}>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#0066cc' }}>
                {formatDuration(routeResult.total_time_minutes)}
              </div>
              <div style={{ fontSize: '0.85rem', color: '#666', marginTop: '0.25rem' }}>
                {routeResult.num_transfers} {routeResult.num_transfers === 1 ? 'transfer' : 'transfers'}
                {routeResult.departure_time && routeResult.arrival_time && (
                  <span> • {formatTime(routeResult.departure_time)} - {formatTime(routeResult.arrival_time)}</span>
                )}
              </div>
            </div>

            <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
              {routeResult.segments.map((seg, idx) => {
                const lineColors: { [key: string]: string } = {
                  'Red': '#DA291C',
                  'Orange': '#ED8B00',
                  'Blue': '#003DA5',
                  'Green': '#00843D',
                  'B': '#00843D',
                  'C': '#00843D',
                  'D': '#00843D',
                  'E': '#00843D',
                };
                const cleanLine = seg.line?.replace(' Line', '').trim() || '';
                const lineColor = lineColors[cleanLine] || '#666';

                return (
                  <div key={idx} style={{
                    marginBottom: '0.75rem',
                    padding: '0.75rem',
                    backgroundColor: '#f8f9fa',
                    borderRadius: '4px',
                    borderLeft: `4px solid ${seg.type === 'train' ? lineColor : seg.type === 'transfer' ? '#FFA500' : '#0066cc'}`
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <div style={{ fontWeight: 'bold', fontSize: '0.95rem' }}>
                        {seg.type === 'train' && seg.line && (
                          <span style={{
                            backgroundColor: lineColor,
                            color: 'white',
                            padding: '2px 6px',
                            borderRadius: '3px',
                            fontSize: '11px',
                            fontWeight: 'bold',
                            marginRight: '6px'
                          }}>
                            {cleanLine}
                          </span>
                        )}
                        {seg.type === 'transfer' && '🔄 Transfer'}
                        {seg.type === 'walk' && '🚶 Walk'}
                      </div>
                      <div style={{ fontSize: '0.85rem', color: '#666' }}>
                        {formatDuration(seg.time_minutes)}
                      </div>
                    </div>

                    <div style={{ fontSize: '0.9rem', marginBottom: '0.25rem' }}>
                      <strong>{seg.from_station_name}</strong>
                      {seg.departure_time && (
                        <span style={{ color: '#666', marginLeft: '8px', fontSize: '0.85rem' }}>
                          {formatTime(seg.departure_time)}
                        </span>
                      )}
                    </div>

                    <div style={{ fontSize: '0.9rem' }}>
                      <strong>{seg.to_station_name}</strong>
                      {seg.arrival_time && (
                        <span style={{ color: '#666', marginLeft: '8px', fontSize: '0.85rem' }}>
                          {formatTime(seg.arrival_time)}
                        </span>
                      )}
                    </div>

                    {seg.status && seg.status !== 'Scheduled' && (
                      <div style={{
                        fontSize: '0.8rem',
                        color: seg.status === 'Delayed' ? '#d32f2f' : '#666',
                        marginTop: '0.25rem',
                        fontStyle: 'italic'
                      }}>
                        {seg.status}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {result && !sameLineRoute?.is_same_line && !routeResult && (
          <div style={{
            backgroundColor: 'white',
            padding: '1rem',
            borderRadius: '8px',
            border: '1px solid #ddd'
          }}>
            <h2 style={{ marginTop: 0, fontSize: '1.25rem', color: '#0066cc' }}>Walking Route</h2>

            <div style={{ marginBottom: '0.75rem' }}>
              <strong>{result.station_1.name}</strong> → <strong>{result.station_2.name}</strong>
            </div>

            <div style={{
              backgroundColor: '#e7f3ff',
              padding: '0.75rem',
              borderRadius: '4px'
            }}>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#0066cc' }}>
                {formatDuration(result.duration_minutes)}
              </div>
              <div style={{ fontSize: '0.85rem', color: '#666', marginTop: '0.25rem' }}>
                {result.distance_km} km
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
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          />

          <MapClickHandler
            onMapClick={handleMapClick}
            selectingStation={selectingStation}
          />

          <MapBoundsUpdater
            startStation={startStation}
            endStation={endStation}
          />

          {/* Render All Route Shapes (Background) */}
          {!result && !routeResult && !sameLineRoute && Object.entries(routeShapes).map(([routeId, shapes]) => {
            const color = getLineColor(routeId);
            return shapes.map(shape => (
              <Polyline
                key={shape.id}
                positions={shape.coordinates}
                pathOptions={{
                  color: color,
                  weight: 3,
                  opacity: 0.5,
                  lineCap: 'round',
                  lineJoin: 'round'
                }}
              />
            ));
          })}

          {/* Show all stations with T logo markers */}
          {stations.map(station => (
            <Marker
              key={station.id}
              position={[station.latitude, station.longitude]}
              icon={createTMarker(station.lines)}
              eventHandlers={{
                click: () => {
                  // Allow clicking on station markers to select them
                  if (!startStation) {
                    setStartStation(station);
                  } else if (!endStation) {
                    setEndStation(station);
                  }
                }
              }}
            >
              <Popup>
                <div>
                  <strong>{station.name}</strong><br />
                  <div style={{ marginTop: '4px' }}>
                    {station.lines.map((line, idx) => {
                      const lineColors: { [key: string]: string } = {
                        'Red': '#DA291C',
                        'Orange': '#ED8B00',
                        'Blue': '#003DA5',
                        'Green': '#00843D',
                        'Green-B': '#00843D',
                        'Green-C': '#00843D',
                        'Green-D': '#00843D',
                        'Green-E': '#00843D',
                        'Silver': '#7C878E',
                        'Mattapan': '#DA291C'
                      };
                      const cleanLine = line.replace(' Line', '').trim();
                      const color = lineColors[cleanLine] || '#000000';
                      return (
                        <span
                          key={idx}
                          style={{
                            display: 'inline-block',
                            backgroundColor: color,
                            color: 'white',
                            padding: '2px 6px',
                            borderRadius: '3px',
                            fontSize: '11px',
                            fontWeight: 'bold',
                            marginRight: '4px',
                            marginBottom: '2px'
                          }}
                        >
                          {cleanLine}
                        </span>
                      );
                    })}
                  </div>
                  <div style={{ marginTop: '6px', fontSize: '12px', color: '#666' }}>
                    {station.municipality}
                  </div>
                </div>
              </Popup>
            </Marker>
          ))}

          {/* Same-line route line */}
          {sameLineRoute && sameLineRoute.is_same_line && (
            <Polyline
              positions={
                sameLineRoute.geometry_coordinates && sameLineRoute.geometry_coordinates.length > 0
                  ? sameLineRoute.geometry_coordinates
                  : sameLineRoute.path_coordinates && sameLineRoute.path_coordinates.length > 0
                    ? sameLineRoute.path_coordinates.map(coord => [coord.latitude, coord.longitude])
                    : [[startStation?.latitude || 0, startStation?.longitude || 0], [endStation?.latitude || 0, endStation?.longitude || 0]]
              }
              pathOptions={{
                color: `#${sameLineRoute.line_color}`,
                weight: 6,
                opacity: 0.8,
                lineCap: 'round',
                lineJoin: 'round'
              }}
            />
          )}

          {/* Walking route line */}
          {routeGeometry.length > 0 && !sameLineRoute?.is_same_line && (
            <Polyline
              positions={routeGeometry}
              pathOptions={{
                color: '#0066cc',
                weight: 4,
                opacity: 0.7,
                dashArray: '10, 10',
                lineCap: 'round',
                lineJoin: 'round'
              }}
            />
          )}

          {/* Calculated Route Segments (Multi-colored) */}
          {routeSegments.map((seg, idx) => (
            <Polyline
              key={idx}
              positions={seg.coordinates}
              pathOptions={{
                color: seg.color,
                weight: 5,
                opacity: seg.opacity,
                dashArray: seg.dashArray || undefined,
                lineCap: 'round',
                lineJoin: 'round'
              }}
            />
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
      </div>
    </div>
  );
}

export default App;