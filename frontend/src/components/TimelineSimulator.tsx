import { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import type { TransferOption } from '../types';

interface TimelineSimulatorProps {
  transferOption?: TransferOption;
}

export function TimelineSimulator({ transferOption }: TimelineSimulatorProps) {
  const [delayMinutes, setDelayMinutes] = useState(0);

  if (!transferOption) {
    return (
      <div className="bg-white rounded-lg shadow-lg p-6">
        <h3 className="text-lg font-bold mb-4">What-If Simulator</h3>
        <p className="text-sm text-gray-500">Select a transfer option to see timeline</p>
      </div>
    );
  }

  const arrivalTime = new Date(transferOption.incoming_prediction.arrival_time);
  const departureTime = new Date(transferOption.outgoing_prediction.arrival_time);
  
  // Apply delay
  const delayedArrival = new Date(arrivalTime);
  delayedArrival.setMinutes(delayedArrival.getMinutes() + delayMinutes);
  
  const walkTimeSeconds = transferOption.walk_time_seconds;
  const bufferTime = 65; // Total buffers
  
  const arrivalAtTransfer = new Date(delayedArrival);
  arrivalAtTransfer.setSeconds(arrivalAtTransfer.getSeconds() + walkTimeSeconds + 35);
  
  const missed = arrivalAtTransfer > departureTime;
  const timeUntilDeparture = (departureTime.getTime() - arrivalAtTransfer.getTime()) / 1000;

  const data = [
    {
      name: 'Base Scenario',
      arrival: arrivalTime.getTime(),
      walk: walkTimeSeconds * 1000,
      departure: departureTime.getTime(),
    },
    {
      name: 'Delayed Scenario',
      arrival: delayedArrival.getTime(),
      walk: walkTimeSeconds * 1000,
      departure: departureTime.getTime(),
      missed,
    },
  ];

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <h3 className="text-lg font-bold mb-4">What-If Simulator</h3>
      
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Delay: {delayMinutes > 0 ? '+' : ''}{delayMinutes} minutes
        </label>
        <input
          type="range"
          min="-10"
          max="30"
          value={delayMinutes}
          onChange={(e) => setDelayMinutes(parseInt(e.target.value))}
          className="w-full"
        />
      </div>

      <div className="mt-4">
        {missed && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
            <strong>Connection Missed!</strong>
            <p className="text-sm mt-1">
              You'll arrive {Math.abs(Math.round(timeUntilDeparture))}s after the train departs.
            </p>
          </div>
        )}
        
        <div className="text-sm text-gray-600 space-y-1">
          <div>
            <strong>Original arrival:</strong> {arrivalTime.toLocaleTimeString()}
          </div>
          {delayMinutes !== 0 && (
            <div>
              <strong>Delayed arrival:</strong> {delayedArrival.toLocaleTimeString()}
            </div>
          )}
          <div>
            <strong>Walk time:</strong> {Math.round(walkTimeSeconds)}s
          </div>
          <div>
            <strong>Departure:</strong> {departureTime.toLocaleTimeString()}
          </div>
        </div>
      </div>
    </div>
  );
}
