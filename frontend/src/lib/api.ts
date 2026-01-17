import axios from 'axios';
import type { Station, TransferOption, GeminiInsight } from '../types';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface TransferRequest {
  origin_stop: string;
  origin_route: string;
  transfer_stop: string;
  transfer_route: string;
  destination_stop: string;
  user_speed_mps: number;
}

export interface TransferResponse {
  options: TransferOption[];
}

export interface GeminiRequest {
  station_name: string;
  math_confidence: string;
  current_time: string;
}

export async function calculateTransfer(req: TransferRequest): Promise<TransferResponse> {
  try {
    const response = await api.post<TransferResponse>('/calculate-transfer', req);
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.detail || 'Failed to calculate transfer');
    }
    throw new Error('Unknown error occurred');
  }
}

export async function getEnhancedConfidence(req: GeminiRequest): Promise<GeminiInsight> {
  try {
    const response = await api.post<GeminiInsight>('/enhanced-confidence', req);
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.detail || 'Failed to get enhanced confidence');
    }
    throw new Error('Unknown error occurred');
  }
}
