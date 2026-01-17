import { WALKING_SPEEDS, type WalkingSpeed } from '../types';

interface WalkingSpeedSliderProps {
  value: WalkingSpeed;
  onChange: (speed: WalkingSpeed) => void;
}

const LABELS: Record<WalkingSpeed, string> = {
  relaxed: 'Relaxed',
  normal: 'Normal',
  brisk: 'Brisk',
  sprint: 'Sprint',
};

export function WalkingSpeedSlider({ value, onChange }: WalkingSpeedSliderProps) {
  const speeds = Object.keys(WALKING_SPEEDS) as WalkingSpeed[];
  const currentIndex = speeds.indexOf(value);

  return (
    <div className="w-full p-4 bg-white rounded-lg shadow-md">
      <label className="block text-sm font-medium text-gray-700 mb-2">
        Walking Speed
      </label>
      <input
        type="range"
        min="0"
        max="3"
        value={currentIndex}
        onChange={(e) => onChange(speeds[parseInt(e.target.value)])}
        className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
      />
      <div className="flex justify-between text-xs text-gray-600 mt-1">
        {speeds.map((speed) => (
          <span key={speed} className={value === speed ? 'font-bold text-mbta-blue' : ''}>
            {LABELS[speed]}
          </span>
        ))}
      </div>
      <div className="text-center text-sm font-semibold text-gray-800 mt-2">
        {WALKING_SPEEDS[value]} m/s
      </div>
    </div>
  );
}
