export const WALKING_SPEEDS = {
  relaxed: 1.2,
  normal: 1.4,
  brisk: 1.6,
  sprint: 2.0,
} as const;

export type WalkingSpeed = keyof typeof WALKING_SPEEDS;

export interface Station {
  id: string;
  name: string;
  lat: number;
  lon: number;
  routes: string[];
}

export interface Prediction {
  route: string;
  direction: string;
  arrival_time: string; // ISO 8601
  vehicle_id?: string;
}

export interface ConfidenceScore {
  score: 'LIKELY' | 'RISKY' | 'UNLIKELY';
  color: 'green' | 'yellow' | 'red';
  cushion_seconds: number;
  message: string;
}

export interface TransferOption {
  incoming_prediction: Prediction;
  outgoing_prediction: Prediction;
  walk_time_seconds: number;
  confidence: ConfidenceScore;
}

export interface GeminiInsight {
  adjusted_confidence: 'LIKELY' | 'RISKY' | 'UNLIKELY';
  reason: string;
  pro_tip: string;
}
