import type { Insights, Metrics, RequestRecord, RequestSummary } from './types';

const API_BASE = '/api';

export interface PaginatedRequests {
  items: RequestSummary[];
  total: number;
  limit: number;
  offset: number;
}

export async function fetchRequests(limit = 100, offset = 0): Promise<PaginatedRequests> {
  const res = await fetch(`${API_BASE}/requests?limit=${limit}&offset=${offset}`);
  if (!res.ok) throw new Error('Failed to fetch requests');
  return res.json();
}

export async function fetchRequest(id: string): Promise<RequestRecord> {
  const res = await fetch(`${API_BASE}/requests/${id}`);
  if (!res.ok) throw new Error('Failed to fetch request');
  return res.json();
}

export async function fetchMetrics(window = 60): Promise<Metrics> {
  const res = await fetch(`${API_BASE}/metrics?window=${window}`);
  if (!res.ok) throw new Error('Failed to fetch metrics');
  return res.json();
}

export async function fetchInsights(window = 60): Promise<Insights> {
  const res = await fetch(`${API_BASE}/insights?window=${window}`);
  if (!res.ok) throw new Error('Failed to fetch insights');
  return res.json();
}
