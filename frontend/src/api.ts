import type { Metrics, RequestRecord, RequestSummary } from './types';

const API_BASE = '/api';

export async function fetchRequests(limit = 100): Promise<RequestSummary[]> {
  const res = await fetch(`${API_BASE}/requests?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch requests');
  const data = await res.json();
  return data.items || [];
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
