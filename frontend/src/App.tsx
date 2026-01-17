import { useState, useCallback, useEffect } from 'react';
import { Brain } from 'lucide-react';
import { Map } from './components/Map';
import { TransferSummary } from './components/TransferSummary';
import { WalkingSpeedSlider } from './components/WalkingSpeedSlider';
import { TimelineSimulator } from './components/TimelineSimulator';
import { GeminiInsights } from './components/GeminiInsights';
import { calculateTransfer, getEnhancedConfidence } from './lib/api';
import type { Station, TransferOption, WalkingSpeed, GeminiInsight } from './types';
import { WALKING_SPEEDS } from './types';

function App() {
  const [origin, setOrigin] = useState<Station | null>(null);
  const [transfer, setTransfer] = useState<Station | null>(null);
  const [destination, setDestination] = useState<Station | null>(null);
  const [walkingSpeed, setWalkingSpeed] = useState<WalkingSpeed>('normal');
  const [transferOptions, setTransferOptions] = useState<TransferOption[]>([]);
  const [selectedOption, setSelectedOption] = useState<TransferOption | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [geminiInsight, setGeminiInsight] = useState<GeminiInsight | null>(null);
  const [showGemini, setShowGemini] = useState(false);

  const handleSelectionComplete = useCallback(
    async (selectedOrigin: Station, selectedTransfer: Station, selectedDestination: Station) => {
      setOrigin(selectedOrigin);
      setTransfer(selectedTransfer);
      setDestination(selectedDestination);
      setError(null);
      setLoading(true);

      try {
        // Find matching routes (simplified - in real app, let user select routes)
        // For origin → transfer, use first route from transfer station that matches origin
        // For transfer → destination, use first route from destination that matches transfer
        const originRoute = selectedOrigin.routes.find(r => selectedTransfer.routes.includes(r)) || selectedOrigin.routes[0] || 'Red';
        const transferRoute = selectedTransfer.routes.find(r => selectedDestination.routes.includes(r)) || selectedTransfer.routes[0] || 'Green';

        const response = await calculateTransfer({
          origin_stop: selectedOrigin.id,
          origin_route: originRoute,
          transfer_stop: selectedTransfer.id,
          transfer_route: transferRoute,
          destination_stop: selectedDestination.id,
          user_speed_mps: WALKING_SPEEDS[walkingSpeed],
        });

        setTransferOptions(response.options);
        if (response.options.length > 0) {
          setSelectedOption(response.options[0]);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to calculate transfer');
      } finally {
        setLoading(false);
      }
    },
    [walkingSpeed]
  );

  // Recalculate when walking speed changes
  useEffect(() => {
    if (origin && transfer && destination) {
      handleSelectionComplete(origin, transfer, destination);
    }
  }, [walkingSpeed]);

  const handleGeminiAnalysis = async () => {
    if (!selectedOption || !transfer) return;

    try {
      // Try real API first, fallback to mock data
      try {
        const insight = await getEnhancedConfidence({
          station_name: transfer.name,
          math_confidence: selectedOption.confidence.score,
          current_time: new Date().toISOString(),
        });
        setGeminiInsight(insight);
      } catch (err) {
        // Fallback to mock data for demo
        console.log('Using mock Gemini data for demo');
        setGeminiInsight({
          adjusted_confidence: selectedOption.confidence.score as 'LIKELY' | 'RISKY' | 'UNLIKELY',
          reason: `${transfer.name} has short transfer distances and good signage. ${origin?.routes[0] || 'Red'} to ${destination?.routes[0] || 'Orange'} is straightforward.`,
          pro_tip: `Exit at the front of the ${origin?.routes[0] || 'Red'} Line train for fastest transfer to ${destination?.routes[0] || 'Orange'} Line ${destination?.name.includes('North') ? 'northbound' : 'southbound'}.`,
        });
      }
      setShowGemini(true);
    } catch (err) {
      console.error('Failed to get Gemini insight:', err);
    }
  };

  return (
    <div className="h-screen w-screen overflow-hidden relative">
      <Map onSelectionComplete={handleSelectionComplete} />

      {/* Sidebar */}
      <div className="absolute top-4 right-4 bottom-4 w-96 max-h-[calc(100vh-2rem)] overflow-y-auto space-y-4 z-10">
        <div className="bg-white/95 backdrop-blur-sm rounded-lg shadow-xl p-4 space-y-4">
          <h1 className="text-2xl font-bold text-mbta-blue">MBTA Transfer Helper</h1>

          <WalkingSpeedSlider value={walkingSpeed} onChange={setWalkingSpeed} />

          {error && (
            <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
              {error}
            </div>
          )}

          {loading && (
            <div className="text-center py-4 text-gray-600">Calculating transfer...</div>
          )}

          {origin && transfer && destination && (
            <>
              <TransferSummary
                origin={origin}
                transfer={transfer}
                destination={destination}
                transferOption={selectedOption || undefined}
                walkingSpeed={WALKING_SPEEDS[walkingSpeed]}
              />

              {selectedOption && (
                <button
                  onClick={handleGeminiAnalysis}
                  className="mt-2 w-full py-2 px-4 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors flex items-center justify-center gap-2 text-sm font-semibold"
                >
                  <Brain className="w-4 h-4" />
                  Why this score?
                </button>
              )}

              {selectedOption && (
                <TimelineSimulator transferOption={selectedOption} />
              )}
            </>
          )}
        </div>
      </div>

      {showGemini && geminiInsight && (
        <GeminiInsights
          insight={geminiInsight}
          onClose={() => setShowGemini(false)}
        />
      )}
    </div>
  );
}

export default App;
