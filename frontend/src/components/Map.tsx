import { useEffect, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import type { Station } from '../types';

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || '';

if (MAPBOX_TOKEN) {
  mapboxgl.accessToken = MAPBOX_TOKEN;
}

interface MapProps {
  onSelectionComplete: (origin: Station, transfer: Station, destination: Station) => void;
}

type SelectionStep = 'origin' | 'transfer' | 'destination' | 'complete';

interface SelectionState {
  origin?: Station;
  transfer?: Station;
  destination?: Station;
}

export function Map({ onSelectionComplete }: MapProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);
  const markersRef = useRef<mapboxgl.Marker[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [step, setStep] = useState<SelectionStep>('origin');
  const [selections, setSelections] = useState<SelectionState>({});

  // Load stations
  useEffect(() => {
    fetch('/stations.json')
      .then((res) => res.json())
      .then((data) => setStations(data))
      .catch((err) => console.error('Failed to load stations:', err));
  }, []);

  // Initialize map
  useEffect(() => {
    if (!mapContainer.current || map.current) return;
    if (!MAPBOX_TOKEN) {
      console.error('Mapbox token is missing. Please set VITE_MAPBOX_TOKEN in .env');
      return;
    }

    try {
      map.current = new mapboxgl.Map({
        container: mapContainer.current,
        style: 'mapbox://styles/mapbox/dark-v11',
        center: [-71.0589, 42.3601],
        zoom: 12,
      });
    } catch (error) {
      console.error('Failed to initialize Mapbox:', error);
    }
  }, []);

  // Update markers when stations or selections change
  useEffect(() => {
    if (!map.current || !stations.length) return;

    // Clear existing markers
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];

    // MBTA brand colors
    const LINE_COLORS: Record<string, string> = {
      Red: '#DA291C',
      Orange: '#ED8B00',
      Blue: '#003882',
      'Green-B': '#00843D',
      'Green-C': '#00843D',
      'Green-D': '#00843D',
      'Green-E': '#00843D',
      Silver: '#7C878E',
    };

    stations.forEach((station) => {
      // Priority: selection color > line color > gray
      let color = '#6B7280'; // default gray
      
      if (selections.origin?.id === station.id) {
        color = '#3B82F6'; // blue for origin
      } else if (selections.transfer?.id === station.id) {
        color = '#EAB308'; // yellow for transfer
      } else if (selections.destination?.id === station.id) {
        color = '#10B981'; // green for destination
      } else if (station.routes && station.routes.length > 0) {
        // Use first route's color, or check for transfer stations (multiple routes)
        const primaryRoute = station.routes[0];
        color = LINE_COLORS[primaryRoute] || LINE_COLORS[station.routes.find(r => r.startsWith('Green')) || ''] || color;
        
        // If station has multiple routes, use a slightly lighter shade to indicate transfer
        if (station.routes.length > 1) {
          // Keep the primary color but make it slightly lighter
          color = color; // Keep as-is for now, or add visual indicator
        }
      }

      const el = document.createElement('div');
      el.className = 'cursor-pointer';
      el.style.width = '24px';
      el.style.height = '24px';
      el.style.borderRadius = '50%';
      el.style.backgroundColor = color;
      el.style.border = '2px solid white';
      el.style.boxShadow = '0 2px 4px rgba(0,0,0,0.3)';

      el.addEventListener('click', () => handleStationClick(station));

      const routesText = station.routes?.join(', ') || '';
      const popupContent = `
        <div class="p-2">
          <strong class="font-bold text-gray-800">${station.name}</strong>
          ${routesText ? `<div class="text-xs text-gray-600 mt-1">${routesText}</div>` : ''}
        </div>
      `;
      
      const marker = new mapboxgl.Marker(el)
        .setLngLat([station.lon, station.lat])
        .setPopup(new mapboxgl.Popup().setHTML(popupContent))
        .addTo(map.current!);

      markersRef.current.push(marker);
    });
  }, [stations, selections]);

  const handleStationClick = (station: Station) => {
    if (step === 'origin') {
      const newSelections = { origin: station };
      setSelections(newSelections);
      setStep('transfer');
    } else if (step === 'transfer') {
      if (station.id === selections.origin?.id) return;
      const newSelections = { ...selections, transfer: station };
      setSelections(newSelections);
      setStep('destination');
    } else if (step === 'destination') {
      if (
        station.id === selections.origin?.id ||
        station.id === selections.transfer?.id
      )
        return;
      const newSelections = { ...selections, destination: station };
      setSelections(newSelections);
      setStep('complete');
      if (newSelections.origin && newSelections.transfer && newSelections.destination) {
        onSelectionComplete(
          newSelections.origin,
          newSelections.transfer,
          newSelections.destination
        );
      }
    }
  };

  if (!MAPBOX_TOKEN) {
    return (
      <div className="relative w-full h-screen bg-gray-100 flex items-center justify-center">
        <div className="bg-white rounded-lg shadow-lg p-8 max-w-md text-center">
          <h2 className="text-2xl font-bold text-gray-800 mb-4">Mapbox Token Required</h2>
          <p className="text-gray-600 mb-4">
            To display the interactive map, please add your Mapbox token to <code className="bg-gray-100 px-2 py-1 rounded">frontend/.env</code>
          </p>
          <div className="text-sm text-gray-500 space-y-2">
            <p><strong>Create</strong> <code>frontend/.env</code>:</p>
            <pre className="bg-gray-100 p-3 rounded text-left text-xs overflow-x-auto">
              VITE_MAPBOX_TOKEN=your_token_here
            </pre>
            <p className="mt-4">
              Get a free token at{' '}
              <a href="https://account.mapbox.com/access-tokens/" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                account.mapbox.com
              </a>
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="relative w-full h-screen">
      <div ref={mapContainer} className="w-full h-full" />
      <div className="absolute top-4 left-4 bg-white/90 backdrop-blur-sm rounded-lg p-4 shadow-lg z-10">
        <h2 className="text-lg font-semibold mb-2 text-gray-800">
          Select Stations:
        </h2>
        <div className="space-y-2 text-sm">
          <div className={`flex items-center gap-2 ${selections.origin ? 'text-green-600' : 'text-gray-600'}`}>
            <span className="font-medium">1. Origin</span>
            {selections.origin && <span className="text-xs">✓ {selections.origin.name}</span>}
          </div>
          <div className={`flex items-center gap-2 ${selections.transfer ? 'text-green-600' : 'text-gray-600'}`}>
            <span className="font-medium">2. Transfer</span>
            {selections.transfer && <span className="text-xs">✓ {selections.transfer.name}</span>}
          </div>
          <div className={`flex items-center gap-2 ${selections.destination ? 'text-green-600' : 'text-gray-600'}`}>
            <span className="font-medium">3. Destination</span>
            {selections.destination && <span className="text-xs">✓ {selections.destination.name}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
