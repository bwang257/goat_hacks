import { useState, useMemo } from 'react';
import type { Station } from '../types';

interface StationSearchProps {
  stations: Station[];
  onStationSelect: (station: Station) => void;
  className?: string;
}

export function StationSearch({ stations, onStationSelect, className = '' }: StationSearchProps) {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);

  const filteredStations = useMemo(() => {
    if (!query.trim()) return [];
    const lowerQuery = query.toLowerCase();
    return stations
      .filter(
        (station) =>
          station.name.toLowerCase().includes(lowerQuery) ||
          station.routes.some((route) => route.toLowerCase().includes(lowerQuery))
      )
      .slice(0, 10); // Limit to 10 results
  }, [query, stations]);

  const handleSelect = (station: Station) => {
    setQuery('');
    setIsOpen(false);
    onStationSelect(station);
  };

  return (
    <div className={`relative ${className}`}>
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          placeholder="Search stations..."
          className="w-full px-4 py-3 pl-12 text-gray-900 bg-white border border-gray-300 rounded-lg shadow-lg focus:outline-none focus:ring-2 focus:ring-mbta-blue focus:border-transparent"
        />
        <svg
          className="absolute left-4 top-3.5 w-5 h-5 text-gray-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
      </div>

      {isOpen && filteredStations.length > 0 && (
        <div className="absolute z-50 w-full mt-2 bg-white border border-gray-300 rounded-lg shadow-xl max-h-96 overflow-y-auto">
          {filteredStations.map((station) => (
            <button
              key={station.id}
              onClick={() => handleSelect(station)}
              className="w-full px-4 py-3 text-left hover:bg-gray-100 transition-colors border-b border-gray-100 last:border-b-0"
            >
              <div className="font-medium text-gray-900">{station.name}</div>
              <div className="text-sm text-gray-500 mt-1">
                {station.routes.join(', ')}
              </div>
            </button>
          ))}
        </div>
      )}

      {isOpen && query && filteredStations.length === 0 && (
        <div className="absolute z-50 w-full mt-2 bg-white border border-gray-300 rounded-lg shadow-xl p-4 text-center text-gray-500">
          No stations found
        </div>
      )}
    </div>
  );
}
