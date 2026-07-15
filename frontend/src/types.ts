export interface RequestSummary {
  id: string;
  timestamp: string;
  model: string | null;
  path: string;
  method: string;
  status: number;
  duration_ms: number | null;
  ttfb_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  error: string | null;
}

export interface RequestRecord extends RequestSummary {
  request: {
    headers: Record<string, string>;
    body: unknown;
  };
  response: {
    status: number;
    headers: Record<string, string>;
    body: string;
  };
  parsed: Record<string, unknown>;
}

export interface Metrics {
  window_minutes: number;
  total_requests: number;
  error_count: number;
  error_rate: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  avg_duration_ms: number | null;
  p50_duration_ms: number | null;
  p95_duration_ms: number | null;
  model_distribution: Record<string, number>;
  path_distribution: Record<string, number>;
}

export interface WSEvent {
  type: string;
  payload: RequestSummary;
}
