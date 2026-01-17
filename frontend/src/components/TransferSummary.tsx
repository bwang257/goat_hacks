import { useEffect, useState } from 'react';
import type { Station, TransferOption } from '../types';
import { ConfidenceBadge } from './ConfidenceBadge';

interface TransferSummaryProps {
  origin: Station;
  transfer: Station;
  destination: Station;
  transferOption?: TransferOption;
  walkingSpeed: number;
}

export function TransferSummary({
  origin,
  transfer,
  destination,
  transferOption,
  walkingSpeed,
}: TransferSummaryProps) {
  if (!transferOption) {
    return (
      <div className="bg-white rounded-lg shadow-lg p-6 max-w-md">
        <h2 className="text-xl font-bold mb-4 text-gray-800">Trip Summary</h2>
        <div className="space-y-2 text-gray-600">
          <div>
            <strong>Origin:</strong> {origin.name}
          </div>
          <div>↓</div>
          <div>
            <strong>Transfer:</strong> {transfer.name}
          </div>
          <div>↓</div>
          <div>
            <strong>Destination:</strong> {destination.name}
          </div>
        </div>
        <p className="mt-4 text-sm text-gray-500">
          Select stations on the map to calculate transfer confidence
        </p>
      </div>
    );
  }

  const arrivalTime = new Date(transferOption.incoming_prediction.arrival_time);
  const departureTime = new Date(transferOption.outgoing_prediction.arrival_time);
  const [timeUntilArrival, setTimeUntilArrival] = useState<number>(0);
  const [timeUntilDeparture, setTimeUntilDeparture] = useState<number>(0);

  useEffect(() => {
    const updateCountdown = () => {
      const now = Date.now();
      const arrivalMs = arrivalTime.getTime();
      const departureMs = departureTime.getTime();
      
      setTimeUntilArrival(Math.max(0, Math.floor((arrivalMs - now) / 1000)));
      setTimeUntilDeparture(Math.max(0, Math.floor((departureMs - now) / 1000)));
    };

    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);

    return () => clearInterval(interval);
  }, [arrivalTime, departureTime]);

  const formatCountdown = (seconds: number): string => {
    if (seconds <= 0) return 'arrived';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6 max-w-md">
      <h2 className="text-xl font-bold mb-4 text-gray-800">Trip Summary</h2>
      
      <div className="space-y-3 mb-4">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">From:</span>
          <span className="font-medium">{origin.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">Transfer at:</span>
          <span className="font-medium">{transfer.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">To:</span>
          <span className="font-medium">{destination.name}</span>
        </div>
      </div>

      <div className="border-t pt-4 space-y-2">
        <div className="text-sm">
          <strong>Arrival at transfer:</strong> {arrivalTime.toLocaleTimeString()}
          {timeUntilArrival > 0 && (
            <span className="text-gray-500 ml-2">(in {formatCountdown(timeUntilArrival)})</span>
          )}
        </div>
        <div className="text-sm">
          <strong>Walk time:</strong> ~{Math.round(transferOption.walk_time_seconds)} seconds
        </div>
        <div className="text-sm">
          <strong>Departure from transfer:</strong> {departureTime.toLocaleTimeString()}
          {timeUntilDeparture > 0 && (
            <span className="text-gray-500 ml-2">(in {formatCountdown(timeUntilDeparture)})</span>
          )}
        </div>
      </div>

      <div className="mt-4">
        <ConfidenceBadge confidence={transferOption.confidence} />
      </div>
    </div>
  );
}
