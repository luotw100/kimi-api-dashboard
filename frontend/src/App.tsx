import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchInsights, fetchMetrics, fetchRequest, fetchRequests } from './api';
import InsightsPanel from './InsightsPanel';
import type { Insights, Metrics, RequestRecord, RequestSummary, SSEEvent, WSEvent } from './types';

function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return '-';
  return n.toLocaleString();
}

function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '-';
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString();
}

function formatCost(cost: number | null | undefined): string {
  if (cost === null || cost === undefined) return '-';
  return `$${cost.toFixed(4)}`;
}

function formatTps(n: number | null | undefined): string {
  if (n === null || n === undefined) return '-';
  return `${n.toLocaleString(undefined, { maximumFractionDigits: 1 })} t/s`;
}

function formatStreaming(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '-';
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];
type DetailTab = 'request' | 'response' | 'usage' | 'events';

export default function App() {
  const [requests, setRequests] = useState<RequestSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [currentPage, setCurrentPage] = useState(1);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [selected, setSelected] = useState<RequestRecord | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>('request');
  const [wsConnected, setWsConnected] = useState(false);
  const [expandedEvents, setExpandedEvents] = useState<Record<number, boolean>>({});

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const loadData = useCallback(async () => {
    try {
      const offset = (currentPage - 1) * pageSize;
      const [reqs, m, i] = await Promise.all([
        fetchRequests(pageSize, offset),
        fetchMetrics(60),
        fetchInsights(60),
      ]);
      setRequests(reqs.items);
      setTotal(reqs.total);
      setMetrics(m);
      setInsights(i);
    } catch (e) {
      console.error('Failed to load data', e);
    }
  }, [currentPage, pageSize]);

  const loadDataRef = useRef(loadData);
  useEffect(() => {
    loadDataRef.current = loadData;
  }, [loadData]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
    let reconnectDelay = 1000;

    const connect = () => {
      ws = new WebSocket(
        `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`,
      );

      ws.onopen = () => {
        setWsConnected(true);
        reconnectDelay = 1000;
      };

      ws.onclose = () => {
        setWsConnected(false);
        ws = null;
        reconnectTimeout = setTimeout(() => {
          connect();
        }, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 30000);
      };

      ws.onerror = () => {
        setWsConnected(false);
      };

      ws.onmessage = (event) => {
        try {
          const msg: WSEvent = JSON.parse(event.data);
          if (msg.type === 'request_finished') {
            loadDataRef.current();
          }
        } catch (e) {
          console.error('Failed to parse WS message', e);
        }
      };
    };

    connect();

    const interval = setInterval(() => {
      loadDataRef.current();
    }, 10000);

    return () => {
      if (ws) ws.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      clearInterval(interval);
    };
  }, []);

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  };

  const handlePrevPage = () => {
    setCurrentPage((p) => Math.max(1, p - 1));
  };

  const handleNextPage = () => {
    setCurrentPage((p) => Math.min(totalPages, p + 1));
  };

  const handleRowClick = async (req: RequestSummary) => {
    try {
      const detail = await fetchRequest(req.id);
      setSelected(detail);
      setDetailTab('request');
      setExpandedEvents({});
    } catch (e) {
      console.error('Failed to load request detail', e);
    }
  };

  const toggleEvent = (idx: number) => {
    setExpandedEvents((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  const renderTimingBar = () => {
    if (!selected || !selected.parsed.duration_ms || !selected.parsed.ttfb_ms) return null;
    const duration = selected.parsed.duration_ms as number;
    const ttfb = selected.parsed.ttfb_ms as number;
    const ttfbPct = Math.min(100, Math.max(0, (ttfb / duration) * 100));
    return (
      <div className="timing-section">
        <div className="timing-header">
          <span>Total: {formatDuration(duration)}</span>
          <span>TTFB: {formatDuration(ttfb)}</span>
          <span>Streaming: {formatDuration(duration - ttfb)}</span>
        </div>
        <div className="timing-bar">
          <div className="timing-ttfb" style={{ width: `${ttfbPct}%` }} title={`TTFB ${formatDuration(ttfb)}`} />
          <div className="timing-stream" style={{ width: `${100 - ttfbPct}%` }} title={`Streaming ${formatDuration(duration - ttfb)}`} />
        </div>
      </div>
    );
  };

  const renderEventSummary = (event: SSEEvent) => {
    const type = event.type || 'unknown';
    const usage = (event.usage as Record<string, number> | undefined) || {};
    const stopReason =
      (event as { stop_reason?: string }).stop_reason ||
      ((event.delta as Record<string, string> | undefined)?.stop_reason);
    const parts: string[] = [type];
    if (usage.input_tokens != null || usage.output_tokens != null) {
      parts.push(`tokens in=${usage.input_tokens ?? '-'} out=${usage.output_tokens ?? '-'}`);
    }
    if (stopReason) parts.push(`stop=${stopReason}`);
    return parts.join(' · ');
  };

  return (
    <div className="app">
      <header>
        <h1>Kimi API Dashboard</h1>
        <div className="ws-status">
          <span className={`ws-dot ${wsConnected ? 'connected' : ''}`}></span>
          <span>{wsConnected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </header>

      {metrics && (
        <div className="metrics">
          <div className="metric-card">
            <h3>Total Requests (1h)</h3>
            <div className="value">{formatNumber(metrics.total_requests)}</div>
          </div>
          <div className="metric-card">
            <h3>Total Tokens (1h)</h3>
            <div className="value">{formatNumber(metrics.total_tokens)}</div>
          </div>
          <div className="metric-card">
            <h3>Avg Duration</h3>
            <div className="value">{formatDuration(metrics.avg_duration_ms)}</div>
          </div>
          <div className="metric-card">
            <h3>Error Rate</h3>
            <div className="value">{(metrics.error_rate * 100).toFixed(1)}%</div>
          </div>
          <div className="metric-card">
            <h3>P99 Duration</h3>
            <div className="value">{formatDuration(metrics.p99_duration_ms)}</div>
          </div>
          <div className="metric-card">
            <h3>P99 TTFB</h3>
            <div className="value">{formatDuration(metrics.p99_ttfb_ms)}</div>
          </div>
          <div className="metric-card">
            <h3>Estimated Cost (1h)</h3>
            <div className="value">{formatCost(insights?.cost_estimate.total_cost)}</div>
          </div>
        </div>
      )}

      <InsightsPanel insights={insights} />

      {requests.length === 0 ? (
        <div className="empty-state">
          No requests yet. Send a request through the proxy to see it here.
        </div>
      ) : (
        <>
          <table className="requests-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Status</th>
                <th>Total</th>
                <th>TTFB</th>
                <th>Streaming</th>
                <th>Input</th>
                <th>Output</th>
                <th>Prefill TPS</th>
                <th>Decode TPS</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((req) => (
                <tr key={req.id} onClick={() => handleRowClick(req)}>
                  <td>{formatTime(req.timestamp)}</td>
                  <td className={req.status >= 400 ? 'status-error' : 'status-ok'}>
                    {req.status}
                  </td>
                  <td>{formatDuration(req.duration_ms)}</td>
                  <td>{formatDuration(req.ttfb_ms)}</td>
                  <td>
                    {formatStreaming(
                      req.duration_ms != null && req.ttfb_ms != null
                        ? req.duration_ms - req.ttfb_ms
                        : null,
                    )}
                  </td>
                  <td>{formatNumber(req.input_tokens)}</td>
                  <td>{formatNumber(req.output_tokens)}</td>
                  <td>{formatTps(req.prefill_tps)}</td>
                  <td>{formatTps(req.decode_tps)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="pagination">
            <div className="page-size">
              <label htmlFor="page-size">每页:</label>
              <select
                id="page-size"
                value={pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
              >
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <option key={size} value={size}>
                    {size} 条
                  </option>
                ))}
              </select>
            </div>

            <div className="page-info">
              第 {currentPage} / {totalPages} 页
            </div>

            <div className="page-actions">
              <button onClick={handlePrevPage} disabled={currentPage === 1}>
                上一页
              </button>
              <button onClick={handleNextPage} disabled={currentPage === totalPages}>
                下一页
              </button>
            </div>
          </div>
        </>
      )}

      {selected && (
        <div className="detail-modal" onClick={() => setSelected(null)}>
          <div className="detail-content" onClick={(e) => e.stopPropagation()}>
            <div className="detail-header">
              <h2>Request Detail: {selected.id}</h2>
              <button onClick={() => setSelected(null)}>Close</button>
            </div>
            <div className="detail-tabs">
              {(['request', 'response', 'usage', 'events'] as DetailTab[]).map((tab) => (
                <button
                  key={tab}
                  className={`detail-tab ${detailTab === tab ? 'active' : ''}`}
                  onClick={() => setDetailTab(tab)}
                >
                  {tab === 'request' && 'Request'}
                  {tab === 'response' && 'Response'}
                  {tab === 'usage' && 'Usage / Timing'}
                  {tab === 'events' && `SSE Events (${selected.events?.length ?? 0})`}
                </button>
              ))}
            </div>
            <div className="detail-body">
              {detailTab === 'request' && (
                <>
                  <div className="detail-section">
                    <h3>Request Headers</h3>
                    <pre>{JSON.stringify(selected.request.headers, null, 2)}</pre>
                  </div>
                  <div className="detail-section">
                    <h3>Request Body</h3>
                    <pre>{JSON.stringify(selected.request.body, null, 2)}</pre>
                  </div>
                </>
              )}
              {detailTab === 'response' && (
                <>
                  <div className="detail-section">
                    <h3>Response Headers</h3>
                    <pre>{JSON.stringify(selected.response.headers, null, 2)}</pre>
                  </div>
                  <div className="detail-section">
                    <h3>Response Body</h3>
                    <pre>{selected.response.body}</pre>
                  </div>
                </>
              )}
              {detailTab === 'usage' && (
                <>
                  <div className="detail-section">
                    <h3>Parsed</h3>
                    <pre>{JSON.stringify(selected.parsed, null, 2)}</pre>
                  </div>
                  <div className="detail-section">{renderTimingBar()}</div>
                </>
              )}
              {detailTab === 'events' && (
                <div className="detail-section">
                  <h3>SSE Events</h3>
                  {selected.events && selected.events.length > 0 ? (
                    <div className="event-list">
                      {selected.events.map((event, idx) => (
                        <div className="event-item" key={idx}>
                          <button className="event-summary" onClick={() => toggleEvent(idx)}>
                            <span className="event-index">#{idx + 1}</span>
                            <span className="event-type">{event.type || 'unknown'}</span>
                            <span className="event-brief">{renderEventSummary(event)}</span>
                            <span className="event-toggle">{expandedEvents[idx] ? '▲' : '▼'}</span>
                          </button>
                          {expandedEvents[idx] && (
                            <pre className="event-raw">{JSON.stringify(event, null, 2)}</pre>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="event-empty">No parsed SSE events available.</p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
