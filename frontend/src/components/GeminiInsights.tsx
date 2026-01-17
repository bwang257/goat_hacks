import { X } from 'lucide-react';
import type { GeminiInsight } from '../types';

interface GeminiInsightsProps {
  insight?: GeminiInsight;
  onClose: () => void;
}

export function GeminiInsights({ insight, onClose }: GeminiInsightsProps) {
  if (!insight) return null;

  const bgColor = {
    LIKELY: 'bg-green-500',
    RISKY: 'bg-yellow-500',
    UNLIKELY: 'bg-red-500',
  }[insight.adjusted_confidence];

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl p-6 max-w-md w-full mx-4 relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600"
        >
          <X size={20} />
        </button>

        <div className="mb-4">
          <div className={`${bgColor} text-white px-3 py-2 rounded-lg inline-block mb-2`}>
            <span className="font-bold">{insight.adjusted_confidence}</span>
          </div>
          <div className="text-xs text-gray-500 mt-1">Powered by Gemini</div>
        </div>

        <div className="space-y-3">
          <div>
            <h3 className="font-semibold text-gray-800 mb-1">Analysis</h3>
            <p className="text-sm text-gray-600">{insight.reason}</p>
          </div>
          <div>
            <h3 className="font-semibold text-gray-800 mb-1">Pro Tip</h3>
            <p className="text-sm text-mbta-blue">{insight.pro_tip}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
