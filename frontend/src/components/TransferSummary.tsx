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
  const walkDistance = transferOption.walk_time_seconds * walkingSpeed;

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
          <strong>Arrival at transfer:</strong>{' '}
          {arrivalTime.toLocaleTimeString()}
        </div>
        <div className="text-sm">
          <strong>Walk time:</strong> {Math.round(transferOption.walk_time_seconds)}s
          ({Math.round(walkDistance)}m @ {walkingSpeed.toFixed(1)} m/s)
        </div>
        <div className="text-sm">
          <strong>Departure from transfer:</strong>{' '}
          {departureTime.toLocaleTimeString()}
        </div>
      </div>

      <div className="mt-4">
        <ConfidenceBadge confidence={transferOption.confidence} />
      </div>
    </div>
  );
}
