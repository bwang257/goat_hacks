import { useState, useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMapEvents, useMap, ZoomControl } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import './App.css';

// Web Speech API types
interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionResultList {
  length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  isFinal: boolean;
  length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognition;
    webkitSpeechRecognition: new () => SpeechRecognition;
  }
}

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
  geometry_coordinates?: [number, number][];
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
  distance_km?: number;  // Added for walking distance display
  departure_time?: string;
  arrival_time?: string;
  status?: string;
  geometry_coordinates?: [number, number][];
  transfer_rating?: 'likely' | 'risky' | 'unlikely';
  slack_time_seconds?: number;
  buffer_seconds?: number;
}

interface EventWarning {
  has_event: boolean;
  event_name?: string;
  event_type?: string;  // "sports", "concert", "other"
  affected_stations: string[];
  congestion_level?: string;  // "moderate", "high", "very_high"
  message?: string;
}

interface WeatherWarning {
  has_warning: boolean;
  condition?: string;  // "rain", "snow", "extreme_cold", "extreme_heat"
  temperature_f?: number;
  description?: string;
  walking_time_adjustment: number;  // Multiplier (1.1 = +10%)
  message?: string;
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
  has_risky_transfers?: boolean;
  alternatives?: RouteResult[];
  event_warning?: EventWarning;
  weather_warning?: WeatherWarning;
}

// Grouped segment for Apple Maps-style display
interface GroupedSegment {
  type: 'train' | 'walk' | 'transfer';
  line?: string;
  route_id?: string;
  segments: RouteSegment[];
  fromStation: string;
  toStation: string;
  departureTime?: string;
  arrivalTime?: string;
  totalStops: number;
  transfer_rating?: string;
  intermediateStops?: string[];
  transfer_from_line?: string;  // Line transferring from
  transfer_to_line?: string;    // Line transferring to
  transfer_station_id?: string;  // Station ID for the transfer
}

// Helper function to normalize line names for grouping
// Green Line branches (B, C, D, E) should be treated as the same line
function normalizeLineName(line: string | undefined): string {
  if (!line) return '';

  // Green Line branches should all be treated as "Green"
  if (line === 'B' || line === 'C' || line === 'D' || line === 'E' ||
      line === 'Green-B' || line === 'Green-C' || line === 'Green-D' || line === 'Green-E') {
    return 'Green';
  }

  // Remove " Line" suffix for consistency
  return line.replace(' Line', '').trim();
}

// Helper function to check if two line names are compatible for grouping
function areLinesCompatible(line1: string | undefined, line2: string | undefined): boolean {
  const normalized1 = normalizeLineName(line1);
  const normalized2 = normalizeLineName(line2);
  return normalized1 === normalized2;
}

// Helper function to group consecutive segments on the same line
function groupSegmentsByLine(segments: RouteSegment[]): GroupedSegment[] {
  const grouped: GroupedSegment[] = [];

  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];

    if (seg.type === 'train') {
      // Check if we can merge with the previous group
      const lastGroup = grouped[grouped.length - 1];

      // Merge if same line (treating Green Line branches as one line)
      if (lastGroup &&
          lastGroup.type === 'train' &&
          areLinesCompatible(lastGroup.line, seg.line)) {
        // Merge with previous group
        lastGroup.segments.push(seg);
        lastGroup.toStation = seg.to_station_name;
        lastGroup.arrivalTime = seg.arrival_time;
        lastGroup.totalStops += 1;
        if (!lastGroup.intermediateStops) {
          lastGroup.intermediateStops = [];
        }
        lastGroup.intermediateStops.push(seg.from_station_name);

        // Update route_id if we're on Green Line to show branch info
        if (normalizeLineName(seg.line) === 'Green') {
          lastGroup.route_id = lastGroup.route_id + '→' + seg.route_id;
        }
      } else {
        // Create new group with normalized line name
        grouped.push({
          type: 'train',
          line: normalizeLineName(seg.line) || seg.line,
          route_id: seg.route_id,
          segments: [seg],
          fromStation: seg.from_station_name,
          toStation: seg.to_station_name,
          departureTime: seg.departure_time,
          arrivalTime: seg.arrival_time,
          totalStops: 1,
          intermediateStops: []
        });
      }
    } else if (seg.type === 'transfer') {
      // Don't show as transfer if it's just a Green Line branch change at the same station
      const lastGroup = grouped[grouped.length - 1];
      if (lastGroup && lastGroup.type === 'train' &&
          normalizeLineName(lastGroup.line) === 'Green' &&
          i + 1 < segments.length && segments[i + 1].type === 'train' &&
          normalizeLineName(segments[i + 1].line) === 'Green' &&
          seg.from_station_name === seg.to_station_name) {
        // Skip this transfer - it's just a Green Line branch change
        continue;
      }

      // Get lines from adjacent train segments
      const prevTrainSeg = i > 0 ? segments[i - 1] : null;
      const nextTrainSeg = i < segments.length - 1 ? segments[i + 1] : null;
      
      const fromLine = prevTrainSeg?.line || null;
      const toLine = nextTrainSeg?.line || null;

      // Transfers get their own group
      grouped.push({
        type: 'transfer',
        segments: [seg],
        fromStation: seg.from_station_name,
        toStation: seg.to_station_name,
        totalStops: 0,
        transfer_rating: seg.transfer_rating,
        transfer_from_line: fromLine || undefined,
        transfer_to_line: toLine || undefined,
        transfer_station_id: seg.from_station_id // Same as to_station_id for transfers
      });
    } else if (seg.type === 'walk') {
      // Walks get their own group
      grouped.push({
        type: 'walk',
        segments: [seg],
        fromStation: seg.from_station_name,
        toStation: seg.to_station_name,
        totalStops: 0
      });
    }
  }

  // Add final station to intermediate stops for each train group
  grouped.forEach(group => {
    if (group.type === 'train' && group.intermediateStops) {
      group.intermediateStops.push(group.toStation);
    }
  });

  return grouped;
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
  const getLineColor = (line: string) => {
    const cleanLine = line.replace(' Line', '').trim();
  const lineColors: { [key: string]: string } = {
    'Red': '#DA291C',
    'Orange': '#ED8B00',
    'Blue': '#003DA5',
    'Green': '#00843D',
    'Green-B': '#00843D',
    'Green-C': '#00843D',
    'Green-D': '#00843D',
    'Green-E': '#00843D',
      'B': '#00843D',
      'C': '#00843D',
      'D': '#00843D',
      'E': '#00843D',
    'Silver': '#7C878E',
    'Mattapan': '#DA291C'
    };
    // Color all commuter rail lines purple
    const commuterRailLines = [
      'Framingham/Worcester', 'Providence/Stoughton', 'Lowell', 'Haverhill',
      'Fitchburg', 'Newburyport/Rockport', 'Kingston', 'Greenbush',
      'Needham', 'Fairmount', 'Franklin/Foxboro', 'Fall River/New Bedford',
      'Foxboro Event Service'
    ];
    if (cleanLine.startsWith('CR-') || commuterRailLines.some(cr => cleanLine.startsWith(cr))) {
      return '#80276C'; // Purple for commuter rail
    }
    return lineColors[cleanLine] || '#000000';
  };

  // Get the primary line color
  let primaryColor = '#000000';
  for (const line of lines) {
    primaryColor = getLineColor(line);
      break;
  }

  // Create multi-line display with unique colors only
  const uniqueColors = new Set<string>();
  const lineIndicators = lines.map(line => {
    const color = getLineColor(line);
    if (uniqueColors.has(color)) {
      return null; // Skip duplicate colors
    }
    uniqueColors.add(color);
    return `<div style="background-color: ${color}; width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin: 0 1px;"></div>`;
  }).filter(indicator => indicator !== null).join('');

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
    return '< 1 min';
  } else if (minutes < 2) {
    return '1 min';
  } else if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    const mins = Math.round(minutes % 60);
    if (mins === 0) {
      return `${hours}h`;
    }
    return `${hours}h ${mins}m`;
  } else {
    return `${Math.round(minutes)} min`;
  }
}

// Voice Input Button Component
function VoiceInputButton({
  onStationsFound,
  disabled
}: {
  onStationsFound: (fromStation: Station, toStation: Station) => void;
  disabled?: boolean;
}) {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  // Check if speech recognition is supported
  const isSpeechSupported = typeof window !== 'undefined' &&
    (window.SpeechRecognition || window.webkitSpeechRecognition);

  const startListening = async () => {
    if (!isSpeechSupported) {
      setError('Voice input not supported in this browser');
      setTimeout(() => setError(null), 3000);
      return;
    }

    setError(null);
    setTranscript('');

    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognitionAPI();

    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interimTranscript = '';
      let finalTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          finalTranscript += result[0].transcript;
        } else {
          interimTranscript += result[0].transcript;
        }
      }

      setTranscript(finalTranscript || interimTranscript);

      // If we have a final transcript, parse it and stop listening
      if (finalTranscript) {
        // Explicitly stop recognition to ensure mic turns off
        if (recognitionRef.current) {
          recognitionRef.current.stop();
        }
        parseAndFindStations(finalTranscript);
      }
    };

    recognition.onerror = () => {
      setIsListening(false);
      setError('Could not hear you. Please try again.');
      setTimeout(() => setError(null), 3000);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const stopListening = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    setIsListening(false);
  };

  const parseAndFindStations = async (query: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/parse-route-query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query })
      });

      const data = await response.json();

      if (data.success && data.from_station && data.to_station) {
        onStationsFound(data.from_station, data.to_station);
        setTranscript('');
      } else {
        setError(data.error || "Couldn't understand. Try: 'From Harvard to Park Street'");
        setTimeout(() => setError(null), 4000);
      }
    } catch (err) {
      setError("Couldn't connect to server");
      setTimeout(() => setError(null), 3000);
    }
  };

  if (!isSpeechSupported) {
    return null; // Don't show button if not supported
  }

  return (
    <div className="voice-input-container">
      <button
        className={`voice-input-button ${isListening ? 'listening' : ''}`}
        onClick={isListening ? stopListening : startListening}
        disabled={disabled}
        aria-label={isListening ? 'Stop listening' : 'Voice input'}
        title={isListening ? 'Tap to stop' : 'Tap to speak your route'}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 1C10.34 1 9 2.34 9 4V12C9 13.66 10.34 15 12 15C13.66 15 15 13.66 15 12V4C15 2.34 13.66 1 12 1Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M19 10V12C19 15.866 15.866 19 12 19C8.13401 19 5 15.866 5 12V10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M12 19V23" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M8 23H16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      {/* Transcript/Error Display */}
      {(isListening || transcript || error) && (
        <div className={`voice-feedback ${error ? 'voice-error' : ''}`}>
          {isListening && !transcript && <span>Listening...</span>}
          {transcript && <span>"{transcript}"</span>}
          {error && <span>{error}</span>}
        </div>
      )}
    </div>
  );
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
    <div className="station-search-wrapper">
      <label className="station-search-label">
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
        className="station-search-input"
      />
      
      {showResults && results.length > 0 && (
        <ul className="search-results">
          {results.map(station => (
            <li
              key={station.id}
              onClick={() => selectStation(station)}
              className="search-result-item"
            >
              <div className="search-result-name">{station.name}</div>
              <div className="search-result-meta">
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

// Component to track zoom level changes
function ZoomTracker({ onZoomChange }: { onZoomChange: (zoom: number) => void }) {
  const map = useMap();
  
  useEffect(() => {
    const updateZoom = () => {
      onZoomChange(map.getZoom());
    };
    
    // Set initial zoom
    updateZoom();
    
    // Listen for zoom changes
    map.on('zoomend', updateZoom);
    map.on('moveend', updateZoom); // Also update on pan (zoom might change due to fitBounds)
    
    return () => {
      map.off('zoomend', updateZoom);
      map.off('moveend', updateZoom);
    };
  }, [map, onZoomChange]);
  
  return null;
}

// Helper to get congestion color
const getCongestionColor = (congestion: string): string => {
  const congestionLower = congestion.toLowerCase();
  if (congestionLower.includes('extreme') || congestionLower.includes('very high')) {
    return '#dc2626';
  } else if (congestionLower.includes('high')) {
    return '#d97706';
  } else if (congestionLower.includes('medium')) {
    return '#eab308';
  } else {
    return '#059669';
  }
};

// Congestion Badge Component
function CongestionBadge({ congestion }: { congestion: string }) {
  const color = getCongestionColor(congestion);
  return (
    <span 
      className="congestion-badge" 
      style={{
        backgroundColor: `${color}15`,
        color: color,
        border: `1px solid ${color}`,
        padding: '0.25rem 0.5rem',
        borderRadius: 'var(--radius-full)',
        fontSize: '0.75rem',
        fontWeight: '600',
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.25rem'
      }}
    >
      {congestion}
    </span>
  );
}

// Component for displaying grouped segments in Apple Maps style
function GroupedSegmentDisplay({ group, isExpanded, onToggle, transferStationData }: {
  group: GroupedSegment;
  isExpanded: boolean;
  onToggle: () => void;
  transferStationData?: any;
}) {
  // Helper function to check if current time is peak hours
  const isPeakHours = (): boolean => {
    const now = new Date();
    const hour = now.getHours();
    const dayOfWeek = now.getDay(); // 0 = Sunday, 6 = Saturday
    
    // Peak hours: Weekdays 7-9 AM and 4-7 PM
    const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5;
    const isMorningPeak = hour >= 7 && hour < 10;
    const isEveningPeak = hour >= 16 && hour < 19;
    
    return isWeekday && (isMorningPeak || isEveningPeak);
  };

  // Helper function to match transfer segments to transfer_station_data.json
  const getTransferInfo = (stationId: string, fromLine: string | undefined, toLine: string | undefined, stationName?: string) => {
    // Debug: Check what we're receiving
    if (!transferStationData) {
      return null;
    }
    
    if (!stationId && !stationName) {
      return null;
    }
    
    // Normalize line names first to check if we have valid lines
    const normalizeLineForData = (line: string | undefined): string => {
      if (!line) return '';
      let normalized = normalizeLineName(line);
      normalized = normalized.replace(/\s*Line\s*/gi, '').replace(/-/g, '').trim();
      if (normalized === 'B' || normalized === 'C' || normalized === 'D' || normalized === 'E') {
        normalized = 'Green';
      }
      return normalized;
    };
    
    const fromLineNormalized = normalizeLineForData(fromLine);
    const toLineNormalized = normalizeLineForData(toLine);
    
    // If we don't have valid line names, we can't match
    if (!fromLineNormalized || !toLineNormalized) {
      return null;
    }
    
    // Try exact station ID match first
    let stationData = transferStationData[stationId];
    
    // If not found, try searching by station name (fallback)
    if (!stationData && stationName) {
      const searchName = stationName.toLowerCase();
      for (const [_id, data] of Object.entries(transferStationData)) {
        const stationInfo = data as any;
        if (stationInfo?.name?.toLowerCase() === searchName) {
          stationData = stationInfo;
          break;
        }
      }
    }
    
    if (!stationData || !stationData.transfers) {
      return null;
    }
    
    // Try exact match first: "Red→Orange"
    const transferKey = `${fromLineNormalized}→${toLineNormalized}`;
    let transferInfo = stationData.transfers[transferKey];
    
    // If not found, try reverse lookup
    if (!transferInfo) {
      const reverseKey = `${toLineNormalized}→${fromLineNormalized}`;
      transferInfo = stationData.transfers[reverseKey];
    }
    
    // If still not found, try partial matches (e.g., Green B→Green C/D should match Green B→Green C/D)
    if (!transferInfo && stationData.transfers) {
      for (const [key, info] of Object.entries(stationData.transfers)) {
        // Check if key contains both line names (in any order)
        if ((key.includes(fromLineNormalized) || fromLineNormalized.includes(key.split('→')[0])) &&
            (key.includes(toLineNormalized) || toLineNormalized.includes(key.split('→')[1]))) {
          transferInfo = info;
          break;
        }
      }
    }
    
    // If found, adjust congestion based on peak hours
    if (transferInfo) {
      const peakHours = isPeakHours();
      const baseCongestion = transferInfo.congestion || '';
      
      // During peak hours, use "High" congestion for all transfer stations
      // Otherwise, use "Low" or "Medium" (default to "Medium" if not specified)
      if (peakHours) {
        transferInfo = {
          ...transferInfo,
          congestion: 'High'
        };
      } else {
        // During off-peak, use lower congestion
        // Check if the original congestion is "Very High" or "Extreme" -> use "Medium"
        // Otherwise keep original or default to "Low"
        const congestionLower = baseCongestion.toLowerCase();
        if (congestionLower.includes('very high') || congestionLower.includes('extreme')) {
          transferInfo = {
            ...transferInfo,
            congestion: 'Medium'
          };
        } else if (congestionLower.includes('high')) {
          transferInfo = {
            ...transferInfo,
            congestion: 'Low'
          };
        } else {
          // Keep original or default to "Low"
          transferInfo = {
            ...transferInfo,
            congestion: baseCongestion || 'Low'
          };
        }
      }
    }
    
    return transferInfo;
  };
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

  const cleanLine = group.line?.replace(' Line', '').trim() || '';

  // Check if it's a commuter rail line (starts with CR- or is a known commuter rail name)
  const commuterRailLines = [
    'Framingham/Worcester', 'Providence/Stoughton', 'Lowell', 'Haverhill',
    'Fitchburg', 'Newburyport/Rockport', 'Kingston', 'Greenbush',
    'Needham', 'Fairmount', 'Franklin/Foxboro', 'Fall River/New Bedford',
    'Foxboro Event Service'
  ];
  const isCommuterRail = cleanLine.startsWith('CR-') ||
    commuterRailLines.some(cr => cleanLine.includes(cr)) ||
    (group.line && (group.line.startsWith('CR-') || commuterRailLines.some(cr => group.line!.includes(cr))));

  const lineColor = isCommuterRail ? '#80276C' : (lineColors[cleanLine] || '#80276C');

  if (group.type === 'train') {
    return (
      <div className="grouped-segment" style={{ borderLeftColor: lineColor }} role="listitem">
        <div
          className="grouped-segment-header"
          onClick={onToggle}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onToggle();
            }
          }}
          role="button"
          tabIndex={0}
          aria-expanded={isExpanded}
          aria-label={`${cleanLine} line from ${group.fromStation} to ${group.toStation}, ${group.totalStops} ${group.totalStops === 1 ? 'stop' : 'stops'}. Press Enter to ${isExpanded ? 'collapse' : 'expand'} details.`}
        >
          {/* Row 1: Line badge + stops */}
          <div className="segment-row segment-row-top">
            <span className="segment-badge-line" style={{ backgroundColor: lineColor }}>
              {group.line || cleanLine}
            </span>
            <div className="segment-stops-expand">
              <span className="grouped-segment-stops">{group.totalStops} {group.totalStops === 1 ? 'stop' : 'stops'}</span>
              <span className="expand-icon" aria-hidden="true">{isExpanded ? '▼' : '▶'}</span>
            </div>
          </div>
          {/* Row 2: From → To */}
          <div className="segment-row segment-row-route">
            {group.fromStation} → {group.toStation}
          </div>
          {/* Row 3: Times */}
          {group.departureTime && (
            <div className="segment-row segment-row-time">
              {formatTime(group.departureTime)} → {group.arrivalTime ? formatTime(group.arrivalTime) : '—'}
            </div>
          )}
        </div>
        {isExpanded && group.intermediateStops && group.intermediateStops.length > 0 && (
          <div className="intermediate-stops">
            {group.intermediateStops.map((stop, idx) => (
              <div key={idx} className="intermediate-stop">
                <span className="stop-dot" style={{ backgroundColor: lineColor }}></span>
                <span className="stop-name">{stop}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  } else if (group.type === 'transfer') {
    const transferInfo = getTransferInfo(
      group.transfer_station_id || '',
      group.transfer_from_line,
      group.transfer_to_line,
      group.fromStation
    );
    
    return (
      <div className="grouped-segment transfer-segment" role="listitem">
        <div className="grouped-segment-header">
          <span className="segment-badge transfer-badge" style={{ backgroundColor: '#FFA500' }}>
            Transfer
          </span>
          <span className="grouped-segment-route">at {group.fromStation}</span>
          {transferInfo?.congestion && (
            <CongestionBadge congestion={transferInfo.congestion} />
          )}
        </div>
        {group.transfer_rating && (
          <div className={`transfer-rating transfer-rating-${group.transfer_rating}`} aria-label={`Transfer rating: ${group.transfer_rating}`}>
            <span className="transfer-rating-text">
              {group.transfer_rating.toUpperCase()}
            </span>
          </div>
        )}
        {transferInfo && (
          <div className="transfer-details" style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
            {transferInfo.platform_position && (
              <div style={{ color: '#666', marginBottom: '0.25rem' }}>
                <strong>Platform:</strong> {transferInfo.platform_position}
              </div>
            )}
            {transferInfo.tip && (
              <div style={{ color: '#666', fontStyle: 'italic' }}>
                {transferInfo.tip}
              </div>
            )}
          </div>
        )}
      </div>
    );
  } else {
    // Walk segment - show time and distance in miles
    const walkSegment = group.segments[0];
    const distanceKm = walkSegment?.distance_km;
    const distanceMeters = walkSegment?.distance_meters;
    // Convert to miles (1 km = 0.621371 miles, 1 m = 0.000621371 miles)
    const distanceMiles = distanceKm
      ? distanceKm * 0.621371
      : distanceMeters
        ? distanceMeters * 0.000621371
        : null;
    const distanceDisplay = distanceMiles
      ? `${distanceMiles.toFixed(2)} mi`
      : null;

    return (
      <div className="grouped-segment walk-segment" role="listitem">
        <div className="grouped-segment-header">
          {/* Row 1: Walk badge */}
          <div className="segment-row segment-row-top">
            <span className="segment-badge-line walk-badge-line">
              Walk
            </span>
          </div>
          {/* Row 2: From → To */}
          <div className="segment-row segment-row-route">
            {group.fromStation} → {group.toStation}
          </div>
          {/* Row 3: Time and distance */}
          <div className="segment-row segment-row-time">
            {formatDuration(group.segments[0]?.time_minutes || 0)}
            {distanceDisplay && (
              <span className="walk-distance"> ({distanceDisplay})</span>
            )}
          </div>
        </div>
      </div>
    );
  }
}

function App() {
  const [stations, setStations] = useState<Station[]>([]);
  const [startStation, setStartStation] = useState<Station | null>(null);
  const [endStation, setEndStation] = useState<Station | null>(null);
  const [result, setResult] = useState<WalkingTimeResult | null>(null);
  const [sameLineRoute, setSameLineRoute] = useState<SameLineRouteResult | null>(null);

  // Helper to get rating-based border color
  const getRatingBorderColor = (segments: RouteSegment[], hasRiskyTransfers?: boolean): string => {
    const transferSegments = segments.filter(s => s.transfer_rating);
    if (transferSegments.length > 0) {
      const hasUnlikely = transferSegments.some(s => s.transfer_rating === 'unlikely');
      const hasRisky = transferSegments.some(s => s.transfer_rating === 'risky');
      if (hasUnlikely) return '#dc2626'; // Red for unlikely
      if (hasRisky) return '#d97706'; // Orange for risky
      return '#059669'; // Green for likely
    }
    // If no risky transfers, show likely (green)
    if (!hasRiskyTransfers) {
      return '#059669'; // Green for likely
    }
    // Default to likely (green)
    return '#059669';
  };
  const [routeResult, setRouteResult] = useState<RouteResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectingStation, setSelectingStation] = useState<'start' | 'end' | null>(null);
  const [routeGeometry, setRouteGeometry] = useState<[number, number][]>([]);
  const [routeSegments, setRouteSegments] = useState<{ coordinates: [number, number][], color: string, opacity: number, dashArray: string | null }[]>([]);
  const [routeShapes, setRouteShapes] = useState<{ [key: string]: { id: string; coordinates: [number, number][]; }[] }>({});
  const [walkingSpeed, setWalkingSpeed] = useState<number>(3.1); // mph (default 5.0 km/h = 3.1 mph)
  const [showSettings, setShowSettings] = useState<boolean>(false);
  const [initialLoading, setInitialLoading] = useState<boolean>(true);
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());
  const [expandedRoutes, setExpandedRoutes] = useState<Set<number>>(new Set());
  const [transferStationData, setTransferStationData] = useState<any>(null);
  const [currentZoom, setCurrentZoom] = useState<number>(13);

  // Helper function to get line color
  const getLineColor = (lineName: string) => {
    if (!lineName) return '#999999';

    // Handle Green Line branches (B, C, D, E)
    if (lineName === 'B' || lineName === 'C' || lineName === 'D' || lineName === 'E') return '#00843D';

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

  // Load all stations on mount and hide initial loading screen
  useEffect(() => {
    const loadData = async () => {
      try {
        await fetch(`${API_BASE}/api/stations`)
          .then(res => res.json())
          .then(data => setStations(data))
          .catch(err => console.error('Error loading stations:', err));
        
        // Hide loading screen after a minimum delay for smooth UX
        setTimeout(() => {
          setInitialLoading(false);
        }, 500);
      } catch (err) {
        // Hide loading screen even if there's an error
        setTimeout(() => {
          setInitialLoading(false);
        }, 500);
      }
    };
    
    loadData();
  }, []);

  // Load route shapes on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/shapes`)
      .then(res => res.json())
      .then(data => setRouteShapes(data))
      .catch(err => console.error('Error loading shapes:', err));
  }, []);

  // Load transfer station data on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/transfer-station-data`)
      .then(res => res.json())
      .then(data => {
        // The backend returns { STATION_GUIDANCE: {...} }, so extract STATION_GUIDANCE
        const stationData = data.STATION_GUIDANCE || data;
        console.log('Loaded transfer station data:', { 
          hasData: !!stationData, 
          keys: Object.keys(stationData || {}).slice(0, 5),
          sample: stationData && Object.keys(stationData)[0] ? stationData[Object.keys(stationData)[0]] : null
        });
        setTransferStationData(stationData);
      })
      .catch(err => console.error('Error loading transfer station data:', err));
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
            use_realtime: true,
            walking_speed_kmh: walkingSpeed * 1.60934 // Convert mph to km/h
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
          // Always fetch 2 alternatives for later departure times (same route at later times)
          let alternatives = routeData.alternatives || [];
          console.log('Initial alternatives from route response:', alternatives.length);
          
          // Always fetch more alternatives if we have fewer than 2
          // These will be the same route at later departure times
          if (alternatives.length < 2) {
            try {
              const altResponse = await fetch(`${API_BASE}/api/route/alternatives?offset=${alternatives.length}&limit=${2 - alternatives.length}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  station_id_1: startStation.id,
                  station_id_2: endStation.id,
                  prefer_fewer_transfers: true,
                  use_realtime: true,
                  walking_speed_kmh: walkingSpeed * 1.60934 // Convert mph to km/h
                })
              });

              if (altResponse.ok) {
                const additionalRoutes: RouteResult[] = await altResponse.json();
                console.log('Fetched additional alternatives:', additionalRoutes.length);
                if (additionalRoutes.length > 0) {
                  // Filter to ensure valid routes (departure < arrival)
                  const validRoutes = additionalRoutes.filter(alt => {
                    if (!alt.departure_time || !alt.arrival_time) return false;
                    const dep = new Date(alt.departure_time);
                    const arr = new Date(alt.arrival_time);
                    return arr > dep && arr > new Date(routeData.departure_time || 0);
                  });
                  // Merge with existing alternatives, ensuring we have up to 2
                  alternatives = [...alternatives, ...validRoutes].slice(0, 2);
                }
              } else {
                console.log('Alternatives endpoint returned error:', altResponse.status, await altResponse.text());
              }
            } catch (err) {
              console.log('Error fetching alternatives:', err);
            }
          }

          // Set route result with alternatives (ensure alternatives array exists)
          const finalRouteData = { ...routeData, alternatives };
          console.log('Final routeResult with alternatives:', finalRouteData.alternatives?.length || 0, finalRouteData.alternatives);
          setRouteResult(finalRouteData);
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
          walking_speed_kmh: walkingSpeed * 1.60934 // Convert mph to km/h
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
    setExpandedRoutes(new Set());
  };

  // Show initial loading screen
  if (initialLoading) {
    return (
      <div className="initial-loading-screen">
        <div className="initial-loading-content">
          <div className="mbta-t-logo-loading">T</div>
          <h1 className="initial-loading-title">MBTA Route Finder</h1>
          <div className="initial-loading-spinner"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Loading Overlay */}
      {loading && (
      <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          flexDirection: 'column',
          gap: '1rem'
        }}>
          <div style={{
            width: '50px',
            height: '50px',
            border: '5px solid #f3f3f3',
            borderTop: '5px solid #0066cc',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite'
          }}></div>
          <div style={{
            color: 'white',
            fontSize: '1.2rem',
            fontWeight: 'bold'
          }}>
            Finding best route...
          </div>
          <style>{`
            @keyframes spin {
              0% { transform: rotate(0deg); }
              100% { transform: rotate(360deg); }
            }
          `}</style>
        </div>
      )}

      {/* Map - Full Screen */}
      <div className="map-container">
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

          {/* Station Markers */}
          {stations.map(station => (
            <Marker
              key={station.id}
              position={[station.latitude, station.longitude]}
              icon={L.divIcon({
                className: 't-marker',
                html: `<div style="
                  background: ${getLineColor(station.lines[0] || 'Gray')};
                  color: white;
                  width: 24px;
                  height: 24px;
                  border-radius: 50%;
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  font-weight: 700;
                  font-size: 12px;
                  border: 2px solid white;
                  box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                ">T</div>`,
                iconSize: [24, 24],
                iconAnchor: [12, 12]
              })}
            >
              <Popup>
                <strong>{station.name}</strong>
                <br />
                {station.lines.join(', ')}
              </Popup>
            </Marker>
          ))}

          {/* Route Geometry */}
          {routeGeometry.length > 0 && (
            <Polyline
              positions={routeGeometry}
              color="#0066cc"
              weight={4}
              opacity={0.7}
            />
          )}

          {/* Route Segments */}
          {routeSegments.map((segment, idx) => (
            <Polyline
              key={idx}
              positions={segment.coordinates}
              color={segment.color}
              weight={4}
              opacity={segment.opacity}
              dashArray={segment.dashArray || undefined}
            />
          ))}
        </MapContainer>
      </div>

      {/* Search Overlay - Top Left */}
      {!(routeResult || sameLineRoute?.is_same_line || result) && (
        <div className="search-overlay">
          <div className="search-overlay-header">
            <div className="search-overlay-title">MBTA Route Finder</div>
            <div className="search-overlay-buttons">
              <VoiceInputButton
                onStationsFound={(from, to) => {
                  setStartStation(from);
                  setEndStation(to);
                }}
              />
              <button
                className="settings-button-compact"
                onClick={() => setShowSettings(!showSettings)}
                aria-label="Toggle settings"
                title="Settings"
              >
                <svg width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M10 12.5C11.3807 12.5 12.5 11.3807 12.5 10C12.5 8.61929 11.3807 7.5 10 7.5C8.61929 7.5 7.5 8.61929 7.5 10C7.5 11.3807 8.61929 12.5 10 12.5Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M16.25 10C16.25 10 15.125 8.875 14.375 8.125L15.625 5.625C15.625 5.625 14.5 4.5 13.75 3.75L11.25 5C11.25 5 10.125 4.25 10 4.25C9.875 4.25 8.75 5 8.75 5L6.25 3.75C6.25 3.75 5.125 4.5 4.375 5.25L5.625 7.75C5.625 7.75 4.5 8.875 4.5 10C4.5 10.125 5.25 11.25 5.25 11.25L3.75 13.75C3.75 13.75 4.5 14.875 5.25 15.625L7.75 14.375C7.75 14.375 8.875 15.5 10 15.5C10.125 15.5 11.25 14.75 11.25 14.75L13.75 15.625C13.75 15.625 14.875 14.5 15.625 13.75L14.375 11.25C14.375 11.25 15.5 10.125 16.25 10Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
            </div>
          </div>
          <div className="search-overlay-controls">
            <StationSearch
              label="From"
              onSelect={setStartStation}
              selectedStation={startStation}
            />
            <StationSearch
              label="To"
              onSelect={setEndStation}
              selectedStation={endStation}
            />
          </div>
        </div>
      )}

      {/* Settings Panel - Overlay */}
      {showSettings && (
        <div className="settings-panel-overlay">
          <div className="settings-panel">
            <div className="settings-panel-header">
              <h2 className="settings-panel-title">Settings</h2>
              <button
                className="settings-panel-close"
                onClick={() => setShowSettings(false)}
                aria-label="Close settings"
              >
                ×
              </button>
            </div>
            <div className="settings-panel-content">
              <div className="control-group">
                <label className="control-label" htmlFor="walking-speed-settings">
                  Walking Speed: {walkingSpeed.toFixed(1)} mph
                </label>
                <input
                  id="walking-speed-settings"
                  type="range"
                  min="1"
                  max="5"
                  step="0.1"
                  value={walkingSpeed}
                  onChange={(e) => setWalkingSpeed(parseFloat(e.target.value))}
                  className="range-slider"
                  aria-label="Walking speed"
                  aria-valuemin={1}
                  aria-valuemax={5}
                  aria-valuenow={walkingSpeed}
                />
                <div className="range-labels">
                  <span>Slow (1 mph)</span>
                  <span>Fast (5 mph)</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Results Overlay - Left Side */}
      {(routeResult || sameLineRoute?.is_same_line || result) && (
        <div className="results-overlay">
          <div className="results-overlay-header">
            <div className="results-overlay-title">
              <button
                onClick={clearSelection}
                className="back-button-compact"
                aria-label="Back to station selection"
              >
                <span className="back-arrow">←</span>
              </button>
              <div>
                <div className="route-from-to">
                  {startStation?.name} → {endStation?.name}
                </div>
                <div className="route-subtitle">Trip Options</div>
              </div>
            </div>
          </div>
          <div className="results-overlay-content">
            {/* Event Warning Banner */}
            {routeResult?.event_warning?.has_event && (
              <div className="warning-banner event-warning-banner" role="alert">
                <div className="warning-banner-icon">!</div>
                <div className="warning-banner-content">
                  <div className="warning-banner-title">
                    {routeResult.event_warning.event_type === 'sports' ? 'Game Day' : 'Event Alert'}
                  </div>
                  <div className="warning-banner-message">
                    {routeResult.event_warning.message || `${routeResult.event_warning.event_name} - Expect higher congestion at affected stations`}
                  </div>
                </div>
              </div>
            )}

            {/* Weather Warning Banner */}
            {routeResult?.weather_warning?.has_warning && (
              <div className="warning-banner weather-warning-banner" role="alert">
                <div className="warning-banner-icon">
                  {routeResult.weather_warning.condition === 'rain' || routeResult.weather_warning.condition === 'snow' ? '~' : '*'}
                </div>
                <div className="warning-banner-content">
                  <div className="warning-banner-title">Weather Advisory</div>
                  <div className="warning-banner-message">
                    {routeResult.weather_warning.message || `${routeResult.weather_warning.description} - Walking times adjusted by ${Math.round((routeResult.weather_warning.walking_time_adjustment - 1) * 100)}%`}
                  </div>
                </div>
              </div>
            )}

            <div className="results-container">
          {/* Same-line route result - Convert to RouteResult format */}
          {sameLineRoute && sameLineRoute.is_same_line && sameLineRoute.line_color && (() => {
            // Convert next_trains to RouteResult format
            const sameLineRoutes: RouteResult[] = (sameLineRoute.next_trains || [])
              .filter((train) => {
                // Filter out invalid trains where arrival is before or equal to departure
                if (!train.departure_time || !train.arrival_time) return false;
                const depTime = new Date(train.departure_time);
                const arrTime = new Date(train.arrival_time);
                return arrTime > depTime; // Only include valid trains
              })
              .slice(0, 3)
              .map((train) => {
                // Parse times and ensure they're valid
                const depTime = new Date(train.departure_time);
                const arrTime = new Date(train.arrival_time);
                
                // Calculate total_time from departure_time to arrival_time (actual trip duration)
                const tripDurationMs = arrTime.getTime() - depTime.getTime();
                const tripDurationMinutes = Math.max(0, tripDurationMs / (1000 * 60));
                
                // Use the calculated duration, fallback to total_trip_minutes if calculation is invalid
                const totalTimeMinutes = tripDurationMinutes > 0 ? tripDurationMinutes : (train.total_trip_minutes || 0);
                
                // Create a single train segment
                const segment: RouteSegment = {
                  from_station_id: startStation?.id || '',
                  from_station_name: sameLineRoute.from_station_name || startStation?.name || '',
                  to_station_id: endStation?.id || '',
                  to_station_name: sameLineRoute.to_station_name || endStation?.name || '',
                  type: 'train',
                  line: sameLineRoute.line_name,
                  route_id: '',
                  time_seconds: totalTimeMinutes * 60,
                  time_minutes: totalTimeMinutes,
                  distance_meters: sameLineRoute.distance_meters || 0,
                  departure_time: train.departure_time,
                  arrival_time: train.arrival_time,
                  status: train.status || 'Scheduled'
                };

                return {
                  segments: [segment],
                  total_time_seconds: totalTimeMinutes * 60,
                  total_time_minutes: totalTimeMinutes,
                  total_distance_meters: sameLineRoute.distance_meters || 0,
                  total_distance_km: (sameLineRoute.distance_meters || 0) / 1000,
                  num_transfers: 0,
                  departure_time: train.departure_time,
                  arrival_time: train.arrival_time,
                  has_risky_transfers: false,
                  alternatives: []
                };
              });

            const primaryRoute = sameLineRoutes[0];
            // Show 2 alternative routes (later trains) - same route at later times
            const alternativeRoutes = sameLineRoutes.slice(1, 3);

            return (
              <>
                {/* Primary Same-Line Route Card */}
                {primaryRoute && (
                  <div 
                    className="result-card route-option-card" 
                    role="region" 
                    aria-label="Primary same-line route option"
                    onClick={() => {
                      const newExpanded = new Set(expandedRoutes);
                      if (newExpanded.has(0)) {
                        newExpanded.delete(0);
                      } else {
                        newExpanded.add(0);
                      }
                      setExpandedRoutes(newExpanded);
                    }}
          style={{
            cursor: 'pointer',
                      border: `2px solid ${getRatingBorderColor(primaryRoute.segments, false)}`
                    }}
                  >
                    <div className="route-option-header">
                      <div className="route-option-title">
                        <div>
                          <span className="transfer-rating-badge transfer-rating-likely" aria-label="Transfer rating: LIKELY">
                            LIKELY
                          </span>
                          <div className="rating-explanation" style={{ fontSize: '0.8rem', color: '#666', marginTop: '0.25rem' }}>
                            No transfers required - direct route
                          </div>
                        </div>
                      </div>
                      <div className="route-option-time">
                        {formatDuration(primaryRoute.total_time_minutes)}
                      </div>
                    </div>

                    <div className="route-option-meta">
                      {primaryRoute.departure_time && primaryRoute.arrival_time && (
                        <span>{formatTime(primaryRoute.departure_time)} - {formatTime(primaryRoute.arrival_time)}</span>
                      )}
                      <span> • {primaryRoute.num_transfers} {primaryRoute.num_transfers === 1 ? 'transfer' : 'transfers'}</span>
                    </div>

                    {expandedRoutes.has(0) && (
                      <div 
                        className="grouped-segments-list" 
                        role="list" 
                        aria-label="Route segments"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {groupSegmentsByLine(primaryRoute.segments).map((group, idx) => (
                          <GroupedSegmentDisplay
                            key={idx}
                            group={group}
                            isExpanded={expandedGroups.has(idx)}
                            onToggle={() => {
                              const newExpanded = new Set(expandedGroups);
                              if (newExpanded.has(idx)) {
                                newExpanded.delete(idx);
                              } else {
                                newExpanded.add(idx);
                              }
                              setExpandedGroups(newExpanded);
                            }}
                            transferStationData={transferStationData}
                          />
                        ))}
            </div>
                    )}
                  </div>
                )}

                {/* Alternative Same-Line Route Cards - Show later trains (same route at later times) */}
                {alternativeRoutes.map((altRoute, altIdx) => (
                  <div 
                    key={`same-line-alt-${altIdx}`} 
                    className="result-card route-option-card alternative-route-option" 
                    role="region" 
                    aria-label={`Alternative same-line route option ${altIdx + 1}`}
                    onClick={() => {
                      const newExpanded = new Set(expandedRoutes);
                      const routeId = 1 + altIdx;
                      if (newExpanded.has(routeId)) {
                        newExpanded.delete(routeId);
                      } else {
                        newExpanded.add(routeId);
                      }
                      setExpandedRoutes(newExpanded);
                    }}
                    style={{ 
                      cursor: 'pointer',
                      border: `2px solid ${getRatingBorderColor(altRoute.segments, false)}`
                    }}
                  >
                    <div className="route-option-header">
                      <div className="route-option-title">
                        <div>
                          <span className="transfer-rating-badge transfer-rating-likely" aria-label="Transfer rating: LIKELY">
                            LIKELY
                          </span>
                          <div className="rating-explanation" style={{ fontSize: '0.8rem', color: '#666', marginTop: '0.25rem' }}>
                            No transfers required - direct route
                          </div>
                        </div>
                      </div>
                      <div className="route-option-time">
                        {formatDuration(altRoute.total_time_minutes)}
                      </div>
                    </div>

                    <div className="route-option-meta">
                      {altRoute.departure_time && altRoute.arrival_time && (
                        <span>{formatTime(altRoute.departure_time)} - {formatTime(altRoute.arrival_time)}</span>
                      )}
                      <span> • {altRoute.num_transfers} {altRoute.num_transfers === 1 ? 'transfer' : 'transfers'}</span>
                    </div>

                    {expandedRoutes.has(1 + altIdx) && (
                      <div 
                        className="grouped-segments-list" 
                        role="list" 
                        aria-label={`Alternative same-line route ${altIdx + 1} segments`}
                        onClick={(e) => e.stopPropagation()}
                      >
                        {groupSegmentsByLine(altRoute.segments).map((group, idx) => (
                          <GroupedSegmentDisplay
                            key={`same-line-alt-${altIdx}-${idx}`}
                            group={group}
                            isExpanded={expandedGroups.has(1000 + altIdx * 100 + idx)}
                            onToggle={() => {
                              const newExpanded = new Set(expandedGroups);
                              const groupId = 1000 + altIdx * 100 + idx;
                              if (newExpanded.has(groupId)) {
                                newExpanded.delete(groupId);
                              } else {
                                newExpanded.add(groupId);
                              }
                              setExpandedGroups(newExpanded);
                            }}
                            transferStationData={transferStationData}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </>
            );
          })()}

           {/* Comprehensive Route Result - Apple Maps Style */}
           {routeResult && !sameLineRoute?.is_same_line && (
             <>
               {/* Primary Route Option */}
               <div 
                 className="result-card route-option-card" 
                 role="region" 
                 aria-label="Primary route option"
                 onClick={() => {
                   const newExpanded = new Set(expandedRoutes);
                   if (newExpanded.has(0)) {
                     newExpanded.delete(0);
                   } else {
                     newExpanded.add(0);
                   }
                   setExpandedRoutes(newExpanded);
                 }}
                 style={{ 
                   cursor: 'pointer',
                   border: `2px solid ${getRatingBorderColor(routeResult.segments, routeResult.has_risky_transfers)}`
                 }}
               >
                 <div className="route-option-header">
                   <div className="route-option-title">
                     {(() => {
                       const transferSegments = routeResult.segments.filter(s => s.transfer_rating);
                       if (transferSegments.length > 0) {
                         const hasUnlikely = transferSegments.some(s => s.transfer_rating === 'unlikely');
                         const hasRisky = transferSegments.some(s => s.transfer_rating === 'risky');
                         const rating = hasUnlikely ? 'unlikely' : (hasRisky ? 'risky' : 'likely');
                         const ratingText = hasUnlikely ? 'UNLIKELY' : (hasRisky ? 'RISKY' : 'LIKELY');
                         return (
                           <div>
                             <span className={`transfer-rating-badge transfer-rating-${rating}`} aria-label={`Transfer rating: ${ratingText}`}>
                               {ratingText}
                             </span>
                             <div className="rating-explanation" style={{ fontSize: '0.8rem', color: '#666', marginTop: '0.25rem' }}>
                               {rating === 'unlikely' && 'You will have less than 2 minutes between trains'}
                               {rating === 'risky' && 'You will have 2-5 minutes between trains'}
                               {rating === 'likely' && 'You will have more than 5 minutes between trains'}
                             </div>
                           </div>
                         );
                       }
                       // Show LIKELY badge if no risky transfers (including 0 transfers)
                       if (!routeResult.has_risky_transfers) {
                         return (
                           <div>
                             <span className="transfer-rating-badge transfer-rating-likely" aria-label="Transfer rating: LIKELY">
                               LIKELY
                             </span>
                             <div className="rating-explanation" style={{ fontSize: '0.8rem', color: '#666', marginTop: '0.25rem' }}>
                               {routeResult.num_transfers > 0 ? 'You will have more than 5 minutes between trains' : 'No transfers required - direct route'}
                             </div>
                           </div>
                         );
                       }
                       // Default to LIKELY if we can't determine
                       return (
                         <div>
                           <span className="transfer-rating-badge transfer-rating-likely" aria-label="Transfer rating: LIKELY">
                             LIKELY
                           </span>
                           <div className="rating-explanation" style={{ fontSize: '0.8rem', color: '#666', marginTop: '0.25rem' }}>
                             No transfers required - direct route
                           </div>
                         </div>
                       );
                     })()}
                   </div>
                   <div className="route-option-time">
                     {formatDuration(routeResult.total_time_minutes)}
                   </div>
                 </div>
            
                 <div className="route-option-meta">
                   {routeResult.departure_time && routeResult.arrival_time && (
                     <span>{formatTime(routeResult.departure_time)} - {formatTime(routeResult.arrival_time)}</span>
                   )}
                   <span> • {routeResult.num_transfers} {routeResult.num_transfers === 1 ? 'transfer' : 'transfers'}</span>
            </div>
            
                 {expandedRoutes.has(0) && (
                   <div 
                     className="grouped-segments-list" 
                     role="list" 
                     aria-label="Route segments"
                     onClick={(e) => e.stopPropagation()}
                   >
                        {groupSegmentsByLine(routeResult.segments).map((group, idx) => (
                          <GroupedSegmentDisplay
                            key={idx}
                            group={group}
                            isExpanded={expandedGroups.has(idx)}
                            onToggle={() => {
                              const newExpanded = new Set(expandedGroups);
                              if (newExpanded.has(idx)) {
                                newExpanded.delete(idx);
                              } else {
                                newExpanded.add(idx);
                              }
                              setExpandedGroups(newExpanded);
                            }}
                            transferStationData={transferStationData}
                          />
                        ))}
                   </div>
                 )}
               </div>

              {/* Alternative Route Options - Always show 2 alternatives (same route at later times) */}
              {routeResult.alternatives && routeResult.alternatives.length > 0 && routeResult.alternatives.slice(0, 2).map((altRoute, altIdx) => (
                <div 
                  key={`alt-${altIdx}`} 
                  className="result-card route-option-card alternative-route-option" 
                  role="region" 
                  aria-label={`Alternative route option ${altIdx + 1}`}
                  onClick={() => {
                    const newExpanded = new Set(expandedRoutes);
                    const routeId = 1 + altIdx;
                    if (newExpanded.has(routeId)) {
                      newExpanded.delete(routeId);
                    } else {
                      newExpanded.add(routeId);
                    }
                    setExpandedRoutes(newExpanded);
                  }}
                    style={{
                    cursor: 'pointer',
                    border: `2px solid ${getRatingBorderColor(altRoute.segments, altRoute.has_risky_transfers)}`
                  }}
                >
                  <div className="route-option-header">
                    <div className="route-option-title">
                      {(() => {
                        const transferSegments = altRoute.segments.filter(s => s.transfer_rating);
                        if (transferSegments.length > 0) {
                          const hasUnlikely = transferSegments.some(s => s.transfer_rating === 'unlikely');
                          const hasRisky = transferSegments.some(s => s.transfer_rating === 'risky');
                          const rating = hasUnlikely ? 'unlikely' : (hasRisky ? 'risky' : 'likely');
                          const ratingText = hasUnlikely ? 'UNLIKELY' : (hasRisky ? 'RISKY' : 'LIKELY');
                          return (
                            <div>
                              <span className={`transfer-rating-badge transfer-rating-${rating}`} aria-label={`Transfer rating: ${ratingText}`}>
                                {ratingText}
                              </span>
                              <div className="rating-explanation" style={{ fontSize: '0.8rem', color: '#666', marginTop: '0.25rem' }}>
                                {rating === 'unlikely' && 'You will have less than 2 minutes between trains'}
                                {rating === 'risky' && 'You will have 2-5 minutes between trains'}
                                {rating === 'likely' && 'You will have more than 5 minutes between trains'}
                    </div>
                    </div>
                          );
                        }
                        // Show LIKELY badge if no risky transfers (including 0 transfers)
                        if (!altRoute.has_risky_transfers) {
                          return (
                            <div>
                              <span className="transfer-rating-badge transfer-rating-likely" aria-label="Transfer rating: LIKELY">
                                LIKELY
                              </span>
                              <div className="rating-explanation" style={{ fontSize: '0.8rem', color: '#666', marginTop: '0.25rem' }}>
                                {altRoute.num_transfers > 0 ? 'You will have more than 5 minutes between trains' : 'No transfers required - direct route'}
                    </div>
                  </div>
                          );
                        }
                        // Default to LIKELY if we can't determine
                        return (
                          <div>
                            <span className="transfer-rating-badge transfer-rating-likely" aria-label="Transfer rating: LIKELY">
                              LIKELY
                            </span>
                            <div className="rating-explanation" style={{ fontSize: '0.8rem', color: '#666', marginTop: '0.25rem' }}>
                              No transfers required - direct route
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                    <div className="route-option-time">
                      {formatDuration(altRoute.total_time_minutes)}
                    </div>
                  </div>

                  <div className="route-option-meta">
                    {altRoute.departure_time && altRoute.arrival_time && (
                      <span>{formatTime(altRoute.departure_time)} - {formatTime(altRoute.arrival_time)}</span>
                    )}
                    <span> • {altRoute.num_transfers} {altRoute.num_transfers === 1 ? 'transfer' : 'transfers'}</span>
            </div>

                  {expandedRoutes.has(1 + altIdx) && (
                    <div 
                      className="grouped-segments-list" 
                      role="list" 
                      aria-label={`Alternative route ${altIdx + 1} segments`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {groupSegmentsByLine(altRoute.segments).map((group, idx) => (
                        <GroupedSegmentDisplay
                          key={`alt-${altIdx}-${idx}`}
                          group={group}
                          isExpanded={expandedGroups.has(1000 + altIdx * 100 + idx)}
                          onToggle={() => {
                            const newExpanded = new Set(expandedGroups);
                            const groupId = 1000 + altIdx * 100 + idx;
                            if (newExpanded.has(groupId)) {
                              newExpanded.delete(groupId);
                            } else {
                              newExpanded.add(groupId);
                            }
                            setExpandedGroups(newExpanded);
                          }}
                          transferStationData={transferStationData}
                        />
                      ))}
          </div>
                  )}
                </div>
              ))}
            </>
          )}

          {/* Walking Route Result */}
          {result && !sameLineRoute?.is_same_line && !routeResult && (
            <div className="result-card" role="article" aria-label="Walking route">
              <h2 className="result-card-title text-accent">Walking Route</h2>

              <p className="result-card-subtitle">
              <strong>{result.station_1.name}</strong> → <strong>{result.station_2.name}</strong>
              </p>

              <div className="time-display">
                <div className="time-value">
                {formatDuration(result.duration_minutes)}
              </div>
                <div className="time-meta">
                {result.distance_km} km
              </div>
            </div>
          </div>
        )}
            </div>
          </div>
        </div>
      )}

      {/* Map - Full Screen */}
      <div className="map-container">
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

          <ZoomTracker onZoomChange={setCurrentZoom} />

          <ZoomControl position="bottomright" />

          {/* Render All Route Shapes (Background) */}
          {!result && !routeResult && !sameLineRoute && Object.entries(routeShapes).map(([routeId, shapes]) => {
            // Commuter rail routes are now enabled (purple lines)

            const color = getLineColor(routeId);
            // Only render the first shape for each route to avoid duplicates
            const mainShape = shapes[0];
            if (!mainShape) return null;

            return (
              <Polyline
                key={mainShape.id}
                positions={mainShape.coordinates}
                pathOptions={{
                  color: color,
                  weight: 3,
                  opacity: 0.5,
                  lineCap: 'round',
                  lineJoin: 'round'
                }}
              />
            );
          })}

          {/* Show all stations with T logo markers - show route stations when route active */}
          {stations.map(station => {
            // Hide non-route stations when route is displayed
            if (routeResult && startStation && endStation) {
              const isOnRoute = routeResult.segments.some(seg =>
                seg.from_station_id === station.id || seg.to_station_id === station.id
              );
              if (!isOnRoute && station.id !== startStation.id && station.id !== endStation.id) {
                return null;
              }
            }
            
            // Only show stations when zoomed in enough (zoom >= 13)
            // Always show start/end stations and stations on the route regardless of zoom
            const isSelectedOrOnRoute = startStation?.id === station.id || 
                                       endStation?.id === station.id ||
                                       (routeResult && routeResult.segments.some(seg =>
                                         seg.from_station_id === station.id || seg.to_station_id === station.id
                                       ));
            
            if (!isSelectedOrOnRoute && currentZoom < 14) {
              return null;
            }

            return (
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
                      {(() => {
                        const getLineColor = (line: string) => {
                          const cleanLine = line.replace(' Line', '').trim();
                      const lineColors: { [key: string]: string } = {
                        'Red': '#DA291C',
                        'Orange': '#ED8B00',
                        'Blue': '#003DA5',
                        'Green': '#00843D',
                        'Green-B': '#00843D',
                        'Green-C': '#00843D',
                        'Green-D': '#00843D',
                        'Green-E': '#00843D',
                            'B': '#00843D',
                            'C': '#00843D',
                            'D': '#00843D',
                            'E': '#00843D',
                        'Silver': '#7C878E',
                        'Mattapan': '#DA291C'
                      };
                          // Color all commuter rail lines purple
                          const commuterRailLines = [
                            'Framingham/Worcester', 'Providence/Stoughton', 'Lowell', 'Haverhill',
                            'Fitchburg', 'Newburyport/Rockport', 'Kingston', 'Greenbush',
                            'Needham', 'Fairmount', 'Franklin/Foxboro', 'Fall River/New Bedford',
                            'Foxboro Event Service'
                          ];
                          if (cleanLine.startsWith('CR-') || commuterRailLines.some(cr => cleanLine.startsWith(cr))) {
                            return '#80276C'; // Purple for commuter rail
                          }
                          return lineColors[cleanLine] || '#000000';
                        };

                        // Deduplicate by color - keep only one line per color
                        const uniqueLinesByColor = new Map<string, string>();
                        station.lines.forEach(line => {
                          const color = getLineColor(line);
                          if (!uniqueLinesByColor.has(color)) {
                            uniqueLinesByColor.set(color, line);
                          }
                        });

                        return Array.from(uniqueLinesByColor.values()).map((line, idx) => {
                      const cleanLine = line.replace(' Line', '').trim();
                          const color = getLineColor(line);
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
                        });
                      })()}
                  </div>
                  <div style={{ marginTop: '6px', fontSize: '12px', color: '#666' }}>
                    {station.municipality}
                  </div>
                </div>
              </Popup>
            </Marker>
            );
          })}

          {/* Same-line route line */}
          {sameLineRoute && sameLineRoute.is_same_line && sameLineRoute.line_color && (
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

          {/* Direct walking path with geometry */}
          {result && !sameLineRoute?.is_same_line && !routeResult && result.geometry_coordinates && result.geometry_coordinates.length > 0 && (
            <Polyline
              positions={result.geometry_coordinates}
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

          {/* Fallback straight line walking path if no geometry */}
          {result && !sameLineRoute?.is_same_line && !routeResult && (!result.geometry_coordinates || result.geometry_coordinates.length === 0) && (
            <Polyline
              positions={[[result.station_1.latitude, result.station_1.longitude], [result.station_2.latitude, result.station_2.longitude]]}
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