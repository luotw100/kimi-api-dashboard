import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchMetrics, fetchRequest, fetchRequests } from './api';
import type { Metrics, RequestRecord, RequestSummary, WSEvent } from './types';

function formatNumber(n: number | null): string {
  if (n === null || n === undefined) return '-';
  return n.toLocaleString();
}

function formatDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return '-';
  return `${ms.toFixed(0)}ms`;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString();
}

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

export default function App() {
  const [requests, setRequests] = useState<RequestSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [currentPage, setCurrentPage] = useState(1);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [selected, setSelected] = useState<RequestRecord | null>(null);
  const [wsConnected, setWsConnected] = useState(false);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const loadData = useCallback(async () => {
    try {
      const offset = (currentPage - 1) * pageSize;
      const [reqs, m] = await Promise.all([fetchRequests(pageSize, offset), fetchMetrics(60)]);
      setRequests(reqs.items);
      setTotal(reqs.total);
      setMetrics(m);
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
            fetchMetrics(60).then(setMetrics).catch(console.error);
          }
        } catch (e) {
          console.error('Failed to parse WS message', e);
        }
      };
    };

    connect();

    const interval = setInterval(() => {
      fetchMetrics(60).then(setMetrics).catch(console.error);
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
    } catch (e) {
      console.error('Failed to load request detail', e);
    }
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
        </div>
      )}

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
                <th>Model</th>
                <th>Path</th>
                <th>Status</th>
                <th>Duration</th>
                <th>TTFB</th>
                <th>Input</th>
                <th>Output</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((req) => (
                <tr key={req.id} onClick={() => handleRowClick(req)}>
                  <td>{formatTime(req.timestamp)}</td>
                  <td>{req.model || '-'}</td>
                  <td>{req.path}</td>
                  <td className={req.status >= 400 ? 'status-error' : 'status-ok'}>
                    {req.status}
                  </td>
                  <td>{formatDuration(req.duration_ms)}</td>
                  <td>{formatDuration(req.ttfb_ms)}</td>
                  <td>{formatNumber(req.input_tokens)}</td>
                  <td>{formatNumber(req.output_tokens)}</td>
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
            <div className="detail-body">
              <div className="detail-section">
                <h3>Request Headers</h3>
                <pre>{JSON.stringify(selected.request.headers, null, 2)}</pre>
              </div>
              <div className="detail-section">
                <h3>Request Body</h3>
                <pre>{JSON.stringify(selected.request.body, null, 2)}</pre>
              </div>
              <div className="detail-section">
                <h3>Response Headers</h3>
                <pre>{JSON.stringify(selected.response.headers, null, 2)}</pre>
              </div>
              <div className="detail-section">
                <h3>Response Body</h3>
                <pre>{selected.response.body}</pre>
              </div>
              <div className="detail-section">
                <h3>Parsed</h3>
                <pre>{JSON.stringify(selected.parsed, null, 2)}</pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
