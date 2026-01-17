import { useState } from 'react';
import React from 'react';
import { MapContainer, TileLayer, CircleMarker, Polyline, Tooltip } from 'react-leaflet';
import { Icon } from 'leaflet';
import { CheckCircle } from 'lucide-react';
import 'leaflet/dist/leaflet.css';
import { STATIONS, type Station } from '../data/stations';
import { LINE_COLORS } from '../data/transfers';

// Fix Leaflet default icon issue
delete (Icon.Default.prototype as any)._getIconUrl;
Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

interface MapProps {
  onSelectionComplete: (origin: Station, transfer: Station, destination: Station) => void;
}

export function Map({ onSelectionComplete }: MapProps) {
  const [origin, setOrigin] = useState<Station | null>(null);
  const [transfer, setTransfer] = useState<Station | null>(null);
  const [destination, setDestination] = useState<Station | null>(null);
  const [hoveredStation, setHoveredStation] = useState<Station | null>(null);

  // Validation logic
  const isValidTransfer = (station: Station): boolean => {
    if (!origin) return false;
    if (!station.isTransferHub) return false;
    // Must share at least one route with origin
    return station.routes.some(route => origin.routes.includes(route));
  };

  const isValidDestination = (station: Station): boolean => {
    if (!transfer) return false;
    // Can't be origin or transfer
    if (station.id === origin?.id || station.id === transfer.id) return false;
    // Must share at least one route with transfer
    return station.routes.some(route => transfer.routes.includes(route));
  };

  // Handle station click
  const handleStationClick = (station: Station) => {
    if (!origin) {
      setOrigin(station);
      setTransfer(null);
      setDestination(null);
    } else if (!transfer) {
      if (isValidTransfer(station)) {
        setTransfer(station);
        setDestination(null);
      }
    } else if (!destination) {
      if (isValidDestination(station)) {
        setDestination(station);
        onSelectionComplete(origin, transfer, station);
      }
    } else {
      // Reset
      setOrigin(station);
      setTransfer(null);
      setDestination(null);
    }
  };

  // Calculate marker radius
  const getRadius = (station: Station): number => {
    if (origin?.id === station.id || transfer?.id === station.id || destination?.id === station.id) {
      return 14;
    }
    if (hoveredStation?.id === station.id) {
      return 12;
    }
    return station.isTransferHub ? 10 : 8;
  };

  // Calculate marker fill color
  const getFillColor = (station: Station): string => {
    if (origin?.id === station.id) return '#3B82F6'; // Blue
    if (transfer?.id === station.id) return '#EAB308'; // Yellow
    if (destination?.id === station.id) return '#10B981'; // Green
    if (hoveredStation?.id === station.id && !isValidTransfer(station) && transfer === null) {
      return '#9CA3AF'; // Gray for invalid hover
    }
    return LINE_COLORS[station.routes[0]] || '#6B7280';
  };

  // Calculate marker opacity
  const getOpacity = (station: Station): number => {
    if (origin?.id === station.id || transfer?.id === station.id || destination?.id === station.id) {
      return 1.0;
    }
    if (transfer && !isValidDestination(station) && destination === null) {
      return 0.4; // Gray out invalid destinations
    }
    if (origin && !isValidTransfer(station) && transfer === null) {
      return 0.4; // Gray out invalid transfers
    }
    return 0.9;
  };

  // Handle calculate button
  const onCalculate = () => {
    if (origin && transfer && destination) {
      onSelectionComplete(origin, transfer, destination);
    }
  };

  return (
    <div className="w-full h-full relative">
      <MapContainer
        center={[42.3601, -71.0589]}
        zoom={13}
        style={{ height: '100%', width: '100%' }}
        zoomControl={false}
        className="z-0"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />

        {/* Station Markers */}
        {STATIONS.map(station => {
          const isSelected = origin?.id === station.id || transfer?.id === station.id || destination?.id === station.id;
          
          return (
            <React.Fragment key={station.id}>
              {/* Glow effect for selected stations */}
              {isSelected && (
                <CircleMarker
                  center={[station.lat, station.lon]}
                  radius={20}
                  pathOptions={{
                    color: getFillColor(station),
                    fillColor: getFillColor(station),
                    fillOpacity: 0.2,
                    weight: 0,
                  }}
                />
              )}
              
              {/* Main marker */}
              <CircleMarker
                center={[station.lat, station.lon]}
                radius={getRadius(station)}
                pathOptions={{
                  color: 'white',
                  fillColor: getFillColor(station),
                  fillOpacity: getOpacity(station),
                  weight: 3,
                }}
                eventHandlers={{
                  click: () => handleStationClick(station),
                  mouseover: () => setHoveredStation(station),
                  mouseout: () => setHoveredStation(null),
                }}
              >
                <Tooltip permanent={false} direction="top" offset={[0, -10]}>
                  <div className="font-semibold">{station.name}</div>
                  <div className="text-xs text-gray-500">{station.routes.join(', ')} Line</div>
                  {station.isTransferHub && (
                    <div className="text-xs text-blue-500 mt-1">Transfer Hub</div>
                  )}
                </Tooltip>
              </CircleMarker>
            </React.Fragment>
          );
        })}

        {/* Route Lines - Origin to Transfer */}
        {origin && transfer && (
          <>
            {/* White outline */}
            <Polyline
              positions={[[origin.lat, origin.lon], [transfer.lat, transfer.lon]]}
              pathOptions={{
                color: 'white',
                weight: 10,
                opacity: 0.5,
              }}
            />
            {/* Colored line on top */}
            <Polyline
              positions={[[origin.lat, origin.lon], [transfer.lat, transfer.lon]]}
              pathOptions={{
                color: LINE_COLORS[origin.routes[0]] || '#6B7280',
                weight: 8,
                opacity: 1.0,
              }}
            />
          </>
        )}

        {/* Route Lines - Transfer to Destination */}
        {transfer && destination && (
          <>
            {/* White outline */}
            <Polyline
              positions={[[transfer.lat, transfer.lon], [destination.lat, destination.lon]]}
              pathOptions={{
                color: 'white',
                weight: 10,
                opacity: 0.5,
              }}
            />
            {/* Colored line on top */}
            <Polyline
              positions={[[transfer.lat, transfer.lon], [destination.lat, destination.lon]]}
              pathOptions={{
                color: LINE_COLORS[destination.routes[0]] || '#6B7280',
                weight: 8,
                opacity: 1.0,
              }}
            />
          </>
        )}
      </MapContainer>

      {/* Beautiful UI Instruction Panel */}
      <div className="absolute top-6 left-6 bg-white/95 backdrop-blur-sm px-6 py-4 rounded-xl shadow-2xl border border-gray-200 max-w-sm z-[1000]">
        <h3 className="text-lg font-bold text-gray-900 mb-3">Plan Your Transfer</h3>
        
        <div className="space-y-3">
          {/* Step 1: Origin */}
          <div className="flex items-start gap-3">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-sm transition-colors ${
                origin ? 'bg-blue-500' : 'bg-gray-300'
              }`}
            >
              1
            </div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-gray-700">Origin Station</div>
              <div className="text-xs text-gray-500">
                {origin ? origin.name : 'Click any station'}
              </div>
            </div>
            {origin && <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0" />}
          </div>

          {/* Step 2: Transfer */}
          <div className="flex items-start gap-3">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-sm transition-colors ${
                transfer ? 'bg-yellow-500' : 'bg-gray-300'
              }`}
            >
              2
            </div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-gray-700">Transfer Hub</div>
              <div className="text-xs text-gray-500">
                {transfer
                  ? transfer.name
                  : origin
                  ? "Choose where you'll switch"
                  : 'Select origin first'}
              </div>
            </div>
            {transfer && <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0" />}
          </div>

          {/* Step 3: Destination */}
          <div className="flex items-start gap-3">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-sm transition-colors ${
                destination ? 'bg-green-500' : 'bg-gray-300'
              }`}
            >
              3
            </div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-gray-700">Destination</div>
              <div className="text-xs text-gray-500">
                {destination
                  ? destination.name
                  : transfer
                  ? 'Choose final stop'
                  : 'Select transfer first'}
              </div>
            </div>
            {destination && <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0" />}
          </div>
        </div>

        {destination && (
          <button
            onClick={onCalculate}
            className="mt-4 w-full bg-gradient-to-r from-blue-600 to-blue-700 text-white py-3 rounded-lg font-semibold hover:from-blue-700 hover:to-blue-800 transition-all shadow-lg"
          >
            Calculate Transfer
          </button>
        )}
      </div>
    </div>
  );
}
