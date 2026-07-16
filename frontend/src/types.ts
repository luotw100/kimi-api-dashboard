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
  prefill_tps: number | null;
  decode_tps: number | null;
}

export interface SSEEvent {
  type?: string;
  [key: string]: unknown;
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
  events?: SSEEvent[];
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
  p99_duration_ms: number | null;
  p50_ttfb_ms: number | null;
  p95_ttfb_ms: number | null;
  p99_ttfb_ms: number | null;
  model_distribution: Record<string, number>;
  path_distribution: Record<string, number>;
}

export interface TimeSeriesPoint {
  minute: string;
  total_requests: number;
  error_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  avg_duration_ms: number | null;
  avg_ttfb_ms: number | null;
}

export interface LatencyStats {
  p50_duration_ms: number | null;
  p95_duration_ms: number | null;
  p99_duration_ms: number | null;
  p50_ttfb_ms: number | null;
  p95_ttfb_ms: number | null;
  p99_ttfb_ms: number | null;
  histogram: { bucket: string; count: number }[];
  top_slow: RequestSummary[];
}

export interface ModelBreakdown {
  model: string;
  count: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  avg_duration_ms: number | null;
  avg_ttfb_ms: number | null;
  error_count: number;
}

export interface PathBreakdown {
  path: string;
  count: number;
  error_count: number;
  error_rate: number;
}

export interface TokenEfficiency {
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  output_input_ratio: number | null;
  tokens_per_second: number | null;
  cache_creation_input_tokens: number;
  cache_read_input_tokens: number;
  cache_hit_rate: number;
}

export interface RequestBodyStats {
  total_messages_records: number;
  avg_messages_count: number;
  max_messages_count: number;
  avg_system_length: number;
  max_system_length: number;
  avg_user_content_length: number;
  max_user_content_length: number;
  tool_count_distribution: Record<string, number>;
  max_tokens_distribution: Record<string, number>;
  streaming_ratio: { streaming: number; non_streaming: number };
  thinking_ratio: { thinking: number; non_thinking: number };
}

export interface CostEstimate {
  total_input_cost: number;
  total_output_cost: number;
  total_cost: number;
  by_model: Record<string, { input_cost: number; output_cost: number; total_cost: number }>;
}

export interface Insights {
  window_minutes: number;
  total_requests: number;
  time_series: TimeSeriesPoint[];
  latency: LatencyStats;
  model_breakdown: ModelBreakdown[];
  path_breakdown: PathBreakdown[];
  stop_reason_distribution: Record<string, number>;
  streaming_ratio: Record<string, number>;
  token_efficiency: TokenEfficiency;
  request_body_stats: RequestBodyStats;
  cost_estimate: CostEstimate;
}

export interface WSEvent {
  type: string;
  payload: RequestSummary;
}
