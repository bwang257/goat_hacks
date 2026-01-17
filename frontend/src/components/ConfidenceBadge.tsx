import type { ConfidenceScore } from '../types';

interface ConfidenceBadgeProps {
  confidence: ConfidenceScore;
  className?: string;
}

export function ConfidenceBadge({ confidence, className = '' }: ConfidenceBadgeProps) {
  const bgColor = {
    green: 'bg-green-500',
    yellow: 'bg-yellow-500',
    red: 'bg-red-500',
  }[confidence.color];

  return (
    <div className={`${className} ${bgColor} text-white px-4 py-2 rounded-lg shadow-md`}>
      <div className="font-bold text-lg">{confidence.score}</div>
      <div className="text-sm opacity-90">{confidence.message}</div>
      {confidence.cushion_seconds > 0 && (
        <div className="text-xs mt-1 opacity-75">
          {Math.abs(confidence.cushion_seconds)}s cushion
        </div>
      )}
    </div>
  );
}
